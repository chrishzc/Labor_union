from datetime import datetime, timezone

from infrastructure.mysql.orders_stage_projection_repository import _PAGE_SQL
from subsystems.orders.stage_projection_query import _candidate_contact_statuses


_OCCURRED_AT = datetime(2026, 9, 12, tzinfo=timezone.utc)


def test_willing_reply_resolves_contact_and_reply_without_waiting_for_whole_pool():
    contact, reply, blockers = _candidate_contact_statuses(
        candidate_pool_id=1,
        candidate_count=3,
        contacted_count=1,
        replied_count=1,
        willing_count=1,
        contacted_at=_OCCURRED_AT,
    )

    assert contact == "completed"
    assert reply == "completed"
    assert blockers == ()


def test_all_current_replies_unwilling_block_reply_instead_of_completing_it():
    contact, reply, blockers = _candidate_contact_statuses(
        candidate_pool_id=1,
        candidate_count=2,
        contacted_count=2,
        replied_count=2,
        willing_count=0,
        contacted_at=_OCCURRED_AT,
    )

    assert contact == "completed"
    assert reply == "blocked"
    assert [item.code for item in blockers] == ["candidate_pool_no_willing_caregiver"]


def test_partial_unwilling_replies_keep_candidate_contact_in_progress():
    contact, reply, blockers = _candidate_contact_statuses(
        candidate_pool_id=1,
        candidate_count=3,
        contacted_count=1,
        replied_count=1,
        willing_count=0,
        contacted_at=_OCCURRED_AT,
    )

    assert contact == "in_progress"
    assert reply == "in_progress"
    assert blockers == ()


def test_all_actual_contacts_complete_contact_while_reply_can_still_be_pending():
    contact, reply, blockers = _candidate_contact_statuses(
        candidate_pool_id=1,
        candidate_count=2,
        contacted_count=2,
        replied_count=0,
        willing_count=0,
        contacted_at=_OCCURRED_AT,
    )

    assert contact == "completed"
    assert reply == "not_started"
    assert blockers == ()


def test_candidate_pool_sql_does_not_treat_queued_info_event_as_delivery():
    assert "candidate_delivery.processing_status = 'sent'" in _PAGE_SQL
    assert "JSON_UNQUOTE(JSON_EXTRACT(event.payload, '$.delivery_status')) = 'manually_confirmed'" in _PAGE_SQL
    assert "COUNT(DISTINCT CASE WHEN event.event_type IN ('info_1_sent', 'info_2_sent') THEN entry.id END)" not in _PAGE_SQL


def test_candidate_pool_sql_only_counts_real_willingness_values_as_replies():
    actual_willingness_predicate = (
        "JSON_UNQUOTE(JSON_EXTRACT(event.payload, '$.willingness')) "
        "IN ('willing', 'unwilling')"
    )

    assert actual_willingness_predicate in _PAGE_SQL
    assert "newer.event_type = 'willingness_changed'" in _PAGE_SQL
    assert "candidate_pool_willing_count" in _PAGE_SQL
