from __future__ import annotations

import json
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
    search = ":".join(mdl_paths)
    content = [
        "# Auto-generated MDL search paths for Isaac Sim",
        f"export MDL_SYSTEM_PATH='{search}'",
        f"export MDL_SEARCH_PATH='{search}'",
    ]
    env_file.write_text("\n".join(content) + "\n", encoding="utf-8")
    return env_file
