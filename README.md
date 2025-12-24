# USD 资产同目录自包含打包器

面向 Isaac Sim / Omniverse 的 USD 资产自包含打包工具，解决 UI 打开 USD 时纹理 / MDL 丢失、反复手动 export `MDL_SYSTEM_PATH` 的痛点。所有 Python 调用必须通过 scripts/isaac_python.sh 使用 Isaac 自带的 Python 环境运行。

## 功能要点
- 递归扫描 layer / references / payload / subLayers / 材质网络（UsdShade 纹理、MDL shader）。
- 复制并归拢：纹理至 out_dir/textures，MDL 至 out_dir/materials，可选复制子 USD/GLB 到 out_dir/assets（GLB 自动转换为 USD）。
- 路径重写：基于每个 layer 目录改写为相对路径，最大化脱离全局环境变量；记录 before/after。
- MDL 兜底：生成 out_dir/env/mdl_paths.env 供启动脚本 export；提供一键脚本启动 Isaac Sim 并打开打包结果。
- Dry-run 支持：仅扫描并输出报告，不复制/改写。

## 环境要求
- 运行于 Isaac Sim Docker 或 Standalone，确保可 `import pxr`。
- 所有命令通过 [scripts/isaac_python.sh](scripts/isaac_python.sh) 调用。

## 快速开始
假设源场景 `scene.usd`，输出目录 `out_dir`：

- Dry-run（仅扫描 + 报告）：
  - `./scripts/isaac_python.sh -m usd_asset_packager --input scene.usd --out out_dir --dry-run`
- 实际打包并复制子 USD：
  - `./scripts/isaac_python.sh -m usd_asset_packager --input scene.usd --out out_dir --copy-usd-deps`
- 打开打包结果（自动 export MDL_SYSTEM_PATH）：
  - `./scripts/open_in_isaac_ui.sh out_dir/scene.usd`

## 为什么以前要 export MDL_SYSTEM_PATH？
- MDL 查找依赖全局搜索路径（MDL_SYSTEM_PATH / MDL_SEARCH_PATH）。UI 进程启动后再 export 无效，因此需要在启动前设置。
- 纯粹改 USD 无法改变 UI 已启动进程的环境；因此我们提供启动脚本确保进程自带搜索路径。

## 我们的改进与仍可能失败的情形
- 改进：
  - 纹理改为相对路径，随包分发，无需远程路径或全局变量。
  - 可定位的 .mdl 与其贴图一并复制到 materials/ 与 textures/。
  - 生成 env/mdl_paths.env，提供 [scripts/launch_isaac_with_env.sh](scripts/launch_isaac_with_env.sh) + [scripts/open_in_isaac_ui.sh](scripts/open_in_isaac_ui.sh) 一键启动。
- 可能失败/需要人工介入：
  - 仅有 MDL module 名称、未找到物理 .mdl 文件时，仍需 MDL_SEARCH_PATH/MDL_SYSTEM_PATH 或手工 distill。
  - 远程 omniverse:// / http(s):// / s3:// 默认不下载；需手动同步或调整。
  - UDIM 模式仅处理 `<UDIM>` 自动扫描；复杂命名需人工检查。
  - SimReady/OmniPBR 内置库版本差异可能导致材质不一致。

## 目录结构
- [scripts/isaac_python.sh](scripts/isaac_python.sh) Isaac Python 入口包装器（请勿修改）。
- [scripts/pack_usd.py](scripts/pack_usd.py) 模块式入口，等价 `-m usd_asset_packager`。
- [scripts/launch_isaac_with_env.sh](scripts/launch_isaac_with_env.sh) 启动 Isaac 并自动加载 env/mdl_paths.env。
- [scripts/open_in_isaac_ui.sh](scripts/open_in_isaac_ui.sh) 启动 Isaac UI 并打开指定 USD。
- [src/usd_asset_packager](src/usd_asset_packager) 核心代码：扫描、复制、改写、报告。

## 运行细节
- 报告输出：out_dir/report.json，包含统计、每项状态、需要的 MDL 搜索路径建议、为何 UI 仍需带环境变量的说明。
- 日志：stdout + out_dir/logs/packager.log。
- 碰撞策略：
  - keep_tree（默认）：尽量保持原始目录结构。
  - hash_prefix：文件名前加 hash 防重名。
- Flatten 选项：none（默认）；layerstack/full 会在打包后把场景打平成单一 USD（仍外部引用纹理）。

## 示例工作流
1) 预检查：
   - `./scripts/isaac_python.sh -m usd_asset_packager --input scene.usd --out out_dir --dry-run`
2) 正式打包：
   - `./scripts/isaac_python.sh -m usd_asset_packager --input scene.usd --out out_dir --copy-usd-deps`
3) 使用 UI 验证：
   - `./scripts/open_in_isaac_ui.sh out_dir/scene.usd`

## 附加说明
- 若不通过启动脚本而直接双击打开 Isaac UI，则无法自动注入 MDL 搜索路径，请手动 export 或使用生成的 env/mdl_paths.env。
- 发现未处理的路径或报错，请查看 out_dir/report.json 和 out_dir/logs/packager.log。
