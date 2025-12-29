# 质量评估报告（测试覆盖与 CI/CD）

版本：v0.1  
日期：2025-12-29  
仓库提交：cc49b659b2321811499a6a92102fd53954839959

## 现状盘点
- 自动化测试：仓库声明 dev 依赖 pytest，但尚未发现 tests/\* 用例与覆盖率配置
- CI/CD：未发现现有 CI 配置（.github/workflows 或 GitLab CI）
- 手动验证：依赖 scripts/render_one_frame.py、compare_usd_prims.py 与 UI 日志证据

## 建议测试策略（pytest + coverage）
- 单元：scan/rewrite/copy 的核心分支与异常路径
  - scan：listOp 兼容、AssetPath/列表处理、MDL import/resource 正则解析
  - copy：MDL/Textures 分桶、UDIM 拷贝、GLB 转换错误分支（通过模拟不可用 converter）
  - rewrite：subLayerPaths 相对改写、references/payloads 替换与失败原因
- 集成：在 Isaac Python 环境下运行 headless 渲染与 prim 差异报告
  - scripts/render_one_frame.py：输出 render.log 与 rgb 图片，grep 关键错误
  - scripts/compare_usd_prims.py：输出 prim_diff_report.json 与位姿差异
- 覆盖率：新增 coverage 配置，目标 ≥ 70%（核心路径）

## CI/CD 建议
- GitHub Actions：\n
  - Job1（Python）：lint + pytest + coverage 报告\n
  - Job2（容器化 Isaac）：运行最小集成验证脚本（需缓存 Isaac 镜像或使用自托管 runner）\n
- 报告产物：上传 report.json、env/mdl_paths.env、render.log 与 diff 报告供审阅

## 风险与缓解
- Isaac 环境下载/许可证限制：优先自托管 runner 或跳过容器化集成，保留本地验证\n
- 组件版本差异：在 CI 中记录 omni/usd 组件版本与运行日志首段，便于比对

## 证据索引（来源于调试记录）
- 渲染验证与差异框架：[2025-12-25_prim-verify-and-render-diff/index.md](file:///shared/smartbot/zzh/my_dev/usd-selfpack/docs/debug_sessions/2025-12-25_prim-verify-and-render-diff/index.md)
- UI 日志证据与归档规范：[2025-12-26_task9-ui-mdl-red/evidence/README.md](file:///shared/smartbot/zzh/my_dev/usd-selfpack/docs/debug_sessions/2025-12-26_task9-ui-mdl-red/evidence/README.md)
