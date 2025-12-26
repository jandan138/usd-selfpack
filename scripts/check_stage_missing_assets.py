from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from pxr import Usd


def _as_posix(p: str) -> str:
    return p.replace("\\", "/")


def main() -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Open a USD stage and produce a structured report of potentially-missing assets "
            "(USD/MDL/textures/etc) based on resolver checks.\n\n"
            "Intended for debugging stage-composition mismatches between original vs packed USD."
        )
    )
    ap.add_argument("--usd", required=True, help="Path to USD file")
    ap.add_argument("--out", default=None, help="Write JSON report to this path")
    ap.add_argument("--max-examples", type=int, default=30)
    args = ap.parse_args()

    usd_path = Path(args.usd)
    if not usd_path.is_file():
        raise SystemExit(f"USD not found: {usd_path}")

    # Import packager scanner/resolver so we mimic the packager's view of the world.
    from usd_asset_packager.scan import scan_stage  # noqa: WPS433

    class _Logger:
        def info(self, *_a, **_k):
            pass

        def warning(self, *_a, **_k):
            pass

        def debug(self, *_a, **_k):
            pass

    stage = Usd.Stage.Open(str(usd_path))
    if not stage:
        raise SystemExit(f"failed to open stage: {usd_path}")

    # Best-effort: load payloads so composition is closer to "what you see".
    try:
        stage.Load()
    except Exception:
        pass

    assets = scan_stage(stage, _Logger())

    # Structured stats
    totals_by_type: Counter[str] = Counter()
    remote_by_type: Counter[str] = Counter()
    unresolved_by_type: Counter[str] = Counter()
    missing_on_disk_by_type: Counter[str] = Counter()

    # Focus: USD composition deps (subLayers/references/payload) by layer.
    missing_usd_by_layer: dict[str, int] = defaultdict(int)

    examples: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for a in assets:
        at = a.asset_type or "(empty)"
        totals_by_type[at] += 1

        if a.is_remote:
            remote_by_type[at] += 1
            if len(examples["remote"]) < args.max_examples:
                examples["remote"].append(
                    {
                        "asset_type": at,
                        "path": a.original_path,
                        "layer": a.layer_identifier,
                        "prim": a.prim_path,
                        "attr": a.attr_name,
                    }
                )
            continue

        resolved = a.resolved_path
        if not resolved:
            unresolved_by_type[at] += 1
            if at == "usd":
                missing_usd_by_layer[a.layer_identifier] += 1
            if len(examples["unresolved"]) < args.max_examples:
                examples["unresolved"].append(
                    {
                        "asset_type": at,
                        "path": a.original_path,
                        "layer": a.layer_identifier,
                        "prim": a.prim_path,
                        "attr": a.attr_name,
                    }
                )
            continue

        rp = Path(resolved)
        if not rp.exists():
            missing_on_disk_by_type[at] += 1
            if at == "usd":
                missing_usd_by_layer[a.layer_identifier] += 1
            if len(examples["missing_on_disk"]) < args.max_examples:
                examples["missing_on_disk"].append(
                    {
                        "asset_type": at,
                        "path": a.original_path,
                        "resolved": _as_posix(str(rp)),
                        "layer": a.layer_identifier,
                        "prim": a.prim_path,
                        "attr": a.attr_name,
                    }
                )

    report: dict[str, Any] = {
        "usd": _as_posix(str(usd_path)),
        "prim_count": sum(1 for _ in stage.TraverseAll()),
        "asset_ref_count": len(assets),
        "totals_by_type": dict(totals_by_type),
        "remote_by_type": dict(remote_by_type),
        "unresolved_by_type": dict(unresolved_by_type),
        "missing_on_disk_by_type": dict(missing_on_disk_by_type),
        "missing_usd_by_layer_top": [
            {"layer_identifier": k, "missing_usd_refs": v}
            for k, v in sorted(missing_usd_by_layer.items(), key=lambda kv: kv[1], reverse=True)[: args.max_examples]
        ],
        "examples": examples,
    }

    # Human summary
    def _fmt(counter: dict[str, int]) -> str:
        return ", ".join(f"{k}={v}" for k, v in sorted(counter.items(), key=lambda kv: kv[0]))

    print(f"USD: {report['usd']}")
    print(f"prim_count: {report['prim_count']}")
    print(f"asset_ref_count: {report['asset_ref_count']}")
    print("totals_by_type:", _fmt(report["totals_by_type"]))
    print("remote_by_type:", _fmt(report["remote_by_type"]))
    print("unresolved_by_type:", _fmt(report["unresolved_by_type"]))
    print("missing_on_disk_by_type:", _fmt(report["missing_on_disk_by_type"]))

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Wrote report: {out_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
