#!/usr/bin/env python3
"""Compare material bindings + external asset dependencies for the same prim across two USD stages.

Run with Isaac Sim python:
  ./scripts/isaac_python.sh ./scripts/compare_prim_materials.py \
    --usd-a /path/to/a/scene.usd \
    --usd-b /path/to/b/scene.usd \
        --prim /World/SomePrim

Focus:
- Material bindings (UsdShade.MaterialBindingAPI)
- Shader networks under bound materials
- External asset paths (Sdf.AssetPath) found on the prim subtree and material subtree
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from pxr import Sdf, Usd, UsdShade


REMOTE_PREFIXES = ("omniverse://", "http://", "https://", "s3://")


@dataclass(frozen=True)
class AssetOccurrence:
    kind: str  # attr | reference | payload | subLayerPaths | binding
    owner_prim: str
    prop: str
    authored: str
    resolved: str
    layer: str


@dataclass
class StageSummary:
    usd: str
    prim: str
    exists: bool
    materials: List[str]
    deps: List[AssetOccurrence]


def _is_remote(path: str) -> bool:
    return any(path.startswith(p) for p in REMOTE_PREFIXES)


def _as_str(v: Any) -> str:
    if v is None:
        return ""
    return str(v)


def _layer_of_attr(attr: Usd.Attribute) -> str:
    try:
        stack = attr.GetPropertyStack()
        if stack:
            layer = stack[0].layer
            if layer is not None:
                return layer.identifier or layer.realPath or ""
    except Exception:
        pass
    return ""


def _gather_refs_from_listop(listop: Sdf.ListOp) -> List[Any]:
    items: List[Any] = []
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

    for attr_name in ("explicitItems", "prependedItems", "appendedItems", "addedItems"):
        try:
            val = getattr(listop, attr_name, None)
            if val:
                items.extend(list(val))
        except Exception:
            continue

    return items


def _asset_occurrence(kind: str, owner_prim: str, prop: str, ap: Sdf.AssetPath, layer: str) -> AssetOccurrence:
    authored = ap.path or ""
    resolved = ap.resolvedPath or ""
    return AssetOccurrence(kind=kind, owner_prim=owner_prim, prop=prop, authored=authored, resolved=resolved, layer=layer)


def _iter_asset_paths_from_value(value: Any) -> Iterable[Sdf.AssetPath]:
    if isinstance(value, Sdf.AssetPath):
        yield value
    elif isinstance(value, (list, tuple)) and value:
        if all(isinstance(v, Sdf.AssetPath) for v in value):
            for v in value:
                yield v


def _collect_asset_attrs_from_prim(prim: Usd.Prim) -> List[AssetOccurrence]:
    out: List[AssetOccurrence] = []
    for attr in prim.GetAttributes():
        try:
            value = attr.Get()
        except Exception:
            continue
        for ap in _iter_asset_paths_from_value(value):
            layer = _layer_of_attr(attr)
            out.append(_asset_occurrence("attr", prim.GetPath().pathString, attr.GetName(), ap, layer))
    return out


def _collect_refs_payloads_from_prim(prim: Usd.Prim) -> List[AssetOccurrence]:
    out: List[AssetOccurrence] = []
    for meta_name in ("references", "payloads"):
        try:
            list_op = prim.GetMetadata(meta_name)
        except Exception:
            list_op = None
        for item in _gather_refs_from_listop(list_op):
            asset_path = getattr(item, "assetPath", "") or ""
            if not asset_path:
                continue
            # References/Payloads store plain string paths; keep in authored, resolved empty.
            out.append(
                AssetOccurrence(
                    kind=meta_name,
                    owner_prim=prim.GetPath().pathString,
                    prop=meta_name,
                    authored=str(asset_path),
                    resolved="",
                    layer="",
                )
            )
    return out


def _collect_materials_for_prim(stage: Usd.Stage, prim: Usd.Prim) -> List[UsdShade.Material]:
    materials: Dict[str, UsdShade.Material] = {}

    def _add_from(p: Usd.Prim) -> None:
        try:
            api = UsdShade.MaterialBindingAPI(p)
            mat, rel = api.ComputeBoundMaterial()
            if mat and mat.GetPrim().IsValid():
                materials[mat.GetPath().pathString] = mat
        except Exception:
            return

    # Check the prim itself and all descendants (bindings are often on meshes).
    if prim and prim.IsValid():
        _add_from(prim)
        for child in Usd.PrimRange(prim):
            _add_from(child)

    # Deterministic order
    return [materials[k] for k in sorted(materials.keys())]


def _collect_binding_relationships(prim: Usd.Prim) -> List[AssetOccurrence]:
    out: List[AssetOccurrence] = []
    try:
        api = UsdShade.MaterialBindingAPI(prim)
        rel = api.GetDirectBindingRel()
        if rel and rel.HasAuthoredTargets():
            for t in rel.GetTargets():
                out.append(
                    AssetOccurrence(
                        kind="binding",
                        owner_prim=prim.GetPath().pathString,
                        prop=rel.GetName(),
                        authored=t.pathString,
                        resolved="",
                        layer="",
                    )
                )
    except Exception:
        pass
    return out


def _collect_deps_for_scope(stage: Usd.Stage, prim: Usd.Prim) -> Tuple[List[str], List[AssetOccurrence]]:
    deps: List[AssetOccurrence] = []

    if not prim or not prim.IsValid():
        return [], deps

    # Prim subtree (attrs + refs/payloads + direct binding rel)
    deps.extend(_collect_binding_relationships(prim))
    for p in Usd.PrimRange(prim):
        deps.extend(_collect_asset_attrs_from_prim(p))
        deps.extend(_collect_refs_payloads_from_prim(p))

    # Bound materials and their subgraphs
    mats = _collect_materials_for_prim(stage, prim)
    mat_paths = [m.GetPath().pathString for m in mats]

    for mat in mats:
        mat_prim = mat.GetPrim()
        for p in Usd.PrimRange(mat_prim):
            deps.extend(_collect_asset_attrs_from_prim(p))

    # Normalize/resolution: if resolved empty and authored is local file-ish, try resolver.
    base = Path(stage.GetRootLayer().realPath or stage.GetRootLayer().identifier).parent
    normalized: List[AssetOccurrence] = []
    for d in deps:
        authored = d.authored
        resolved = d.resolved
        if d.kind in ("references", "payloads"):
            if authored and not _is_remote(authored):
                p = Path(authored)
                if not p.is_absolute():
                    cand = (base / authored).resolve()
                else:
                    cand = p
                if cand.exists():
                    resolved = str(cand)
        elif d.kind == "attr":
            if authored and not resolved and not _is_remote(authored):
                p = Path(authored)
                cand = (base / authored).resolve() if not p.is_absolute() else p
                if cand.exists():
                    resolved = str(cand)

        normalized.append(
            AssetOccurrence(kind=d.kind, owner_prim=d.owner_prim, prop=d.prop, authored=authored, resolved=resolved, layer=d.layer)
        )

    # De-dup while keeping order
    seen = set()
    deduped: List[AssetOccurrence] = []
    for d in normalized:
        key = (d.kind, d.owner_prim, d.prop, d.authored, d.resolved, d.layer)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(d)

    return mat_paths, deduped


def summarize_stage(usd_path: str, prim_path: str) -> StageSummary:
    stage = Usd.Stage.Open(usd_path)
    if not stage:
        return StageSummary(usd=usd_path, prim=prim_path, exists=False, materials=[], deps=[])

    prim = stage.GetPrimAtPath(prim_path)
    if not prim or not prim.IsValid():
        return StageSummary(usd=usd_path, prim=prim_path, exists=False, materials=[], deps=[])

    mats, deps = _collect_deps_for_scope(stage, prim)
    return StageSummary(usd=usd_path, prim=prim_path, exists=True, materials=mats, deps=deps)


def _index_deps(deps: Sequence[AssetOccurrence]) -> Dict[Tuple[str, str, str, str], AssetOccurrence]:
    # Keyed by (kind, owner_prim, prop, authored). resolved/layer become values to compare.
    out: Dict[Tuple[str, str, str, str], AssetOccurrence] = {}
    for d in deps:
        out[(d.kind, d.owner_prim, d.prop, d.authored)] = d
    return out


def _print_diff(a: StageSummary, b: StageSummary) -> None:
    print("=" * 80)
    print("Prim:", a.prim)
    print("USD A:", a.usd)
    print("USD B:", b.usd)
    print("=" * 80)

    if not a.exists:
        print("[A] prim not found / stage open failed")
    if not b.exists:
        print("[B] prim not found / stage open failed")
    if not a.exists or not b.exists:
        return

    if a.materials != b.materials:
        print("\n[DIFF] Bound material paths differ")
        print("  A:", a.materials)
        print("  B:", b.materials)

    idx_a = _index_deps(a.deps)
    idx_b = _index_deps(b.deps)

    keys = sorted(set(idx_a.keys()) | set(idx_b.keys()))
    only_a = [k for k in keys if k not in idx_b]
    only_b = [k for k in keys if k not in idx_a]
    both = [k for k in keys if k in idx_a and k in idx_b]

    def fmt(d: AssetOccurrence) -> str:
        extra = []
        if d.layer:
            extra.append(f"layer={d.layer}")
        if d.resolved:
            extra.append(f"resolved={d.resolved}")
        suffix = (" " + " ".join(extra)) if extra else ""
        return f"{d.kind} {d.owner_prim} {d.prop} -> {d.authored}{suffix}"

    if only_a:
        print("\n[ONLY IN A] dependencies")
        for k in only_a[:200]:
            print("  ", fmt(idx_a[k]))
        if len(only_a) > 200:
            print(f"  ... ({len(only_a) - 200} more)")

    if only_b:
        print("\n[ONLY IN B] dependencies")
        for k in only_b[:200]:
            print("  ", fmt(idx_b[k]))
        if len(only_b) > 200:
            print(f"  ... ({len(only_b) - 200} more)")

    changed = []
    for k in both:
        da = idx_a[k]
        db = idx_b[k]
        if (da.resolved or "") != (db.resolved or "") or (da.layer or "") != (db.layer or ""):
            changed.append((da, db))

    if changed:
        print("\n[CHANGED] same authored path but different resolved/layer")
        for da, db in changed[:200]:
            print("  ", da.kind, da.owner_prim, da.prop)
            print("     authored:", da.authored)
            print("     A resolved:", da.resolved or "(empty)")
            print("     B resolved:", db.resolved or "(empty)")
            if da.layer or db.layer:
                print("     A layer:", da.layer or "(empty)")
                print("     B layer:", db.layer or "(empty)")
        if len(changed) > 200:
            print(f"  ... ({len(changed) - 200} more)")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Compare a prim's materials and external asset deps across two USDs")
    parser.add_argument("--usd-a", required=True, help="First USD path")
    parser.add_argument("--usd-b", required=True, help="Second USD path")
    parser.add_argument("--prim", required=True, help="Prim path to compare")
    parser.add_argument("--json-out", default="", help="Optional JSON output path")
    args = parser.parse_args(argv)

    a = summarize_stage(args.usd_a, args.prim)
    b = summarize_stage(args.usd_b, args.prim)

    _print_diff(a, b)

    if args.json_out:
        payload = {"a": asdict(a), "b": asdict(b)}
        Path(args.json_out).write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        print("\n[OK] wrote JSON:", args.json_out)

    # Non-zero if any stage missing
    return 0 if (a.exists and b.exists) else 2


if __name__ == "__main__":
    raise SystemExit(main())
