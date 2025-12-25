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
    def _resolve_case_insensitive(base: Path, rel: Path) -> Optional[Path]:
        """Resolve a relative path against base, case-insensitively per segment.

        This helps with upstream assets authored with inconsistent casing (e.g. "Textures" vs "textures")
        when running on Linux.
        """

        cur = base
        for part in rel.parts:
            if part in ("", "."):
                continue
            if part == "..":
                cur = cur.parent
                continue
            # Prefer exact match first.
            exact = cur / part
            if exact.exists():
                cur = exact
                continue
            if not cur.is_dir():
                return None
            try:
                folded = part.casefold()
                match = None
                with os.scandir(cur) as it:
                    for ent in it:
                        if ent.name.casefold() == folded:
                            match = ent.path
                            break
                if match is None:
                    return None
                cur = Path(match)
            except Exception:
                return None
        return cur if cur.exists() else None

    # Sdf.AssetPath 可能带有 assetPath 和 resolvedPath，这里仅做文件存在性检查。
    base_dir = Path(layer_path).parent
    # If asset_path is relative, try direct then case-insensitive.
    if not Path(asset_path).is_absolute():
        try:
            candidate = (base_dir / asset_path).expanduser().resolve()
        except Exception:
            candidate = None
        if candidate and candidate.exists():
            return str(candidate)
        ci = _resolve_case_insensitive(base_dir, Path(asset_path))
        if ci and ci.exists():
            return str(ci.resolve())
    else:
        candidate = Path(asset_path).expanduser()
        if candidate.exists():
            return str(candidate.resolve())
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
