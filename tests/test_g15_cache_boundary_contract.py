"""G15 contract: caches cannot participate in formal command workflows."""

from __future__ import annotations

from pathlib import Path


WORKFLOW_ROOT = Path("subsystems")
FORBIDDEN_CACHE_DEPENDENCIES = ("QueryCachePort", "TtlProjectionCache")


def test_g15_formal_workflows_have_no_cache_dependency():
    workflow_paths = sorted(WORKFLOW_ROOT.rglob("*workflow.py"))

    assert workflow_paths
    for workflow_path in workflow_paths:
        source = workflow_path.read_text(encoding="utf-8")
        for dependency in FORBIDDEN_CACHE_DEPENDENCIES:
            assert dependency not in source, workflow_path


def test_g15_the_only_ttl_cache_is_a_read_only_holiday_projection():
    cache_paths = sorted(Path("subsystems").rglob("*cache.py"))

    assert cache_paths == [Path("subsystems/scheduling/holiday_query_cache.py")]
    source = cache_paths[0].read_text(encoding="utf-8")
    assert "def query_holidays" in source
    assert "def invalidate_holiday_query_cache" in source
    assert "get_or_load" in source
    assert "commit(" not in source
    assert "rollback(" not in source
