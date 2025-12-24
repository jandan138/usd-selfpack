from __future__ import annotations

import logging
from pathlib import Path
from typing import List

from .types import AssetRef


def collect_mdl_search_paths(copies: List[str]) -> List[str]:
    paths = []
    for cp in copies:
        parent = Path(cp).parent
        if str(parent) not in paths:
            paths.append(str(parent))
    return paths


def warn_unresolved_mdls(assets: List[AssetRef], logger: logging.Logger) -> List[str]:
    warnings: List[str] = []
    for asset in assets:
        if asset.asset_type != "mdl":
            continue
        if asset.is_remote:
            warnings.append(f"MDL remote {asset.original_path} 未复制，需手动提供搜索路径")
        elif not asset.resolved_path:
            warnings.append(f"MDL {asset.original_path} 未解析到物理文件，可能需要 MDL_SYSTEM_PATH/MDL_SEARCH_PATH")
    for msg in warnings:
        logger.warning(msg)
    return warnings
