#!/bin/sh

set -eu

PAGE47_ROOT=/home/ubuntu/page47-preflight
cd "$PAGE47_ROOT"
if ! /usr/bin/flock -n /tmp/page47-snapshotter.lock sh -c '
  "$1/.venv/bin/python" "$1/scripts/snapshotter.py" \
    --config "$1/config/cities/seattle.yaml" \
    --store "$1/runtime/evidence/seattle"
  "$1/.venv/bin/python" "$1/scripts/snapshotter.py" \
    --config "$1/config/cities/denver.yaml" \
    --store "$1/runtime/evidence/denver"
  "$1/.venv/bin/python" "$1/scripts/apply_captured_events.py" \
    --config "$1/config/cities/seattle.yaml" \
    --database "$1/runtime/records/seattle.sqlite3" \
    --evidence-root "$1/runtime/evidence/seattle"
  "$1/.venv/bin/python" "$1/scripts/apply_captured_events.py" \
    --config "$1/config/cities/denver.yaml" \
    --database "$1/runtime/records/denver.sqlite3" \
    --evidence-root "$1/runtime/evidence/denver"
  "$1/.venv/bin/python" "$1/scripts/read_captured_attachments.py" \
    --database "$1/runtime/records/seattle.sqlite3" \
    --evidence-root "$1/runtime/evidence/seattle" \
    --substance-config "$1/config/substance.yaml"
  "$1/.venv/bin/python" "$1/scripts/apply_pdf_placements.py" \
    --config "$1/config/cities/seattle.yaml" \
    --database "$1/runtime/records/seattle.sqlite3" \
    --evidence-root "$1/runtime/evidence/seattle"
' sh "$PAGE47_ROOT"; then
  printf '%s\n' "Page 47 snapshot skipped because another capture is still running." >&2
  exit 1
fi
