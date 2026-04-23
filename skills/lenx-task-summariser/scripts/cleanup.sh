#!/usr/bin/env bash
# cleanup.sh — Remove all intermediate artifacts from the summarisation run.
# Usage: ./cleanup.sh <work-dir>
set -euo pipefail

WORK_DIR="${1:-.lenx-summariser-work}"

if [ -d "$WORK_DIR" ]; then
  rm -rf "$WORK_DIR"
fi
