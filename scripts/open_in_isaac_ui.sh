#!/usr/bin/env bash
set -euo pipefail

# 一键启动 Isaac Sim UI 并打开指定 USD，自动加载 env/mdl_paths.env。
# 用法： ./scripts/open_in_isaac_ui.sh <packed_scene.usd> [extra kit args]

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <packed_scene.usd> [extra kit args]" >&2
  exit 2
fi

SCENE_PATH="$1"
shift || true
OUT_DIR="$(cd "$(dirname "$SCENE_PATH")" && pwd)"

# 先加载环境并定位 isaac-sim.sh
source "$(dirname "$0")/launch_isaac_with_env.sh" "$OUT_DIR" --/app/file/open="${SCENE_PATH}" "$@"
