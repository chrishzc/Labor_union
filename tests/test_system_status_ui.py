"""The performance snapshot must remain an information-only admin view."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_system_status_page_reads_the_snapshot_without_threshold_alerts():
    source = (ROOT / "ui/pages/08_system_status.py").read_text(encoding="utf-8")

    assert 'title = "🩺 系統狀態"' in source
    assert "client.performance_snapshot(token)" in source
    assert "不會發出警告、建立異常或阻擋 release" in source
    assert "st.warning" not in source
