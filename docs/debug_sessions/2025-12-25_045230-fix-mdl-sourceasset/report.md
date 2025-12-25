# 修复记录：MDL `info:mdl:sourceAsset` 相对路径导致材质红/编译失败

时间戳：2025-12-25 04:52:30

## 结论（TL;DR）
- 根因：`info:mdl:sourceAsset` 这类字段多数**写在被 reference 的 USD 依赖层**里；我们之前只 rewrite 了 root layer stack，没有 rewrite 这些 copied USD deps，导致它们仍然包含 `../../Materials/*.mdl`，进而让 neuraylib 解析出非法模块名 `::..::..::Materials::*` 并失败。
- 修复：在打包阶段对 copied USD deps（输出的 `assets/*.usd`）再做一次“layer 文件就地改写”，把 `info:mdl:sourceAsset` 改成 basename（`X.mdl`），让 neuraylib 通过 `MDL_SEARCH_PATH` 在 `materials/` 下找到模块。
- 结果：离屏渲染触发 MDL 编译后，不再出现 `C120 could not find module` / `USD_MDL Invalid` / `Empty identifier`，材质正常显示。

## 复现与证据
### 复现方式（强制触发编译）
- 使用 [scripts/render_one_frame.py](../../scripts/render_one_frame.py) 离屏渲染来触发材质/MDL 编译（仅打开 stage 不一定会触发）。

### 典型错误链（修复前）
- neuraylib：`MDLC:COMPILER ... C120 could not find module '::..::..::Materials::DayMaterial'`
- USD_MDL：`'../../Materials/DayMaterial.mdl' is Invalid`
- Hydra：`Failed to create MDL shade node ... Empty identifier: ''`

### 静态验证点
- 抽查 shader prim 的属性：`info:mdl:sourceAsset` 不应再包含 `..`，应为 `DayMaterial.mdl` / `Num595....mdl` 这种 basename。

## 根因分析（为什么之前的 rewrite 没生效）
- `rewrite_layers(stage, ...)` 只处理 `stage.GetLayerStack()` 里的 layer。
- 但 `--copy-usd-deps` 复制出来的依赖 USD（例如输出到 `output/.../assets/*.usd`）往往不属于 root stage 的 layer stack，它们只是被 root layer 通过 references/payload 引入。
- 因此这些文件虽被复制，但其中的 `info:mdl:sourceAsset` / 贴图路径等仍保持原样，没有经过 rewrite。

## 修复方案（设计思路）
1. 保持最小改动：不改变 scan 的数据结构，也不引入复杂的“重新 compose stage”流程。
2. 在拷贝完成后，对输出目录中的每个 copied USD layer 文件做一次“就地改写 asset path”：
   - 使用 `pxr.UsdUtils.ModifyAssetPaths(layer, callback)`，它会遍历该 layer 文件里所有 authored asset path。
3. 对 `info:mdl:sourceAsset` 采用特殊规则：
   - 只要它对应的是 `.mdl` 文件，就把 `../../Materials/X.mdl` 改成 `X.mdl`（basename），避免 neuraylib 生成 `::..::..::Materials::X`。

## 实现细节（代码改动）
### 1) 新增：对单个 layer 文件就地改写
- 文件： [src/usd_asset_packager/rewrite.py](../../src/usd_asset_packager/rewrite.py)
- 新增函数：`rewrite_layer_file_asset_paths(layer_path, replacements, logger)`
  - `replacements` 是 `{old_asset_path_str: new_asset_path_str}` 的映射
  - 调用 `UsdUtils.ModifyAssetPaths()` 并 `layer.Save()`

### 2) packager 追加一步：rewrite copied USD deps
- 文件： [src/usd_asset_packager/packager.py](../../src/usd_asset_packager/packager.py)
- 当 `copy_usd_deps=True`：
  - 遍历 copy 成功的 USD deps（输出 `assets/*.usd`）
  - 针对每个 layer，收集它对应的扫描资产引用，构建 replacements
  - 调用 `rewrite_layer_file_asset_paths()` 修改该输出文件
  - 对 MDL `info:mdl:sourceAsset` 强制改写为 basename

## 验证结果（修复后）
- 输出目录示例：`output/task9_omni_fix_mdl_source_v2`
- 静态抽查（shader prim）：`info:mdl:sourceAsset` 已变为 `AssetPath(Num595... .mdl)`（无 `..`）
- 动态验证（离屏渲染）：
  - grep 关键错误签名（`MDLC:COMPILER|could not find module|Empty identifier|USD_MDL`）无匹配
  - 材质在 Isaac 中已可正常显示

## 仍未解决/后续工作（独立问题）
- 仍存在大量 `instance.usd` 引用缺失/无法打开的问题（与 MDL 红材质链条不同）。
- 建议后续单独追：scan 是否覆盖到这些 `output/models/.../instance.usd` 依赖、以及 copy/rewrite 的目标路径策略是否一致。
