#!/usr/bin/env python3
"""Scan Omniverse Kit / Isaac Sim logs for MDL-related errors.

Why:
- A material can appear red even when USD asset paths are resolvable, if MDL
  compilation/loading fails inside the renderer.

Usage:
  python scripts/scan_kit_log_mdl_errors.py
  python scripts/scan_kit_log_mdl_errors.py --log /path/to/kit_*.log
  python scripts/scan_kit_log_mdl_errors.py --tail 400

Notes:
- This script does NOT require Isaac Sim Python; plain Python is fine.
"""

from __future__ import annotations

import argparse
import glob
import os
import re
from pathlib import Path
from typing import Iterable, List, Optional, TextIO, Tuple


DEFAULT_PATTERNS = [
    r"\bMDL\b",
    r"\bmdl\b",
    r"neuray",
    r"omni\.mdl",
    r"rtx\.mdl",
    r"material.*(error|fail)",
    r"shader.*(error|fail)",
    r"compile.*(error|fail)",
    r"cannot\s+open",
    r"not\s+found",
]


def _default_log_candidates() -> List[Path]:
    home = Path(os.environ.get("HOME", "~")).expanduser()
    roots = [
        home / ".nvidia-omniverse" / "logs" / "Kit",
        home / ".local" / "share" / "ov" / "data" / "Kit",
    ]
    files: List[Path] = []
    for root in roots:
        if not root.exists():
            continue
        for p in root.rglob("kit_*.log"):
            if p.is_file():
                files.append(p)
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return files


def _read_lines(path: Path) -> List[str]:
    try:
        data = path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return [f"[ERROR] Failed to read {path}: {e}"]
    return data.splitlines()


def _compile_regexes(patterns: Iterable[str]) -> List[re.Pattern[str]]:
    return [re.compile(p, re.IGNORECASE) for p in patterns]


def _match_any(line: str, regs: List[re.Pattern[str]]) -> bool:
    return any(r.search(line) for r in regs)


def _extract_matches(lines: List[str], regs: List[re.Pattern[str]], context: int) -> List[Tuple[int, List[str]]]:
    hits: List[Tuple[int, List[str]]] = []
    last_end = -1
    for i, line in enumerate(lines):
        if not _match_any(line, regs):
            continue
        start = max(0, i - context)
        end = min(len(lines), i + context + 1)
        if start <= last_end:
            # merge with previous
            prev_i, prev_block = hits[-1]
            new_block = prev_block + lines[last_end + 1 : end]
            hits[-1] = (prev_i, new_block)
        else:
            hits.append((start, lines[start:end]))
        last_end = end - 1
    return hits


def _block_contains(block: List[str], needles: List[str]) -> bool:
    if not needles:
        return True
    lower_needles = [n.lower() for n in needles]
    for line in block:
        l = line.lower()
        if any(n in l for n in lower_needles):
            return True
    return False


def _writeln(fp: TextIO, s: str = "") -> None:
    fp.write(s + "\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", help="Path to a specific kit_*.log")
    ap.add_argument("--tail", type=int, default=800, help="Only scan last N lines (default: 800)")
    ap.add_argument("--context", type=int, default=2, help="Context lines around matches (default: 2)")
    ap.add_argument(
        "--pattern",
        action="append",
        default=[],
        help="Additional regex pattern (can be repeated)",
    )
    ap.add_argument(
        "--contains",
        action="append",
        default=[],
        help="Only keep matching blocks that contain this substring (case-insensitive). Can be repeated.",
    )
    ap.add_argument(
        "--out",
        help="Write results to a file instead of stdout (recommended for long logs).",
    )
    args = ap.parse_args()

    if args.log:
        log_path = Path(args.log).expanduser().resolve()
        if not log_path.exists():
            raise SystemExit(f"Log file not found: {log_path}")
    else:
        candidates = _default_log_candidates()
        if not candidates:
            print("No Kit logs found under ~/.nvidia-omniverse/logs/Kit or ~/.local/share/ov/data/Kit")
            return 2
        log_path = candidates[0]

    patterns = DEFAULT_PATTERNS + list(args.pattern)
    regs = _compile_regexes(patterns)

    lines = _read_lines(log_path)
    if args.tail and len(lines) > args.tail:
        base = len(lines) - args.tail
        scan_lines = lines[-args.tail :]
    else:
        base = 0
        scan_lines = lines

    hits = _extract_matches(scan_lines, regs, context=args.context)
    if args.contains:
        hits = [(start, block) for (start, block) in hits if _block_contains(block, args.contains)]

    out_fp: Optional[TextIO] = None
    try:
        if args.out:
            out_path = Path(args.out).expanduser().resolve()
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_fp = out_path.open("w", encoding="utf-8")
            fp = out_fp
        else:
            fp = None

        def emit(s: str = "") -> None:
            nonlocal fp
            if fp is not None:
                _writeln(fp, s)
            else:
                try:
                    print(s)
                except BrokenPipeError:
                    # If output is being piped to a command that closes early.
                    raise SystemExit(0)

        emit(f"LOG: {log_path}")
        emit(f"Scanning lines: {base+1}..{base+len(scan_lines)}")
        emit("Patterns:")
        for p in patterns:
            emit(f"  {p}")
        if args.contains:
            emit("Contains filters:")
            for c in args.contains:
                emit(f"  {c}")

        if not hits:
            emit("\nNo MDL-related matches found in scanned region.")
            return 0

        emit(f"\nFound {len(hits)} matching block(s):")
        for start, block in hits:
            line_no = base + start + 1
            emit("\n---")
            emit(f"@ line {line_no}")
            for j, l in enumerate(block):
                emit(f"{line_no + j:>7} | {l}")
    finally:
        if out_fp is not None:
            out_fp.close()

    if args.out:
        # Give the user a short stdout hint even when writing to file.
        print(f"Wrote output to: {Path(args.out).expanduser().resolve()}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
