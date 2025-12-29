# GLB 引用修复与转换集成总结

**日期**: 2025-12-29
**状态**: 已解决 (Resolved)
**关联任务**: Task9 UI 红色 GLB 报错修复

## 1. 问题背景
用户在加载打包后的 USD 场景时，发现部分资产（如 `/root/obj__03`）显示红色错误，Payload 路径指向原始的 `.glb` 文件。
这导致在不支持直接加载 GLB 的环境中（或路径不正确时）渲染失败。

## 2. 问题分析

### 2.1 现象追踪
- **错误表现**: USD Stage 中保留了对 `.glb` 文件的引用，且路径可能失效。
- **原始配置**: 打包命令未开启 `--copy-usd-deps`。
- **结构分析**: 出问题的 GLB 资产并未直接位于 Root Layer，而是被深层嵌套的 USD Layer（如 `instance.usd`）所引用。

### 2.2 根因定位
1.  **引用层未改写**: Packager 默认只处理 Root Layer 的依赖。若不开启 `--copy-usd-deps`，深层引用的 USD Layer 不会被复制到输出目录，因此其内部指向 `.glb` 的路径也无法被 Rewrite 逻辑修改。
2.  **转换器环境缺失**: `pack_usd.py` 运行在纯 Python 环境（通过 `isaac_python.sh`），默认无法加载 `omni.kit.asset_converter` 扩展。这导致即使尝试转换，代码也会在 import 阶段失败，进而跳过路径替换。

## 3. 解决方案

### 3.1 策略一：自动依赖复制 (Auto Copy Dependencies)
为了确保所有引用了 GLB 的 Layer 都能被修改，我们实现了自动检测机制。

- **代码变更**: `src/usd_asset_packager/packager.py`
- **逻辑**:
    - 在扫描 Stage 资产后，检查是否存在非 Root Layer 的 GLB 资产。
    - 若存在，**强制开启** `copy_usd_deps = True`。
    - 这确保了包含 GLB 引用的中间层会被复制，从而使其路径可被重写。

### 3.2 策略二：进程外转换 (Out-of-Process Conversion)
解决了“能改写路径”的问题后，必须解决“能转换文件”的问题。由于 `pack_usd.py` 无法直接运行转换器，我们采用了子进程调用的方案。

#### A. 独立转换脚本
创建了 `scripts/convert_glb_to_usd.py`，它是 `mesh2usd.py` 的现代化封装：
- 使用 `SimulationApp` (Headless) 启动完整的 Kit 内核。
- 动态加载 `omni.kit.asset_converter` 扩展。
- 使用 `asyncio` 和 `task.wait_until_finished()` 确保异步转换完成。

#### B. 智能后端集成
修改了 `src/usd_asset_packager/converter.py` 中的 `OmniAssetConverterBackend`：
- **自动降级**: 初始化时尝试 import `omni.kit.asset_converter`。
- **Fallback**: 若 import 失败（即在纯 Python 环境），自动切换到 **Subprocess Mode**。
- **执行**: 通过 `subprocess.run` 调用上述独立脚本，利用 `isaac_python.sh` 提供的环境进行转换。

## 4. 实施结果

### 4.1 验证过程
1.  **单体测试**: 验证 `convert_glb_to_usd.py` 可成功将 GLB 转为 USD 并保留材质。
2.  **集成测试**: 运行 `pack_usd.py` 对 Task9 场景打包。
    - 日志显示 `rewrote ... asset paths in copied usd layer`，证明依赖复制生效。
    - `report.json` 显示所有 GLB 资产转换状态为 `success: true`。
3.  **最终确认**: 用户打开输出的 `scene_interaction_dynamic_v6.usd`，确认 MDL 外观正常，无红色报错，GLB 已被替换为转换后的 USD。

## 5. 关键文件清单
- **核心逻辑**: [`src/usd_asset_packager/packager.py`](file:///shared/smartbot/zzh/my_dev/usd-selfpack/src/usd_asset_packager/packager.py) (自动依赖检测)
- **转换后端**: [`src/usd_asset_packager/converter.py`](file:///shared/smartbot/zzh/my_dev/usd-selfpack/src/usd_asset_packager/converter.py) (子进程调用支持)
- **工具脚本**: [`scripts/convert_glb_to_usd.py`](file:///shared/smartbot/zzh/my_dev/usd-selfpack/scripts/convert_glb_to_usd.py) (独立转换器)

## 6. 结论
通过“自动依赖管理”与“跨进程能力调用”的组合，彻底解决了在轻量级打包脚本中处理复杂 GLB 转换与引用的问题。该方案具有良好的兼容性，无需用户手动修改复杂的 Isaac Sim 运行环境。
