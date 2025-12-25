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

# Normalize to absolute paths to avoid Kit/WD ambiguities.
if command -v realpath >/dev/null 2>&1; then
  SCENE_PATH="$(realpath "$SCENE_PATH")"
else
  SCENE_PATH="$(cd "$(dirname "$SCENE_PATH")" && pwd)/$(basename "$SCENE_PATH")"
fi

OUT_DIR="$(cd "$(dirname "$SCENE_PATH")" && pwd)"

# In containers / SSH sessions there is often no X server.
# Isaac Sim UI requires a working display; otherwise prefer headless startup.
if [[ -z "${DISPLAY:-}" ]]; then
  has_no_window=0
  for arg in "$@"; do
    if [[ "$arg" == "--no-window" ]]; then
      has_no_window=1
      break
    fi
  done
  if [[ "$has_no_window" -eq 0 ]]; then
    echo "[WARN] DISPLAY is not set; adding --no-window (headless)." >&2
    set -- --no-window "$@"
  fi
fi

# Default log location under the package folder (unless user already set one).
has_log_file=0
for arg in "$@"; do
  if [[ "$arg" == --/log/file=* ]]; then
    has_log_file=1
    break
  fi
done
if [[ "$has_log_file" -eq 0 ]]; then
  mkdir -p "${OUT_DIR}/logs"
  set -- --/log/file="${OUT_DIR}/logs/kit_open.log" "$@"
fi

# 先加载环境并定位 isaac-sim.sh
source "$(dirname "$0")/launch_isaac_with_env.sh" "$OUT_DIR" --/app/file/open="${SCENE_PATH}" "$@"
