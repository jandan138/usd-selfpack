# 2025-12-25 Prim 结构/位姿/渲染一致性验证（交接文档）

> 目的：当前打包后的 USD 与原始 USD “明显长得不一样”。除了 기존 的依赖/MDL 编译验证之外，补一层**结构一致性验证**：验证每个 prim 是否仍存在、关键位姿是否一致、以及渲染结果是否一致。
>
> 本文把目前遇到的问题、做过的所有尝试与结果、以及如何复现/验证写清楚，让新的 AI 读完即可继续推进。

---

## 1. 项目背景（最小必要上下文）

该仓库是一个 USD 资产自打包工具：扫描依赖 → 拷贝资产/子 USD → 重写 asset path → 生成 `report.json` + `env/mdl_paths.env`（用于 Isaac/Kit 侧 MDL 搜索路径）→（可选）flatten。

验证目标：
- **自包含**：拷贝/重写后不再依赖源目录
- **可渲染**：headless render 不出现 `UsdToMdl` / `MDLC:COMPILER` 典型缺资源错误
- **一致性**（新增）：prim 结构/位姿/渲染与原始 stage 尽可能一致

---

## 2. 当前进度与产物

### 2.1 已验证过的包（flex_task1_cookie v9）

- 已验证：不再出现坏路径模式 `../../Materials/Textures/*.png`（之前的典型问题）
- 已验证：headless render log 未出现 MDL 缺资源/缺 module 签名
- 做过脚本修正：`scripts/render_one_frame.py` 兼容文档里的 `--resolution 256 256` 形式，并强制 Replicator 输出到指定 `--out-dir`，避免写到默认 `/root/omni.replicator_out/...`。

### 2.2 新打包任务（task9）

输入：
- `/shared/smartbot/jiamingda/data_code/simbench/MesaTask-USD/simbench_shared/GRSceneUSD/task9/scene.usd`

输出（本次会话生成）：
- `output/task9_pack_2025-12-25_101221/scene.usd`
- `output/task9_pack_2025-12-25_101221/report.json`
- `output/task9_pack_2025-12-25_101221/env/mdl_paths.env`

渲染验证（通过）：
- 输出目录：`output/task9_pack_2025-12-25_101221/render_verify/`
- 产出：`rgb_0000.png`, `rgb_0001.png`, `rgb_0002.png`
- `render.log` 未匹配 `UsdToMdl|MDLC:COMPILER|could not find module|can not be found|Could not open asset` 等关键签名

新增一致性验证（已落地最小工具 + 一次实跑结果）：
- 新增脚本：`scripts/compare_usd_prims.py`
- 实跑（原始 vs 打包）：
  - A=`/shared/smartbot/jiamingda/data_code/simbench/MesaTask-USD/simbench_shared/GRSceneUSD/task9/scene.usd`
  - B=`output/task9_pack_2025-12-25_101221/scene.usd`
  - 输出报告：`output/task9_pack_2025-12-25_101221/prim_diff_report.json`
  - 关键结果（需要进一步解释原因）：
    - `prim_counts`: A=5579, B=9086, common=4417
    - `only_in_a`: 1162
    - `only_in_b`: 4669
    - `xform_diffs`（top 50）存在非零平移差异（最大约 0.068）

注意：
- 打包命令那次“退出码=1”并非 packager 自身失败，而是 stdout 管道到 `tee $OUT/pack.log` 时 `$OUT` 还没创建导致 `tee` 失败（因此 exit code 变 1）。packager 的真实日志在 `output/.../logs/packager.log`，并且明确写了 `packaging finished; report at .../report.json`。

---

## 3. 当前卡点/问题清单（含观察）

### 问题 A：两个 USD 明显长得不一样（核心卡点）

现象：
- 原始 USD 与打包输出 USD（或 flatten 后 USD）在视觉上差异明显（几何缺失、变形、位置不对、材质/纹理不同等）。

原因候选（需要验证，不要先入为主）：
1) **引用/子层没加载全**：原始 stage 依赖相对路径 `assets/*.usd`，在不同工作目录/解析环境下会打开失败，导致 stage 组成不同
2) **打包重写导致引用变化**：`references`/`payloads`/sublayers 的 rewrite 可能没覆盖某种 listOp/组合写法
3) **flatten vs 非 flatten 差异**：flatten 改写 layer stack 后，某些 `variant`/`inherits`/`specializes` 的 composition 结果不同
4) **资产转换/补丁策略差异**：比如 glb->usd、MDL 资源别名/Textures alias 的处理

要点：仅靠“MDL 编译不报错”无法证明几何/位姿一致，因此新增验证层。

补充：本次已用 `scripts/compare_usd_prims.py` 对 task9 做了初次量化对比，确实发现 prim 数量与部分位姿存在差异；下一步要优先判定这是否是“原始 stage 打开不全/解析环境不同”导致的假差异，还是 packager 真的改变了 composition 结果。

### 问题 B：report.json 的 stats 计数明显不可信

观察：
- `report.json` 的 `stats` 里常出现 `textures: 0`、`mdls: 0`，但实际输出目录存在纹理/mdl 文件。

推测：
- 可能是 asset_type 命名（`texture` vs `textures` 等）与计数逻辑不一致导致。

影响：
- report 仍可用作详细 copies/rewrites 列表，但不要把 `stats.textures/mdls` 当作是否拷贝成功的依据。

---

## 4. 已做的尝试与结果（可复现）

### 尝试 1：检查 v9 是否还含坏路径 `../../Materials/Textures`

目的：验证之前的典型 “UsdToMdl 找不到 ../../Materials/Textures/*.png” 是否在 v9 被消除。

方法：对打包输出 USD 扫描 AssetPath，统计是否存在该子串。

结果：
- v9 中 `../../Materials/Textures/` 与 `../../Materials/textures/` 计数为 0。

### 尝试 2：headless render 强制触发 UsdToMdl / MDL 编译（v9）

目的：用渲染链路验证 MDL 资源是否真正可解析。

命令（示例）：

```bash
OUT=output/<your_pack_dir>
./scripts/isaac_python.sh scripts/render_one_frame.py \
  --usd "$OUT/scene_simready.usd" \
  --env "$OUT/env/mdl_paths.env" \
  --out-dir "$OUT/render_verify" \
  --resolution 512 512

grep -RIn "UsdToMdl|MDLC:COMPILER|could not find module|can not be found|Could not open asset" "$OUT/render_verify/render.log" || true
```

结果：
- 未出现上述关键错误签名；成功产出 rgb 图片。

### 尝试 3：修正 headless render 脚本的 CLI/输出行为

问题：文档期望 `--resolution 256 256`，脚本原先只支持 `256x256`；且 Replicator 输出可能落到默认目录。

修正点（已完成）：
- `scripts/render_one_frame.py` 支持：`--resolution 256x256` 和 `--resolution 256 256`
- 强制 Replicator disk backend root_dir 指向 `--out-dir`
- 以绝对路径打开 USD，降低相对路径歧义

结果：
- 文档命令可直接运行；输出目录可控。

### 尝试 4：task9 打包 + 渲染验证

打包命令（等价示例）：

```bash
IN=/shared/smartbot/jiamingda/data_code/simbench/MesaTask-USD/simbench_shared/GRSceneUSD/task9/scene.usd
OUT=output/task9_pack_2025-12-25_101221
./scripts/isaac_python.sh -m usd_asset_packager \
  --input "$IN" --out "$OUT" --copy-usd-deps --log-level INFO
```

结果：
- 产出 `scene.usd` / `report.json` / `env/mdl_paths.env`
- `report.json`：`warnings=1`（"rewrote asset paths in copied USD deps: 302"），`rewrite_fail=2`
- 两个 rewrite_fail 记录为 `reason: not found in list`，字段指向 `scene.usd` 中 `/root/room` 与 `/root/obj_table` 的 `references`。
- 但渲染验证通过，且进一步检查 `output/.../scene.usd` 中不再包含原始绝对源路径（`/shared/smartbot/gaoning/...` 等）。

解释（暂定）：
- rewrite_fail 的实现可能是“记录时用来查找 before 值，但 listOp/内部表示不完全匹配”，导致报告里标记失败，但最终结果仍写出了 `after`。

---

## 5. 新增验证层：prim 存在性/位姿/渲染一致性

这部分是“下一步怎么解决 + 怎么验证”的关键。

### 5.1 结构一致性（prim 是否仍存在）

目标：比较 A/B 两个 stage 的 prim path 集合差异。

最小可行输出：
- `only_in_A`（只在原始 stage 存在）
- `only_in_B`（只在打包 stage 存在）

建议忽略：
- Session layer 产生的 runtime prim
- 某些 render delegate 自动生成 prim（如果是 UI 里打开对比，需谨慎）

建议以“打开 USD 文件后 stage.TraverseAll() 的 prim path 集合”作为对比基准。

### 5.2 位姿一致性（位置/旋转/缩放是否一致）

目标：对共同存在的 prim，比较其世界空间变换（或至少比较 XformOps）。

最低成本策略：
- 对 `UsdGeom.Xformable` prim：比较 world transform matrix（或 translation/rotation/scale）
- 允许一个容忍度 $\epsilon$（比如 1e-4）

注意：
- 某些 prim 依赖时间采样；默认以 `Usd.TimeCode.Default()` 对齐
- 如果原始 stage 没加载全，world transform 对比会被误导，所以需先确保两侧 stage 解析环境一致（见 6.1）

### 5.3 渲染一致性（图像对比）

目标：固定相机/分辨率/渲染设置，渲染 A/B 并做像素级或统计级对比。

建议做两层：
1) **快速信号**：计算 `MSE/PSNR` 或 `mean abs diff`；或者仅比较 hash（对噪声敏感）
2) **可解释输出**：输出差分图 `diff.png`（abs difference 放大）

前提：
- 相机必须固定：优先使用 stage 内已有 camera；无 camera 时使用相同的“创建 camera”逻辑
- 渲染帧数固定：当前脚本固定 render 3 帧；对比时可只取 `rgb_0002.png` 或第一张

---

## 6. 下一步建议（按优先级）

### 6.1 先解决“打开 stage 不一致”的根因

两个 USD 看起来不一样，最常见是：两边 stage 的依赖解析环境不一致。

动作：
- 对原始 USD：在 Isaac/Kit 或同一 pxr resolver 环境中打开，并捕获 `Could not open asset` 警告
- 对打包 USD：同样方式打开

验证：
- 两边打开时的缺资产 warning 数量应接近 0（或至少一致）

### 6.2 落地 prim/位姿 diff 工具（自动化）

建议新增一个脚本：
- 输入：`--usd-a`, `--usd-b`, `--out report.json`
- 输出：prim path 差异、共同 prim 的 world transform 差异 TOP-N

状态：已新增 `scripts/compare_usd_prims.py`（用 XformCache 取 world transform，避免 USD Python 绑定返回值差异）。

### 6.3 渲染 diff 工具（自动化）

建议新增：
- `render_one_frame.py` 已能渲染单个 USD
- 新增一个小脚本 `compare_render_outputs.py`：输入 A/B 渲染目录，输出统计与 `diff.png`

---

## 7. 快速复现/排查清单（给下一位 AI）

1) 选定要对比的两个 USD：
   - A=原始输入（例如 task9 的 `/.../scene.usd`）
   - B=打包输出（例如 `output/task9_pack_.../scene.usd`）

2) 在同一个 Isaac 环境分别渲染：

```bash
# A
./scripts/isaac_python.sh scripts/render_one_frame.py \
  --usd "/abs/path/to/original/scene.usd" \
  --out-dir "output/_verify/original" \
  --resolution 512 512

# B
OUT=output/task9_pack_2025-12-25_101221
./scripts/isaac_python.sh scripts/render_one_frame.py \
  --usd "$OUT/scene.usd" \
  --env "$OUT/env/mdl_paths.env" \
  --out-dir "output/_verify/packed" \
  --resolution 512 512

# grep 关键错误
for d in output/_verify/original output/_verify/packed; do
  echo "== $d =="
  grep -RIn "UsdToMdl|MDLC:COMPILER|could not find module|can not be found|Could not open asset" "$d/render.log" || true
done
```

3) 做 prim/位姿一致性 diff（待落地脚本后直接跑）。

```bash
IN=/shared/smartbot/jiamingda/data_code/simbench/MesaTask-USD/simbench_shared/GRSceneUSD/task9/scene.usd
OUT=output/task9_pack_2025-12-25_101221

./scripts/isaac_python.sh scripts/compare_usd_prims.py \
  --usd-a "$IN" \
  --usd-b "$OUT/scene.usd" \
  --out "$OUT/prim_diff_report.json" \
  --max-xf-diffs 50
```

---

## 8. 备注

- 本次 task9 的 `report.json` 里 `rewrite_fail=2`，但进一步检查打包后的 `scene.usd` 不包含原始绝对路径；更像是报告记录侧的“listOp 匹配”问题，而非实际写入失败。
- 目前 `report.json.stats` 计数不可靠，应以输出目录实际文件、以及 `copies/rewrites` 明细为准。
