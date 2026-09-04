#!/bin/sh

set -eu

PAGE47_ROOT=/home/ubuntu/page47-preflight
cd "$PAGE47_ROOT"
if ! /usr/bin/flock -n /tmp/page47-snapshotter.lock \
  "$PAGE47_ROOT/.venv/bin/python" "$PAGE47_ROOT/scripts/snapshotter.py" \
  --config "$PAGE47_ROOT/config/cities/seattle.yaml" \
  --store "$PAGE47_ROOT/runtime/evidence/seattle"; then
  printf '%s\n' "Page 47 snapshot skipped because another capture is still running." >&2
  exit 1
fi
