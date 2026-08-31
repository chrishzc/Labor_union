"""Protect the existing Scheduling-page entry to the typed M3 workbench."""

from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[8]
SCHEDULING_PAGE = REPOSITORY_ROOT / "ui_react/src/pages/SchedulingPage.tsx"


def test_scheduling_page_mounts_matching_coordination_workbench() -> None:
    source = SCHEDULING_PAGE.read_text(encoding="utf-8")

    assert "import { MatchingCoordinationWorkbench }" in source
    assert 'data-surface-id="scheduling.tab.matching"' in source
    assert "setActiveTab('matching')" in source
    assert "activeTab === 'matching' && <MatchingCoordinationWorkbench />" in source
