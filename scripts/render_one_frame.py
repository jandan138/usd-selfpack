from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path


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
        # strip simple quotes
        if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
            value = value[1:-1]
        os.environ[key] = value


def _pick_camera_path(stage) -> str | None:
    # Keep imports local; stage is a pxr.Usd.Stage.
    from pxr import UsdGeom

    for prim in stage.Traverse():
        if prim.IsA(UsdGeom.Camera):
            return str(prim.GetPath())
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="Open a USD in Isaac and render 1 frame (forces MDL compilation).")
    ap.add_argument("--usd", required=True, help="Path to USD file to open")
    ap.add_argument(
        "--env",
        default=None,
        help="Optional env file to source (e.g. <out>/env/mdl_paths.env). Loaded before Kit starts.",
    )
    ap.add_argument(
        "--out-dir",
        default=None,
        help="Where to write rendered outputs (defaults to <usd_dir>/logs/render_one_frame)",
    )
    ap.add_argument("--warmup-frames", type=int, default=60)
    # Accept both forms:
    # - `--resolution 256x256` (legacy)
    # - `--resolution 256 256` (doc-friendly)
    ap.add_argument(
        "--resolution",
        nargs="+",
        default=["256", "256"],
        help="Resolution as 'WxH' (e.g. 256x256) or two ints (e.g. 256 256)",
    )
    args = ap.parse_args()

    usd_path = Path(args.usd)
    if not usd_path.is_file():
        raise SystemExit(f"USD not found: {usd_path}")

    if args.env:
        _load_env_file(args.env)

    out_dir = Path(args.out_dir) if args.out_dir else (usd_path.parent / "logs" / "render_one_frame")
    out_dir = out_dir.expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    width: int
    height: int
    if len(args.resolution) == 1:
        m = re.match(r"^(\d+)x(\d+)$", str(args.resolution[0]))
        if not m:
            raise SystemExit("--resolution must be '256x256' or '256 256'")
        width, height = int(m.group(1)), int(m.group(2))
    elif len(args.resolution) == 2:
        width, height = int(args.resolution[0]), int(args.resolution[1])
    else:
        raise SystemExit("--resolution must be '256x256' or two ints")

    # Launch Kit
    from omni.isaac.kit import SimulationApp

    simulation_app = SimulationApp({"headless": True})

    try:
        import omni.usd
        import carb

        ctx = omni.usd.get_context()
        # Avoid relative-path ambiguities (and layer reload warnings) by opening via an absolute path.
        ctx.open_stage(str(usd_path.resolve()))

        # Let extensions initialize + stage load.
        for _ in range(max(1, args.warmup_frames)):
            simulation_app.update()

        stage = ctx.get_stage()
        if stage is None:
            raise RuntimeError("Stage failed to open (ctx.get_stage() is None)")

        cam_path = _pick_camera_path(stage)

        # Force a render via Replicator (offscreen). This tends to trigger material translation/MDL compilation.
        import omni.replicator.core as rep

        # Ensure Replicator disk backend writes exactly under `out_dir`.
        # Without this, Replicator may write under a default root like /root/omni.replicator_out.
        try:
            carb.settings.get_settings().set("/omni/replicator/backends/disk/root_dir", str(out_dir))
        except Exception:
            pass

        if cam_path is None:
            cam_prim = rep.create.camera(position=(0, 150, 120), look_at=(0, 0, 0))
        else:
            cam_prim = cam_path

        render_product = rep.create.render_product(cam_prim, (width, height))

        writer = rep.WriterRegistry.get("BasicWriter")
        # With root_dir set, output_dir should be relative.
        writer.initialize(output_dir=".", rgb=True)
        writer.attach([render_product])

        # Render a couple frames to be safe.
        for _ in range(3):
            rep.orchestrator.step()
            simulation_app.update()

        print(f"OK: rendered to {out_dir}")
        return 0
    finally:
        simulation_app.close()


if __name__ == "__main__":
    raise SystemExit(main())
