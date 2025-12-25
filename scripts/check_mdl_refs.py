#!/usr/bin/env python3
"""Diagnose MDL resolution problems without needing the Isaac UI.

What it does:
- Locates an MDL file inside a packaged out_dir (supports Materials/ and materials/).
- Scans the MDL source for referenced texture-like filenames (png/jpg/exr/etc).
- Checks whether those referenced files exist (case-sensitive) relative to:
  - the MDL file directory
  - out_dir (common pack layout)
  - out_dir/Textures, out_dir/textures (and nested)

This helps debug the "everything is red" symptom when MDL search paths are set
but the MDL (or textures used by it) still can't be loaded at runtime.

Usage (inside Isaac Sim python):
  ./scripts/isaac_python.sh scripts/check_mdl_refs.py \
    --out-dir /path/to/out_dir \
      --mdl Materials/Num595f215bc6dce910dd2f0f2d.mdl
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Tuple


_TEXTURE_EXTS = (
    ".png",
    ".jpg",
    ".jpeg",
    ".tif",
    ".tiff",
    ".exr",
    ".hdr",
    ".dds",
    ".ktx",
    ".bmp",
    ".tga",
)


@dataclass(frozen=True)
class RefResult:
    raw: str
    exists: bool
    resolved: Optional[Path]
    hint: Optional[str]


@dataclass(frozen=True)
class MdlLocalResult:
    raw: str
    exists_next_to_mdl: bool
    expected: Path


def _find_case_insensitive(path: Path) -> Optional[Path]:
    """If path doesn't exist due to case mismatch, try to find a match."""
    if path.exists():
        return path

    parts = list(path.parts)
    if not parts:
        return None

    current = Path(parts[0])
    start_idx = 1
    if path.is_absolute():
        current = Path("/")
        start_idx = 1

    for part in parts[start_idx:]:
        if not current.exists() or not current.is_dir():
            return None
        entries = {p.name.lower(): p for p in current.iterdir()}
        match = entries.get(part.lower())
        if match is None:
            return None
        current = match
    return current


def _scan_mdl_for_strings(text: str) -> List[str]:
    # MDL uses double-quoted strings. We'll conservatively extract any quoted string
    # containing a known image extension.
    results: List[str] = []
    for m in re.finditer(r"\"([^\"\\]*(?:\\.[^\"\\]*)*)\"", text):
        s = m.group(1)
        s_unescaped = s.replace("\\\\", "\\").replace("\\\"", '"')
        lower = s_unescaped.lower()
        if any(ext in lower for ext in _TEXTURE_EXTS):
            results.append(s_unescaped)
    return results


def _candidate_search_roots(out_dir: Path, mdl_dir: Path) -> List[Path]:
    roots = [mdl_dir, out_dir]
    for name in ("Textures", "textures"):
        p = out_dir / name
        if p.exists():
            roots.append(p)
    # Common: out_dir/textures/textures
    p2 = out_dir / "textures" / "textures"
    if p2.exists():
        roots.append(p2)
    return roots


def _iter_texture_candidates(raw: str, roots: Iterable[Path]) -> Iterable[Tuple[str, Path]]:
    p = Path(raw)

    # If it's absolute, only that.
    if p.is_absolute():
        yield ("absolute", p)
        return

    # If it's explicitly relative with ./ or ../, resolve under each root.
    if raw.startswith("./") or raw.startswith("../"):
        for root in roots:
            yield (f"root:{root}", (root / p).resolve())
        return

    # Otherwise treat as relative path or basename:
    for root in roots:
        yield (f"root:{root}", (root / p).resolve())


def _resolve_ref(raw: str, roots: List[Path]) -> RefResult:
    # Fast path: if raw is a URL-ish thing, don't try.
    if raw.startswith("http://") or raw.startswith("https://") or raw.startswith("omniverse://"):
        return RefResult(raw=raw, exists=False, resolved=None, hint="URL/remote path")

    for how, candidate in _iter_texture_candidates(raw, roots):
        if candidate.exists():
            return RefResult(raw=raw, exists=True, resolved=candidate, hint=how)
        ci = _find_case_insensitive(candidate)
        if ci is not None and ci.exists():
            return RefResult(
                raw=raw,
                exists=False,
                resolved=ci,
                hint=f"case-mismatch vs {candidate} (actual: {ci})",
            )

    return RefResult(raw=raw, exists=False, resolved=None, hint="not found")


def _resolve_next_to_mdl(raw: str, mdl_dir: Path) -> MdlLocalResult:
    # MDL resources like "./Textures/foo.png" are typically resolved relative to the
    # MDL module file directory.
    raw_norm = raw
    if raw_norm.startswith("./"):
        raw_norm = raw_norm[2:]
    expected = (mdl_dir / raw_norm).resolve()
    return MdlLocalResult(raw=raw, exists_next_to_mdl=expected.exists(), expected=expected)


def _locate_mdl(out_dir: Path, mdl_rel: str) -> Path:
    mdl_rel = mdl_rel.lstrip("/")
    candidates = [out_dir / mdl_rel]

    # Also try flipping Materials/materials if user passed one.
    parts = Path(mdl_rel).parts
    if parts:
        if parts[0] == "Materials":
            candidates.append(out_dir / "materials" / Path(*parts[1:]))
        elif parts[0] == "materials":
            candidates.append(out_dir / "Materials" / Path(*parts[1:]))

    for c in candidates:
        if c.exists():
            return c

    raise FileNotFoundError(f"MDL not found. Tried: {', '.join(str(c) for c in candidates)}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", required=True, help="Packaged output directory (e.g. /path/to/out_dir)")
    ap.add_argument("--mdl", required=True, help="MDL path relative to out-dir (e.g. Materials/Num....mdl)")
    args = ap.parse_args()

    out_dir = Path(args.out_dir).resolve()
    mdl_file = _locate_mdl(out_dir, args.mdl)

    print("OUT_DIR:", out_dir)
    print("MDL_FILE:", mdl_file)

    text = mdl_file.read_text(encoding="utf-8", errors="replace")
    refs = _scan_mdl_for_strings(text)

    if not refs:
        print("No texture-like string references found inside MDL.")
        return 0

    roots = _candidate_search_roots(out_dir, mdl_file.parent)
    print("Search roots:")
    for r in roots:
        print("  ", r)

    # Deduplicate while keeping order
    seen = set()
    refs_unique: List[str] = []
    for r in refs:
        if r in seen:
            continue
        seen.add(r)
        refs_unique.append(r)

    local_results = [_resolve_next_to_mdl(r, mdl_file.parent) for r in refs_unique]
    results = [_resolve_ref(r, roots) for r in refs_unique]

    missing = [x for x in results if not x.exists]
    found = [x for x in results if x.exists]

    local_missing = [x for x in local_results if not x.exists_next_to_mdl]

    print(f"Found {len(found)} referenced files (somewhere in pack), missing {len(missing)}.")
    print(f"Missing next to MDL (MDL-dir relative): {len(local_missing)}.")

    if local_missing:
        print("\nMISSING NEXT TO MDL (likely MDL resource-resolution issue):")
        for x in local_missing:
            print("  ", x.raw)
            print("     expected:", x.expected)

    if found:
        print("\nFOUND:")
        for x in found[:50]:
            print("  ", x.raw, "->", x.resolved)
        if len(found) > 50:
            print(f"  ... ({len(found)-50} more)")

    if missing:
        print("\nMISSING / SUSPICIOUS:")
        for x in missing:
            print("  ", x.raw, "->", x.hint)
            if x.resolved is not None:
                print("     candidate:", x.resolved)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
