from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional, Tuple

REMOTE_PREFIXES = ("omniverse://", "http://", "https://", "s3://")
UDIM_TOKEN = "<UDIM>"
UDIM_RE = re.compile(r"1\d{3}")


def is_remote(path: str) -> bool:
    return any(path.startswith(prefix) for prefix in REMOTE_PREFIXES)


def is_udim_path(path: str) -> bool:
    return UDIM_TOKEN in path or bool(UDIM_RE.search(Path(path).name))


def resolve_with_layer(layer_path: str, asset_path: str) -> Optional[str]:
    """将 USD 中的 asset path 解析为本地绝对路径。

    - 以 layer 所在目录为基准处理相对路径。
    - 远程路径直接返回 None，交由上层处理。
    """

    if not asset_path:
        return None
    if is_remote(asset_path):
        return None
    # Sdf.AssetPath 可能带有 assetPath 和 resolvedPath，这里仅做文件存在性检查。
    base_dir = Path(layer_path).parent
    candidate = (base_dir / asset_path).expanduser().resolve()
    if candidate.exists():
        return str(candidate)
    # 如果 asset_path 已是绝对路径
    abs_candidate = Path(asset_path).expanduser()
    if abs_candidate.exists():
        return str(abs_candidate.resolve())
    return None


def compute_relative(from_path: Path, to_path: Path) -> str:
    """计算 from_path 所在目录到目标的相对路径。"""

    return os.path.relpath(to_path, start=from_path.parent)


def udim_tiles(path_with_udim: str) -> Tuple[str, list[str]]:
    """给定包含 <UDIM> 的路径，扫描同目录下符合 1xxx 的 tile。

    返回 (pattern_dir, tiles)。若目录不存在或无匹配，tiles 为空。
    """

    p = Path(path_with_udim)
    directory = p.parent
    tiles: list[str] = []
    if not directory.exists():
        return str(directory), tiles
    prefix = p.name.replace(UDIM_TOKEN, "")
    for file in directory.iterdir():
        if file.is_file() and prefix in file.name and UDIM_RE.search(file.name):
            tiles.append(str(file))
    return str(directory), sorted(tiles)
