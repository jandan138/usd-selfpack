#!/usr/bin/env python3
"""Validate that all external asset file paths referenced by a prim are relative to a given USD file.

Run with Isaac Sim python:
  ./scripts/isaac_python.sh ./scripts/validate_prim_relative_deps.py \
        --usd /path/to/packaged/scene.usd \
        --prim /World/SomePrim

What it checks:
- Scans the prim subtree + bound material subtree.
- Collects any Sdf.AssetPath values and reference/payload paths.
- Flags:
  - absolute paths
  - remote paths (omniverse/http/https/s3)
  - relative paths that resolve to missing files
  - relative paths that "escape" the USD directory via '..'

Note: For MDL module names that are not file paths (no extension), existence can't be validated.
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
class DepIssue:
    severity: str  # error | warn
    kind: str  # attr | references | payloads
    owner_prim: str
    prop: str
    authored: str
    resolved: str
    message: str


def _is_remote(path: str) -> bool:
    return any(path.startswith(p) for p in REMOTE_PREFIXES)


def _iter_asset_paths_from_value(value: Any) -> Iterable[Sdf.AssetPath]:
    if isinstance(value, Sdf.AssetPath):
        yield value
    elif isinstance(value, (list, tuple)) and value:
        if all(isinstance(v, Sdf.AssetPath) for v in value):
            for v in value:
                yield v


def _gather_refs_from_listop(listop: Sdf.ListOp) -> List[Any]:
    items: List[Any] = []
    if not listop:
        return items
    for getter_name in ("GetExplicitItems", "GetPrependedItems", "GetAppendedItems", "GetAddedItems"):
        getter = getattr(listop, getter_name, None)
        if getter is None:
            continue
        try:
            items.extend(getter())
        except Exception:
            pass
    for attr_name in ("explicitItems", "prependedItems", "appendedItems", "addedItems"):
        try:
            val = getattr(listop, attr_name, None)
            if val:
                items.extend(list(val))
        except Exception:
            pass
    return items


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

    _add_from(prim)
    for p in Usd.PrimRange(prim):
        _add_from(p)

    return [materials[k] for k in sorted(materials.keys())]


def _resolve_against_base(base_dir: Path, authored: str) -> Tuple[str, Optional[Path]]:
    if not authored:
        return "", None
    if _is_remote(authored):
        return "", None
    p = Path(authored)
    if p.is_absolute():
        if p.exists():
            return str(p.resolve()), p.resolve()
        return str(p), p

    resolved = (base_dir / authored).resolve()
    return str(resolved), resolved


def _is_within(base_dir: Path, path: Path) -> bool:
    try:
        return path.resolve().is_relative_to(base_dir.resolve())
    except Exception:
        # Python < 3.9 or weird path; fallback
        try:
            base = str(base_dir.resolve())
            cand = str(path.resolve())
            return cand.startswith(base.rstrip("/") + "/") or cand == base
        except Exception:
            return False


def validate(usd_path: str, prim_path: str) -> Tuple[List[DepIssue], Dict[str, int]]:
    stage = Usd.Stage.Open(usd_path)
    if not stage:
        raise RuntimeError(f"Failed to open stage: {usd_path}")

    prim = stage.GetPrimAtPath(prim_path)
    if not prim or not prim.IsValid():
        raise RuntimeError(f"Prim not found: {prim_path}")

    root_layer_path = stage.GetRootLayer().realPath or stage.GetRootLayer().identifier
    base_dir = Path(root_layer_path).parent

    issues: List[DepIssue] = []

    def check_path(kind: str, owner: str, prop: str, authored: str, from_assetpath_resolved: str = "") -> None:
        authored = authored or ""
        if not authored:
            return
        if _is_remote(authored):
            issues.append(DepIssue("warn", kind, owner, prop, authored, "", "remote path"))
            return

        p = Path(authored)
        if p.is_absolute():
            sev = "error"
            msg = "absolute path"
            issues.append(DepIssue(sev, kind, owner, prop, authored, from_assetpath_resolved, msg))
            return

        # Relative to scene.usd directory
        resolved_str, resolved_path = _resolve_against_base(base_dir, authored)

        # Existence check only if looks like a file path
        if resolved_path is not None and (Path(authored).suffix or Path(resolved_str).suffix):
            if not resolved_path.exists():
                issues.append(DepIssue("error", kind, owner, prop, authored, resolved_str, "relative but missing on disk"))

        # Escape check
        if resolved_path is not None and not _is_within(base_dir, resolved_path):
            issues.append(DepIssue("warn", kind, owner, prop, authored, resolved_str, "relative path escapes USD directory"))

    # Prim subtree
    for p in Usd.PrimRange(prim):
        for attr in p.GetAttributes():
            try:
                v = attr.Get()
            except Exception:
                continue
            for ap in _iter_asset_paths_from_value(v):
                check_path("attr", p.GetPath().pathString, attr.GetName(), ap.path or "", ap.resolvedPath or "")

        for meta_name in ("references", "payloads"):
            try:
                list_op = p.GetMetadata(meta_name)
            except Exception:
                list_op = None
            for item in _gather_refs_from_listop(list_op):
                asset_path = getattr(item, "assetPath", "") or ""
                check_path(meta_name, p.GetPath().pathString, meta_name, str(asset_path))

    # Material subtree
    for mat in _collect_materials_for_prim(stage, prim):
        for p in Usd.PrimRange(mat.GetPrim()):
            for attr in p.GetAttributes():
                try:
                    v = attr.Get()
                except Exception:
                    continue
                for ap in _iter_asset_paths_from_value(v):
                    check_path("attr", p.GetPath().pathString, attr.GetName(), ap.path or "", ap.resolvedPath or "")

    stats = {
        "issues_total": len(issues),
        "errors": sum(1 for i in issues if i.severity == "error"),
        "warns": sum(1 for i in issues if i.severity == "warn"),
    }
    return issues, stats


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Validate prim dependency paths are relative to a USD")
    parser.add_argument("--usd", required=True, help="USD path")
    parser.add_argument("--prim", required=True, help="Prim path")
    parser.add_argument("--json-out", default="", help="Optional JSON output path")
    args = parser.parse_args(argv)

    issues, stats = validate(args.usd, args.prim)

    print("=" * 80)
    print("USD:", args.usd)
    print("Prim:", args.prim)
    print("Stats:", stats)
    print("=" * 80)

    if issues:
        for i in issues[:400]:
            print(f"[{i.severity.upper()}] {i.kind} {i.owner_prim} {i.prop} -> {i.authored}")
            if i.resolved:
                print(f"         resolved: {i.resolved}")
            print(f"         {i.message}")
        if len(issues) > 400:
            print(f"... ({len(issues) - 400} more)")
    else:
        print("[OK] No issues found")

    if args.json_out:
        payload = {"stats": stats, "issues": [asdict(i) for i in issues]}
        Path(args.json_out).write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        print("\n[OK] wrote JSON:", args.json_out)

    return 0 if stats["errors"] == 0 else 3


if __name__ == "__main__":
    raise SystemExit(main())
