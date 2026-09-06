from __future__ import annotations

from pathlib import Path


def test_scheduled_collector_processes_both_configured_cities() -> None:
    script = (Path(__file__).parents[1] / "deploy" / "run_snapshotter.sh").read_text(
        encoding="utf-8"
    )

    assert script.count("scripts/read_captured_attachments.py") == 2
    assert script.count("scripts/apply_pdf_placements.py") == 2
    assert script.count("scripts/notify_findings.py") == 1
    assert "runtime/records/denver.sqlite3" in script
    assert "runtime/evidence/denver" in script
    assert '--web-config "$1/config/web.yaml"' in script
    assert "Page47SnapshotRunSuccess" in script
