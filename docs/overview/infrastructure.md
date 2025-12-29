# 基础设施拓扑与环境说明

版本：v0.1  
日期：2025-12-29  
仓库提交：cc49b659b2321811499a6a92102fd53954839959

## 拓扑视图（文字说明）
- 主机环境：Isaac Sim（含 pxr 与 omni 组件）
- 入口脚本：scripts/isaac_python.sh（统一 Python 运行时）
- 打包器：usd_asset_packager（CLI/模块）
- 转换后端：omni.kit.asset_converter（GLB→USD）
- 产物：out_dir/scene.usd、materials/、textures/、assets/、assets_converted_gltf/、env/mdl_paths.env、report.json
- UI 验证：open_in_isaac_ui.sh / launch_isaac_with_env.sh 注入 env 后打开

## 开发 vs 生产环境差异
- 开发：允许 dry-run；可关闭 glTF 转换；不一定启用 --copy-usd-deps；用于快速迭代与验证
- 生产：建议启用 --copy-usd-deps 与 glTF 转换；确保所有引用改写到输出；强制通过脚本注入 env/mdl_paths.env

## 关键依赖与可用性
- Isaac/Omni 组件可用性：UI 日志显示 omni.kit.asset_converter（见证据）可用；若不可用，report.json reason 将提示启用
- USD Resolver：负责 layer/相对路径解析，配合 [resolver.py](file:///shared/smartbot/zzh/my_dev/usd-selfpack/src/usd_asset_packager/resolver.py) 做大小写不敏感解析与 UDIM 扫描

## 扩展性需求与策略
- 资产类型扩展：可在 scan/copy/rewrite 中新增规则与后端
- 环境差异适配：通过 alias/symlink 保持 “Materials/Textures” 与同目录资源期望
- 引用本地化：--copy-usd-deps 打通 referenced/payloaded layer 的二次改写（见 [packager.py](file:///shared/smartbot/zzh/my_dev/usd-selfpack/src/usd_asset_packager/packager.py#L153-L191)）

## 证据索引（来源于调试记录）
- UI 组件版本与可用性：见 [ui_open_packed.log 片段](file:///shared/smartbot/zzh/my_dev/usd-selfpack/docs/debug_sessions/2025-12-26_task9-ui-mdl-red/evidence/ui_open_packed.log#L331-L357)
- MDL 环境注入：见 [README.md](file:///shared/smartbot/zzh/my_dev/usd-selfpack/README.md#L41-L56) 与 [2025-12-25-mdl-materials-packaging/attempts.md](file:///shared/smartbot/zzh/my_dev/usd-selfpack/docs/debug_sessions/2025-12-25-mdl-materials-packaging/attempts.md)
