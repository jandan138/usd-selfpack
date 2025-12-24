from __future__ import annotations

import logging
from typing import List

from pxr import Sdf, Usd, UsdShade

from .resolver import is_remote, is_udim_path, resolve_with_layer
from .types import AssetRef


def _gather_refs_from_listop(listop: Sdf.ListOp) -> List[Sdf.Reference]:
    items: List[Sdf.Reference] = []
    if not listop:
        return items
    getters = [
        getattr(listop, "GetExplicitItems", None),
        getattr(listop, "GetPrependedItems", None),
        getattr(listop, "GetAppendedItems", None),
        getattr(listop, "GetAddedItems", None),
    ]
    for getter in getters:
        if getter is None:
            continue
        try:
            items.extend(getter())
        except Exception:
            continue
    # 兼容旧 API 的属性访问
    for attr_name in ("explicitItems", "prependedItems", "appendedItems", "addedItems"):
        try:
            val = getattr(listop, attr_name, None)
            if val:
                items.extend(list(val))
        except Exception:
            continue
    return items


def _record_asset(asset_refs: List[AssetRef], asset_type: str, asset_path: str, resolved: str | None,
                  layer_id: str, prim_path: str, attr_name: str) -> None:
    asset_refs.append(
        AssetRef(
            asset_type=asset_type,
            original_path=asset_path,
            resolved_path=resolved,
            layer_identifier=layer_id,
            prim_path=prim_path,
            attr_name=attr_name,
            is_remote=is_remote(asset_path),
            is_udim=is_udim_path(asset_path),
        )
    )


def scan_stage(stage: Usd.Stage, logger: logging.Logger) -> List[AssetRef]:
    """扫描整个 Stage 的依赖与材质。

    - 使用 Usd.Stage.Open / Traverse 来遍历 prim。
    - 通过 Sdf.Layer.subLayerPaths 捕获层依赖。
    - 通过属性值中出现的 Sdf.AssetPath / 字符串捕获贴图、MDL、USD 引用。
    """

    asset_refs: List[AssetRef] = []

    # 1) layer subLayers
    for layer in stage.GetLayerStack():
        for sub in layer.subLayerPaths:
            resolved = resolve_with_layer(layer.realPath, sub) if layer.realPath else None
            _record_asset(asset_refs, "usd", sub, resolved, layer.identifier, "(subLayer)", "subLayerPaths")

    # 2) prim references / payloads
    for prim in stage.TraverseAll():
        ref_listop = prim.GetMetadata("references")
        for ref in _gather_refs_from_listop(ref_listop):
            asset_path = ref.assetPath
            resolved = resolve_with_layer(prim.GetStage().GetRootLayer().realPath, asset_path) if asset_path else None
            asset_type = _guess_asset_type(prim, None, asset_path or "")
            _record_asset(asset_refs, asset_type, asset_path or "", resolved,
                          prim.GetStage().GetEditTarget().GetLayer().identifier,
                          prim.GetPath().pathString, "references")

        payload_listop = prim.GetMetadata("payloads")
        for payload in _gather_refs_from_listop(payload_listop):
            asset_path = payload.assetPath
            resolved = resolve_with_layer(prim.GetStage().GetRootLayer().realPath, asset_path) if asset_path else None
            asset_type = _guess_asset_type(prim, None, asset_path or "")
            _record_asset(asset_refs, asset_type, asset_path or "", resolved,
                          prim.GetStage().GetEditTarget().GetLayer().identifier,
                          prim.GetPath().pathString, "payloads")

        # 3) 材质网络与通用 asset 属性
        for attr in prim.GetAttributes():
            val = attr.Get()
            if val is None:
                continue
            layer_id = "" if not attr.GetPropertyStack() else attr.GetPropertyStack()[0].layer.identifier
            # asset or asset[]
            if isinstance(val, Sdf.AssetPath):
                asset_path = val.path
                asset_type = _guess_asset_type(prim, attr, asset_path)
                resolved = resolve_with_layer(layer_id or prim.GetStage().GetRootLayer().realPath, asset_path)
                _record_asset(asset_refs, asset_type, asset_path, resolved, layer_id or prim.GetStage().GetRootLayer().identifier,
                              prim.GetPath().pathString, attr.GetName())
            elif isinstance(val, list) and val and isinstance(val[0], Sdf.AssetPath):
                for idx, ap in enumerate(val):
                    asset_type = _guess_asset_type(prim, attr, ap.path)
                    resolved = resolve_with_layer(layer_id or prim.GetStage().GetRootLayer().realPath, ap.path)
                    _record_asset(asset_refs, asset_type, ap.path, resolved, layer_id or prim.GetStage().GetRootLayer().identifier,
                                  prim.GetPath().pathString, f"{attr.GetName()}[{idx}]")

    logger.info("scan completed: %d assets", len(asset_refs))
    return asset_refs


def _guess_asset_type(prim: Usd.Prim, attr: Usd.Attribute | None, asset_path: str) -> str:
    """简单推测资产类型，仅用于报告分类。"""

    lower = asset_path.lower()
    if lower.endswith((".usd", ".usda", ".usdc")):
        return "usd"
    if lower.endswith((".glb", ".gltf")):
        return "glb"
    if lower.endswith(".mdl") or (attr and "mdl" in attr.GetName().lower()):
        return "mdl"
    # Shader 类型辅助判断
    if prim.IsA(UsdShade.Shader):
        shader = UsdShade.Shader(prim)
        shader_id = shader.GetIdAttr().Get()
        if shader_id and "mdl" in shader_id.lower():
            return "mdl"
    # 纹理常见后缀
    if lower.endswith((".png", ".jpg", ".jpeg", ".tga", ".exr", ".hdr", ".ktx2", ".dds")):
        return "texture"
    return "other"
