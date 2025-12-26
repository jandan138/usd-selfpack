from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Dict, List
import os
import hashlib

from pxr import Usd, UsdUtils

from .converter import make_converter
from .copy_utils import copy_asset
from .mdl import collect_mdl_search_paths, warn_unresolved_mdls
from .report import write_mdl_env, write_report
from .rewrite import rewrite_layer_file_asset_paths, rewrite_layers
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

        if not self.dry_run:
            self._ensure_output_aliases()
            self._ensure_mdl_dir_texture_aliases(copy_actions)

        # 构建新 layer 路径：以输入 USD 所在目录为基准保持树结构
        layer_new_path: Dict[str, Path] = {}
        base_root = self.input_path.parent

        def _hash_prefix(text: str) -> str:
            return hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]

        for layer in stage.GetLayerStack():
            if not layer.realPath:
                continue
            try:
                rel = Path(layer.realPath).resolve().relative_to(base_root.resolve())
            except Exception:
                # Avoid collisions when multiple external layers share the same basename.
                prefix = _hash_prefix(str(Path(layer.realPath).resolve()))
                rel = Path("external_layers") / prefix / Path(layer.realPath).name
            target = self.out_dir / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            layer_new_path[layer.identifier] = target

        # 改写 asset path 并导出 layer 副本
        if not self.dry_run:
            rewrite_actions = rewrite_layers(stage, assets, copy_targets, layer_new_path, self.logger)
            report.rewrites = rewrite_actions
        else:
            self.logger.info("dry-run 不执行 rewrite")

        if not self.dry_run:
            # Ensure each directory containing USD layers has `Materials`/`Textures`
            # aliases, so authored paths like `Materials/foo.mdl` resolve from any
            # nested layer without using "..".
            self._ensure_layer_dir_aliases(layer_new_path)

        # 额外：改写已复制的 USD 依赖文件（references/payload 引入的 layer 不在 root layer stack 里）
        if not self.dry_run and self.copy_usd_deps:
            usd_layer_out: Dict[str, Path] = {}
            for cp in copy_actions:
                if not (cp.success and cp.target_path and cp.asset.asset_type == "usd"):
                    continue
                # resolved_path 是原始绝对路径（最佳键）；同时兼容 original_path 为绝对路径的情况
                if cp.asset.resolved_path:
                    usd_layer_out[cp.asset.resolved_path] = Path(cp.target_path)
                if cp.asset.original_path and cp.asset.original_path.startswith("/"):
                    usd_layer_out[cp.asset.original_path] = Path(cp.target_path)

            # 对每个 copied USD layer，按该 layer 中扫描到的引用构建 replacements，然后用 UsdUtils 修改该文件
            extra_rewrites = 0
            for src_layer_id, out_layer_path in usd_layer_out.items():
                # 仅处理存在于输出的 USD 文件
                if not out_layer_path.exists():
                    continue
                replacements: Dict[str, str] = {}
                for asset in assets:
                    if asset.layer_identifier != src_layer_id:
                        continue
                    if id(asset) not in copy_targets:
                        continue
                    target_abs = copy_targets[id(asset)]
                    rel_path = os.path.relpath(target_abs, start=out_layer_path.parent)
                    # 多个位置可能引用同一路径；保持第一次映射即可
                    replacements.setdefault(asset.original_path, rel_path)

                if not replacements:
                    continue
                changed = rewrite_layer_file_asset_paths(out_layer_path, replacements, self.logger)
                extra_rewrites += changed
                if changed:
                    self.logger.info("rewrote %d asset paths in copied usd layer: %s", changed, out_layer_path)

            if extra_rewrites:
                report.warnings.append(f"rewrote asset paths in copied USD deps: {extra_rewrites}")

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

    def _ensure_mdl_dir_texture_aliases(self, copy_actions: List[CopyAction]) -> None:
        """Ensure each copied MDL directory has a `Textures` alias.

        Many collected MDL files reference resources like "./Textures/foo.png".
        On Linux this can fail if the actual folder is `textures` or if we pack
        textures under `out_dir/textures/...`. We create a per-directory symlink
        `Textures` pointing at the corresponding packed texture subfolder.
        """

        materials_root = self.out_dir / "materials"
        textures_root = self.out_dir / "textures"

        for cp in copy_actions:
            if not (cp.success and cp.target_path and cp.asset.asset_type == "mdl"):
                continue
            try:
                mdl_path = Path(cp.target_path)
                mdl_dir = mdl_path.parent
                rel_dir = mdl_dir.relative_to(materials_root)
            except Exception:
                continue

            # Common upstream layout is <Materials>/textures/*.png
            candidate = textures_root / rel_dir / "textures"
            if not candidate.exists():
                # Fall back to the corresponding directory itself.
                candidate = textures_root / rel_dir
            if not candidate.exists():
                continue

            link = mdl_dir / "Textures"
            if link.exists():
                continue
            try:
                rel_target = os.path.relpath(candidate, start=mdl_dir)
                os.symlink(rel_target, link)
            except Exception as exc:  # noqa: BLE001
                self.logger.debug("failed to create MDL Textures alias %s -> %s: %s", link, candidate, exc)

    def _ensure_output_aliases(self) -> None:
        """Ensure common case/structure aliases exist in output.

        Many upstream assets (USD and MDL) reference folders like 'Materials' and
        'Textures' with specific casing and/or expect a 'Textures' folder next
        to the MDL module. Our packer normalizes to lowercase ('materials',
        'textures'), so we provide symlinks to preserve compatibility.
        """

        materials = self.out_dir / "materials"
        textures = self.out_dir / "textures"

        if materials.exists() and not (self.out_dir / "Materials").exists():
            try:
                os.symlink("materials", self.out_dir / "Materials")
                self.logger.info("created alias: %s -> %s", self.out_dir / "Materials", materials)
            except Exception as exc:  # noqa: BLE001
                self.logger.warning("failed to create Materials alias symlink: %s", exc)

        if textures.exists() and not (self.out_dir / "Textures").exists():
            try:
                os.symlink("textures", self.out_dir / "Textures")
                self.logger.info("created alias: %s -> %s", self.out_dir / "Textures", textures)
            except Exception as exc:  # noqa: BLE001
                self.logger.warning("failed to create Textures alias symlink: %s", exc)

        # MDL modules often reference resources relative to the module dir, e.g. "./Textures/foo.png".
        # Provide a symlink so those resolve to the packed texture directory.
        if materials.exists() and textures.exists():
            mdl_textures = materials / "Textures"
            if not mdl_textures.exists():
                try:
                    os.symlink("../textures", mdl_textures)
                    self.logger.info("created alias: %s -> %s", mdl_textures, textures)
                except Exception as exc:  # noqa: BLE001
                    self.logger.warning("failed to create materials/Textures symlink: %s", exc)

    def _ensure_layer_dir_aliases(self, layer_new_path: Dict[str, Path]) -> None:
        materials = self.out_dir / "materials"
        textures = self.out_dir / "textures"
        if not (materials.exists() and textures.exists()):
            return

        dirs = {p.parent for p in layer_new_path.values()}
        # Also include the directory of copied USD deps (typically assets/*)
        dirs.add((self.out_dir / "assets"))

        for d in sorted(dirs):
            if not d.exists():
                continue
            # Avoid creating self-referential aliases inside the target folders.
            if d == materials or d == textures:
                continue

            try:
                mat_link = d / "Materials"
                if not mat_link.exists():
                    rel = os.path.relpath(materials, start=d)
                    os.symlink(rel, mat_link)
            except Exception as exc:  # noqa: BLE001
                self.logger.debug("failed to create Materials alias in %s: %s", d, exc)

            try:
                tex_link = d / "Textures"
                if not tex_link.exists():
                    rel = os.path.relpath(textures, start=d)
                    os.symlink(rel, tex_link)
            except Exception as exc:  # noqa: BLE001
                self.logger.debug("failed to create Textures alias in %s: %s", d, exc)
