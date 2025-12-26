from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pxr import Gf, Usd, UsdGeom


@dataclass(frozen=True)
class XfDiff:
    prim_path: str
    trans_dist: float
    max_abs_mat_delta: float


def _open_stage(path: str) -> Usd.Stage:
    stage = Usd.Stage.Open(path)
    if not stage:
        raise SystemExit(f"failed to open stage: {path}")
    return stage


def _prim_paths(stage: Usd.Stage) -> set[str]:
    return {str(p.GetPath()) for p in stage.TraverseAll()}


def _world_xf(prim: Usd.Prim, time: Usd.TimeCode) -> Gf.Matrix4d | None:
    if not prim.IsA(UsdGeom.Xformable):
        return None
    # Use XformCache for world transform.
    # NOTE: Avoid calling Xformable.GetLocalTransformation() because its Python
    # return signature varies across USD builds (2-tuple vs 3-tuple).
    cache = UsdGeom.XformCache(time)
    return cache.GetLocalToWorldTransform(prim)


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


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Compare two USD stages: prim presence + world xform diffs (best-effort)."
    )
    ap.add_argument("--usd-a", required=True)
    ap.add_argument("--usd-b", required=True)
    ap.add_argument("--out", default=None, help="Write JSON report to this path")
    ap.add_argument("--max-xf-diffs", type=int, default=200)
    ap.add_argument("--epsilon-trans", type=float, default=1e-4)
    ap.add_argument("--epsilon-mat", type=float, default=1e-6)
    args = ap.parse_args()

    stage_a = _open_stage(args.usd_a)
    stage_b = _open_stage(args.usd_b)

    paths_a = _prim_paths(stage_a)
    paths_b = _prim_paths(stage_b)

    only_in_a = sorted(paths_a - paths_b)
    only_in_b = sorted(paths_b - paths_a)
    common = sorted(paths_a & paths_b)

    time = Usd.TimeCode.Default()

    xf_diffs: list[XfDiff] = []
    for p in common:
        prim_a = stage_a.GetPrimAtPath(p)
        prim_b = stage_b.GetPrimAtPath(p)
        if not prim_a or not prim_b:
            continue
        ma = _world_xf(prim_a, time)
        mb = _world_xf(prim_b, time)
        if ma is None or mb is None:
            continue
        trans_dist = _translation_distance(ma, mb)
        mat_delta = _mat_max_abs_delta(ma, mb)
        if trans_dist > args.epsilon_trans or mat_delta > args.epsilon_mat:
            xf_diffs.append(XfDiff(p, trans_dist, mat_delta))

    xf_diffs.sort(key=lambda d: (d.trans_dist, d.max_abs_mat_delta), reverse=True)
    xf_diffs = xf_diffs[: max(0, args.max_xf_diffs)]

    report: dict[str, Any] = {
        "usd_a": str(Path(args.usd_a)),
        "usd_b": str(Path(args.usd_b)),
        "prim_counts": {"a": len(paths_a), "b": len(paths_b), "common": len(common)},
        "only_in_a": only_in_a,
        "only_in_b": only_in_b,
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
    print("Prim counts:")
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


if __name__ == "__main__":
    raise SystemExit(main())
