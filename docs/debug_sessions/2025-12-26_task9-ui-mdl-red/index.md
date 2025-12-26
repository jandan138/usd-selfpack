# 2025-12-26 — task9：UI 打开仍大量红色（MDL 报错）排查记录

> 背景：已完成对 `scene_flattened_simready.usd` 的打包输出，但在 Isaac/Kit UI 打开 stage 时仍出现大量红色对象；同时 UI log 里仍有 MDL 相关报错。
>
> 本文目标：让一个新的 AI 只读这一篇 + 链接到的历史文档，就能继续推进：知道哪些步骤已经做过、当前卡点是什么、下一步需要收集什么证据、以及可能的修复方向。

---

## 0. 前置：之前已经做过什么（不要重复造轮子）

以下工作在 2025-12-25 已经做过一轮并形成文档结论，本次排查默认这些是“已完成基线”，除非 UI log 证明它们失效：

- **MDL materials/Textures 打包与 alias 策略**（`Materials -> materials`、`Textures -> textures`、`materials/Textures -> ../textures` 等）：
   - 见：`docs/debug_sessions/2025-12-25-mdl-materials-packaging/attempts.md`
- **修复 `info:mdl:sourceAsset` 导致的红材质**（将 `../../Materials/X.mdl` 等改写为 basename，使 neuraylib 通过 `MDL_SEARCH_PATH` 找到模块）：
   - 见：`docs/debug_sessions/2025-12-25_045230-fix-mdl-sourceasset/report.md`
- **一致性验证框架（prim/位姿/渲染 diff 的思路与脚本入口）**：
   - 见：`docs/debug_sessions/2025-12-25_prim-verify-and-render-diff/index.md`

本次（2025-12-26）问题是：即便按上述策略打包完成，UI 打开仍大量红色，且 UI log 仍出现 MDL 相关报错。

---

## 1. 现象

- **关键对比**：原始 task9 USD 在 UI 打开时背景/物体不红；但**打包后的 USD 打开后变红**（用户观察）。
- UI log 里存在大量 MDL 相关报错（用户观察）。
- 当前阶段不优先处理 GLB 引用问题（若存在 `.glb` 作为 payload/reference 造成红色，先暂时忽略）。

### 1.1 本次验证输入/输出（务必固定，以免复现口径漂移）

- 输入（原始）：`/shared/smartbot/jiamingda/data_code/simbench/MesaTask-USD/simbench_shared/GRSceneUSD/task9/scene_flattened_simready.usd`
- 输出（打包）：`output/task9_scene_flattened_simready_pack_2025-12-26_074727/scene_flattened_simready.usd`
- 输出目录关键文件：
   - `output/task9_scene_flattened_simready_pack_2025-12-26_074727/env/mdl_paths.env`
   - `output/task9_scene_flattened_simready_pack_2025-12-26_074727/report.json`
   - `output/task9_scene_flattened_simready_pack_2025-12-26_074727/logs/packager.log`

> 注：输出目录以实际打包产物为准（此处记录一次已完成的打包目录）。

---

## 2. 初步判断（需要证据支持）

UI 的红色通常来自两类原因：

1) **MDL 无法解析/编译**
   - `info:mdl:sourceAsset` 指向的 `.mdl` 找不到
   - MDL module/package 名与文件路径不匹配（搜索路径存在但仍编译失败）
   - 依赖的贴图或 include 模块缺失
   - MDL 内部引用路径大小写/alias 不兼容

2) **USD 材质绑定或 shader graph 发生变化**
   - 绑定丢失、material prim 不存在、primvar 不一致等

目前用户反馈“UI log 里还有 mdl 报错”，更像是 (1)。注意：**UI 红色**与**headless render 是否报错**可能不一致；本次以“UI 打开后的 log 与显示”为准。

---

## 3. 需要补齐的关键信息（请把信息粘贴到本文档）

为避免凭感觉排查，需要把 UI log 中的关键报错“落盘到文档”。建议至少粘贴以下信息：

- Isaac/Kit 版本（或启动命令中的 kit app 版本）
- 打开的是原始还是打包后的 USD（或两者都打开过）
- UI log 中 MDL 相关错误片段（建议每类错误粘贴 3~10 行上下文）

### 3.1 MDL 报错片段（待补齐）

> 在这里粘贴 UI log 中的 MDL 错误。
>
> 建议按“错误类型”分段：
> - `MDLC:COMPILER` / `UsdToMdl`
> - `could not find module`
> - `texture` / `resource` not found
> - `neuraylib` search path 输出

### 3.2 建议同时补齐的“最小截图/证据”

- UI 中任选 1~3 个红色 prim：记录其 prim path（例如 `/root/xxx`）
- 对这些 prim：
   - 材质绑定到哪个 Material（若可见）
   - 对应 shader 的 `info:mdl:sourceAsset` 值（最好直接把属性面板内容抄下来）

这能把“红色”从笼统现象，落到可定位的具体 shader/mdl 文件。

---

## 3.3 证据/日志归档规范（建议统一落到本目录）

由于 MDL 报错条目可能很多，建议先把**完整 UI/terminal 输出**保存到一个规范目录，再从中摘取关键片段补充到 3.1。

- 证据目录：`docs/debug_sessions/2025-12-26_task9-ui-mdl-red/evidence/`
- 推荐至少保存两份 UI 打开日志（在同一台机器/同一启动方式下对比）：
   - `evidence/ui_open_original.log`（打开原始 USD）
   - `evidence/ui_open_packed.log`（打开打包 USD）
- 如果是从 terminal 启动 UI：建议用 `tee` 同时落盘与显示，例如：
   - `... 2>&1 | tee evidence/ui_open_packed.log`
- 如果 UI 有内置日志文件：把原始日志文件复制到 `evidence/`，并在文件名中标注 open 的 USD（original/packed）。

---

## 4. 预期采取的解决思路（按优先级）

### 4.1 先确认 MDL 搜索路径与输出一致

预期：打包输出目录存在 `env/mdl_paths.env`，UI 打开时通过启动脚本注入 `MDL_SEARCH_PATH/MDL_SYSTEM_PATH`，至少能覆盖：

- `out_dir/materials`
- `out_dir/materials/external/**`（若存在分桶）
- 以及被 alias 的 `Materials -> materials` 兼容路径

如果 UI 日志里打印了 neuraylib 的 search path，需要核对它是否包含上述路径。

补充检查点：
- 打开 UI 是否通过仓库脚本启动（`scripts/open_in_isaac_ui.sh` 或 `scripts/launch_isaac_with_env.sh`）。如果不是，`mdl_paths.env` 可能根本没注入。

### 4.2 复核 `info:mdl:sourceAsset` 改写是否仍满足 neuraylib

历史问题（已在 2025-12-25 解决过一轮）：
- `info:mdl:sourceAsset` 出现 `../../Materials/X.mdl` 一类路径，会导致 neuraylib 解析为异常 module（例如 `::..::..::Materials::X`），进而编译失败。

预期策略：
- 对 `.mdl` 的 `info:mdl:sourceAsset` 改写为 basename（`X.mdl`），让 neuraylib 在 `MDL_SEARCH_PATH` 中找到模块。

需要核对：
- 这次“红色”对应的 shader prim，`info:mdl:sourceAsset` 具体是什么（是否仍带 `..` 或指向不存在文件）。

如果 `info:mdl:sourceAsset` 是 basename（例如 `DayMaterial.mdl`），但仍报 “module not found”，通常说明：
- `MDL_SEARCH_PATH` 未覆盖到 `out_dir/materials`（或覆盖顺序不对），或
- `.mdl` 所在目录结构与 module 名要求不一致（需要从 log 中确认 neuraylib 期待的 module 名）。

### 4.3 若 MDL 文件存在但仍编译失败：按依赖链补齐资源

常见情形：
- `.mdl` 找得到，但其内部 `import` 的 module 找不到
- 或 `texture_2d("...")` 的路径无法在搜索路径下解析

策略：
- 以 UI log 报错里的 module/texture 名为入口，反查输出目录中对应文件是否存在
- 若存在但找不到，优先检查：大小写、alias、以及 search path 是否覆盖

### 4.4 若“红色”来自材质绑定丢失：再做 USD 侧的结构核对

当 MDL error 并不明显时，需要回到 USD：
- 是否 material prim 缺失
- bind 的 relationship 是否被改写破坏
- `Looks`、`Materials` 等目录结构是否发生变化

---

## 5. 与打包器实现相关的已知行为（用于排查时避免误判）

- 输出目录会创建 alias：`Materials -> materials`、`Textures -> textures`、`materials/Textures -> ../textures`。
- 对于不在 base_root 下的外部 USD layer，会使用哈希分桶路径以避免同名覆盖（例如 `external_layers/<hash>/<basename>` 或 `assets/external/<hash>/<basename>` 一类）。

这些行为可能会改变“文件在磁盘上的相对位置”，但只要：
- USD 内的 asset path 已被正确改写
- UI 启动时 MDL search path 覆盖了 materials 根目录

就不应该导致 MDL 自身找不到模块。

---

## 6. 下一步执行清单（给下一位 AI，按顺序做）

> 注意：本清单描述的是“要收集什么证据/产物”，不要求先改代码。

1) **拿到 UI log 的原始文本**
   - 把完整 log 先落盘到 `evidence/`（见 3.3），再把关键片段粘贴进 3.1。

1.1) **在同一环境下对比 original vs packed 的 UI log**
   - 分别打开原始 USD 与打包 USD，各保存一份 log（`ui_open_original.log` / `ui_open_packed.log`）。
   - 重点关注：packed 才出现的 MDL 报错类型与首个触发的 shader/material。

2) **确认启动方式与 env 注入**
   - 明确 UI 是用什么命令启动的。
   - 如果使用仓库脚本启动：记录实际加载的 `mdl_paths.env` 路径。

3) **从 1~3 个红色 prim 反查到具体 shader/mdl**
   - 记录 prim path、绑定的 material、shader 的 `info:mdl:sourceAsset`。
   - 把这些信息补齐到 3.2。

4) **把错误归类到可执行分支**
   - A. `MDL_SEARCH_PATH`/`MDL_SYSTEM_PATH` 未生效（启动脚本/环境注入问题）
   - B. `info:mdl:sourceAsset` 值不符合预期（仍包含 `..` 或指向错误路径）
   - C. `.mdl` 找得到但其依赖找不到（import/贴图/resource 缺失或大小写不匹配）
   - D. MDL 编译器报语法/版本不兼容（需要确认 Isaac/Kit 支持的 MDL 版本/特性）

5) **再决定是否需要改 packager**
   - 只有当证据表明是“打包后路径/布局/改写”导致的 (B)/(C) 类问题，才进入代码修改阶段。


---

## 7. 需要用户补齐的信息（用于推进下一轮）

- 把 UI log 中的 MDL 报错片段粘贴到本文档 3.1
- 指明“红色”是打开原始 USD 还是打包 USD（或两者）

在信息补齐后，再决定是：
- 继续优化 `mdl_paths.env` / alias / MDL sourceAsset rewrite
- 还是回到 USD 绑定/结构一致性问题
