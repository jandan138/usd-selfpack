from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

# Use isaacsim.SimulationApp if available (newer SDKs), else fallback to omni.isaac.kit
try:
    from isaacsim import SimulationApp
except ImportError:
    from omni.isaac.kit import SimulationApp

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

async def convert_async(in_file: str, out_file: str, load_materials: bool = True):
    import omni.kit.asset_converter

    def progress_callback(progress, total_steps):
        pass

    converter_context = omni.kit.asset_converter.AssetConverterContext()
    converter_context.ignore_materials = not load_materials
    # Usually we want world unit in meters for Isaac Sim, but default might be cm.
    # mesh2usd.py sets this to True.
    converter_context.use_meter_as_world_unit = True
    
    instance = omni.kit.asset_converter.get_instance()
    task = instance.create_converter_task(
        in_file, out_file, progress_callback, converter_context
    )
    
    success = True
    while True:
        # wait_until_finished() is an async method in newer Kit versions
        success = await task.wait_until_finished()
        if not success:
            await asyncio.sleep(0.1)
        else:
            break
    return success

def main() -> int:
    ap = argparse.ArgumentParser(description="Convert GLB/GLTF to USD using Isaac Sim's Asset Converter (Async/Task-based).")
    ap.add_argument("--input", required=True, help="Path to input GLB/GLTF file")
    ap.add_argument("--out", required=True, help="Path to output USD file")
    ap.add_argument(
        "--env",
        default=None,
        help="Optional env file to source. Loaded before Kit starts.",
    )
    ap.add_argument(
        "--merge-materials",
        action="store_true",
        help="If set, enables material merging in the converter context."
    )
    args = ap.parse_args()

    input_path = Path(args.input).resolve()
    if not input_path.is_file():
        raise SystemExit(f"Input file not found: {input_path}")

    output_path = Path(args.out).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if args.env:
        _load_env_file(args.env)

    print(f"[INFO] Initializing Isaac Sim (Headless)...")
    
    # 1. Start SimulationApp
    kit = SimulationApp({"headless": True})
    
    try:
        import omni
        # Newer Isaac Sim uses isaacsim.core.utils.extensions, older uses omni.isaac.core.utils.extensions
        try:
            from isaacsim.core.utils.extensions import enable_extension
        except ImportError:
            from omni.isaac.core.utils.extensions import enable_extension

        # 2. Enable converter extension
        enable_extension("omni.kit.asset_converter")
        
        print(f"[INFO] Starting conversion: {input_path} -> {output_path}")
        
        # 3. Run async conversion loop
        loop = asyncio.get_event_loop()
        status = loop.run_until_complete(
            convert_async(str(input_path), str(output_path), load_materials=True)
        )
        
        if status:
            print(f"[SUCCESS] Conversion finished: {output_path}")
            return 0
        else:
            print(f"[ERROR] Conversion returned status: {status}", file=sys.stderr)
            return 1

    except Exception as e:
        print(f"[ERROR] Exception during conversion: {e}", file=sys.stderr)
        return 1
    finally:
        print("[INFO] Closing Isaac Sim...")
        kit.close()

if __name__ == "__main__":
    sys.exit(main())
