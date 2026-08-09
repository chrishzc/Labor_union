import pytest

from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import IdempotencyKey
from shared_kernel.performance import (
    BackgroundJobAction,
    BackgroundJobStatus,
    CacheIdentity,
    CacheKeyParts,
    CursorPageRequest,
    RequestSupersession,
    SingleFlightCommandIdentity,
    SingleFlightState,
    UiOperationKind,
    allows_optimistic_success,
    build_cache_key,
    require_payload_budget,
    transition_background_job,
)


def test_only_local_display_can_show_optimistic_success():
    assert allows_optimistic_success(UiOperationKind.LOCAL_DISPLAY)
    for operation in UiOperationKind:
        if operation is not UiOperationKind.LOCAL_DISPLAY:
            assert not allows_optimistic_success(operation)


def test_cache_identity_changes_when_scope_or_facts_change():
    baseline = CacheIdentity(
        "orders-summary", "admin", 3, "orders-v1", "Asia/Taipei", "zh-TW"
    )
    changed_scope = CacheIdentity(
        "orders-summary", "operator", 3, "orders-v1", "Asia/Taipei", "zh-TW"
    )
    changed_facts = CacheIdentity(
        "orders-summary", "admin", 4, "orders-v1", "Asia/Taipei", "zh-TW"
    )

    assert baseline.fingerprint() != changed_scope.fingerprint()
    assert baseline.fingerprint() != changed_facts.fingerprint()


def test_cache_key_and_cursor_page_are_bounded_and_deterministic():
    key_parts = CacheKeyParts(
        "query", "orders", ("orders:read",), 1, "v1", "Asia/Taipei"
    )

    assert build_cache_key(key_parts) == build_cache_key(key_parts)
    assert CursorPageRequest(page_size=200).page_size == 200
    with pytest.raises(ValueError, match="page_size_invalid"):
        CursorPageRequest(page_size=201)


def test_single_flight_and_request_supersession_reject_duplicates_and_late_results():
    identity = SingleFlightCommandIdentity(
        IdempotencyKey("apply:1"), PreviewFingerprint("a" * 64)
    )
    active = SingleFlightState().begin(identity.idempotency_key.value)

    with pytest.raises(ValueError, match="already_in_flight"):
        active.begin(identity.idempotency_key.value)
    assert not RequestSupersession(2).accepts(1)
    assert RequestSupersession(2).accepts(2)


def test_background_job_lifecycle_and_payload_budget_fail_closed():
    assert transition_background_job(
        BackgroundJobStatus.QUEUED, BackgroundJobAction.START
    ) is BackgroundJobStatus.RUNNING
    with pytest.raises(ValueError, match="job_state_conflict"):
        transition_background_job(BackgroundJobStatus.SUCCEEDED, BackgroundJobAction.START)
    with pytest.raises(ValueError, match="payload_too_large"):
        require_payload_budget({"summary": "x"}, 201, 200)
