# 接口规范（CLI、报告与环境示例）

版本：v0.1  
日期：2025-12-29  
仓库提交：cc49b659b2321811499a6a92102fd53954839959

## CLI 入口与参数
- 入口：`python -m usd_asset_packager` 或 [scripts/pack_usd.py](file:///shared/smartbot/zzh/my_dev/usd-selfpack/scripts/pack_usd.py)
- 参数定义：见 [cli.py](file:///shared/smartbot/zzh/my_dev/usd-selfpack/src/usd_asset_packager/cli.py#L9-L28)
  - 必填：`--input <主USD>`、`--out <输出目录>`
  - 常用：`--copy-usd-deps`、`--flatten {none|layerstack|full}`、`--no-convert-gltf`、`--converter {omni|fallback_gltf2usd}`、`--log-level {DEBUG|INFO|WARNING}`

## 示例命令
- Dry-run（仅扫描）：
  - `./scripts/isaac_python.sh -m usd_asset_packager --input scene.usd --out out_dir --dry-run`
- 正式打包（含 GLB 转换与复制子 USD）：
  - `./scripts/isaac_python.sh -m usd_asset_packager --input scene.usd --out out_dir --copy-usd-deps`
- 打开 UI（注入 env/mdl_paths.env）：
  - `./scripts/open_in_isaac_ui.sh out_dir/scene.usd`

## 报告格式（report.json 片段）
```json
{
  "stats": {
    "textures": 123,
    "mdls": 42,
    "usd": 17,
    "glb": 3,
    "remote": 0,
    "copy_fail": 1,
    "rewrite_fail": 2
  },
  "mdl_paths": ["/abs/path/to/out_dir/materials", "..."],
  "warnings": ["glTF converter unavailable; enable omni.kit.asset_converter"],
  "assets": [
    {
      "asset_type": "mdl",
      "original_path": "../../Materials/DayMaterial.mdl",
      "resolved_path": "/abs/src/.../DayMaterial.mdl",
      "layer_identifier": "file.usd",
      "prim_path": "/root/materials/Day",
      "attr_name": "info:mdl:sourceAsset",
      "is_remote": false,
      "is_udim": false,
      "notes": ""
    }
  ],
  "copies": [
    {
      "asset": { "...": "..." },
      "target_path": "out_dir/materials/external/<hash>/DayMaterial.mdl",
      "success": true,
      "reason": "already copied"
    }
  ],
  "rewrites": [
    {
      "layer_identifier": "file.usd",
      "prim_path": "/root/materials/Day",
      "attr_name": "info:mdl:sourceAsset",
      "before": "../../Materials/DayMaterial.mdl",
      "after": "DayMaterial.mdl",
      "success": true,
      "reason": ""
    }
  ],
  "notes": "UI 进程若未在启动前设置 MDL_SYSTEM_PATH/MDL_SEARCH_PATH..."
}
```

## 环境文件（env/mdl_paths.env 示例）
```
export MDL_SYSTEM_PATH="/abs/out_dir/materials:/isaac-sim/materials"
export MDL_SEARCH_PATH="/abs/out_dir/materials:/isaac-sim/materials"
```

## 错误处理与诊断
- 复制/转换失败：`CopyAction.reason` 提供失败原因（例如 `converter unavailable`、`source missing`）
- 改写失败：`RewriteAction.success=false` 与 `reason="not found in list"` 或异常信息
- UI 日志诊断：建议通过 [scripts/capture_ui_open_log.sh](file:///shared/smartbot/zzh/my_dev/usd-selfpack/scripts/capture_ui_open_log.sh) 归档首个错误片段

## 证据索引（来源于调试记录）
- 典型改写/失败案例与验证方法：[2025-12-25_prim-verify-and-render-diff/index.md](file:///shared/smartbot/zzh/my_dev/usd-selfpack/docs/debug_sessions/2025-12-25_prim-verify-and-render-diff/index.md)
- MDL env 生成与使用：[2025-12-25-mdl-materials-packaging/attempts.md](file:///shared/smartbot/zzh/my_dev/usd-selfpack/docs/debug_sessions/2025-12-25-mdl-materials-packaging/attempts.md)
