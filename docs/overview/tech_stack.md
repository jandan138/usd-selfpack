# 技术栈清单（版本与选型理由）

版本：v0.1  
日期：2025-12-29  
仓库提交：cc49b659b2321811499a6a92102fd53954839959

## 语言与运行时
- Python ≥ 3.10（见 [pyproject.toml](file:///shared/smartbot/zzh/my_dev/usd-selfpack/pyproject.toml#L6)）
- USD/pxr Python 绑定（Usd/UsdShade/Sdf/UsdUtils）

## Isaac/Omni 组件版本（来源于 UI 日志）
- omni.kit.asset_converter 2.8.3（见 [ui_open_packed.log](file:///shared/smartbot/zzh/my_dev/usd-selfpack/docs/debug_sessions/2025-12-26_task9-ui-mdl-red/evidence/ui_open_packed.log#L331)）
- omni.usd 1.12.4（见 [ui_open_packed.log](file:///shared/smartbot/zzh/my_dev/usd-selfpack/docs/debug_sessions/2025-12-26_task9-ui-mdl-red/evidence/ui_open_packed.log#L416)）
- omni.ui 2.26.5（见 [ui_open_packed.log](file:///shared/smartbot/zzh/my_dev/usd-selfpack/docs/debug_sessions/2025-12-26_task9-ui-mdl-red/evidence/ui_open_packed.log#L415)）
- 其他 UI 组件版本详见同日志相邻行（以当前环境为准）

## 项目依赖与可选项
- 必要：Isaac 环境（通过 [scripts/isaac_python.sh](file:///shared/smartbot/zzh/my_dev/usd-selfpack/scripts/isaac_python.sh) 运行）
- 转换后端：优先 omni.kit.asset_converter；可选 fallback gltf2usd（见 [converter.py](file:///shared/smartbot/zzh/my_dev/usd-selfpack/src/usd_asset_packager/converter.py)）
- 开发依赖：pytest（见 [pyproject.toml](file:///shared/smartbot/zzh/my_dev/usd-selfpack/pyproject.toml#L11)）

## 选型理由
- 与 Isaac 渲染路径一致：使用 Omniverse 官方 converter 与 USD API，降低“转换/渲染不一致”风险
- 兼容性：rewrite/listOp 处理兼容不同 USD 绑定字段暴露方式（见 [rewrite.py](file:///shared/smartbot/zzh/my_dev/usd-selfpack/src/usd_asset_packager/rewrite.py#L171-L189)）
- 可降级：在 converter 不可用或不需要时，可关闭或切换 fallback

## 风险点
- UI 组件版本差异导致转换或渲染差异
- 未启用 --copy-usd-deps 时，外部 layer 的引用改写遗漏
- 远程/大小写敏感路径解析失败（通过 [resolver.py](file:///shared/smartbot/zzh/my_dev/usd-selfpack/src/usd_asset_packager/resolver.py) 缓解）

## 证据索引（来源于调试记录）
- 组件版本来源与红材质排查：[2025-12-26_task9-ui-mdl-red/index.md](file:///shared/smartbot/zzh/my_dev/usd-selfpack/docs/debug_sessions/2025-12-26_task9-ui-mdl-red/index.md)
- MDL 搜索路径与 env 生成：[2025-12-25-mdl-materials-packaging/attempts.md](file:///shared/smartbot/zzh/my_dev/usd-selfpack/docs/debug_sessions/2025-12-25-mdl-materials-packaging/attempts.md)
