# GLB 处理（2025-12-24）

目标：将引用的 .glb/.gltf 转为 USD，复制到 out_dir/assets，并改写引用。

实现要点：
- 扫描阶段将后缀 .glb/.gltf 标记为 `glb` 类型。
- 复制阶段调用 `usd_from_gltf` 转换：
  - 找不到转换器时返回失败并写入 report/log。
  - 目标文件名强制改为 .usd。
- 改写阶段将引用指向转换后的相对路径。

关键代码：
- 转换工具封装：[src/usd_asset_packager/glb.py](../../src/usd_asset_packager/glb.py)
- 复制策略与命名：[src/usd_asset_packager/copy_utils.py](../../src/usd_asset_packager/copy_utils.py)
- 扫描类型识别：[src/usd_asset_packager/scan.py](../../src/usd_asset_packager/scan.py)

使用建议：
- 如果自定义 usd_from_gltf 路径，请确保在 PATH 中可被 `shutil.which` 找到。
- 转换失败时，可手动转换后放入 out_dir/assets 并更新引用。