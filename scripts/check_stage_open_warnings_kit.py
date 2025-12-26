from __future__ import annotations

import argparse
import json
import os
import re
import shutil
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


def _as_posix(p: str) -> str:
    return p.replace("\\", "/")


def _load_env_file(env_path: str) -> None:
    """Load a simple `export KEY=VALUE` env file into os.environ.

    Must be called BEFORE SimulationApp is created.
    """

    path = Path(env_path)
    if not path.is_file():
        raise FileNotFoundError(env_path)

    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
            value = value[1:-1]
        os.environ[key] = value


@dataclass(frozen=True)
class Pattern:
    name: str
    regex: re.Pattern[str]


_DEFAULT_PATTERNS: list[Pattern] = [
    Pattern("could_not_open_asset", re.compile(r"Could not open asset", re.IGNORECASE)),
    Pattern("failed_to_open_layer", re.compile(r"Failed to open layer", re.IGNORECASE)),
    Pattern("could_not_resolve", re.compile(r"Could not resolve|Cannot resolve", re.IGNORECASE)),
    Pattern("cant_find", re.compile(r"can't be found|cannot be found|could not find", re.IGNORECASE)),
    # Include common MDL translator/compile signatures (not strictly stage-open, but useful in same pass).
    Pattern("usd_to_mdl", re.compile(r"UsdToMdl", re.IGNORECASE)),
    Pattern("mdl_compiler", re.compile(r"MDLC:COMPILER", re.IGNORECASE)),
]


_QUOTED = re.compile(r"['\"]([^'\"]+)['\"]")


def _extract_candidate_paths(line: str) -> list[str]:
    # Heuristic: grab quoted substrings that look like paths or URIs.
    cands: list[str] = []
    for s in _QUOTED.findall(line):
        s2 = s.strip()
        if not s2:
            continue
        if "://" in s2 or s2.startswith("/") or s2.startswith("."):
            cands.append(_as_posix(s2))
            continue
        # Windows drive
        if re.match(r"^[a-zA-Z]:\\", s2):
            cands.append(_as_posix(s2))
            continue
        # file-ish extensions
        if re.search(r"\.(usd|usda|usdc|usdz|mdl|png|jpg|jpeg|tga|exr|hdr|dds)\b", s2, re.IGNORECASE):
            cands.append(_as_posix(s2))
    return cands


def _iter_log_lines(path: Path) -> Iterable[str]:
    if not path.is_file():
        return []
    # Kit logs can have odd encodings; be permissive.
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        yield line


def main() -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Open a USD stage inside Isaac/Kit (SimulationApp), capture Kit log output, and produce a structured JSON "
            "summary of missing-asset / resolve warnings during stage open."
        )
    )
    ap.add_argument("--usd", required=True, help="Path to USD file")
    ap.add_argument(
        "--env",
        default=None,
        help="Optional env file to source (e.g. <out>/env/mdl_paths.env). Loaded before Kit starts.",
    )
    ap.add_argument(
        "--out-dir",
        default=None,
        help="Output directory (defaults to <usd_dir>/logs/open_warnings_kit)",
    )
    ap.add_argument("--out", default=None, help="Write JSON report to this path (defaults to <out-dir>/open_warnings.json)")
    ap.add_argument(
        "--kit-log",
        default=None,
        help="Force Kit to write its log to this file (defaults to <out-dir>/kit_open.log)",
    )
    ap.add_argument("--warmup-frames", type=int, default=120, help="Number of SimulationApp.update() calls after open_stage")
    ap.add_argument("--max-examples", type=int, default=50)
    args = ap.parse_args()

    usd_path = Path(args.usd)
    if not usd_path.is_file():
        raise SystemExit(f"USD not found: {usd_path}")

    if args.env:
        _load_env_file(args.env)

    out_dir = Path(args.out_dir) if args.out_dir else (usd_path.parent / "logs" / "open_warnings_kit")
    out_dir = out_dir.expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    kit_log_path = Path(args.kit_log).expanduser().resolve() if args.kit_log else (out_dir / "kit_open.log")
    out_json_path = Path(args.out).expanduser().resolve() if args.out else (out_dir / "open_warnings.json")

    # Launch Kit
    from omni.isaac.kit import SimulationApp

    simulation_app = SimulationApp({"headless": True})

    try:
        import carb
        import carb.settings
        import omni.usd

        settings = carb.settings.get_settings()
        # Kit typically chooses a log file very early. Capture the actual active log path first.
        active_log_raw_before = None
        try:
            active_log_raw_before = settings.get("/log/file")
        except Exception:
            active_log_raw_before = None
        active_log_path_before = (
            Path(str(active_log_raw_before)).expanduser().resolve() if active_log_raw_before else None
        )

        # Make sure we have a sane log level.
        try:
            settings.set("/log/level", "Info")
        except Exception:
            pass

        # We intentionally do NOT rely on changing `/log/file` (often too late). Instead we copy
        # whatever Kit is actually using into `kit_log_path` at the end.
        active_log_path = active_log_path_before

        ctx = omni.usd.get_context()
        ctx.open_stage(str(usd_path.resolve()))

        # Let stage load and logs flush.
        for _ in range(max(1, int(args.warmup_frames))):
            simulation_app.update()

        stage = ctx.get_stage()
        if stage is None:
            raise RuntimeError("Stage failed to open (ctx.get_stage() is None)")

        # A couple more updates for late warnings.
        for _ in range(10):
            simulation_app.update()

        prim_count = sum(1 for _ in stage.TraverseAll())

        # Determine which log file to parse.
        parse_log_path = active_log_path if active_log_path and active_log_path.is_file() else None

        # Parse Kit log (do this BEFORE closing SimulationApp; close() may hard-exit the process).
        counts: Counter[str] = Counter()
        unique_paths_by_category: dict[str, set[str]] = defaultdict(set)
        example_lines: dict[str, list[str]] = defaultdict(list)

        for line in _iter_log_lines(parse_log_path) if parse_log_path else []:
            matched_any = False
            for pat in _DEFAULT_PATTERNS:
                if not pat.regex.search(line):
                    continue
                matched_any = True
                counts[pat.name] += 1
                for p in _extract_candidate_paths(line):
                    unique_paths_by_category[pat.name].add(p)
                if len(example_lines[pat.name]) < args.max_examples:
                    example_lines[pat.name].append(line)
            if not matched_any:
                continue

        # Best-effort: copy the parsed log to out_dir for auditing.
        if parse_log_path and parse_log_path.is_file():
            try:
                if kit_log_path != parse_log_path:
                    shutil.copyfile(parse_log_path, kit_log_path)
            except Exception:
                pass

        report: dict[str, Any] = {
            "usd": _as_posix(str(usd_path.resolve())),
            "env": _as_posix(str(Path(args.env).resolve())) if args.env else None,
            "out_dir": _as_posix(str(out_dir)),
            "kit_log": _as_posix(str(kit_log_path)),
            "kit_log_source": _as_posix(str(parse_log_path)) if parse_log_path else None,
            "prim_count": prim_count,
            "counts_by_category": dict(counts),
            "unique_paths_by_category": {k: sorted(v) for k, v in unique_paths_by_category.items()},
            "examples": example_lines,
        }

        out_json_path.parent.mkdir(parents=True, exist_ok=True)
        out_json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

        # Human-friendly summary
        def _fmt(counter: dict[str, int]) -> str:
            if not counter:
                return "(none)"
            return ", ".join(f"{k}={v}" for k, v in sorted(counter.items(), key=lambda kv: kv[0]))

        print(f"USD: {report['usd']}")
        print(f"prim_count: {report['prim_count']}")
        print(f"kit_log: {report['kit_log']}")
        print("counts_by_category:", _fmt(report["counts_by_category"]))
        print(f"Wrote report: {out_json_path}")

        return 0

    finally:
        simulation_app.close()


if __name__ == "__main__":
    raise SystemExit(main())
