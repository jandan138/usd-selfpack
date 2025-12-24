# CLI 速查（2025-12-24）

核心入口：`./scripts/isaac_python.sh -m usd_asset_packager ...`

常用参数：
- `--input <scene.usd>` 主场景
- `--out <out_dir>` 输出目录
- `--copy-usd-deps` 复制子 USD/GLB 依赖（GLB 自动转换为 USD）
- `--flatten none|layerstack|full` 打平 layerstack（full 当前等同 layerstack）
- `--collision-strategy keep_tree|hash_prefix` 文件命名策略
- `--dry-run` 仅扫描与报告，不复制不改写
- `--log-level DEBUG|INFO|WARNING`

示例：
- Dry-run：`./scripts/isaac_python.sh -m usd_asset_packager --input scene.usd --out out_dir --dry-run`
- 复制依赖并打平：`./scripts/isaac_python.sh -m usd_asset_packager --input scene.usd --out out_dir --copy-usd-deps --flatten layerstack`
- 打开结果（自动 MDL 环境）：`./scripts/open_in_isaac_ui.sh out_dir/scene.usd`

相关代码：
- CLI 参数解析：[src/usd_asset_packager/cli.py](../../src/usd_asset_packager/cli.py)
- 业务流程入口：[src/usd_asset_packager/packager.py](../../src/usd_asset_packager/packager.py)
