# USD 资产同目录自包含打包器

面向 Isaac Sim / Omniverse 的 USD 资产自包含打包工具，解决 UI 打开 USD 时纹理 / MDL 丢失、反复手动 export `MDL_SYSTEM_PATH` 的痛点。所有 Python 调用必须通过 `scripts/isaac_python.sh` 使用 Isaac 自带的 Python 环境运行。

## 功能要点
- **深度递归扫描**: 遍历 layer / references / payload / subLayers / 材质网络（UsdShade 纹理、MDL shader）。
- **智能资产归拢**: 
  - 纹理 -> `out_dir/textures`
  - MDL -> `out_dir/materials`
  - 子 USD/GLB -> `out_dir/assets` (GLB 自动转换为 USD)
- **路径重写**: 将所有绝对路径改写为相对路径，实现真正的“自包含”分发。
- **自动化 GLB 转换**: 自动检测并转换引用的 GLB/GLTF 文件为 USD，并正确链接材质。
- **环境隔离**: 生成 `out_dir/env/mdl_paths.env`，配合一键启动脚本，无需手动配置全局环境变量。

## 环境要求
- 运行于 Isaac Sim Docker 或 Standalone，确保可 `import pxr`。
- 所有命令通过 [scripts/isaac_python.sh](scripts/isaac_python.sh) 调用。

## 快速开始 (以 Task9 场景为例)

假设我们要打包一个复杂的场景（如 Task9），其中包含深层嵌套的 USD 引用和 GLB 资产。

**输入文件**: `/path/to/task9/scene.usd`
**输出目录**: `output/task9_packed`

### 1. 执行打包命令

使用 `pack_usd.py` 进行打包。建议开启 `--copy-usd-deps` 以确保深层引用的 USD Layer 被复制并改写（这对于处理嵌套的 GLB 引用至关重要），并开启 `--convert-gltf` 自动转换模型。

```bash
./scripts/isaac_python.sh scripts/pack_usd.py \
  --input /path/to/task9/scene.usd \
  --out output/task9_packed \
  --copy-usd-deps \
  --convert-gltf \
  --log-level INFO
```

**参数说明**:
- `--copy-usd-deps`: **强烈推荐**。不仅复制纹理，还递归复制所有被引用的 USD 文件。这允许打包器改写子 USD 中的路径，解决深层嵌套资源（如 GLB）的引用问题。
- `--convert-gltf`: 自动调用 Isaac Sim 的转换器将 GLB/GLTF 转为 USD。

### 2. 检查输出报告

打包完成后，查看 `output/task9_packed/report.json`。关注以下字段：
- `assets`: 列出了所有被处理的资产。
- `success`: 确认所有 GLB 转换状态为 `true`。

### 3. 打开打包后的场景

我们提供了一键启动脚本，它会自动加载必要的 MDL 搜索路径，确保材质显示正确（解决“红色路径”警告但材质正常的问题）。

```bash
./scripts/open_in_isaac_ui.sh output/task9_packed/scene.usd
```

**注意**: 
- 打开后，如果看到 Material 属性面板中的 MDL 路径显示为红色（如 `@gltf/pbr.mdl@`），这是正常的。只要场景中的物体正确显示了纹理（如木纹、金属），即说明 MDL 系统工作正常。

## 常见问题与改进

### 为什么以前要 export MDL_SYSTEM_PATH？
MDL 查找依赖全局搜索路径。UI 进程启动后再设置无效。我们现在通过生成 `env/mdl_paths.env` 并由启动脚本预加载，彻底解决了这个问题。

### GLB 转换与 MDL
- 本工具会自动将 GLB 转换为 USD，并使用 `gltf/pbr.mdl` 着色器。
- 转换后的 USD 会引用提取出的纹理（`.png`），方便后续编辑。
- 引用系统 MDL（如 `gltf/pbr.mdl`）在 UI 中可能显示为红色路径，这是 Isaac Sim 的标准行为，不影响渲染。

### 目录结构
- [scripts/isaac_python.sh](scripts/isaac_python.sh): Isaac Python 环境包装器。
- [scripts/pack_usd.py](scripts/pack_usd.py): 打包工具入口。
- [scripts/convert_glb_to_usd.py](scripts/convert_glb_to_usd.py): 独立的 GLB 转换工具（基于 SimulationApp）。
- [scripts/open_in_isaac_ui.sh](scripts/open_in_isaac_ui.sh): 带环境配置的 UI 启动器。
- [src/usd_asset_packager](src/usd_asset_packager): 核心源码。

## 高级选项
- **Dry-run**: `--dry-run` 仅扫描不复制，用于检查依赖。
- **Flatten**: `--flatten layerstack` 可将层级打平，但通常不建议用于保留原始引用的场景。
- **No Convert**: `--no-convert-gltf` 禁用转换，仅复制 GLB 文件（适用于目标环境支持直接加载 GLB 的情况）。
