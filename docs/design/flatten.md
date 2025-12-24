# Flatten 打平（2025-12-24）

目标：生成单一 USD（layerstack 展开），减少对外部 USD/GLB 的依赖，贴图仍以相对路径存在。

策略：
- 开启方式：`--flatten layerstack` 或 `--flatten full`（当前行为相同）。
- 自动启用 `--copy-usd-deps` 以确保子层本地化。
- 打包改写后再执行 `UsdUtils.FlattenLayerStack`，输出 `<root>_flatten.usda`。

关键代码：
- 打平逻辑触发：[src/usd_asset_packager/packager.py](../../src/usd_asset_packager/packager.py)
- 改写后的 layer 导出：[src/usd_asset_packager/rewrite.py](../../src/usd_asset_packager/rewrite.py)

限制：
- 远程/缺失资产仍会失败并记录警告。
- 贴图仍为外部文件，不会内嵌。
- full 模式未来可扩展更多清理/合并策略（目前等同 layerstack）。