"""Regression contracts for shared performance and UX safety primitives."""

import pytest

from shared_kernel.performance import (
    BackgroundJobAction,
    BackgroundJobStatus,
    CacheIdentity,
    CacheKeyParts,
    CursorPageRequest,
    CursorPaginationPolicy,
    RequestSupersession,
    SingleFlightState,
    UiOperationKind,
    allows_optimistic_success,
    build_cache_key,
    require_payload_budget,
    transition_background_job,
)


def test_cursor_page_request_enforces_default_limit_and_canonical_cursor() -> None:
    assert CursorPageRequest().page_size == 50
    assert CursorPageRequest(page_size=200, after_cursor="cursor-001").after_cursor == "cursor-001"

    for invalid_size in (0, -1, 201, True):
        with pytest.raises((TypeError, ValueError)):
            CursorPageRequest(page_size=invalid_size)
    with pytest.raises((TypeError, ValueError)):
        CursorPageRequest(after_cursor=" cursor-001 ")


def test_cursor_pagination_policy_resolves_default_and_rejects_oversized_requests() -> None:
    policy = CursorPaginationPolicy(default_page_size=25, maximum_page_size=100)

    assert policy.resolve_page_size(None) == 25
    assert policy.resolve_page_size(100) == 100

    with pytest.raises(ValueError):
        CursorPaginationPolicy(default_page_size=101, maximum_page_size=100)
    with pytest.raises((TypeError, ValueError)):
        policy.resolve_page_size(0)
    with pytest.raises(ValueError):
        policy.resolve_page_size(101)


def test_cache_key_requires_sorted_unique_permission_scope_and_tracks_fact_version() -> None:
    base = CacheKeyParts(
        namespace="orders",
        resource_identity="order-123",
        permission_scope=("orders.read", "orders.write"),
        facts_version=7,
        contract_version="v1",
        time_zone="Asia/Taipei",
    )
    changed = CacheKeyParts(
        namespace="orders",
        resource_identity="order-123",
        permission_scope=("orders.read", "orders.write"),
        facts_version=8,
        contract_version="v1",
        time_zone="Asia/Taipei",
    )

    assert build_cache_key(base) == build_cache_key(base)
    assert build_cache_key(base) != build_cache_key(changed)
    with pytest.raises(ValueError, match="sorted and unique"):
        CacheKeyParts(
            namespace="orders",
            resource_identity="order-123",
            permission_scope=("orders.write", "orders.read"),
            facts_version=7,
            contract_version="v1",
            time_zone="Asia/Taipei",
        )


def test_cache_identity_fingerprint_changes_with_actor_or_facts() -> None:
    base = CacheIdentity("order-123", "operator-1", 7, "v1", "Asia/Taipei", "zh-TW")
    actor_changed = CacheIdentity("order-123", "operator-2", 7, "v1", "Asia/Taipei", "zh-TW")
    facts_changed = CacheIdentity("order-123", "operator-1", 8, "v1", "Asia/Taipei", "zh-TW")

    assert base.fingerprint() == base.fingerprint()
    assert base.fingerprint() != actor_changed.fingerprint()
    assert base.fingerprint() != facts_changed.fingerprint()


def test_single_flight_state_rejects_duplicate_active_command_and_finish_is_idempotent() -> None:
    empty = SingleFlightState()
    active = empty.begin("orders:123:cancel")

    assert active.active_command_identities == frozenset({"orders:123:cancel"})
    with pytest.raises(ValueError, match="command_already_in_flight"):
        active.begin("orders:123:cancel")
    assert active.finish("orders:123:cancel") == empty
    assert empty.finish("orders:123:cancel") == empty


def test_request_supersession_accepts_only_latest_generation() -> None:
    generation = RequestSupersession(3)
    next_generation = generation.next()

    assert generation.accepts(3) is True
    assert generation.accepts(2) is False
    assert next_generation.latest_generation == 4
    assert next_generation.accepts(4) is True
    with pytest.raises((TypeError, ValueError)):
        RequestSupersession(-1)
    with pytest.raises((TypeError, ValueError)):
        generation.accepts(True)


def test_optimistic_success_is_limited_to_local_display() -> None:
    assert allows_optimistic_success(UiOperationKind.LOCAL_DISPLAY) is True
    for operation in UiOperationKind:
        if operation is UiOperationKind.LOCAL_DISPLAY:
            continue
        assert allows_optimistic_success(operation) is False
    with pytest.raises(TypeError, match="UiOperationKind"):
        allows_optimistic_success("query")


def test_background_job_transition_table_rejects_unlisted_transitions() -> None:
    assert transition_background_job(
        BackgroundJobStatus.QUEUED,
        BackgroundJobAction.START,
    ) is BackgroundJobStatus.RUNNING
    assert transition_background_job(
        BackgroundJobStatus.RUNNING,
        BackgroundJobAction.SUCCEED,
    ) is BackgroundJobStatus.SUCCEEDED
    with pytest.raises(ValueError, match="job_state_conflict"):
        transition_background_job(
            BackgroundJobStatus.QUEUED,
            BackgroundJobAction.SUCCEED,
        )


def test_payload_budget_accepts_boundary_and_rejects_oversize_or_invalid_sizes() -> None:
    payload = {"items": [1, 2, 3]}

    require_payload_budget(payload, serialized_size_bytes=1024, maximum_size_bytes=1024)
    with pytest.raises(ValueError, match="payload_too_large"):
        require_payload_budget(payload, serialized_size_bytes=1025, maximum_size_bytes=1024)
    with pytest.raises(TypeError, match="mapping"):
        require_payload_budget([], serialized_size_bytes=0, maximum_size_bytes=1)
    with pytest.raises((TypeError, ValueError)):
        require_payload_budget(payload, serialized_size_bytes=-1, maximum_size_bytes=1)
    with pytest.raises((TypeError, ValueError)):
        require_payload_budget(payload, serialized_size_bytes=0, maximum_size_bytes=0)
