# Isaac 环境与运行（2025-12-24）

运行前提：使用自带的 Isaac Python。
- 入口脚本：[scripts/isaac_python.sh](../../scripts/isaac_python.sh)
- 自动定位 ISAAC_SIM_ROOT，配置 PYTHONPATH 与 LD_LIBRARY_PATH。

启动 UI（自动加载 MDL 搜索路径）：
- `./scripts/open_in_isaac_ui.sh out_dir/scene.usd`
- 内部会读取 out_dir/env/mdl_paths.env 并调用 isaac-sim.sh。

仅设置环境不启动：
- `DRY_LAUNCH=1 ./scripts/launch_isaac_with_env.sh out_dir`

环境文件来源：
- 打包时生成 [out_dir/env/mdl_paths.env](../../scripts/launch_isaac_with_env.sh)（路径拼接自复制后的 materials/）。

问题排查：
- 若提示找不到 isaac-sim.sh，请设置 `ISAAC_SIM_ROOT` 或调整脚本内路径列表。
- 若 UI 打开仍缺 MDL，请确认 MDL_SYSTEM_PATH/MDL_SEARCH_PATH 已在启动前注入，并检查 out_dir/report.json 的警告。