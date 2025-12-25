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
        if len(v) > 6:
            return f"list(len={len(v)}, first={_fmt_value(v[0])})"
        return "[" + ", ".join(_fmt_value(x) for x in v) + "]"
    s = str(v)
    if len(s) > 300:
        s = s[:300] + "..."
    return s


def _spec_default(spec: Any) -> Any:
    # Sdf.AttributeSpec has .default; in some bindings it's .GetDefaultValue()
    for name in ("default", "Default"):
        if hasattr(spec, name):
            return getattr(spec, name)
    if hasattr(spec, "GetDefaultValue"):
        try:
            return spec.GetDefaultValue()
        except Exception:
            return None
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--usd", required=True)
    ap.add_argument("--prim", required=True)
    ap.add_argument("--attr", required=True, help="Attribute name, e.g. info:id or info:mdl:sourceAsset")
    args = ap.parse_args()

    stage = Usd.Stage.Open(args.usd)
    if not stage:
        raise SystemExit(f"failed to open stage: {args.usd}")

    prim = stage.GetPrimAtPath(args.prim)
    if not prim:
        raise SystemExit(f"prim not found: {args.prim}")

    attr = prim.GetAttribute(args.attr)
    if not attr:
        raise SystemExit(f"attr not found: {args.attr}")

    print(f"Stage: {args.usd}")
    print(f"Prim:  {args.prim}")
    print(f"Attr:  {args.attr}")
    try:
        resolved = attr.Get()
    except Exception as exc:
        resolved = f"<ERROR> {exc}"
    print(f"Resolved value: {_fmt_value(resolved)}")

    try:
        ri = attr.GetResolveInfo()
        # ri may print useful source info
        print(f"ResolveInfo: {ri}")
    except Exception:
        pass

    try:
        stack = attr.GetPropertyStack(Usd.TimeCode.Default())
    except Exception:
        stack = attr.GetPropertyStack()

    print(f"Property stack count: {len(stack)}")
    for i, spec in enumerate(stack):
        layer_id = None
        try:
            layer_id = spec.layer.identifier  # type: ignore[attr-defined]
        except Exception:
            try:
                layer_id = spec.layerId  # type: ignore[attr-defined]
            except Exception:
                layer_id = None

        path = None
        try:
            path = spec.path.pathString
        except Exception:
            try:
                path = str(spec.path)
            except Exception:
                path = None

        dtype = None
        try:
            dtype = getattr(spec, "typeName", None)
        except Exception:
            dtype = None

        default = _spec_default(spec)

        print(f"  [{i}] layer={layer_id}")
        if path:
            print(f"      specPath={path}")
        if dtype:
            print(f"      typeName={dtype}")
        print(f"      default={_fmt_value(default)}")


if __name__ == "__main__":
    main()
