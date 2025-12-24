from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Dict, List

from pxr import Usd, UsdUtils

from .converter import make_converter
from .copy_utils import copy_asset
from .mdl import collect_mdl_search_paths, warn_unresolved_mdls
from .report import write_mdl_env, write_report
from .rewrite import rewrite_layers
from .scan import scan_stage
from .types import AssetRef, CopyAction, PackReport


class Packager:
    """主业务流程：扫描 -> 复制 -> 改写 -> 报告。"""

    def __init__(
        self,
        input_path: Path,
        out_dir: Path,
        mode: str = "self_contained",
        copy_usd_deps: bool = False,
        dry_run: bool = False,
        collision_strategy: str = "keep_tree",
        flatten: str = "none",
        log_level: str = "INFO",
        convert_gltf: bool = True,
        converter: str = "omni",
    ) -> None:
        self.input_path = input_path
        self.out_dir = out_dir
        self.mode = mode
        self.copy_usd_deps = copy_usd_deps
        self.dry_run = dry_run
        self.collision_strategy = collision_strategy
        self.flatten = flatten
        self.convert_gltf = convert_gltf
        self.converter = converter
        self.logger = self._setup_logging(log_level)

    def _setup_logging(self, level: str) -> logging.Logger:
        log_dir = self.out_dir / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        logger = logging.getLogger("usd_asset_packager")
        logger.setLevel(getattr(logging, level.upper(), logging.INFO))
        fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
        if not logger.handlers:
            fh = logging.FileHandler(log_dir / "packager.log", encoding="utf-8")
            fh.setFormatter(fmt)
            logger.addHandler(fh)
            sh = logging.StreamHandler(sys.stdout)
            sh.setFormatter(fmt)
            logger.addHandler(sh)
        return logger

    def run(self) -> PackReport:
        self.out_dir.mkdir(parents=True, exist_ok=True)
        if self.flatten != "none":
            if not self.copy_usd_deps:
                self.logger.info("flatten 需要本地化引用，自动启用 copy_usd_deps")
            # flatten 需要完整资产树
            self.copy_usd_deps = True

        # 通过 Usd.Stage.Open 打开场景，利用 USD resolver
        stage = Usd.Stage.Open(str(self.input_path))
        if not stage:
            raise RuntimeError(f"无法打开 {self.input_path}")

        report = PackReport()

        assets = scan_stage(stage, self.logger)
        report.assets = assets

        # 记录 layer 真实路径，供相对解析
        layer_real_map: Dict[str, str] = {}
        for layer in stage.GetLayerStack():
            if layer.realPath:
                layer_real_map[layer.identifier] = layer.realPath

        warnings = warn_unresolved_mdls(assets, self.logger)
        report.warnings.extend(warnings)

        copy_actions: List[CopyAction] = []
        copy_targets: Dict[int, str] = {}

        if not self.dry_run:
            base_root = self.input_path.parent
            converter_backend = make_converter(self.converter, self.logger) if self.convert_gltf else None
            for asset in assets:
                if asset.asset_type in ("texture", "mdl"):
                    action = copy_asset(asset, self.out_dir, self.collision_strategy, base_root, layer_real_map,
                                        self.logger, converter_backend, self.convert_gltf)
                elif asset.asset_type == "glb":
                    # glb 必须转换为 usd 才能参与 rewrite/flatten
                    action = copy_asset(asset, self.out_dir, self.collision_strategy, base_root, layer_real_map,
                                        self.logger, converter_backend, self.convert_gltf)
                elif asset.asset_type == "usd" and self.copy_usd_deps:
                    action = copy_asset(asset, self.out_dir, self.collision_strategy, base_root, layer_real_map,
                                        self.logger, converter_backend, self.convert_gltf)
                else:
                    action = CopyAction(asset=asset, target_path=None, success=False, reason="copy skipped")
                copy_actions.append(action)
                if action.success and action.target_path:
                    copy_targets[id(asset)] = action.target_path
            report.copies = copy_actions
        else:
            self.logger.info("dry-run 模式：不复制文件、不改写 USD")

        # 构建新 layer 路径：以输入 USD 所在目录为基准保持树结构
        layer_new_path: Dict[str, Path] = {}
        base_root = self.input_path.parent
        for layer in stage.GetLayerStack():
            if not layer.realPath:
                continue
            try:
                rel = Path(layer.realPath).resolve().relative_to(base_root.resolve())
            except Exception:
                rel = Path(layer.realPath).name
            target = self.out_dir / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            layer_new_path[layer.identifier] = target

        # 改写 asset path 并导出 layer 副本
        if not self.dry_run:
            rewrite_actions = rewrite_layers(stage, assets, copy_targets, layer_new_path, self.logger)
            report.rewrites = rewrite_actions
        else:
            self.logger.info("dry-run 不执行 rewrite")

        # flatten 层级：将改写后的 root 打平成单一 layer（纹理仍为外部相对路径）
        if not self.dry_run and self.flatten != "none":
            root_layer_path = layer_new_path.get(stage.GetRootLayer().identifier)
            if root_layer_path:
                flat_path = root_layer_path.with_name(root_layer_path.stem + "_flatten.usd")
                try:
                    packaged_stage = Usd.Stage.Open(str(root_layer_path))
                    flat_layer = UsdUtils.FlattenLayerStack(packaged_stage)
                    flat_layer.Export(str(flat_path))
                    self.logger.info("flattened stage -> %s", flat_path)
                except Exception as exc:  # noqa: BLE001
                    self.logger.error("flatten failed: %s", exc)
                    report.warnings.append(f"flatten failed: {exc}")
            else:
                self.logger.warning("无法定位 root layer 以进行 flatten")

        # MDL 搜索路径建议：来自成功复制的 MDL 文件目录
        mdl_copied = [cp.target_path for cp in copy_actions if cp.asset.asset_type == "mdl" and cp.success and cp.target_path]
        report.mdl_paths = collect_mdl_search_paths(mdl_copied)
        if not self.dry_run:
            write_mdl_env(report.mdl_paths, self.out_dir)

        write_report(report, self.out_dir)
        self.logger.info("packaging finished; report at %s", self.out_dir / "report.json")
        return report
