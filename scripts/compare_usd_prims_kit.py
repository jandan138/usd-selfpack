from __future__ import annotations

import argparse
import json
import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def _as_posix(p: str) -> str:
    return p.replace("\\", "/")


def _load_env_file(env_path: str) -> None:
    """Load a simple `export KEY=VALUE` env file into os.environ.

    Must be called BEFORE SimulationApp is created.
    """

    path = Path(env_path)
    if not path.is_file():
        raise FileNotFoundError(env_path)

    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
            value = value[1:-1]
        os.environ[key] = value


@dataclass(frozen=True)
class XfDiff:
    prim_path: str
    trans_dist: float
    max_abs_mat_delta: float


def main() -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Compare two USD stages as opened by Isaac/Kit (SimulationApp + omni.usd open_stage): "
            "prim presence + world xform diffs. This tends to match what you see in the app UI more closely."
        )
    )
    ap.add_argument("--usd-a", required=True)
    ap.add_argument("--usd-b", required=True)
    ap.add_argument(
        "--env",
        default=None,
        help="Optional env file to source before Kit starts (e.g. <pack_out>/env/mdl_paths.env).",
    )
    ap.add_argument("--out", default=None, help="Write JSON report to this path")
    ap.add_argument("--warmup-frames", type=int, default=120)
    ap.add_argument("--max-xf-diffs", type=int, default=200)
    ap.add_argument("--epsilon-trans", type=float, default=1e-4)
    ap.add_argument("--epsilon-mat", type=float, default=1e-6)
    args = ap.parse_args()

    usd_a = Path(args.usd_a)
    usd_b = Path(args.usd_b)
    if not usd_a.is_file():
        raise SystemExit(f"USD A not found: {usd_a}")
    if not usd_b.is_file():
        raise SystemExit(f"USD B not found: {usd_b}")

    if args.env:
        _load_env_file(args.env)

    # IMPORTANT: Do not import `pxr` before Kit starts.
    # Import + create SimulationApp only after env is loaded.
    from omni.isaac.kit import SimulationApp

    simulation_app = SimulationApp({"headless": True})

    try:
        import omni.usd

        # Now it's safe to import pxr.
        from pxr import Gf, Usd, UsdGeom

        def _mat_max_abs_delta(a: Gf.Matrix4d, b: Gf.Matrix4d) -> float:
            md = 0.0
            for r in range(4):
                for c in range(4):
                    md = max(md, abs(a[r][c] - b[r][c]))
            return md

        def _translation_distance(a: Gf.Matrix4d, b: Gf.Matrix4d) -> float:
            ta = Gf.Vec3d(a.ExtractTranslation())
            tb = Gf.Vec3d(b.ExtractTranslation())
            d = ta - tb
            return float(math.sqrt(d[0] * d[0] + d[1] * d[1] + d[2] * d[2]))

        def _snapshot_stage(stage: Usd.Stage, time: Usd.TimeCode) -> tuple[set[str], dict[str, Gf.Matrix4d]]:
            paths: set[str] = set()
            xforms: dict[str, Gf.Matrix4d] = {}
            cache = UsdGeom.XformCache(time)
            for prim in stage.TraverseAll():
                p = str(prim.GetPath())
                paths.add(p)
                if prim.IsA(UsdGeom.Xformable):
                    try:
                        xforms[p] = cache.GetLocalToWorldTransform(prim)
                    except Exception:
                        pass
            return paths, xforms

        ctx = omni.usd.get_context()

        def _open_and_snapshot(label: str, usd_path: Path) -> tuple[set[str], dict[str, Gf.Matrix4d]]:
            ctx.open_stage(str(usd_path.resolve()))
            for _ in range(max(1, int(args.warmup_frames))):
                simulation_app.update()

            stage = ctx.get_stage()
            if stage is None:
                raise RuntimeError(f"Stage failed to open for {label}: {usd_path}")

            for _ in range(10):
                simulation_app.update()

            return _snapshot_stage(stage, Usd.TimeCode.Default())

        paths_a, xforms_a = _open_and_snapshot("A", usd_a)
        paths_b, xforms_b = _open_and_snapshot("B", usd_b)

        only_in_a = sorted(paths_a - paths_b)
        only_in_b = sorted(paths_b - paths_a)
        common = sorted(paths_a & paths_b)

        xf_diffs: list[XfDiff] = []
        missing_xf_a = 0
        missing_xf_b = 0

        for p in common:
            ma = xforms_a.get(p)
            mb = xforms_b.get(p)
            if ma is None:
                missing_xf_a += 1
                continue
            if mb is None:
                missing_xf_b += 1
                continue
            trans_dist = _translation_distance(ma, mb)
            mat_delta = _mat_max_abs_delta(ma, mb)
            if trans_dist > args.epsilon_trans or mat_delta > args.epsilon_mat:
                xf_diffs.append(XfDiff(p, trans_dist, mat_delta))

        xf_diffs.sort(key=lambda d: (d.trans_dist, d.max_abs_mat_delta), reverse=True)
        xf_diffs = xf_diffs[: max(0, args.max_xf_diffs)]

        report: dict[str, Any] = {
            "mode": "kit",
            "usd_a": _as_posix(str(usd_a.resolve())),
            "usd_b": _as_posix(str(usd_b.resolve())),
            "env": _as_posix(str(Path(args.env).resolve())) if args.env else None,
            "prim_counts": {"a": len(paths_a), "b": len(paths_b), "common": len(common)},
            "only_in_a": only_in_a,
            "only_in_b": only_in_b,
            "xform_stats": {
                "xformable_prims_a": len(xforms_a),
                "xformable_prims_b": len(xforms_b),
                "missing_xform_in_a_for_common": missing_xf_a,
                "missing_xform_in_b_for_common": missing_xf_b,
            },
            "xform_diffs": [
                {
                    "prim_path": d.prim_path,
                    "translation_distance": d.trans_dist,
                    "max_abs_matrix_delta": d.max_abs_mat_delta,
                }
                for d in xf_diffs
            ],
        }

        # Human-friendly summary
        print("Prim counts (Kit-opened):")
        print(f"  A: {len(paths_a)}")
        print(f"  B: {len(paths_b)}")
        print(f"  Common: {len(common)}")
        print(f"Only in A: {len(only_in_a)}")
        print(f"Only in B: {len(only_in_b)}")
        print(f"Xform diffs (reported): {len(xf_diffs)}")

        if only_in_a[:10]:
            print("\nExamples only_in_a:")
            for p in only_in_a[:10]:
                print("  ", p)
        if only_in_b[:10]:
            print("\nExamples only_in_b:")
            for p in only_in_b[:10]:
                print("  ", p)
        if xf_diffs[:10]:
            print("\nTop xform diffs:")
            for d in xf_diffs[:10]:
                print(
                    f"  {d.prim_path}  trans_dist={d.trans_dist:.6g}  max_abs_mat_delta={d.max_abs_mat_delta:.6g}"
                )

        if args.out:
            out_path = Path(args.out)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"\nWrote report: {out_path}")

        return 0

    finally:
        # Close at the very end; closing earlier can prevent Python code from continuing.
        simulation_app.close()


if __name__ == "__main__":
    raise SystemExit(main())
