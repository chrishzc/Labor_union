"""Protect the Scheduling-page cutover away from the standalone M3 workbench entry."""

from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[8]
SCHEDULING_PAGE = REPOSITORY_ROOT / "ui_react/src/pages/SchedulingPage.tsx"
MATCHING_WORKBENCH = REPOSITORY_ROOT / "ui_react/src/components/MatchingCoordinationWorkbench.tsx"


def test_scheduling_page_does_not_mount_matching_coordination_workbench() -> None:
    source = SCHEDULING_PAGE.read_text(encoding="utf-8")

    assert "import { MatchingCoordinationWorkbench }" not in source
    assert 'data-surface-id="scheduling.tab.matching"' not in source
    assert "setActiveTab('matching')" not in source
    assert "activeTab === 'matching' && <MatchingCoordinationWorkbench />" not in source
    assert MATCHING_WORKBENCH.is_file()
