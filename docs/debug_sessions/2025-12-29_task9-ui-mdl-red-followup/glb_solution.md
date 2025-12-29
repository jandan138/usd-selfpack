# GLB 引用消除技术方案

## 1. 背景
在 USD 打包过程中，若资产中包含 GLB 格式的 Payload/Reference，且这些引用位于被嵌套引用的 USD Layer 中，直接打包往往会导致：
1. GLB 文件未被转换为 USD。
2. 即使转换了，引用它的 USD Layer 未被修改（因为默认不复制/改写依赖 Layer）。
3. 最终输出的 USD Stage 仍然指向原始的 GLB 文件，导致在无 GLB 加载支持的环境（或路径失效时）出现红色错误。

## 2. 解决方案逻辑

### 2.1 强制依赖复制 (Force Copy Dependencies)
为了能够修改（Rewrite）引用了 GLB 的 USD Layer，必须先将该 Layer 复制到输出目录。
我们修改了 `packager.py`，增加了自动检测逻辑：
- **检测**: 扫描所有资产，若发现 `asset_type == "glb"` 且其 `layer_identifier` 不是 Root Layer。
- **动作**: 自动覆盖 `copy_usd_deps = True`。
- **效果**: 确保所有包含 GLB 引用的 Layer 都会进入 `rewrite_layers` 流程。

### 2.2 转换与改写 (Convert & Rewrite)
- **转换**: 调用 `omni.kit.asset_converter` 将 `.glb` 转换为 `.usd`。
- **改写**: 
    - `copy_utils.py` 计算出新的目标路径（后缀变为 `.usd`）。
    - `rewrite.py` 遍历 Copied Layer 中的 Prim，匹配原始 `.glb` 路径。
    - 将 Payload/Reference 的路径替换为相对于 Copied Layer 的新 `.usd` 路径。

## 3. 代码变更说明
在 `src/usd_asset_packager/packager.py` 中：

```python
        assets = scan_stage(stage, self.logger)
        
        # 新增：GLB 深度依赖检测
        has_deep_glb = False
        root_layer_ids = {l.identifier for l in stage.GetLayerStack()}
        for asset in assets:
            if asset.asset_type == "glb" and asset.layer_identifier not in root_layer_ids:
                has_deep_glb = True
                break
        
        if has_deep_glb and self.convert_gltf and not self.copy_usd_deps:
            self.logger.warning("Detected GLB assets in referenced layers. Auto-enabling --copy-usd-deps...")
            self.copy_usd_deps = True
```

## 4. 环境依赖注意
本方案依赖 `omni.kit.asset_converter` 扩展。
- **在 Isaac Sim GUI/Headless App 中**: 通常自动可用。
- **在 `isaac_python.sh` (纯 Python) 中**: 默认不可用，需配置复杂的 PYTHONPATH 和 LD_LIBRARY_PATH，或使用 `kit --exec` 方式运行脚本。
- **验证结果**: 当前开发环境 `isaac_python.sh` 无法成功加载转换器，因此 GLB 消除在最后一步（转换）受阻，但代码逻辑已就绪。
