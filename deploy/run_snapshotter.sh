#!/bin/sh

set -eu

PAGE47_ROOT=/home/ubuntu/page47-preflight
cd "$PAGE47_ROOT"
exec 9>/tmp/page47-snapshotter.lock
if ! /usr/bin/flock -n 9; then
  printf '%s\n' "Page 47 snapshot skipped because another capture is still running." >&2
  exit 1
fi

"$PAGE47_ROOT/.venv/bin/python" "$PAGE47_ROOT/scripts/snapshotter.py" \
  --config "$PAGE47_ROOT/config/cities/seattle.yaml" \
  --store "$PAGE47_ROOT/runtime/evidence/seattle"
"$PAGE47_ROOT/.venv/bin/python" "$PAGE47_ROOT/scripts/snapshotter.py" \
  --config "$PAGE47_ROOT/config/cities/denver.yaml" \
  --store "$PAGE47_ROOT/runtime/evidence/denver"
"$PAGE47_ROOT/.venv/bin/python" "$PAGE47_ROOT/scripts/apply_captured_events.py" \
  --config "$PAGE47_ROOT/config/cities/seattle.yaml" \
  --database "$PAGE47_ROOT/runtime/records/seattle.sqlite3" \
  --evidence-root "$PAGE47_ROOT/runtime/evidence/seattle"
"$PAGE47_ROOT/.venv/bin/python" "$PAGE47_ROOT/scripts/apply_captured_events.py" \
  --config "$PAGE47_ROOT/config/cities/denver.yaml" \
  --database "$PAGE47_ROOT/runtime/records/denver.sqlite3" \
  --evidence-root "$PAGE47_ROOT/runtime/evidence/denver"
"$PAGE47_ROOT/.venv/bin/python" "$PAGE47_ROOT/scripts/read_captured_attachments.py" \
  --database "$PAGE47_ROOT/runtime/records/seattle.sqlite3" \
  --evidence-root "$PAGE47_ROOT/runtime/evidence/seattle" \
  --substance-config "$PAGE47_ROOT/config/substance.yaml"
"$PAGE47_ROOT/.venv/bin/python" "$PAGE47_ROOT/scripts/read_captured_attachments.py" \
  --database "$PAGE47_ROOT/runtime/records/denver.sqlite3" \
  --evidence-root "$PAGE47_ROOT/runtime/evidence/denver" \
  --substance-config "$PAGE47_ROOT/config/substance.yaml"
"$PAGE47_ROOT/.venv/bin/python" "$PAGE47_ROOT/scripts/apply_pdf_placements.py" \
  --config "$PAGE47_ROOT/config/cities/seattle.yaml" \
  --database "$PAGE47_ROOT/runtime/records/seattle.sqlite3" \
  --evidence-root "$PAGE47_ROOT/runtime/evidence/seattle"
"$PAGE47_ROOT/.venv/bin/python" "$PAGE47_ROOT/scripts/apply_pdf_placements.py" \
  --config "$PAGE47_ROOT/config/cities/denver.yaml" \
  --database "$PAGE47_ROOT/runtime/records/denver.sqlite3" \
  --evidence-root "$PAGE47_ROOT/runtime/evidence/denver"
if [ -n "${PAGE47_EVIDENCE_BACKUP_BUCKET:-}" ]; then
  PAGE47_EVIDENCE_BACKUP_REGION_VALUE=${PAGE47_EVIDENCE_BACKUP_REGION:-eu-west-2}
  "$PAGE47_ROOT/.venv/bin/python" "$PAGE47_ROOT/scripts/backup_evidence.py" \
    --evidence-root "$PAGE47_ROOT/runtime/evidence/seattle" \
    --bucket "$PAGE47_EVIDENCE_BACKUP_BUCKET" \
    --prefix cities/seattle \
    --region "$PAGE47_EVIDENCE_BACKUP_REGION_VALUE"
  "$PAGE47_ROOT/.venv/bin/python" "$PAGE47_ROOT/scripts/backup_evidence.py" \
    --evidence-root "$PAGE47_ROOT/runtime/evidence/denver" \
    --bucket "$PAGE47_EVIDENCE_BACKUP_BUCKET" \
    --prefix cities/denver \
    --region "$PAGE47_EVIDENCE_BACKUP_REGION_VALUE"
fi
"$PAGE47_ROOT/.venv/bin/python" "$PAGE47_ROOT/scripts/notify_findings.py" \
  --web-config "$PAGE47_ROOT/config/web.yaml" \
  --address-config "$PAGE47_ROOT/config/address.yaml" \
  --notification-config "$PAGE47_ROOT/config/notifications.yaml"

printf 'Page47SnapshotRunSuccess captured_at=%s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
