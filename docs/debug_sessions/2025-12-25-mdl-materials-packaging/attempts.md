# 2025-12-25：USD Self-Pack — Isaac Sim/Kit 里 MDL 材质变红（缺模块 / Empty identifier）排查记录

> 目标：让打包后的自包含 USD 场景在 Isaac Sim/Kit 中打开并正常编译/显示 MDL 材质（不再出现“红材质”、MDL missing module、Hydra “Empty identifier” 等错误）。

## 0. 背景与现象
- 现象：在 Isaac Sim/Kit 打开打包输出的 `scene.usd` 后，材质变红，日志出现 MDL 编译相关错误。
- 特征错误（后续通过“强制渲染触发编译”稳定复现）：
  - `MDLC:COMPILER comp error: C120 could not find module '::..::..::Materials::DayMaterial'`
  - `USD_MDL ... '../../Materials/DayMaterial.mdl' is Invalid`
  - `Failed to create MDL shade node ... Empty identifier: ''`
  - 类似错误也发生在 `Num595f...` 等自动生成/拷贝后的 MDL 文件上。

## 1. 尝试 1：仅 headless 打开 USD + 读 Kit 日志（发现“打开成功但不一定触发材质编译”）
- 做法：用 headless 方式让 Kit 打开打包后的 `scene.usd`，读取输出日志（例如 `output/.../logs/kit_open.log`）。
- 观察：
  - Kit 能启动并到达 “app ready”。
  - 日志中能看到启动参数包含 `--/app/file/open=.../scene.usd`，说明 stage open 这一步本身并不一定失败。
  - 但**仅仅 open stage 不一定会触发 MDL 编译**，因此日志里可能缺少关键的 MDL 编译失败信息。
- 结论：需要一个“必然触发材质编译”的验证动作。

## 2. 尝试 2：确认 MDL 搜索路径是否注入（验证 env/alias 逻辑）
- 做法：检查 packager 输出的 `env/mdl_paths.env` 及 Kit 日志中 neuraylib 的 MDL search path 输出。
- 观察：
  - 日志里出现类似：`add MDL search path: file:/.../output/.../materials`
  - 说明 packager 生成的 MDL 路径（`MDL_SYSTEM_PATH` / `MDL_SEARCH_PATH`）以及输出目录下 `materials/` 的预期确实被 neuraylib 收到。
- 结论：**“找不到模块”的根因不一定是 search path 没加**，更可能是 *USD 里写的 MDL module 引用形式本身不被 neuray 解析*。

## 3. 尝试 3：尝试直接用 Python API 操作/查询 MDL（失败，转向渲染触发）
- 做法：在 Isaac Python 环境里尝试 import 相关 MDL Python 模块（希望直接触发/检查 MDL 编译）。
- 结果：出现类似 `ModuleNotFoundError: No module named 'omni.mdl'`。
- 结论：这条路径不稳定/不可依赖，转向更确定的方式：**渲染**。

## 4. 尝试 4：新增“离屏渲染一帧”脚本，强制触发 MDL 编译（得到关键错误链）
- 做法：新增脚本 `scripts/render_one_frame.py`：
  - headless 启动 `SimulationApp`
  - 打开 stage
  - 使用 Replicator/Writer 输出一帧（或少量帧）RGB
  - 目的：触发 Hydra/MDL 真正编译
- 结果（关键收获）：稳定复现 MDL 编译错误链：
  - neuraylib 报 C120：找不到模块 `::..::..::Materials::DayMaterial` / `::..::..::Materials::Num595...`
  - USD_MDL 报 `../../Materials/*.mdl` invalid
  - Hydra 报 “Empty identifier” 并导致材质创建失败（红材质）
- 结论：根因聚焦到一个模式：
  - USD 里 MDL sourceAsset 写成了带 `..` 的相对路径（如 `../../Materials/DayMaterial.mdl`）
  - neuraylib 会把这种路径转成 MDL 模块名 `::..::..::Materials::DayMaterial`，这是非法/不可解析的模块名

## 5. 尝试 5：修 packager 的 rewrite 逻辑（针对 `info:mdl:sourceAsset` 去掉 `..`）
- 动机：既然 neuray 的 module resolution 不接受 `::..::..::Materials::X` 这种形式，那么需要把 USD 中的 `info:mdl:sourceAsset` 改写成可在 `materials/` 搜索路径下找到的模块引用。

- 改动点（第一次尝试）：修改 `src/usd_asset_packager/rewrite.py`，增加特判：
  - 当资产类型是 `mdl` 且属性名是 `info:mdl:sourceAsset` 时，写入 basename（例如 `Num595....mdl` 或 `DayMaterial.mdl`），避免 `../../Materials/...`。

- 执行：重新打包到新输出目录，例如：
  - `output/task9_omni_fix_mdl_source`
  - 并确保 `materials/` 下确实拷贝了对应 `.mdl` 文件
  - 同时输出目录会创建兼容性 alias（例如 `Materials -> materials`，`Textures -> textures`，以及 `materials/Textures -> ../textures`）

## 6. 尝试 6：用 prim dump 验证 rewrite 是否真的生效（发现未生效，定位到“rewrite 匹配条件没打中”）
- 做法：用 `scripts/dump_usd_prim.py` dump 某个 shader prim 的关键属性，重点看：
  - `info:implementationSource`
  - `info:mdl:sourceAsset`
  - `info:mdl:sourceAsset:subIdentifier`
- 观察（关键 blocker）：即使在新输出里，仍然看到：
  - `info:implementationSource: sourceAsset`
  - `info:mdl:sourceAsset: AssetPath(../../Materials/Num595....mdl)`
  - 说明**特判 rewrite 没有真正作用到这个字段**。

- 推断原因（未最终确认）：
  - 资产扫描阶段对该属性的 `asset_type`/`attr_name` 分类不一致（例如 `attr_name` 实际不是严格的 `info:mdl:sourceAsset`，或 rewrite 对某类元数据/字段没覆盖）
  - 或者该字段位于某个引用 layer/子 layer，当前 rewrite 只改写了部分 layer

## 7. 同期发现：还有大量 USD reference 打不开（可能是独立问题）
- 在渲染触发阶段，日志中还出现很多：
  - `Could not open asset .../output/models/.../instance.usd for reference introduced by ...`
- 这可能是另一个问题：
  - 依赖没有被扫描/复制全
  - 或 rewrite 指到了一个没有被拷贝的路径
- 但本轮主线优先级仍然是：先把 MDL 的 `../../Materials/...` 模块引用形式修掉，让材质能编译。

## 8. 当前状态（截至 2025-12-25）
- 已经建立了“稳定复现 + 验证”闭环：
  - 通过离屏渲染触发 MDL 编译来抓真实错误
  - 通过 prim dump 验证 USD 中 MDL 字段是否被正确改写
- 已确认核心错误形态：
  - `info:mdl:sourceAsset` 中的 `../../Materials/*.mdl` 会导致 neuray 解析成 `::..::..::Materials::*` 并失败
- 已做过一次 rewrite 修复尝试，但验证显示未生效（需要继续修正 rewrite/scan 的匹配覆盖范围）。

## 9. 下一步（待做）
- 找到 `rewrite.py` 为什么没有改写到 `info:mdl:sourceAsset`：
  - 对照 `dump_usd_prim.py` 看到的真实属性名/字段写入位置
  - 追踪扫描结果里记录的 `attr_name`/`asset_type`，以及 rewrite 对各类字段的覆盖（属性、元数据、shader inputs 等）
- 重新打包并用 `render_one_frame.py` 复验：
  - MDL C120 missing module 消失
  - Hydra “Empty identifier” 不再出现

---

## 10. 2025-12-25 04:52:30 更新：定位根因并修复（已解决红材质主链）

### 根因（为什么之前的 rewrite 特判没生效）
- 之前的 `rewrite_layers(stage, ...)` 只会改写并导出 stage 的 layer stack（root+sublayers）。
- 但大量 `info:mdl:sourceAsset` 是写在 **被 reference 的 USD 依赖文件** 里（最终被复制到输出的 `assets/*.usd`）。
- 这些 copied USD deps 不在 root stage 的 layer stack 内，所以先前不会被 rewrite。

### 修复方案
- 在复制完成后，对输出的 `assets/*.usd` 逐个做一次“layer 文件就地改写 asset path”。
- 使用 `pxr.UsdUtils.ModifyAssetPaths(layer, callback)` 遍历并改写 layer 中所有 authored asset path。
- 对 `info:mdl:sourceAsset` 做特殊规则：把 `../../Materials/X.mdl` 改为 `X.mdl`（basename），让 neuraylib 从 `MDL_SEARCH_PATH` 中的 `materials/` 找到模块。

### 代码改动点
- `src/usd_asset_packager/rewrite.py`
  - 新增 `rewrite_layer_file_asset_paths()`：对单个输出 layer 文件就地 rewrite + save。
- `src/usd_asset_packager/packager.py`
  - 当 `--copy-usd-deps` 开启时，额外对 copied USD deps 执行一次就地 rewrite。

### 验证结果
- 静态：`scripts/dump_usd_prim.py` 抽查 shader prim，`info:mdl:sourceAsset` 已变为 basename（无 `..`）。
- 动态：离屏渲染触发编译后，`C120 could not find module` / `USD_MDL Invalid` / `Empty identifier` 不再出现，材质正常显示。

### 遗留问题（独立）
- 仍存在大量 `instance.usd` 引用缺失（需后续单独追依赖扫描/复制）。

---

## 附：本次迭代中出现/新增的关键文件
- `scripts/render_one_frame.py`：离屏渲染触发 MDL 编译
- `scripts/dump_usd_prim.py`：dump prim 属性用于验证 rewrite
- `src/usd_asset_packager/rewrite.py`：资产路径改写逻辑（已做过一次针对 `info:mdl:sourceAsset` 的尝试性特判）
- `src/usd_asset_packager/packager.py`、`src/usd_asset_packager/report.py`：输出 alias + 写 `env/mdl_paths.env`
