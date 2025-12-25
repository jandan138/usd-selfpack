# 2025-12-25 flex_task1_cookie self-pack 进展/问题/验证交接

> 目的：把 `flex_task1_cookie/Collected_scene/scene_simready.usd` 打成一个**完全自包含**的 USD 包，在 Omniverse Isaac/Kit 里打开并能正常渲染（无红材质）。
>
> 核心验证：用离屏渲染脚本 `scripts/render_one_frame.py` 强制触发 **MDL 编译/UsdToMdl 转换**，以日志是否出现关键错误签名作为 pass/fail。

---

## 1. 当前状态（截至 v9）

### 已完成（基本确认有效）

1) **USD 依赖扫描 + 拷贝 + rewrite 框架**已搭起来：
- 输出结构为 keep-tree：`out/{assets,materials,textures}`（以及兼容 alias：`Materials/Textures`）。
- USD layer 导出到 output 后，会对 sublayers/references/payloads/属性 Sdf.AssetPath 进行 rewrite。

2) **MDL 模块依赖闭包**已处理：
- 之前遇到 MDL compiler 报错（例如找不到 `OmniUe4Function/Base`），原因是 MDL 文件里有 `using <Module> import ...` 的依赖形式，未被扫描。
- 现在已加入 MDL import 扫描：同时支持 `import ...;` 与 `using <...> import ...;`，并把兄弟模块一并拷贝到 package。

3) **MDL 内部资源（纹理）依赖闭包**已处理一大部分：
- MDL 内出现形如 `"./Textures/white.png"`、`"./Textures/normal.png"` 的资源引用，通过扫描 MDL 里的字符串字面量（扩展名 png/jpg/exr/...）来发现并复制。
- 为满足 MDL 的 `./Textures/*` 相对路径语义，在每个 MDL 模块目录旁边创建 `Textures -> <packed textures subtree>` 的 symlink/alias。

### 仍在失败/待确认（最后一公里）

**症状**：离屏渲染日志仍反复出现：
- `[UsdToMdl] ... References an asset that can not be found: '../../Materials/Textures/white.png'`
- 同类还包括 `black.png`, `normal.png`，以及若干 `*_color.png`, `*_metallic.png`。

**关键观察**：
- MDL 自己引用的 `./Textures/*.png` 通常已被满足（靠 MDL 目录旁 `Textures` alias）。
- 但 USD Shader 的 `inputs:*_Tex` 里仍可能保留原始路径 `../../Materials/Textures/*.png`，没有被 rewrite。

**根因路径**（已多次验证）：
- `rewrite_layers()` 的替换映射来源于 copy 阶段成功解析并复制的资产（也就是 `resolved_path != None` 的 AssetRef）。
- 当前仍存在大量纹理 AssetRef：`original_path: ../../Materials/Textures/white.png` 但 `resolved_path: None`，导致：
  - copy 阶段不会复制它
  - rewrite 阶段也没有 replacement entry
  - 最终 USD 里仍保留 `../../Materials/Textures/*.png`，渲染时 UsdToMdl 找不到

**最新改动（v9 前）**：
- 已对 `resolve_with_layer()` 做了调整（目标：让 `../../Materials/Textures/*.png` 能被解析到真实文件路径，从而进入 copy+rewrite）。
- v9 打包日志显示大量 textures 已被复制进 package（例如 `Materials/textures/white.png`）。
- 但 v9 的 headless render 尚未完整跑通（渲染那次被人工 cancel），以及 shader inputs 是否已 rewrite 仍需验证。

---

## 2. 主要问题清单（“卡住点”）

### 问题 A：UsdToMdl 找不到 `../../Materials/Textures/*.png`

**表现**：render log 重复报缺资源。

**已做尝试**：
1) 拷贝 textures 到 `out/textures/...`（成功）
2) 创建全局 alias：
   - `out/Materials -> out/materials`
   - `out/Textures -> out/textures`
   - `out/materials/Textures -> out/textures`（给 MDL `./Textures` 用）
3) 为每个 USD layer 目录创建局部 alias（减少 `..` 依赖）：在包含输出 USD layer 的目录旁创建 `Materials/Textures` 软链。

**结果**：
- MDL 内 `./Textures/*.png` 大概率可满足；
- 但 USD Shader inputs 里仍可能是 `../../Materials/Textures/*.png`，如果该路径无法被解析并 rewrite，UsdToMdl 依旧报错。

---

### 问题 B：扫描到的纹理 AssetRef `resolved_path: None`，导致无法 copy + rewrite

**表现**：`report.json` 里可以看到很多：
- `asset_type: texture`
- `original_path: ../../Materials/Textures/white.png`
- `resolved_path: None`

**已做尝试**：
1) 修复扫描器使用 layer 路径的 bug
- 之前扫描器拿 `layer.identifier` 当“文件系统路径基准”去 resolve，相对路径会失败。
- 已改为用 `propertyStack[0].layer.realPath`（或 rootLayer.realPath）作为 resolve base。

**结果**：
- 对一部分相对路径解析有改善，但仍有很多 `../../Materials/Textures/*.png` 解析失败。

2) 调整 resolver 的 resolve 顺序/策略
- 之前 `resolve_with_layer()` 可能过早调用 `.resolve()` 或对大小写/存在性判断不友好，导致 symlink/相对路径在存在时仍返回 None。
- v9 之前对 `resolve_with_layer()` 做了修复（目标：不要因为 `.resolve()`/`exists()` 时机导致误判；并处理 `Textures` vs `textures` 等大小写差异）。

**结果**：
- v9 打包阶段确实复制了很多 `Materials/textures/*.png` 到 package。
- 但仍需用“shader inputs 是否 rewrite”+“headless render 是否无 missing texture”来判定最终是否彻底解决。

---

## 3. 验证方法（离屏渲染强制触发 MDL 编译）

### 3.1 Render 脚本参数（重要）

`python scripts/render_one_frame.py` **不支持** `--frames`。

支持参数（至少确认过）：
- `--usd <path>`
- `--env <mdl_paths.env>`
- `--out-dir <dir>`
- `--warmup-frames <n>`
- `--resolution <w> <h>`

### 3.2 标准命令（建议直接照抄）

在 repo 根目录：

```bash
OUT=output/flex_task1_cookie_pack_2025-12-25_v9
rm -rf "$OUT/render"

./scripts/launch_isaac_with_env.sh \
  --env "$OUT/env/mdl_paths.env" \
  -- python scripts/render_one_frame.py \
    --usd "$OUT/scene_simready.usd" \
    --env "$OUT/env/mdl_paths.env" \
    --out-dir "$OUT/render" \
    --warmup-frames 3 \
    --resolution 256 256 \
  | tee "$OUT/render.log"
```

### 3.3 通过/失败判据（基于日志）

失败签名（出现任一条基本都说明仍有外部依赖/路径没修好）：
- `UsdToMdl` + `References an asset that can not be found`（尤其是 `../../Materials/Textures/*.png`）
- `MDLC:COMPILER` + `could not find module`（MDL import 没闭包）

快速 grep：

```bash
grep -nE "UsdToMdl|MDLC:COMPILER|can not be found|could not find module" "$OUT/render.log" | head
```

---

## 4. 过程中做过的关键修复（按时间线）

### v0~v4：USD payload/references 扫描问题
- 发现 payload 元数据 key 应该是 `payload`（singular），不是 `payloads`。
- 修复后能更完整地发现 payload 依赖。

### v5：MDL sourceAsset authoring 问题 + 暴露真实 compiler error
- 早期出现 `Empty identifier` 类错误。
- 调整 `info:mdl:sourceAsset` rewrite 逻辑（不要强行改成 `Materials/<basename>` 这种破坏相对关系的写法；要保持与 keep-tree 输出一致）。
- 随后能看到更真实的 MDL compiler error：缺模块（`OmniUe4Function/Base`）。

### v6：补齐 MDL import 依赖
- 增加 MDL import 扫描：
  - `import ...;`
  - `using <...> import ...;`
- 复制兄弟模块，使 MDL 编译通过。

### v6：转向“缺纹理”问题
- headless render 出现大量：
  - `[UsdToMdl] ... '../../Materials/Textures/*.png' not found`

### v6~v8：补齐 MDL resource（纹理）依赖 + alias
- 扫描 MDL 文件中的字符串字面量，抓取看起来像纹理路径的引用并复制。
- 为每个 MDL 模块目录创建 `Textures` alias，满足 `./Textures/*.png`。

结果：
- MDL 内部纹理引用基本 OK。
- 但 USD shader inputs 仍可能保留 `../../Materials/Textures/*.png`，没被 rewrite。

### v7/v8：扫描器 base path bug
- 发现扫描器在 resolve 相对路径时使用了 layer identifier，而非真实文件路径。
- 修复为使用 `layer.realPath`。

结果：
- 一部分相对路径解析改善，但 `report.json` 仍看到大量 `resolved_path: None`。

### v9：resolver 行为调整（目标：让 `../../Materials/Textures/*.png` 可解析）
- 对 `resolve_with_layer()` 进行修复（避免 `.resolve()`/`exists()` 时机导致误判；并处理大小写差异）。

结果：
- v9 打包日志显示很多 `Materials/textures/*.png` 成功复制。
- v9 render 尚未完成跑完（当次被 cancel），需要重新验证。

---

## 5. 需要补做的验证（让新的 AI 可以直接接着干）

### 5.1 验证 1：v9 的 USD shader inputs 是否已经 rewrite

之前做过一次检查，但代码写错 import（把 `UsdShade` 写成了 `Usd.Shade`），导致脚本报：
- `AttributeError: module 'pxr.Usd' has no attribute 'Shade'`

正确的检查方式（注意 import `UsdShade`）：

```bash
./scripts/isaac_python.sh - <<'PY'
from pxr import Usd, UsdShade

stage = Usd.Stage.Open('output/flex_task1_cookie_pack_2025-12-25_v9/scene_simready.usd')
prim = stage.GetPrimAtPath('/root/looks/room/material_room/Shader')

# 不一定每次都是这个 prim 路径，若找不到需要用 Traverse() 搜索某个特征（例如 material_room）
if not prim:
    print('Prim not found')
    raise SystemExit(1)

shader = UsdShade.Shader(prim)
for name in ['inputs:BaseColor_Tex','inputs:Normal_Tex','inputs:Metallic_Tex','inputs:Roughness_Tex']:
    attr = prim.GetAttribute(name)
    if not attr:
        continue
    print(name, '=>', attr.Get())
PY
```

期望：不再出现 `../../Materials/Textures/*.png`（应该变成 package 内可解析路径，或者至少在 layer 相对路径下可解析）。

### 5.2 验证 2：重新跑 headless render（强制 MDL 编译）

按「第 3 节」标准命令跑 v9。

期望：render.log 中不再出现 `UsdToMdl ... can not be found: '../../Materials/Textures/*.png'`。

---

## 6. 如果 v9 仍失败：下一步排查路线

> 目标：定位为什么 `../../Materials/Textures/*.png` 仍没被 rewrite。

1) **在 report.json 里查这些纹理是否仍 `resolved_path: None`**

```bash
OUT=output/flex_task1_cookie_pack_2025-12-25_v9
python - <<'PY'
import json
p = 'output/flex_task1_cookie_pack_2025-12-25_v9/report.json'
needle = '../../Materials/Textures/white.png'
with open(p,'r') as f:
    data = json.load(f)
assets = data.get('assets', [])
rows = [a for a in assets if a.get('original_path') == needle]
print('matches:', len(rows))
for a in rows[:5]:
    print('layer:', a.get('layer_identifier'))
    print('resolved:', a.get('resolved_path'))
    print('type:', a.get('asset_type'))
    print('---')
PY
```

- 若仍是 None：继续加强 `resolve_with_layer()`（比如：
  - 对 base layer path 做更稳健的目录推导
  - 对 `Materials/Textures` 的大小写 alias 做 case-insensitive 真实路径查找
  - 处理 USD 的搜索路径语义与本地 fs 差异）

2) **如果 resolved_path 已有值，但 shader inputs 仍未改**
- 说明 rewrite 映射没有命中该属性的 Sdf.AssetPath（或者该资产被当成“无需 rewrite”跳过）。
- 需要检查 rewrite 逻辑是否覆盖：
  - 属性类型是 `Sdf.AssetPath` / `Sdf.AssetPathArray`
  - metadata list-op（references/payload）
  - subLayerPaths

3) **如果 shader inputs 已 rewrite，但 render 仍报错**
- 需要确认：
  - 纹理文件是否实际存在于被 rewrite 的目标路径
  - 目标路径对 Isaac/Kit 的 asset resolver 是否可达（相对路径基于哪个 layer 解析）
  - 是否存在额外的 MDL/UsdToMdl 侧资源查找规则（例如必须通过 MDL search path）

---

## 7. 一些已知坑（防止重复踩）

- `render_one_frame.py` 没有 `--frames` 参数；用 `--warmup-frames`。
- USD `layer.identifier` 不一定是可用的文件系统路径；resolve 资产路径时应优先用 `layer.realPath`。
- MDL import 有两类：`import ...;` 和 `using <...> import ...;`。
- `Textures` vs `textures` 的大小写差异会导致 Linux 上 resolve 失败；要么统一 rewrite，要么 resolver 做 case-insensitive fallback。

---

## 8. 结论（交接给下一位 AI）

当前“最后卡住”的核心是：
- **USD-authored 的纹理 asset path（例如 `../../Materials/Textures/*.png`）是否能被 resolver 正确解析**，从而进入 copy+rewrite 映射。

下一步最关键的动作：
1) 用正确的 `UsdShade` 脚本确认 v9 的 shader inputs 是否还在指向 `../../Materials/Textures/*.png`。
2) 重新跑 headless render，grep `UsdToMdl` missing texture 错误是否消失。
3) 若仍失败：回到 `report.json` 看这些纹理是否 `resolved_path: None`，然后继续加强 resolver（尤其是大小写/相对路径/alias 的组合情况）。
