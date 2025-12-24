from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path
from typing import Tuple


def _find_usd_from_gltf() -> str | None:
    """查找 usd_from_gltf 可执行，优先使用 PATH。

    Isaac/Omniverse 通常自带该工具，若找不到则返回 None。
    """

    return shutil.which("usd_from_gltf")


def convert_glb_to_usd(src: Path, dst: Path, logger: logging.Logger) -> Tuple[bool, str]:
    """将 glb/gltf 转换为 usd/usda。

    优先尝试 usd_from_gltf；若缺失则返回失败并提示人工介入。
    """

    tool = _find_usd_from_gltf()
    if not tool:
        return False, "usd_from_gltf not found; please install or expose in PATH"

    dst.parent.mkdir(parents=True, exist_ok=True)
    cmd = [tool, str(src), str(dst)]
    try:
        proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    except Exception as exc:  # noqa: BLE001
        return False, f"launch failed: {exc}"

    if proc.returncode != 0:
        logger.error("usd_from_gltf failed (%s): %s", proc.returncode, proc.stderr.strip())
        return False, proc.stderr.strip() or "usd_from_gltf failed"

    logger.info("converted GLB -> USD: %s -> %s", src, dst)
    return True, "converted"
