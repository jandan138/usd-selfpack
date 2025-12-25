from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, List, Set, Tuple

from pxr import Sdf, Usd


def _iter_assetpaths(stage: Usd.Stage) -> List[Tuple[str, str, str]]:
    out: List[Tuple[str, str, str]] = []
    for prim in stage.TraverseAll():
        for attr in prim.GetAttributes():
            try:
                val = attr.Get()
            except Exception:
                continue
            if val is None:
                continue
            if isinstance(val, Sdf.AssetPath):
                out.append((prim.GetPath().pathString, attr.GetName(), val.path))
            elif isinstance(val, list) and val and isinstance(val[0], Sdf.AssetPath):
                for i, ap in enumerate(val):
                    out.append((prim.GetPath().pathString, f"{attr.GetName()}[{i}]", ap.path))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--usd", required=True)
    args = ap.parse_args()

    stage = Usd.Stage.Open(args.usd)
    if not stage:
        raise SystemExit(f"failed to open stage: {args.usd}")

    mdls: Dict[str, int] = {}
    all_assetpaths = _iter_assetpaths(stage)
    for _prim_path, _attr_name, asset_path in all_assetpaths:
        if not asset_path:
            continue
        if asset_path.lower().endswith(".mdl"):
            mdls[asset_path] = mdls.get(asset_path, 0) + 1

    print("Unique MDL asset paths (path -> count):")
    for p in sorted(mdls.keys()):
        print(f"  {p} -> {mdls[p]}")

    # Also show whether Materials/ vs materials/ appears.
    has_upper = any("/Materials/" in p or p.startswith("Materials/") or p.startswith("./Materials/") for p in mdls)
    has_lower = any("/materials/" in p or p.startswith("materials/") or p.startswith("./materials/") for p in mdls)
    print(f"has Materials/: {has_upper}")
    print(f"has materials/: {has_lower}")


if __name__ == "__main__":
    main()
