# 路径改写逻辑（2025-12-24）

目标：在不改动源文件的前提下，改写复制后的 layer 中的资产路径为相对路径。

实现要点：
- 为每个 layer 计算 out_dir 下的新路径，保持相对结构。
- `references` / `payloads`：更新 listOp 中的 `assetPath`。
- 资产属性：对 `Sdf.AssetPath` 或列表替换为相对路径。
- subLayerPaths 同步改写指向新 layer。
- 改写发生在复制后的 layer 上，最后 `Export` 到 out_dir。

关键代码：
- 改写器：[src/usd_asset_packager/rewrite.py](../../src/usd_asset_packager/rewrite.py)
- 复制规划：路径相对化由 [src/usd_asset_packager/copy_utils.py](../../src/usd_asset_packager/copy_utils.py) 生成目标路径。

注意事项：
- 仅处理已复制资产的相对路径；未复制的远程/缺失资产会被跳过并在 report 中标记。
- 改写后会记录 before/after 以便排查。