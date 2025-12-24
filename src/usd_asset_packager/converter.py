from __future__ import annotations

import logging
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
    """Use omni.kit.asset_converter (Omniverse/Isaac built-in) to convert glTF/GLB to USD."""

    name = "omni"

    def __init__(self, logger: logging.Logger) -> None:
        self._logger = logger
        self._converter = None
        self._context = None
        self._init_error: Optional[str] = None
        try:
            import omni.kit.asset_converter as kit_converter  # noqa: WPS433

            self._converter_mod = kit_converter
            self._converter = kit_converter.AssetConverter()
            ctx = kit_converter.AssetConverterContext()
            # reasonable defaults for static glTF/GLB payloads
            ctx.ignore_materials = False
            ctx.ignore_cameras = False
            ctx.ignore_lights = False
            ctx.embed_textures = True
            ctx.merge_materials = False
            self._context = ctx
        except Exception as exc:  # noqa: BLE001
            self._init_error = f"omni.kit.asset_converter unavailable: {exc}"

    @property
    def available(self) -> bool:
        return self._init_error is None and self._converter is not None and self._context is not None

    def convert(self, src: Path, dst: Path) -> Tuple[bool, str]:
        if not self.available:
            return False, self._init_error or "asset converter not initialized"
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            # Some converter builds expose async convert; others are sync. Handle both.
            result = self._converter.convert(str(src), str(dst), self._context)
            # result may have wait_until_finished/is_done/is_success; normalize.
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
                return True, "converted via omni.kit.asset_converter"
            return False, message or "asset_converter failed"
        except Exception as exc:  # noqa: BLE001
            self._logger.error("omni converter failed: %s", exc)
            return False, f"asset_converter exception: {exc}"


class FallbackGltf2UsdBackend(ConverterBackend):
    """Optional pure-Python fallback using gltf2usd/usd-core if available.

    This is best-effort and may lose materials; not enabled unless requested.
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
