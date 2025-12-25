# 下一阶段计划：让 MDL 材质在 Isaac/Kit 中可编译可加载

> 背景：当前打包输出的 USD 里，部分 shader prim 的 `info:mdl:sourceAsset` 仍是 `../../Materials/*.mdl`，导致 neuraylib 把它当作模块名 `::..::..::Materials::*`，从而报 C120 missing module，最终 Hydra 报 “Empty identifier” 并出现红材质。

## 目标（Definition of Done）
- 打包输出的 USD 中，相关 shader prim 的 `info:mdl:sourceAsset` 不再包含 `..` 路径段（例如不再出现 `../../Materials/*.mdl`）。
- 用 `scripts/render_one_frame.py` 对输出 `scene.usd` 做离屏渲染时：
  - 不再出现 neuraylib `C120 could not find module '::..::..::Materials::...'`
  - 不再出现 `Failed to create MDL shade node ... Empty identifier`（至少针对已知出问题的 DayMaterial/Num595...）

## 计划步骤
1. 定位 rewrite 没命中的真实原因
   - 在源码层面追踪：`scan` 记录到的字段名/类型是否与 rewrite 的条件一致。
   - 重点确认：
     - 该值到底是“属性 attribute”还是“元数据 metadata”写在 layer 里
     - rewrite 是否遍历到该字段（例如只处理了 inputs，而没处理 `info:*` 属性）

2. 扩大/修正 rewrite 覆盖面（最小改动原则）
   - 让 rewrite 对以下情况都能生效：
     - 属性名等于 `info:mdl:sourceAsset`
     - 或者更保守：所有 `info:mdl:*sourceAsset*` 类字段都做同样的“去掉 `..`”规则（仅针对值看起来像 `.mdl` 的 AssetPath）。
   - 改写策略：把 `../../Materials/X.mdl` 改成 `X.mdl`（basename），让 MDL search path 去解析。

3. 重新打包 + 双重验证
   - 重新运行 packager 生成新输出目录。
   - 验证 1（静态）：用 `scripts/dump_usd_prim.py` 抽查 2-3 个已知问题 shader prim，确认 `info:mdl:sourceAsset` 已变为 `X.mdl`。
   - 验证 2（动态）：用 `scripts/render_one_frame.py` 离屏渲染，确认 MDL 错误链消失。

4. （可选，独立问题）处理 `instance.usd` 等引用缺失
   - 若渲染仍被大量缺失引用阻塞，再单独追：scan 是否漏掉模型 USD 依赖、copy-usd-deps 是否覆盖到 payload/reference 组合等。

## 风险与回滚
- 风险：某些材质需要的不是 `X.mdl` 文件名，而是更严格的 module 名/包结构；basename 改写可能对少数 case 不适用。
- 回滚：rewrite 改动尽量做成“仅当包含 `..` 且扩展名为 `.mdl` 时才改写”，避免影响其它合法路径。
