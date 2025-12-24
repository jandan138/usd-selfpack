# 常见问题排查（2025-12-24）

1) MDL 仍然缺失
- 检查 out_dir/report.json 中的 warnings。
- 确认 UI 是通过 `scripts/open_in_isaac_ui.sh` 启动。
- 如果 MDL 为模块名无物理文件，需手动提供 MDL_SYSTEM_PATH/MDL_SEARCH_PATH 或做材质 distill。

2) GLB 转换失败
- 查看 logs/packager.log 中的 usd_from_gltf 输出。
- 确认 usd_from_gltf 在 PATH 中；必要时手动转换并替换 out_dir/assets 内文件。

3) 远程资源未下载
- 设计上默认不下载远程资源；请手动同步到本地后重跑。

4) Flatten 结果不完整
- 确认已使用 `--flatten layerstack` 且 `--copy-usd-deps` 被启用。
- 检查报告中的 rewrite_fail/copy_fail 计数。

5) UDIM 贴图缺失
- 仅支持 `<UDIM>` 模式扫描 tiles；若命名不规范需手动补齐。

相关代码参考：
- 报告生成：[src/usd_asset_packager/report.py](../../src/usd_asset_packager/report.py)
- GLB 转换：[src/usd_asset_packager/glb.py](../../src/usd_asset_packager/glb.py)
- 扫描与改写：[src/usd_asset_packager/scan.py](../../src/usd_asset_packager/scan.py)、[src/usd_asset_packager/rewrite.py](../../src/usd_asset_packager/rewrite.py)
