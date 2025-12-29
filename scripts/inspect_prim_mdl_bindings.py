from __future__ import annotations

import argparse
from typing import Iterable, Optional, Tuple

from pxr import Sdf, Usd, UsdShade


def _as_str(v) -> str:
    if v is None:
        return "<None>"
    if isinstance(v, Sdf.AssetPath):
        return v.path
    return str(v)


def _get_attr(prim: Usd.Prim, name: str):
    a = prim.GetAttribute(name)
    if not a:
        return None
    try:
        return a.Get()
    except Exception:
        return None


def _iter_shader_prims(material_prim: Usd.Prim) -> Iterable[Usd.Prim]:
    for p in Usd.PrimRange(material_prim):
        if p.GetTypeName() == "Shader":
            yield p


def _compute_surface_sources(mat: UsdShade.Material) -> Iterable[Tuple[str, Optional[UsdShade.Shader], str]]:
    # Try both default and common render contexts.
    contexts = ["", "mdl", "ri", "universalRenderContext"]
    seen = set()
    for ctx in contexts:
        key = ctx
        if key in seen:
            continue
        seen.add(key)
        try:
            shader, output_name = mat.ComputeSurfaceSource(renderContext=ctx)  # type: ignore[arg-type]
        except Exception:
            shader, output_name = (None, "")
        yield (ctx or "<default>", shader, output_name or "")


def main() -> None:
    ap = argparse.ArgumentParser(description="Inspect bound material + MDL-related shader attributes for a prim")
    ap.add_argument("--usd", required=True, help="USD file to open")
    ap.add_argument("--prim", default="/root/obj_table", help="Prim path to inspect")
    args = ap.parse_args()

    stage = Usd.Stage.Open(args.usd)
    if not stage:
        raise SystemExit(f"failed to open stage: {args.usd}")

    prim = stage.GetPrimAtPath(args.prim)
    print(f"prim: {args.prim}")
    print(f"exists: {bool(prim)}")
    if not prim:
        return

    # Material binding
    mba = UsdShade.MaterialBindingAPI(prim)
    material, rel = mba.ComputeBoundMaterial()
    print(f"bound_material: {material.GetPath() if material else '<None>'}")
    print(f"binding_rel: {rel.GetPath() if rel else '<None>'}")

    if not material:
        return

    mat = UsdShade.Material(material)

    print("surface_sources:")
    for ctx, shader, out_name in _compute_surface_sources(mat):
        spath = shader.GetPath() if shader else "<None>"
        print(f"  {ctx}: shader={spath} output={out_name}")

    # Walk shaders under the material prim and print MDL-relevant attributes.
    print("shaders_under_material:")
    for s_prim in _iter_shader_prims(material):
        print(f"  shader: {s_prim.GetPath()}")
        for name in [
            "info:id",
            "info:implementationSource",
            "info:sourceAsset",
            "info:sourceAsset:subIdentifier",
            "info:mdl:sourceAsset",
            "info:mdl:sourceAsset:subIdentifier",
            "inputs:file",
        ]:
            v = _get_attr(s_prim, name)
            if v is None:
                continue
            print(f"    {name}: {_as_str(v)}")


if __name__ == "__main__":
    main()
