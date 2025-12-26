# Changelog（2025-12-24）

## 0.1.0
- 初版：USD 自包含打包，纹理/MDL 复制与改写，报告与 MDL env 生成。
- 新增：GLB 自动转换为 USD 并改写引用。
- 新增：`--flatten` 支持 layerstack 打平，输出单一 USD。
- 文档：新增 docs 目录索引、使用指南、设计说明、运维与排障。

## Unreleased
- 修复：外部 USD layer（不在 base_root 下）不再使用 basename 输出，改为哈希分桶路径以避免同名覆盖导致的 stage 组成错误。
- 改进：打包过程中断后重复运行同一 out_dir 时会跳过已拷贝且大小一致的文件，加快断点续跑。