from __future__ import annotations

import argparse
from pxr import Usd, Sdf

def inspect_prim(usd_path: str, prim_path_str: str):
    print(f"Opening stage: {usd_path}")
    stage = Usd.Stage.Open(usd_path)
    if not stage:
        print("Error: Could not open stage.")
        return

    prim = stage.GetPrimAtPath(prim_path_str)
    if not prim.IsValid():
        print(f"Error: Prim '{prim_path_str}' not found in stage.")
        return

    print(f"\n=== Inspecting Prim: {prim.GetPath()} ===")
    
    # 1. Check for Direct References/Payloads on this Prim
    # These are "Introduction" points - where a new file is brought in.
    print(f"\n[1] Composition Arcs (References/Payloads on {prim.GetName()}):")
    has_arcs = False
    
    if prim.HasAuthoredReferences():
        has_arcs = True
        refs = prim.GetMetadata("references")
        # refs is a pxr.Sdf.ReferenceListOp
        # We need to access explicit items or prepended items
        print("  - References:")
        # The API for ListOp is a bit complex, let's look at the composition directly
        # Or simpler: traverse the PrimStack to see specs with references
        for ref in refs.GetAddedOrExplicitItems():
            print(f"    * AssetPath: {ref.assetPath}")
            print(f"    * PrimPath:  {ref.primPath}")

    if prim.HasAuthoredPayloads():
        has_arcs = True
        payloads = prim.GetMetadata("payload")
        print("  - Payloads:")
        for pl in payloads.GetAddedOrExplicitItems():
            print(f"    * AssetPath: {pl.assetPath}")
            print(f"    * PrimPath:  {pl.primPath}")

    if not has_arcs:
        print("  (None direct)")

    # 2. Check Prim Stack (Where is this prim defined?)
    # This shows all the layers that have an opinion on this prim.
    # The 'strongest' layer is usually the one being edited or the local file.
    # The 'weaker' layers are usually the files brought in by references.
    print(f"\n[2] Prim Stack (Definition Source Layers):")
    print("    (Ordered from Strongest [Local] to Weakest [Referenced])")
    
    stack = prim.GetPrimStack()
    for i, node in enumerate(stack):
        layer = node.layer
        # Check if this layer is the root layer or an external one
        is_root = (layer == stage.GetRootLayer())
        prefix = "[Root Layer]" if is_root else "[External]"
        
        print(f"  {i+1}. {prefix} {layer.identifier}")
        print(f"     Path in Layer: {node.path}")
        
        # If we hit an external layer, that's likely the file you are looking for!
        if not is_root:
            print(f"     ^^^ This prim is defined inside this USD file.")

    # 3. Ancestor Check (Recursion)
    # Often the prim itself doesn't have the reference, but its parent does.
    # e.g. /World/Table has reference to table.usd, and we are looking at /World/Table/Leg
    print(f"\n[3] Ancestor Check (Who introduced this hierarchy?):")
    curr = prim
    while not curr.IsPseudoRoot():
        if curr.HasAuthoredReferences() or curr.HasAuthoredPayloads():
            print(f"  -> Found composition arc on ancestor: {curr.GetPath()}")
            if curr.HasAuthoredReferences():
                 refs = curr.GetMetadata("references")
                 for ref in refs.GetAddedOrExplicitItems():
                     print(f"     [Reference] Asset: {ref.assetPath}")
            if curr.HasAuthoredPayloads():
                 pls = curr.GetMetadata("payload")
                 for pl in pls.GetAddedOrExplicitItems():
                     print(f"     [Payload]   Asset: {pl.assetPath}")
            # Usually we stop at the first one found as it's the closest container
            break
        curr = curr.GetParent()
    else:
        print("  (No ancestors introduce references/payloads. Defined purely in Root?)")

def main():
    parser = argparse.ArgumentParser(description="Find the source USD file for a given prim.")
    parser.add_argument("--usd", required=True, help="Path to the root USD stage.")
    parser.add_argument("--prim", required=True, help="Prim path to inspect (e.g. /root/obj_0/mesh).")
    args = parser.parse_args()
    
    inspect_prim(args.usd, args.prim)

if __name__ == "__main__":
    main()
