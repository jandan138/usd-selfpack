#!/usr/bin/env bash
set -euo pipefail

# 启动 Isaac Sim 前自动加载打包输出的 env/mdl_paths.env 并设置 MDL_SYSTEM_PATH。
# 使用示例：
#   ./scripts/launch_isaac_with_env.sh out_dir [extra args passed to isaac-sim.sh]
# 若只想生成环境变量而不启动，可设置 DRY_LAUNCH=1。

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <out_dir> [isaac-sim args...]" >&2
  exit 2
fi

OUT_DIR="$1"
shift || true
ENV_FILE="${OUT_DIR}/env/mdl_paths.env"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "[WARN] ${ENV_FILE} not found. Will launch without MDL env; MDL shaders may fail." >&2
else
  # shellcheck source=/dev/null
  source "$ENV_FILE"
  export MDL_SYSTEM_PATH
  export MDL_SEARCH_PATH
  echo "[INFO] Loaded MDL env from ${ENV_FILE}" >&2
fi

# 复用 isaac_python.sh 的定位逻辑
resolve_isaac_root() {
  if [[ -n "${ISAAC_SIM_ROOT:-}" && -x "${ISAAC_SIM_ROOT}/isaac-sim.sh" ]]; then
    echo "$ISAAC_SIM_ROOT"
    return 0
  fi
  if [[ -x "/isaac-sim/isaac-sim.sh" ]]; then
    echo "/isaac-sim"
    return 0
  fi
  local ov_root="${HOME}/.local/share/ov/pkg"
  if [[ -d "$ov_root" ]]; then
    local candidates=()
    while IFS= read -r -d '' dir; do
      candidates+=("$dir")
    done < <(find "$ov_root" -maxdepth 1 -type d -name 'isaac_sim-*' -print0 2>/dev/null)
    if [[ ${#candidates[@]} -gt 0 ]]; then
      IFS=$'\n' read -r -d '' -a sorted < <(printf '%s\n' "${candidates[@]}" | sort -V && printf '\0') || true
      for (( idx=${#sorted[@]}-1; idx>=0; idx--)); do
        local dir="${sorted[$idx]}"
        [[ -z "$dir" ]] && continue
        if [[ -x "$dir/isaac-sim.sh" ]]; then
          echo "$dir"
          return 0
        fi
      done
    fi
  fi
  for base in /opt/nvidia/isaac-sim /opt/NVIDIA/isaac-sim /opt/omniverse/isaac-sim; do
    if [[ -x "${base}/isaac-sim.sh" ]]; then
      echo "$base"
      return 0
    fi
  done
  return 1
}

ISAAC_ROOT="$(resolve_isaac_root)" || {
  echo "ERROR: Could not locate isaac-sim.sh. Set ISAAC_SIM_ROOT or adjust script." >&2
  exit 1
}

if [[ -n "${DRY_LAUNCH:-}" ]]; then
  echo "[INFO] DRY_LAUNCH set, not starting Isaac. MDL_SYSTEM_PATH=${MDL_SYSTEM_PATH:-}"
  exit 0
fi

RUNNER="${ISAAC_ROOT}/isaac-sim.sh"
if [[ ! -x "$RUNNER" ]]; then
  echo "ERROR: ${RUNNER} not executable. Edit scripts/launch_isaac_with_env.sh to match your install." >&2
  exit 1
fi

exec "$RUNNER" "$@"
