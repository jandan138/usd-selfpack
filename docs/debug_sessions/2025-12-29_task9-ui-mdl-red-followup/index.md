# 2025-12-29 — task9：MDL 全红已消失；遗留 GLB payload 红色（/root/obj__03）排查记录

> 背景：延续 [2025-12-26_task9-ui-mdl-red](../2025-12-26_task9-ui-mdl-red/index.md)。
>
> - 2025-12-26：打包后 UI 大量红色，倾向 MDL 问题，但当时 UI log 里缺少“明确的编译错误行”。
> - 2025-12-29：我们已经拿到了明确的 MDLC 编译错误（你在 UI terminal 里贴的那段），并据此完成了一个布局修复；现在材质看上去正常、全红消失。
>
> 本文目标：把“已解决的 MDL 全红”固定成可复现结论，并把新出现的 GLB payload 红色问题落到可执行的证据链与下一步思路。

---

## 0. 本次（2025-12-29）验证口径

### 0.1 输入（原始）

- `/shared/smartbot/jiamingda/data_code/simbench/MesaTask-USD/simbench_shared/GRSceneUSD/task9/scene_interaction_dynamic_v6.usd`

### 0.2 输出（打包）

你本次运行的打包命令（材质已正常）：

- `cd /shared/smartbot/zzh/my_dev/usd-selfpack && ./scripts/isaac_python.sh scripts/pack_usd.py --input /shared/smartbot/jiamingda/data_code/simbench/MesaTask-USD/simbench_shared/GRSceneUSD/task9/scene_interaction_dynamic_v6.usd --out output/task9_interaction_dynamic_v6_pack_mdlpkgfix_2025-12-29-1034 --log-level INFO`

> 注意：这条命令 **没有** `--copy-usd-deps`，因此它不会把 referenced USD layers 全部复制到输出；它只会改写并导出 root layer stack（以及拷贝/改写扫描到的 texture/mdl/glb 等资产）。

---

## 1. 已解决：MDL 全红消失（材质恢复正常）

### 1.1 关键证据：MDLC 编译错误明确指向“相对 import 失效”

你在 UI terminal 里贴的关键报错（摘要）：

- `MDLC:COMPILER ... Num595f...mdl(...): C109 'camera_position' has not been declared`
- `... C109 'convert_to_left_hand' has not been declared`
- `... C109 'unpack_normal_map' has not been declared`
- `... C109 'OmniUe4Base' has not been declared`
- `Failed to create MDL shade node ... createMdlModule failed`

我们随后打开对应 `.mdl` 文件，确认其开头存在：

- `using .::OmniUe4Function import *;`
- `using .::OmniUe4Base import *;`

这些是“**同目录相对模块导入**”，语义是：`Num...mdl` 依赖的 `OmniUe4Function.mdl` / `OmniUe4Base.mdl` 必须在 **同一个包目录**。

### 1.2 Root cause：MDL 被按“单文件哈希分桶”，把同目录模块拆散

我们检查旧输出目录时发现：

- `Num595f...mdl` 在 `materials/external/<hashA>/`
- 但 `OmniUe4Base.mdl`、`OmniUe4Function.mdl` 可能在 `materials/external/<hashB>/`、`materials/external/<hashC>/`

这会导致：

- `using .::OmniUe4Base` 在 `hashA` 目录下解析不到同目录模块 → MDLC 报“未声明” → UI 红色。

### 1.3 修复策略：external MDL 改为“按源目录打包成一个 package”

修复的核心是：

- 对 external 的 `*.mdl`，不再按“文件路径”分桶，而按“源目录路径”统一分桶：
  - 同一个源 `.../Materials/` 下的 `.mdl` 全部落到 `materials/external/<dirhash>/`
- 对 MDL 内引用的 `./Textures/...` 资源，同样按“所属 mdl 的源目录 hash”放置到：
  - `textures/external/<dirhash>/textures/...`
- 然后在 `materials/external/<dirhash>/Textures` 处建立 alias（symlink）指回对应的 `textures/external/<dirhash>/textures`。

### 1.4 结果：你已验证“材质看上去正常，全红消失”

这说明：

- 2025-12-26 阶段 UI log 里看不见明确报错行的 `CompileFailed`，其根因极可能就是 MDL package 拆散导致的 MDLC 编译失败。
- 现在“MDL 同目录依赖 + 贴图 alias”链路基本闭环。

---

## 2. 新问题：GLB payload 红色（/root/obj__03 指向 3.glb）

### 2.1 现象

你在新输出 stage 里仍看到：

- `/root/obj__03` 找不到/红色
- 显示的 asset path 是红色：
  - `../../../../../../../zzh/my_dev/exciting-benchmark/scripts/assets/task9_tea_teapot_livingroom/task9_tea_teapot_livingroom/3.glb`

### 2.2 初步判断：这不是“MDL 全红”的同一类问题

现在材质已正常，说明：

- MDL 编译失败导致的全红已经解决；
- 剩余的红色更可能来自 **payload/reference 无法加载**（例如 `.glb` payload 没被转换、或 USD 里仍引用旧路径）。

### 2.3 为什么会出现：打包没有把 glb payload 改写/转换到输出（可能原因）

从现象看，打开 stage 时仍然引用原始的 `.../3.glb` 路径，这通常意味着至少发生了其中之一：

1) **转换没有发生**
   - 例如转换器不可用，或运行环境缺少 `omni.kit.asset_converter`。
   - 这种情况下，packager 会记录 glb 但无法生成对应的 `.usd`，因此 rewrite 也不会把 payload 改成新的 `.usd`。

2) **转换发生了，但引用该 glb 的 layer 没被改写**
   - 你本次命令没带 `--copy-usd-deps`，若 glb 引用位于某个 referenced layer（不在 root layer stack）里，那该 layer 可能不会被导出/改写到输出 → 仍保留旧 glb 路径。

3) **glb 在你打开 stage 的那台机器上路径本来就不可达**
   - 引用的是 `/shared/smartbot/zzh/my_dev/exciting-benchmark/...` 这类开发路径；如果 UI 机器不具备该路径，原始场景能显示可能是因为 UI 用了另一个 resolver/search root（或本地缓存），而打包输出没有。

---

## 3. 下一步解决思路（不改代码）

目标：让 `/root/obj__03` 这类 `.glb` payload 不再直接引用原始 `*.glb`，而是引用输出目录里的转换结果 `*.usd`。

### 3.1 先用 report.json 确认“3.glb 这条资产链路”走到了哪一步

在输出目录中检查两点：

- `report.json` 里 `asset_type == "glb"`、且与 `3.glb` 对应的条目：
  - 是否存在 `resolved_path`（能否找到源 glb）
- `report.json` 里的 copy/conversion 结果（`copies` 部分）：
  - 对应 `3.glb` 的 `success` 是否为 true
  - `reason` 是否提示 `converter unavailable` 或 `glTF conversion disabled`

若 conversion 没成功，优先解决“转换器不可用/未启用”。

### 3.2 若要彻底本地化引用：建议启用 `--copy-usd-deps`

原因：如果 glb payload 引用出现在 referenced/payloaded 的外部 USD layer 里（而不是 root layer stack），只有开启 `--copy-usd-deps`：

- 才会把那些 layer 一并复制到输出
- 并对这些 copied layers 做二次 rewrite（把内部引用改到输出目录）

这样才能保证“所有层级里出现的 glb 引用”都被改写到转换后的 `.usd`。

### 3.3 验证点（不需要贴大日志）

当你下一次生成新输出后，只要验证 3 点即可判断是否走通：

1) 输出目录存在 `assets_converted_gltf/`，且包含对应编号的 `.usd`
2) 打包后的 usd 文件里，`payload` 不再指向 `.../3.glb`，而指向 `.../assets_converted_gltf/.../3.usd`（或同等路径）
3) UI 打开时不再出现 `Cannot determine file format for ...*.glb:SDF_FORMAT_ARGS:target=usd` / 或不再红

---

## 4. evidence 归档建议

把你现在 UI 中看到的 3 个信息落到 evidence，后续 AI/排查者就不需要口述复现：

- `evidence/ui_open_pack_mdlpkgfix_2025-12-29-1034.log`（只要包含首个 glb 相关 error 段即可）
- `evidence/red_prims_notes.md`：写清楚
  - 红色 prim path（例如 `/root/obj__03`）
  - UI 面板显示的 asset path（就是那条 `.../3.glb`）
- `evidence/report_glb_snippet.txt`：从 `report.json` 摘录 `3.glb` 对应的资产记录和 copyAction 结果

