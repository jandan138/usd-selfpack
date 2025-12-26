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

### 外部 layer（不在 base_root 下）的路径规划

当某个 USD layer 的真实路径无法相对化到 base_root 时，不能简单使用 basename 作为输出路径：不同来源可能存在同名 layer（例如大量 `instance.usd`），会在 out_dir 下发生静默覆盖，导致最终 stage 组成结果错误。

当前策略：
- 对这类“外部 layer”使用哈希分桶目录（例如 `external_layers/<hash>/<basename>` 一类），保证不同来源不会互相覆盖。
- 仍会在改写阶段把 sublayer/reference/payload 指向新的相对路径。
