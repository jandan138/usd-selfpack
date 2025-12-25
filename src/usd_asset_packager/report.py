from __future__ import annotations

import json
import os
from pathlib import Path
from typing import List

from .types import PackReport


def write_report(report: PackReport, out_dir: Path) -> Path:
    report.update_stats()
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "report.json"
    payload = report.to_dict()
    payload["notes"] = (
        "UI 进程若未在启动前设置 MDL_SYSTEM_PATH/MDL_SEARCH_PATH，仍可能无法解析 MDL 模块；"
        "本工具已生成 env/mdl_paths.env 供 scripts/launch_isaac_with_env.sh 使用。"
    )
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def write_mdl_env(mdl_paths: List[str], out_dir: Path) -> Path:
    env_dir = out_dir / "env"
    env_dir.mkdir(parents=True, exist_ok=True)
    env_file = env_dir / "mdl_paths.env"

    def _split_colon_paths(raw: str) -> List[str]:
        parts: List[str] = []
        for part in raw.split(":"):
            part = part.strip()
            if not part:
                continue
            parts.append(part)
        return parts

    def _is_abs_like(p: str) -> bool:
        return p.startswith("/") or p.startswith("//")

    def _dedupe_keep_order(paths: List[str]) -> List[str]:
        seen = set()
        out: List[str] = []
        for p in paths:
            if p in seen:
                continue
            seen.add(p)
            out.append(p)
        return out

    raw_paths = [p for p in mdl_paths if p]

    def _to_abs_path(p: str) -> str:
        # `mdl_paths` may already contain paths relative to the *current working dir*
        # (e.g. "output/foo/materials") or paths relative to `out_dir` (e.g. "materials").
        # Make the env file robust by emitting absolute paths only.
        if _is_abs_like(p):
            return str(Path(p).resolve())
        candidate = Path(p)
        if candidate.exists():
            return str(candidate.resolve())
        return str((out_dir / p).resolve())

    abs_paths = [_to_abs_path(p) for p in raw_paths]

    extra_env = os.environ.get("USD_ASSET_PACKAGER_MDL_EXTRA_PATHS", "")
    extra_paths = _split_colon_paths(extra_env) if extra_env else []

    # Common Isaac Sim install path: keep it if it exists.
    isaac_builtin = "/isaac-sim/materials"
    if Path(isaac_builtin).exists():
        extra_paths = [isaac_builtin, *extra_paths]

    # Prefer absolute paths only to avoid duplicated / malformed entries.
    search_paths = _dedupe_keep_order([*abs_paths, *extra_paths])
    search = ":".join(search_paths)
    content = [
        "# Auto-generated MDL search paths for Isaac Sim",
        "# This file is meant to be sourced by bash (see scripts/launch_isaac_with_env.sh).",
        "# Keep it simple (no shell parameter expansion) so it can also be parsed by Python helpers.",
        f"export MDL_SYSTEM_PATH=\"{search}\"",
        f"export MDL_SEARCH_PATH=\"{search}\"",
    ]
    env_file.write_text("\n".join(content) + "\n", encoding="utf-8")
    return env_file
