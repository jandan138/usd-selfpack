# 项目架构（物理部署与逻辑架构）

版本：v0.1  
日期：2025-12-29  
仓库提交：cc49b659b2321811499a6a92102fd53954839959

## 物理部署视图
- 运行环境：Isaac Sim Docker/Standalone（通过 scripts/isaac_python.sh 使用内置 Python/pxr/omni）
- 打包器：CLI 运行 usd_asset_packager（或 scripts/pack_usd.py）
- 转换服务：omni.kit.asset_converter（GLB/GLTF → USD）
- 产物目录：out_dir/scene.usd、materials/、textures/、assets/、assets_converted_gltf/、env/mdl_paths.env、report.json
- UI 验证：scripts/open_in_isaac_ui.sh 或 scripts/launch_isaac_with_env.sh 注入 MDL 搜索路径并打开结果

## 逻辑架构视图
- 总控：[packager.py](file:///shared/smartbot/zzh/my_dev/usd-selfpack/src/usd_asset_packager/packager.py)
- 扫描：[scan.py](file:///shared/smartbot/zzh/my_dev/usd-selfpack/src/usd_asset_packager/scan.py)
- 复制/分桶与转换：[copy_utils.py](file:///shared/smartbot/zzh/my_dev/usd-selfpack/src/usd_asset_packager/copy_utils.py)、[converter.py](file:///shared/smartbot/zzh/my_dev/usd-selfpack/src/usd_asset_packager/converter.py)
- 改写与导出：[rewrite.py](file:///shared/smartbot/zzh/my_dev/usd-selfpack/src/usd_asset_packager/rewrite.py)
- 解析辅助：[resolver.py](file:///shared/smartbot/zzh/my_dev/usd-selfpack/src/usd_asset_packager/resolver.py)
- 报告与环境：[report.py](file:///shared/smartbot/zzh/my_dev/usd-selfpack/src/usd_asset_packager/report.py)、[mdl.py](file:///shared/smartbot/zzh/my_dev/usd-selfpack/src/usd_asset_packager/mdl.py)
- 类型模型：[types.py](file:///shared/smartbot/zzh/my_dev/usd-selfpack/src/usd_asset_packager/types.py)

```
[Isaac Python] --scripts/isaac_python.sh-->
  usd_asset_packager (CLI)
    ├─ packager.py (总控)
    │   ├─ scan.py ──> AssetRef 列表
    │   ├─ copy_utils.py ──> 复制/分桶/GLB转换
    │   │   └─ converter.py (omni/fallback)
    │   ├─ rewrite.py ──> 改写/导出 layer
    │   ├─ report.py + mdl.py ──> report.json / env/mdl_paths.env
    │   └─ resolver.py ──> 路径解析/UDIM
    └─ 输出 out_dir/
        ├─ scene.usd / assets / assets_converted_gltf
        ├─ materials / textures
        ├─ env/mdl_paths.env
        └─ report.json
```

## 模块依赖关系图（简化）
- Packager → Scan、CopyUtils、Rewrite、Report、Mdl、Converter、Resolver
- Scan → Resolver、pxr.Usd/UsdShade/Sdf → 产出 AssetRef 列表（含 MDL import/resource 与 usedLayers）
- CopyUtils → ConverterBackend、Resolver → 复制/分桶/转换生成输出路径与别名
- Rewrite → pxr.Usd/Sdf/UsdUtils → 基于 Copy 结果改写 USD 引用并导出 layer
- Report/Mdl → 汇总统计、生成 env/mdl_paths.env 与 report.json

## 证据索引（来源于调试记录）
- MDL “相对 import 失效→红材质”根因与修复：[2025-12-25_045230-fix-mdl-sourceasset/report.md](file:///shared/smartbot/zzh/my_dev/usd-selfpack/docs/debug_sessions/2025-12-25_045230-fix-mdl-sourceasset/report.md)
- UI 打开红色与证据归档规范：[2025-12-26_task9-ui-mdl-red/index.md](file:///shared/smartbot/zzh/my_dev/usd-selfpack/docs/debug_sessions/2025-12-26_task9-ui-mdl-red/index.md)
- MDL 分桶策略修正（同目录依赖恢复）：[2025-12-29_task9-ui-mdl-red-followup/index.md](file:///shared/smartbot/zzh/my_dev/usd-selfpack/docs/debug_sessions/2025-12-29_task9-ui-mdl-red-followup/index.md)
