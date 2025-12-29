from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import List

from pxr import Sdf, Usd, UsdShade

from .resolver import is_remote, is_udim_path, resolve_with_layer
from .types import AssetRef


_MDL_IMPORT_RE = re.compile(r"^\s*import\s+([^;]+);", re.MULTILINE)
_MDL_USING_IMPORT_RE = re.compile(r"^\s*using\s+([^\s;]+)\s+import\b", re.MULTILINE)
_MDL_RESOURCE_STR_RE = re.compile(
    r"(?P<q>['\"])(?P<path>[^'\"\r\n]+\.(?:png|jpg|jpeg|tga|exr|hdr|dds|ktx2))(?P=q)",
    re.IGNORECASE,
)


def _scan_mdl_import_deps(mdl_file: str) -> List[str]:
    """Extract MDL module file dependencies from `import ...;` statements.

    Returns absolute file paths for modules that exist next to `mdl_file`.
    This is intentionally conservative (only same-directory modules) to
    avoid pulling in Isaac/Kit built-ins.
    """

    p = Path(mdl_file)
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return []

    specs: List[str] = []
    for m in _MDL_IMPORT_RE.finditer(text):
        specs.append((m.group(1) or "").strip())
    for m in _MDL_USING_IMPORT_RE.finditer(text):
        specs.append((m.group(1) or "").strip())

    deps: List[str] = []
    for spec in specs:
        if not spec:
            continue
        # Keep only the first token (drop `::*`, `as`, etc)
        token = spec.split()[0]
        # Strip common suffixes/prefixes
        token = token.rstrip(";")
        if token.endswith("::*"):
            token = token[: -len("::*")]
        token = token.lstrip(".")
        token = token.lstrip(":")
        # Module name is the last component after '::'
        name = token.split("::")[-1].strip()
        # Some imports may be quoted (rare) or include invalid chars.
        name = name.strip('"\'')
        if not name:
            continue
        dep_path = p.parent / f"{name}.mdl"
        if dep_path.is_file():
            deps.append(str(dep_path))
    # De-dup while preserving order
    seen = set()
    out: List[str] = []
    for d in deps:
        if d in seen:
            continue
        seen.add(d)
        out.append(d)
    return out


def _scan_mdl_resource_deps(mdl_file: str) -> List[str]:
    """Extract file resource dependencies referenced by an MDL module.

    Currently focuses on texture-like resources (png/jpg/exr/etc) referenced via
    string literals, e.g. texture_2d("./Textures/white.png").

    Returns absolute file paths for resources that exist on disk.
    """

    p = Path(mdl_file)
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return []

    deps: List[str] = []
    for m in _MDL_RESOURCE_STR_RE.finditer(text):
        raw = (m.group("path") or "").strip()
        if not raw:
            continue
        lower = raw.lower()
        # Ignore remote/builtin-like references.
        if lower.startswith(("http://", "https://", "omniverse://", "mdl://")):
            continue
        if "::" in raw and "/" not in raw and "\\" not in raw:
            # Likely a module symbol, not a file path.
            continue

        cand = (p.parent / raw)
        if not cand.is_file():
            # Common upstream issue: MDL uses './Textures' but folder is 'textures' on Linux.
            raw2 = raw.replace("/Textures/", "/textures/").replace("./Textures/", "./textures/")
            cand2 = (p.parent / raw2)
            if cand2.is_file():
                cand = cand2

        if cand.is_file():
            deps.append(str(cand.resolve()))

    # De-dup while preserving order
    seen = set()
    out: List[str] = []
    for d in deps:
        if d in seen:
            continue
        seen.add(d)
        out.append(d)
    return out


def _gather_refs_from_listop(listop) -> List[object]:
    """Best-effort extraction of items from USD list-op objects.

    Works across Sdf.ReferenceListOp / Sdf.PayloadListOp variations across USD builds.
    Returned items are typically Sdf.Reference or Sdf.Payload (both provide .assetPath).
    """

    items: List[object] = []
    if not listop:
        return items
    getter_names = (
        # Common across list op types
        "GetAddedOrExplicitItems",
        "GetExplicitItems",
        "GetPrependedItems",
        "GetAppendedItems",
        "GetAddedItems",
    )
    for name in getter_names:
        getter = getattr(listop, name, None)
        if getter is None:
            continue
        try:
            got = getter()
        except Exception:
            continue
        if got:
            items.extend(list(got))

    # Fallback for older USD Python bindings exposing list fields.
    attr_names = (
        "addedOrExplicitItems",
        "explicitItems",
        "prependedItems",
        "appendedItems",
        "addedItems",
    )
    for attr_name in attr_names:
        try:
            val = getattr(listop, attr_name, None)
        except Exception:
            continue
        if val:
            try:
                items.extend(list(val))
            except Exception:
                pass
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

    # Some scenes rely on resolver search paths, so authored reference strings
    # (e.g. "../../models/.../instance.usd") may not be directly resolvable via
    # simple path joins. However, once the stage opens successfully, USD knows
    # the resolved file-backed layers that are actually used by the composed
    # stage.
    #
    # We record these used file-backed layers as USD dependencies so that
    # `--copy-usd-deps` can produce a self-contained output even when we cannot
    # deterministically resolve the authored reference strings.
    layer_stack_ids = {layer.identifier for layer in stage.GetLayerStack()}

    # 1) layer subLayers
    for layer in stage.GetLayerStack():
        for sub in layer.subLayerPaths:
            resolved = resolve_with_layer(layer.realPath, sub) if layer.realPath else None
            _record_asset(asset_refs, "usd", sub, resolved, layer.identifier, "(subLayer)", "subLayerPaths")

    # 2) prim references / payloads
    # USD metadata keys are 'references' and (critically) 'payload' (singular).
    # Some older code uses 'payloads', so we probe both for robustness.
    for prim in stage.TraverseAll():
        prim_stack = []
        try:
            prim_stack = prim.GetPrimStack()
        except Exception:
            prim_stack = []

        authored_layer = prim_stack[0].layer if prim_stack else None
        authored_layer_id = authored_layer.identifier if authored_layer else prim.GetStage().GetEditTarget().GetLayer().identifier
        authored_layer_real = authored_layer.realPath if authored_layer else prim.GetStage().GetRootLayer().realPath

        ref_listop = prim.GetMetadata("references")
        for ref in _gather_refs_from_listop(ref_listop):
            asset_path = getattr(ref, "assetPath", "")
            resolved = resolve_with_layer(authored_layer_real, asset_path) if asset_path else None
            asset_type = _guess_asset_type(prim, None, asset_path or "")
            _record_asset(
                asset_refs,
                asset_type,
                asset_path or "",
                resolved,
                authored_layer_id,
                prim.GetPath().pathString,
                "references",
            )

        payload_meta_name = "payload" if prim.GetMetadata("payload") else "payloads"
        payload_listop = prim.GetMetadata(payload_meta_name)
        for payload in _gather_refs_from_listop(payload_listop):
            asset_path = getattr(payload, "assetPath", "")
            resolved = resolve_with_layer(authored_layer_real, asset_path) if asset_path else None
            asset_type = _guess_asset_type(prim, None, asset_path or "")
            _record_asset(
                asset_refs,
                asset_type,
                asset_path or "",
                resolved,
                authored_layer_id,
                prim.GetPath().pathString,
                payload_meta_name,
            )

        # 3) 材质网络与通用 asset 属性
        for attr in prim.GetAttributes():
            val = attr.Get()
            if val is None:
                continue
            prop_stack = []
            try:
                prop_stack = attr.GetPropertyStack()
            except Exception:
                prop_stack = []
            prop_layer = prop_stack[0].layer if prop_stack else None
            layer_id = prop_layer.identifier if prop_layer else ""
            layer_real = prop_layer.realPath if prop_layer else ""
            resolve_base = layer_real or prim.GetStage().GetRootLayer().realPath
            layer_id_for_record = layer_id or prim.GetStage().GetRootLayer().identifier
            # asset or asset[]
            if isinstance(val, Sdf.AssetPath):
                asset_path = val.path
                asset_type = _guess_asset_type(prim, attr, asset_path)
                resolved = resolve_with_layer(resolve_base, asset_path)
                _record_asset(asset_refs, asset_type, asset_path, resolved, layer_id_for_record,
                              prim.GetPath().pathString, attr.GetName())
            elif isinstance(val, list) and val and isinstance(val[0], Sdf.AssetPath):
                for idx, ap in enumerate(val):
                    asset_type = _guess_asset_type(prim, attr, ap.path)
                    resolved = resolve_with_layer(resolve_base, ap.path)
                    _record_asset(asset_refs, asset_type, ap.path, resolved, layer_id_for_record,
                                  prim.GetPath().pathString, f"{attr.GetName()}[{idx}]")

    # 4) MDL module dependencies (imports) for locally-resolved MDL files.
    # This closes a common gap where USD references only the top-level .mdl, but
    # that .mdl imports siblings like OmniUe4Base/OmniUe4Function.
    extra: List[AssetRef] = []
    for asset in asset_refs:
        if asset.asset_type != "mdl":
            continue
        if not asset.resolved_path:
            continue
        for dep_abs in _scan_mdl_import_deps(asset.resolved_path):
            # Record as an MDL asset with a non-stage layer identifier; it's only
            # used for copy/report, not for USD rewrite.
            _record_asset(
                extra,
                "mdl",
                dep_abs,
                dep_abs,
                layer_id=asset.resolved_path,
                prim_path="(mdl_import)",
                attr_name="mdl_import",
            )
    if extra:
        asset_refs.extend(extra)
        logger.info("scan: added %d mdl import deps", len(extra))

    # 5) MDL resource dependencies (textures referenced inside MDL code).
    # We scan all locally-resolved MDL files, including imported siblings.
    mdl_paths: List[str] = []
    for asset in asset_refs:
        if asset.asset_type != "mdl" or not asset.resolved_path:
            continue
        mdl_paths.append(asset.resolved_path)
    # De-dup while preserving order
    seen_mdl = set()
    uniq_mdl_paths: List[str] = []
    for mp in mdl_paths:
        if mp in seen_mdl:
            continue
        seen_mdl.add(mp)
        uniq_mdl_paths.append(mp)

    mdl_tex_extra: List[AssetRef] = []
    for mp in uniq_mdl_paths:
        for dep_abs in _scan_mdl_resource_deps(mp):
            _record_asset(
                mdl_tex_extra,
                "texture",
                dep_abs,
                dep_abs,
                layer_id=mp,
                prim_path="(mdl_resource)",
                attr_name="mdl_resource",
            )
    if mdl_tex_extra:
        asset_refs.extend(mdl_tex_extra)
        logger.info("scan: added %d mdl resource deps", len(mdl_tex_extra))

    # 6) referenced/payloaded file-backed layers actually used by the stage
    # NOTE: `GetUsedLayers()` includes sublayers and referenced layers; we skip
    # anything already in the root layer stack (those are exported separately).
    used_layer_extra: List[AssetRef] = []
    try:
        for layer in stage.GetUsedLayers():
            if not layer:
                continue
            if layer.identifier in layer_stack_ids:
                continue
            real = getattr(layer, "realPath", None)
            if not real:
                continue
            _record_asset(used_layer_extra, "usd", real, real, "(usedLayer)", "(usedLayer)", "usedLayer")
    except Exception:
        used_layer_extra = []

    if used_layer_extra:
        asset_refs.extend(used_layer_extra)
        logger.info("scan: added %d used USD layers", len(used_layer_extra))

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
