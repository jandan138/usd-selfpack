# evidence 目录说明

本目录用于归档“可复现证据”，避免只凭口述排查。

建议文件命名（按实际情况取其一或全部）：

- `ui_open_original.log`
  - 在 UI 中打开原始 USD 时的完整日志输出
- `ui_open_packed.log`
  - 在 UI 中打开打包 USD 时的完整日志输出
- `ui_env.txt`
  - 启动方式与环境信息（例如是否加载了打包输出的 `env/mdl_paths.env`，以及关键环境变量）
- `red_prims_notes.md`
  - 1~3 个红色 prim 的 prim path、绑定的 material、shader 的 `info:mdl:sourceAsset` 等信息（手抄即可）

最小要求：至少提供 `ui_open_original.log` 与 `ui_open_packed.log`，并明确两者的启动方式一致。
