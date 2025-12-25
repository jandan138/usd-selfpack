from __future__ import annotations

import argparse
from collections import Counter

from pxr import Sdf, Usd


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--usd", required=True)
    args = ap.parse_args()

    stage = Usd.Stage.Open(args.usd)
    if not stage:
        raise SystemExit(f"failed to open stage: {args.usd}")

    counter = Counter()
    examples = {}

    for prim in stage.TraverseAll():
        for attr in prim.GetAttributes():
            try:
                val = attr.Get()
            except Exception:
                continue
            if val is None:
                continue

            aps = []
            if isinstance(val, Sdf.AssetPath):
                aps = [val.path]
            elif isinstance(val, list) and val and isinstance(val[0], Sdf.AssetPath):
                aps = [ap.path for ap in val]

            for p in aps:
                if not p:
                    continue
                # bucket by common folders
                if "/Materials/" in p or p.startswith("Materials/") or p.startswith("./Materials/") or p.startswith("../Materials/"):
                    key = "Materials"
                elif "/materials/" in p or p.startswith("materials/") or p.startswith("./materials/") or p.startswith("../materials/"):
                    key = "materials"
                elif "/Textures/" in p or p.startswith("Textures/") or p.startswith("./Textures/") or p.startswith("../Textures/"):
                    key = "Textures"
                elif "/textures/" in p or p.startswith("textures/") or p.startswith("./textures/") or p.startswith("../textures/"):
                    key = "textures"
                else:
                    continue

                counter[key] += 1
                if key not in examples:
                    examples[key] = p

    print("AssetPath folder summary (bucket -> count, example):")
    for k, c in counter.most_common():
        print(f"  {k}: {c}  e.g. {examples.get(k,'')}")


if __name__ == "__main__":
    main()
