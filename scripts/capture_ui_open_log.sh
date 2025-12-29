#!/usr/bin/env bash
set -euo pipefail

# Capture Isaac/Kit UI open log into a deterministic evidence file.
#
# Usage:
#   ./scripts/capture_ui_open_log.sh <original|packed> <scene.usd> <evidence_dir> [extra kit args...]
#
# Notes:
# - This calls scripts/open_in_isaac_ui.sh, which loads <out_dir>/env/mdl_paths.env
#   (where out_dir is the directory containing the USD file).
# - The main Kit log is written via --/log/file=... into evidence_dir.

if [[ $# -lt 3 ]]; then
  echo "Usage: $0 <original|packed> <scene.usd> <evidence_dir> [extra kit args...]" >&2
  exit 2
fi

LABEL="$1"
SCENE="$2"
EVIDENCE_DIR="$3"
shift 3 || true

mkdir -p "$EVIDENCE_DIR"

# Normalize to absolute paths to avoid Kit/WD ambiguities.
if command -v realpath >/dev/null 2>&1; then
  SCENE="$(realpath "$SCENE")"
  EVIDENCE_DIR="$(realpath "$EVIDENCE_DIR")"
else
  SCENE="$(cd "$(dirname "$SCENE")" && pwd)/$(basename "$SCENE")"
  EVIDENCE_DIR="$(cd "$EVIDENCE_DIR" && pwd)"
fi

LOG_FILE="${EVIDENCE_DIR}/ui_open_${LABEL}.log"

# If DISPLAY is unset, open_in_isaac_ui.sh will add --no-window automatically.
exec "$(dirname "$0")/open_in_isaac_ui.sh" "$SCENE" --/log/file="$LOG_FILE" "$@"
