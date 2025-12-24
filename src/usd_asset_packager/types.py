from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class AssetRef:
    """记录扫描到的资产引用。"""

    asset_type: str  # texture | mdl | usd | glb | other
    original_path: str
    resolved_path: Optional[str]
    layer_identifier: str
    prim_path: str
    attr_name: str
    is_remote: bool = False
    is_udim: bool = False
    notes: str = ""


@dataclass
class CopyAction:
    """描述一次复制行为及结果。"""

    asset: AssetRef
    target_path: Optional[str]
    success: bool
    reason: str = ""


@dataclass
class RewriteAction:
    """描述一次路径改写的前后记录。"""

    layer_identifier: str
    prim_path: str
    attr_name: str
    before: str
    after: str
    success: bool
    reason: str = ""


@dataclass
class PackReport:
    """最终报告。"""

    assets: List[AssetRef] = field(default_factory=list)
    copies: List[CopyAction] = field(default_factory=list)
    rewrites: List[RewriteAction] = field(default_factory=list)
    stats: Dict[str, int] = field(default_factory=dict)
    mdl_paths: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "stats": self.stats,
            "mdl_paths": self.mdl_paths,
            "warnings": self.warnings,
            "assets": [asset.__dict__ for asset in self.assets],
            "copies": [copy.__dict__ for copy in self.copies],
            "rewrites": [rewrite.__dict__ for rewrite in self.rewrites],
        }

    def update_stats(self) -> None:
        counters = {
            "textures": 0,
            "mdls": 0,
            "usd": 0,
            "glb": 0,
            "remote": 0,
            "copy_fail": 0,
            "rewrite_fail": 0,
        }
        for asset in self.assets:
            if asset.asset_type in counters:
                counters[asset.asset_type] += 1
            if asset.is_remote:
                counters["remote"] += 1
        for cp in self.copies:
            if not cp.success:
                counters["copy_fail"] += 1
        for rw in self.rewrites:
            if not rw.success:
                counters["rewrite_fail"] += 1
        self.stats = counters


def ensure_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
