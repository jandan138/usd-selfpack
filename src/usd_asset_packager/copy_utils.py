from __future__ import annotations

import hashlib
import logging
import shutil
from pathlib import Path
from typing import Optional

from .converter import ConverterBackend
from .resolver import resolve_with_layer, udim_tiles
from .types import AssetRef, CopyAction


def _hash_prefix(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]


def _target_base(asset_type: str, out_dir: Path) -> Path:
    if asset_type == "texture":
        return out_dir / "textures"
    if asset_type == "mdl":
        return out_dir / "materials"
    if asset_type == "usd":
        return out_dir / "assets"
    if asset_type == "glb":
        return out_dir / "assets_converted_gltf"
    return out_dir / "assets" / "misc"


def plan_target_path(asset: AssetRef, out_dir: Path, collision_strategy: str, base_root: Path) -> Path:
    src = asset.resolved_path or asset.original_path
    base = _target_base(asset.asset_type, out_dir)
    # glb/gltf 目标改为 .usd
    name = Path(src).name
    if asset.asset_type == "glb":
        name = Path(name).with_suffix(".usd").name
    if collision_strategy == "hash_prefix":
        prefix = _hash_prefix(src)
        return base / f"{prefix}_{name}"
    # keep_tree
    try:
        rel = Path(src).resolve().relative_to(base_root.resolve())
    except Exception:
        rel = name
    if asset.asset_type == "glb":
        rel = Path(rel).with_suffix(".usd")
    return base / rel


def copy_asset(asset: AssetRef, out_dir: Path, collision_strategy: str, base_root: Path,
               layer_real_map: dict[str, str], logger: logging.Logger,
               converter_backend: Optional[ConverterBackend] = None,
               convert_gltf: bool = True) -> CopyAction:
    if asset.is_remote:
        return CopyAction(asset=asset, target_path=None, success=False, reason="remote source not copied")

    # 解析绝对路径（优先已有 resolved_path，否则用 layer 再解算）
    src_path: Optional[str] = asset.resolved_path
    if not src_path:
        layer_real = layer_real_map.get(asset.layer_identifier)
        if layer_real:
            src_path = resolve_with_layer(layer_real, asset.original_path)
    if not src_path:
        return CopyAction(asset=asset, target_path=None, success=False, reason="source missing")

    src = Path(src_path)
    target = plan_target_path(asset, out_dir, collision_strategy, base_root)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        if asset.asset_type == "glb":
            if not convert_gltf:
                return CopyAction(asset=asset, target_path=str(target), success=False,
                                  reason="glTF conversion disabled (--no-convert-gltf)")
            if not converter_backend or not converter_backend.available:
                return CopyAction(asset=asset, target_path=str(target), success=False,
                                  reason="glTF converter unavailable; enable omni.kit.asset_converter")
            ok, reason = converter_backend.convert(src, target)
            return CopyAction(asset=asset, target_path=str(target), success=ok, reason=reason)
        if asset.is_udim and "<UDIM>" in asset.original_path:
            pattern_dir, tiles = udim_tiles(str(src))
            if not tiles:
                return CopyAction(asset=asset, target_path=str(target), success=False,
                                  reason=f"UDIM tiles not found under {pattern_dir}")
            for tile in tiles:
                tile_src = Path(tile)
                tile_target = target.parent / tile_src.name
                tile_target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(tile_src, tile_target)
            logger.info("copied UDIM tiles to %s", target.parent)
            return CopyAction(asset=asset, target_path=str(target), success=True, reason="udim copied")
        shutil.copy2(src, target)
        logger.info("copied %s -> %s", src, target)
        return CopyAction(asset=asset, target_path=str(target), success=True)
    except Exception as exc:  # noqa: BLE001
        return CopyAction(asset=asset, target_path=str(target), success=False, reason=str(exc))
