# 扫描逻辑（2025-12-24）

目标：收集 USD 依赖（layer、references、payloads）、材质贴图、MDL、GLB 资产。

实现要点：
- 遍历 layer stack 的 `subLayerPaths`。
- 对所有 prim 扫描 `references` 与 `payloads` 的 listOp。
- 遍历属性，捕获 `Sdf.AssetPath` / `list[Sdf.AssetPath]`。
- 识别类型：USD/MDL/Texture/GLB 通过后缀与 Shader Id 判断。
- 标记远程路径（omniverse/http/https/s3）与 UDIM。

关键代码：
- 扫描入口：[src/usd_asset_packager/scan.py](../../src/usd_asset_packager/scan.py)
- 解析/分类工具：[src/usd_asset_packager/resolver.py](../../src/usd_asset_packager/resolver.py)
- 数据结构：[src/usd_asset_packager/types.py](../../src/usd_asset_packager/types.py)

扩展点：
- 可增加对 clip、asset 节点的特定识别。
- 远程资源目前只记录不下载，必要时可在此处挂接下载逻辑。