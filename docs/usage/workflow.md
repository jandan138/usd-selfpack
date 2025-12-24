# 推荐工作流（2025-12-24）

1) 预检查（不写文件）：
   - `./scripts/isaac_python.sh -m usd_asset_packager --input scene.usd --out out_dir --dry-run`
   - 查看 out_dir/report.json、out_dir/logs/packager.log。
2) 正式打包：
   - `./scripts/isaac_python.sh -m usd_asset_packager --input scene.usd --out out_dir --copy-usd-deps`
   - 如需打平：附加 `--flatten layerstack`。
3) 打开验证：
   - `./scripts/open_in_isaac_ui.sh out_dir/scene.usd`
   - 或手动启动：`./scripts/launch_isaac_with_env.sh out_dir --/app/file/open=out_dir/scene.usd`

输出目录结构示例：
- out_dir/scene.usd (改写后的 root)
- out_dir/scene_flatten.usda (flatten 结果，若启用)
- out_dir/textures/...
- out_dir/materials/...
- out_dir/assets/... (子 USD 与转换后的 GLB)
- out_dir/env/mdl_paths.env
- out_dir/report.json
- out_dir/logs/packager.log

相关代码：
- 报告与 MDL env 生成：[src/usd_asset_packager/report.py](../../src/usd_asset_packager/report.py)
- 打包流程：[src/usd_asset_packager/packager.py](../../src/usd_asset_packager/packager.py)
