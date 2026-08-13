"""Stage 6 schema, release manifest, privacy, and supervisor lock tests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_stage6_schema_owns_group_monitor_and_alert_runtime() -> None:
    group_sql = (ROOT / "db/schema_parts/160_line_order_group_runtime.sql").read_text(encoding="utf-8")
    monitor_sql = (ROOT / "db/schema_parts/161_runtime_monitoring_line_alerts.sql").read_text(encoding="utf-8")
    assert "line_order_group_participants" in group_sql
    assert "line_order_group_runtime_events" in group_sql
    assert "runtime_health_status" in monitor_sql
    assert "runtime_health_events" in monitor_sql
    assert "line_alert_notification_targets" in monitor_sql
    assert "line_alert_delivery_intents" in monitor_sql


def test_stage6_invitation_privacy_and_active_monitor_are_wired() -> None:
    delivery = (ROOT / "infrastructure/mysql/line_delivery_task_repository.py").read_text(encoding="utf-8")
    monitor = (ROOT / "scripts/run_service_monitor.py").read_text(encoding="utf-8")
    supervisor = (
        ROOT / "scripts/launchers/start_fastapi_ngrok.py"
    ).read_text(encoding="utf-8")
    assert "[REDACTED]" in delivery
    assert "line_group_invitation_requires_new_command" in delivery
    assert "RuntimeHealthObservation" in monitor
    assert '"Monitor": run_monitor' in supervisor
    assert "restart_counts[name] > 3" in supervisor


def test_stage6_release_hashes_are_locked() -> None:
    path = ROOT / "db/migration_releases/labor_union_2026_08_08_line_stage6_v1.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    assert manifest["source_baseline"]["baseline_id"] == "line-stage5-v1"
    for artifact in manifest["artifacts"]:
        assert _sha(ROOT / artifact["relative_path"]) == artifact["sha256"]
    descriptor = manifest["descriptor_artifact"]
    assert _sha(ROOT / descriptor["relative_path"]) == descriptor["sha256"]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
