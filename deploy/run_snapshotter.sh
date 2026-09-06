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
  "$1/.venv/bin/python" "$1/scripts/read_captured_attachments.py" \
    --database "$1/runtime/records/denver.sqlite3" \
    --evidence-root "$1/runtime/evidence/denver" \
    --substance-config "$1/config/substance.yaml"
  "$1/.venv/bin/python" "$1/scripts/apply_pdf_placements.py" \
    --config "$1/config/cities/seattle.yaml" \
    --database "$1/runtime/records/seattle.sqlite3" \
    --evidence-root "$1/runtime/evidence/seattle"
  "$1/.venv/bin/python" "$1/scripts/apply_pdf_placements.py" \
    --config "$1/config/cities/denver.yaml" \
    --database "$1/runtime/records/denver.sqlite3" \
    --evidence-root "$1/runtime/evidence/denver"
  "$1/.venv/bin/python" "$1/scripts/notify_findings.py" \
    --web-config "$1/config/web.yaml" \
    --address-config "$1/config/address.yaml" \
    --notification-config "$1/config/notifications.yaml"
' sh "$PAGE47_ROOT"; then
  printf '%s\n' "Page 47 snapshot skipped because another capture is still running." >&2
  exit 1
fi
printf 'Page47SnapshotRunSuccess captured_at=%s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
