# evidence 目录说明（2025-12-29 follow-up）

本目录用于归档本次 follow-up 的关键证据，避免只凭口述推进。

建议最少保存：

- `ui_open_pack_mdlpkgfix_2025-12-29-1034.log`
  - 打开 `output/task9_interaction_dynamic_v6_pack_mdlpkgfix_2025-12-29-1034/scene_interaction_dynamic_v6.usd` 的 UI 日志
  - 重点保留首个 `.glb` 相关 error 片段（无需全量）

- `red_prims_notes.md`
  - 红色 prim 的 prim path（例如 `/root/obj__03`）
  - UI 面板展示的 asset path（例如 `.../3.glb`）

- `report_glb_snippet.txt`
  - 从输出目录 `report.json` 里摘录与 `3.glb` 对应的：
    - `asset_type == glb` 的条目（含 resolved_path）
    - 对应 copy/conversion 结果（success/reason/target_path）

如果后续启用 `--copy-usd-deps` 产生新输出，建议把新旧两份 report 的 glb 片段都保存，便于对比。
