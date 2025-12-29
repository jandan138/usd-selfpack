# 核心业务流程与数据流

版本：v0.1  
日期：2025-12-29  
仓库提交：cc49b659b2321811499a6a92102fd53954839959

## 流程概述
- 打开 Stage（Usd.Stage.Open）→ 获取 layerStack/usedLayers
- 扫描资产引用（attributes/references/payloads/MDL imports/resources）
- 复制/分桶资产（textures/materials/usd/glb）并进行 GLB→USD 转换
- 改写路径（subLayerPaths、references/payloads、Sdf.AssetPath 列表/标量）
- 导出新 layer 树，生成报告与 env（可选 flatten）

## 数据结构（关键字段）
- AssetRef（见 [types.py](file:///shared/smartbot/zzh/my_dev/usd-selfpack/src/usd_asset_packager/types.py#L8-L21)）
  - asset_type, original_path, resolved_path, layer_identifier, prim_path, attr_name, is_remote, is_udim
- CopyAction（见 [types.py](file:///shared/smartbot/zzh/my_dev/usd-selfpack/src/usd_asset_packager/types.py#L23-L31)）
  - asset（AssetRef）, target_path, success, reason
- RewriteAction（见 [types.py](file:///shared/smartbot/zzh/my_dev/usd-selfpack/src/usd_asset_packager/types.py#L33-L44)）
  - layer_identifier, prim_path, attr_name, before, after, success, reason
- PackReport（见 [types.py](file:///shared/smartbot/zzh/my_dev/usd-selfpack/src/usd_asset_packager/types.py#L46-L121)）
  - assets, copies, rewrites, stats, mdl_paths, warnings

## 关键处理逻辑
- 扫描（[scan.py](file:///shared/smartbot/zzh/my_dev/usd-selfpack/src/usd_asset_packager/scan.py)）
  - subLayerPaths、references/payloads（兼容 listOp 差异）
  - 资产属性（Sdf.AssetPath / 列表）
  - MDL imports/resources（同目录 .mdl/.png 等补齐）
  - usedLayers（确保 --copy-usd-deps 可本地化外部 layer）
- 复制与分桶（[copy_utils.py](file:///shared/smartbot/zzh/my_dev/usd-selfpack/src/usd_asset_packager/copy_utils.py)）
  - MDL/Textures 按“源目录哈希”同桶，保证 `using .::` 相对依赖可解析
  - GLB/GLTF 目标改写为 `.usd`，通过 omni.kit.asset_converter 转换
- 改写（[rewrite.py](file:///shared/smartbot/zzh/my_dev/usd-selfpack/src/usd_asset_packager/rewrite.py)）
  - subLayerPaths 相对改写
  - references/payloads listOp 替换指定 assetPath
  - 普通属性 AssetPath/AssetPath[] 改写
  - 导出新 layer；对 copied USD deps 进行“就地改写”（需 --copy-usd-deps）
- 报告与环境（[report.py](file:///shared/smartbot/zzh/my_dev/usd-selfpack/src/usd_asset_packager/report.py)、[mdl.py](file:///shared/smartbot/zzh/my_dev/usd-selfpack/src/usd_asset_packager/mdl.py)）
  - 统计与失败原因归档、MDL 搜索路径生成 env/mdl_paths.env

## 证据索引（来源于调试记录）
- MDL 相对路径/模块名问题与修复：[2025-12-25_045230-fix-mdl-sourceasset/report.md](file:///shared/smartbot/zzh/my_dev/usd-selfpack/docs/debug_sessions/2025-12-25_045230-fix-mdl-sourceasset/report.md)
- MDL 分桶与 alias 策略：见 [README.md 功能说明](file:///shared/smartbot/zzh/my_dev/usd-selfpack/README.md#L31-L40)
- 业务验证脚本与差异分析：[2025-12-25_prim-verify-and-render-diff/index.md](file:///shared/smartbot/zzh/my_dev/usd-selfpack/docs/debug_sessions/2025-12-25_prim-verify-and-render-diff/index.md)
