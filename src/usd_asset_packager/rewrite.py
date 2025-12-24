from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Dict, List

from pxr import Sdf, Usd

from .types import AssetRef, RewriteAction


def _layer_by_identifier(stage: Usd.Stage) -> Dict[str, Sdf.Layer]:
    mapping: Dict[str, Sdf.Layer] = {}
    for layer in stage.GetLayerStack():
        mapping[layer.identifier] = layer
    return mapping


def rewrite_layers(stage: Usd.Stage, assets: List[AssetRef], copy_targets: Dict[int, str],
                   layer_new_path: Dict[str, Path], logger: logging.Logger) -> List[RewriteAction]:
    """根据复制结果改写 USD 里的 asset path，并把 layer 导出到新的路径。

    - 仅改写资产所属的 layer，避免覆盖其他层。
    - subLayer / references / payloads 分别处理。
    """

    layer_map = _layer_by_identifier(stage)
    rewrites: List[RewriteAction] = []

    # 先改 subLayerPaths
    for layer_id, layer_obj in layer_map.items():
        new_layer_path = layer_new_path.get(layer_id)
        if not new_layer_path:
            continue
        new_subs = []
        changed = False
        for sub in layer_obj.subLayerPaths:
            sub_layer_new = None
            for old_id, path in layer_new_path.items():
                old_layer = layer_map.get(old_id)
                if old_layer and (old_layer.identifier.endswith(sub) or old_layer.realPath == sub):
                    sub_layer_new = path
                    break
            if sub_layer_new:
                rel = os.path.relpath(sub_layer_new, start=new_layer_path.parent)
                new_subs.append(rel)
                changed = True
                rewrites.append(
                    RewriteAction(
                        layer_identifier=layer_id,
                        prim_path="(layer)",
                        attr_name="subLayerPaths",
                        before=sub,
                        after=rel,
                        success=True,
                    )
                )
            else:
                new_subs.append(sub)
        if changed:
            layer_obj.subLayerPaths = new_subs

    # 改写 attributes / references / payloads
    for asset in assets:
        layer_obj = layer_map.get(asset.layer_identifier)
        if not layer_obj:
            continue
        if id(asset) not in copy_targets:
            continue
        target_abs = copy_targets[id(asset)]
        new_layer_path = layer_new_path.get(asset.layer_identifier)
        if not new_layer_path:
            continue
        rel_path = os.path.relpath(target_abs, start=new_layer_path.parent)
        prim = stage.GetPrimAtPath(asset.prim_path)
        if not prim:
            rewrites.append(
                RewriteAction(layer_identifier=asset.layer_identifier, prim_path=asset.prim_path,
                              attr_name=asset.attr_name, before=asset.original_path, after=asset.original_path,
                              success=False, reason="prim missing"),
            )
            continue

        # references / payloads 改写 metadata listOp
        if asset.attr_name in ("references", "payloads"):
            meta_name = asset.attr_name
            list_op = prim.GetMetadata(meta_name)
            if not list_op:
                rewrites.append(
                    RewriteAction(layer_identifier=asset.layer_identifier, prim_path=asset.prim_path,
                                  attr_name=asset.attr_name, before=asset.original_path, after=asset.original_path,
                                  success=False, reason="metadata missing"),
                )
                continue
            updated = False
            def _replace(items):
                nonlocal updated
                new_items = []
                for item in items:
                    if getattr(item, "assetPath", "") == asset.original_path:
                        new_item = type(item)(assetPath=rel_path, primPath=item.primPath,
                                              layerOffset=item.layerOffset, customData=item.customData)
                        new_items.append(new_item)
                        updated = True
                    else:
                        new_items.append(item)
                return new_items

            try:
                list_op.SetExplicitItems(_replace(list_op.GetExplicitItems()))
                list_op.SetAddedItems(_replace(list_op.GetAddedItems()))
                list_op.SetPrependedItems(_replace(list_op.GetPrependedItems()))
                list_op.SetAppendedItems(_replace(list_op.GetAppendedItems()))
                prim.SetMetadata(meta_name, list_op)
                rewrites.append(
                    RewriteAction(layer_identifier=asset.layer_identifier, prim_path=asset.prim_path,
                                  attr_name=asset.attr_name, before=asset.original_path, after=rel_path,
                                  success=updated, reason="" if updated else "not found in list"),
                )
            except Exception as exc:  # noqa: BLE001
                rewrites.append(
                    RewriteAction(layer_identifier=asset.layer_identifier, prim_path=asset.prim_path,
                                  attr_name=asset.attr_name, before=asset.original_path, after=asset.original_path,
                                  success=False, reason=str(exc)),
                )
            continue

        # 普通 attribute
        attr_name = asset.attr_name.split("[")[0]
        attr = prim.GetAttribute(attr_name)
        if not attr:
            rewrites.append(
                RewriteAction(layer_identifier=asset.layer_identifier, prim_path=asset.prim_path,
                              attr_name=asset.attr_name, before=asset.original_path, after=asset.original_path,
                              success=False, reason="attr missing"),
            )
            continue
        try:
            with Usd.EditContext(stage, layer_obj):
                val = attr.Get()
                success = False
                if isinstance(val, Sdf.AssetPath):
                    attr.Set(Sdf.AssetPath(rel_path))
                    success = True
                elif isinstance(val, list) and val and isinstance(val[0], Sdf.AssetPath):
                    new_list = []
                    for item in val:
                        if item.path == asset.original_path:
                            new_list.append(Sdf.AssetPath(rel_path))
                            success = True
                        else:
                            new_list.append(item)
                    attr.Set(new_list)
                else:
                    attr.Set(Sdf.AssetPath(rel_path))
                    success = True
            rewrites.append(
                RewriteAction(layer_identifier=asset.layer_identifier, prim_path=asset.prim_path,
                              attr_name=asset.attr_name, before=asset.original_path, after=rel_path,
                              success=success, reason="" if success else "value not asset"),
            )
        except Exception as exc:  # noqa: BLE001
            rewrites.append(
                RewriteAction(layer_identifier=asset.layer_identifier, prim_path=asset.prim_path,
                              attr_name=asset.attr_name, before=asset.original_path, after=asset.original_path,
                              success=False, reason=str(exc)),
            )

    # 导出各 layer 到新路径
    for layer_id, new_path in layer_new_path.items():
        layer_obj = layer_map.get(layer_id)
        if not layer_obj:
            continue
        new_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            layer_obj.Export(str(new_path))
            logger.info("exported layer %s -> %s", layer_id, new_path)
        except Exception as exc:  # noqa: BLE001
            rewrites.append(
                RewriteAction(layer_identifier=layer_id, prim_path="(layer)", attr_name="export",
                              before=layer_obj.identifier, after=str(new_path), success=False, reason=str(exc)),
            )

    return rewrites
