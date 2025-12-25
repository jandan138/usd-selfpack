from __future__ import annotations

import argparse
from typing import Any

from pxr import Sdf, Usd


def _fmt_value(v: Any) -> str:
    if v is None:
        return "None"
    if isinstance(v, Sdf.AssetPath):
        return f"AssetPath({v.path})"
    if isinstance(v, list):
        if len(v) == 0:
            return "[]"
        if len(v) > 5:
            return f"list(len={len(v)}, first={_fmt_value(v[0])})"
        return "[" + ", ".join(_fmt_value(x) for x in v) + "]"
    s = str(v)
    if len(s) > 300:
        s = s[:300] + "..."
    return s


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--usd", required=True)
    ap.add_argument("--prim", required=True)
    args = ap.parse_args()

    stage = Usd.Stage.Open(args.usd)
    if not stage:
        raise SystemExit(f"failed to open stage: {args.usd}")

    prim = stage.GetPrimAtPath(args.prim)
    print(f"Prim path: {args.prim}")
    print(f"Exists: {bool(prim)}")
    if not prim:
        return

    print(f"TypeName: {prim.GetTypeName()}")
    print(f"IsA(UsdShade.Shader)? {prim.GetTypeName() == 'Shader'}")

    # Common metadata
    for key in ["kind", "assetInfo", "customData"]:
        try:
            md = prim.GetMetadata(key)
        except Exception:
            md = None
        if md:
            print(f"metadata[{key}]: {_fmt_value(md)}")

    # Attributes
    attrs = list(prim.GetAttributes())
    print(f"Attribute count: {len(attrs)}")
    for a in sorted(attrs, key=lambda x: x.GetName()):
        name = a.GetName()
        try:
            v = a.Get()
        except Exception as exc:
            print(f"  {name}: <ERROR reading> {exc}")
            continue
        print(f"  {name}: {_fmt_value(v)}")



if __name__ == "__main__":
    main()
