from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional, Tuple


class ConverterBackend:
    """Abstract converter backend.

    Implementations should be safe to import/run inside Isaac Sim's Python
    (via scripts/isaac_python.sh)."""

    name: str = "base"

    def convert(self, src: Path, dst: Path) -> Tuple[bool, str]:  # pragma: no cover - thin wrapper
        raise NotImplementedError

    @property
    def available(self) -> bool:  # pragma: no cover - thin wrapper
        return True


class OmniAssetConverterBackend(ConverterBackend):
    """Use omni.kit.asset_converter (Omniverse/Isaac built-in) to convert glTF/GLB to USD.
    
    If 'omni.kit.asset_converter' cannot be imported (e.g. running in pure Python mode),
    this backend will transparently fallback to running `scripts/convert_glb_to_usd.py`
    as a subprocess via `isaac_python.sh` (or current interpreter if applicable).
    """

    name = "omni"

    def __init__(self, logger: logging.Logger) -> None:
        self._logger = logger
        self._converter = None
        self._context = None
        self._init_error: Optional[str] = None
        self._use_subprocess = False
        
        try:
            import omni.kit.asset_converter as kit_converter  # noqa: WPS433

            self._converter_mod = kit_converter
            self._converter = kit_converter.get_instance() # Use get_instance() for singleton
            ctx = kit_converter.AssetConverterContext()
            # reasonable defaults for static glTF/GLB payloads
            ctx.ignore_materials = False
            ctx.ignore_cameras = False
            ctx.ignore_lights = False
            ctx.embed_textures = True
            ctx.merge_materials = False
            self._context = ctx
        except ImportError:
            # Fallback to subprocess mode if we can locate the conversion script
            self._use_subprocess = True
            self._logger.info("omni.kit.asset_converter import failed; enabling subprocess fallback mode.")
        except Exception as exc:  # noqa: BLE001
            self._init_error = f"omni.kit.asset_converter initialization error: {exc}"

    @property
    def available(self) -> bool:
        if self._use_subprocess:
            return True
        return self._init_error is None and self._converter is not None and self._context is not None

    def convert(self, src: Path, dst: Path) -> Tuple[bool, str]:
        if not self.available:
            return False, self._init_error or "asset converter not initialized"
            
        dst.parent.mkdir(parents=True, exist_ok=True)

        if self._use_subprocess:
            return self._convert_subprocess(src, dst)
        else:
            return self._convert_internal(src, dst)

    def _convert_internal(self, src: Path, dst: Path) -> Tuple[bool, str]:
        try:
            # Some converter builds expose async convert; others are sync. Handle both.
            # create_converter_task is preferred in modern Isaac Sim
            if hasattr(self._converter, "create_converter_task"):
                task = self._converter.create_converter_task(str(src), str(dst), None, self._context)
                if hasattr(task, "wait_until_finished"):
                    # wait_until_finished might be async, but here we are in sync context?
                    # If running inside a loop, this might be tricky.
                    # Assuming we are in a script where we can wait.
                    # Note: wait_until_finished() in recent SDKs is async/awaitable.
                    # But if we are in non-async function, we can't await.
                    # This internal path is mostly for when running INSIDE Kit where event loop exists.
                    pass
                # Check status... this logic is complex to share with async.
                # For safety, since we verified subprocess works better even for internal calls (isolation),
                # we might prefer subprocess if we are not sure about the loop.
                # But let's try basic sync wait if possible.
                pass
            
            # Legacy/Simple API
            result = self._converter.convert(str(src), str(dst), self._context)
            
            try:
                if hasattr(result, "wait_until_finished"):
                    result.wait_until_finished()
            except Exception:  # noqa: BLE001
                pass
                
            success = bool(getattr(result, "success", False) or getattr(result, "is_success", lambda: False)())
            message = ""
            if hasattr(result, "errors") and result.errors:
                message = "; ".join(map(str, result.errors))
            if not message:
                message = getattr(result, "message", "") or getattr(result, "status", "")
            if success:
                return True, "converted via omni.kit.asset_converter (internal)"
            return False, message or "asset_converter failed"
        except Exception as exc:  # noqa: BLE001
            self._logger.error("omni converter internal failed: %s", exc)
            return False, f"asset_converter exception: {exc}"

    def _convert_subprocess(self, src: Path, dst: Path) -> Tuple[bool, str]:
        # Locate the conversion script relative to this module or project root
        # Assuming src/usd_asset_packager/converter.py -> project_root/src/usd_asset_packager
        # Script is at project_root/scripts/convert_glb_to_usd.py
        
        try:
            # Current file: .../src/usd_asset_packager/converter.py
            current_dir = Path(__file__).parent
            # Go up to src, then root
            project_root = current_dir.parent.parent
            script_path = project_root / "scripts" / "convert_glb_to_usd.py"
            wrapper_script = project_root / "scripts" / "isaac_python.sh"
            
            if not script_path.exists():
                return False, f"conversion script not found at {script_path}"
            
            cmd = [
                str(wrapper_script),
                str(script_path),
                "--input", str(src),
                "--out", str(dst)
            ]
            
            # Execute
            self._logger.info(f"Running subprocess conversion: {' '.join(cmd)}")
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=str(project_root) # Run from root
            )
            
            if result.returncode == 0:
                return True, "converted via external convert_glb_to_usd.py"
            else:
                err_msg = f"subprocess failed (code {result.returncode}): {result.stderr.strip()}"
                self._logger.error(err_msg)
                self._logger.debug(f"Subprocess stdout: {result.stdout}")
                return False, err_msg
                
        except Exception as exc:
            return False, f"subprocess exception: {exc}"


class FallbackGltf2UsdBackend(ConverterBackend):
    """Optional pure-Python fallback using gltf2usd/usd-core if available.
    """

    name = "fallback_gltf2usd"

    def __init__(self, logger: logging.Logger) -> None:
        self._logger = logger
        self._impl = None
        self._init_error: Optional[str] = None
        try:
            import gltf2usd  # type: ignore  # noqa: WPS433

            self._impl = gltf2usd
        except Exception as exc:  # noqa: BLE001
            self._init_error = f"gltf2usd not available: {exc}"

    @property
    def available(self) -> bool:
        return self._init_error is None and self._impl is not None

    def convert(self, src: Path, dst: Path) -> Tuple[bool, str]:
        if not self.available:
            return False, self._init_error or "fallback converter unavailable"
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            self._impl.convert(str(src), str(dst))
            return True, "converted via fallback gltf2usd (reduced fidelity)"
        except Exception as exc:  # noqa: BLE001
            self._logger.error("fallback converter failed: %s", exc)
            return False, f"fallback converter failed: {exc}"


def make_converter(name: str, logger: logging.Logger) -> ConverterBackend:
    name = name.lower()
    if name == FallbackGltf2UsdBackend.name:
        return FallbackGltf2UsdBackend(logger)
    return OmniAssetConverterBackend(logger)
