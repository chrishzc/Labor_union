"""
File: test_orders_stage_projection.py
Description: 驗證 Orders 七階段投影的 owner lineage、partial availability、游標及 bounded SQL。
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pytest

from domains.orders.lifecycle import OrderLifecycleScope, OrderLifecycleStatus
from infrastructure.mysql.orders_stage_projection_repository import MySqlOrdersStageProjectionRepository, _PAGE_SQL
from shared_kernel.clock import FixedBusinessClock, TAIPEI_TIME_ZONE
from subsystems.orders.stage_projection_query import OrderStageProjectionContractError, OrderStageProjectionQueryService, StageProjectionQuery


NOW = datetime(2026, 8, 21, 8, 0, 0)
BUSINESS_CLOCK = FixedBusinessClock(datetime(2026, 8, 21, 18, 0, tzinfo=TAIPEI_TIME_ZONE))


def test_service_completion_projection_reads_the_canonical_orders_receipt() -> None:
    assert "o.status AS lifecycle_status" in _PAGE_SQL
    assert "scheduling_service_before_replacement_successors" in _PAGE_SQL
    assert "replacement.replacement_generation_id = scheduling.effective_generation_id" in _PAGE_SQL
    assert "GROUP BY case_no, replacement_generation_id" in _PAGE_SQL
    assert "FROM order_auto_completion_apply_receipts" in _PAGE_SQL
    assert "orders-auto-completion-receipt:" in _PAGE_SQL
    assert "service_lock.client_settlement_fingerprint AS service_completion_identity" not in _PAGE_SQL


def test_staff_settlement_reads_staff_payables_projection_not_obligation_status() -> None:
    assert "LEFT JOIN staff_payable_projections projection" in _PAGE_SQL
    assert "COALESCE(projection.status, 'payable') <> 'completed'" in _PAGE_SQL


def _row(case_no: str = "CASE-001") -> dict[str, object]:
    return {
        "case_no": case_no,
        "lifecycle_status": OrderLifecycleStatus.DISCUSSION.value,
        "replacement_resume_step": None,
        "order_version": 7,
        "order_updated_at": NOW,
        "import_receipt_id": 1,
        "import_created_at": NOW,
        "imported_terms_complete": 1,
        "terms_event_id": 2,
        "terms_version": 2,
        "terms_created_at": NOW,
        "candidate_pool_id": 1,
        "candidate_pool_created_at": NOW,
        "candidate_pool_candidate_count": 1,
        "candidate_pool_contacted_count": 1,
        "candidate_pool_contacted_at": NOW,
        "candidate_pool_replied_count": 1,
        "candidate_pool_replied_at": NOW,
        "matching_plan_id": 3,
        "matching_plan_version": 1,
        "matching_plan_status": "accepted",
        "matching_created_at": NOW,
        "matching_customer_decision": "accepted",
        "matching_customer_decision_at": NOW,
        "willingness_contact_attempt_count": 2,
        "willingness_count": 2,
        "willingness_replied_count": 2,
        "willingness_accepted_count": 1,
        "willingness_contacted_at": NOW,
        "willingness_replied_at": NOW,
        "resume_attempt_count": 1,
        "resume_sent_count": 1,
        "resume_sent_at": NOW,
        "matching_segment_count": 1,
        "staff_contract_sent_count": 1,
        "staff_contract_sent_at": NOW,
        "staff_contract_signed_count": 1,
        "staff_contract_signed_at": NOW,
        "client_contract_sent_count": 1,
        "client_contract_sent_at": NOW,
        "client_contract_signed_count": 1,
        "client_contract_signed_at": NOW,
        "contract_event_id": 4,
        "contract_created_at": NOW,
        "finance_version": 5,
        "deposit_obligation_count": 1,
        "deposit_open_count": 0,
        "deposit_updated_at": NOW,
        "confirmed_version_id": 6,
        "confirmed_version": 2,
        "confirmed_at": NOW,
        "scheduling_version": 8,
        "assignment_count": 2,
        "assignment_active_count": 0,
        "assignment_completed_count": 2,
        "assignment_updated_at": NOW,
        "assignment_first_service_date": date(2026, 8, 1),
        "assignment_last_service_date": date(2026, 8, 20),
        "service_start_seconds": 9 * 60 * 60,
        "service_end_seconds": 17 * 60 * 60,
        "service_end_day_offset": 0,
        "service_completion_identity": "a" * 64,
        "service_completed_at": NOW,
        "client_obligation_count": 2,
        "client_open_count": 0,
        "client_updated_at": NOW,
        "staff_obligation_count": 2,
        "staff_open_count": 0,
        "staff_payables_version": 9,
        "staff_updated_at": NOW,
    }


class _Repository:
    def __init__(self, rows: tuple[dict[str, object], ...]) -> None:
        self.rows = rows

    def fetch_page(self, *, after_case_no: str | None, page_size: int, lifecycle_scope: OrderLifecycleScope):
        del after_case_no, page_size, lifecycle_scope
        return self.rows


def test_projection_keeps_seven_stages_eleven_steps_and_three_settlement_owners() -> None:
    page = OrderStageProjectionQueryService(_Repository((_row(),)), BUSINESS_CLOCK).query(StageProjectionQuery(50))
    item = page.items[0]
    assert len(item.stages) == 7
    assert len(item.sop_steps) == 11
    assert [part.code for part in item.stages[-1].settlement] == ["service_completion", "client_settlement", "staff_payout"]
    assert item.stages[-1].status == "completed"
    assert item.current_stage_code == "settlement_payout"
    assert [step.status for step in item.sop_steps] == ["completed"] * 11
    assert page.stage_counts["settlement_payout"] == 1


def test_date_only_service_period_remains_available_until_last_service_day_ends() -> None:
    row = _row()
    row.update(
        assignment_first_service_date=date(2026, 8, 20),
        assignment_last_service_date=date(2026, 8, 21),
        service_start_seconds=None,
        service_end_seconds=None,
        service_end_day_offset=None,
    )

    item = OrderStageProjectionQueryService(
        _Repository((row,)), BUSINESS_CLOCK
    ).query(StageProjectionQuery(50)).items[0]

    assert item.stages[5].status == "in_progress"


def test_missing_owner_fact_is_local_unavailable_and_never_copies_prior_stage() -> None:
    row = _row()
    row.update({"confirmed_version_id": None, "confirmed_version": None, "confirmed_at": None, "client_obligation_count": 0, "client_updated_at": None})
    item = OrderStageProjectionQueryService(_Repository((row,)), BUSINESS_CLOCK).query(StageProjectionQuery(50)).items[0]
    assert item.stages[4].status == "unavailable"
    assert item.stages[6].status == "in_progress"
    assert item.stages[6].settlement[1].status == "unavailable"
    assert item.stages[3].status == "completed"


def test_imported_complete_terms_finish_step_one_without_a_terms_change_event() -> None:
    row = _row("HCM-IMPORTED-STEP3")
    row.update({"terms_event_id": None, "terms_version": None, "terms_created_at": None})

    item = OrderStageProjectionQueryService(_Repository((row,)), BUSINESS_CLOCK).query(
        StageProjectionQuery(50)
    ).items[0]

    assert item.sop_steps[0].status == "completed"
    assert item.sop_steps[2].status == "completed"


def test_matching_pool_step_completes_from_candidate_pool_fact_before_customer_acceptance() -> None:
    row = _row("MATCHING-POOL-COMPLETED")
    row["matching_plan_status"] = "proposed"
    row["matching_customer_decision"] = "pending"
    row["willingness_count"] = 1
    row["willingness_replied_count"] = 1
    row["willingness_accepted_count"] = 1

    item = OrderStageProjectionQueryService(_Repository((row,)), BUSINESS_CLOCK).query(
        StageProjectionQuery(50)
    ).items[0]

    assert item.stages[1].status == "in_progress"
    assert item.sop_steps[1].status == "completed"
    assert item.sop_steps[2].status == "completed"
    assert item.sop_steps[3].status == "completed"


def test_customer_decision_event_completes_matching_and_review_without_mutating_plan_status() -> None:
    row = _row("MATCHING-CUSTOMER-DECISION")
    row["matching_plan_status"] = "proposed"
    row["matching_customer_decision"] = "accepted"

    item = OrderStageProjectionQueryService(_Repository((row,)), BUSINESS_CLOCK).query(
        StageProjectionQuery(50)
    ).items[0]

    assert item.stages[1].status == "completed"
    assert item.stages[2].status == "completed"
    assert item.sop_steps[4].status == "completed"
    assert item.sop_steps[2].label == "發送訂單資訊詢問月嫂意願（LINE 或人工確認）"


def test_candidate_pool_steps_do_not_require_a_formal_matching_plan() -> None:
    row = _row("CANDIDATE-POOL-BEFORE-PLAN")
    row.update({
        "matching_plan_id": None,
        "matching_plan_version": None,
        "matching_plan_status": None,
        "matching_created_at": None,
        "candidate_pool_id": 31,
        "candidate_pool_candidate_count": 2,
        "candidate_pool_contacted_count": 2,
        "candidate_pool_contacted_at": NOW,
        "candidate_pool_replied_count": 2,
        "candidate_pool_replied_at": NOW,
    })

    item = OrderStageProjectionQueryService(_Repository((row,)), BUSINESS_CLOCK).query(
        StageProjectionQuery(50)
    ).items[0]

    assert item.stages[1].status == "in_progress"
    assert item.stages[1].source.identity == "candidate-contact-pool:31"
    assert [step.status for step in item.sop_steps[1:4]] == ["completed"] * 3


def test_line_delivery_step_never_completes_without_contact_timestamp() -> None:
    row = _row("LINE-DELIVERY-TIMESTAMP-MISSING")
    row.update({
        "matching_segment_count": 1,
        "willingness_count": 1,
        "willingness_replied_count": 1,
        "willingness_accepted_count": 1,
        "willingness_contacted_at": None,
        "candidate_pool_contacted_at": None,
    })

    item = OrderStageProjectionQueryService(_Repository((row,)), BUSINESS_CLOCK).query(
        StageProjectionQuery(50)
    ).items[0]

    assert item.sop_steps[2].status == "in_progress"
    assert item.sop_steps[2].occurred_at is None


def test_imported_terms_missing_any_required_root_fact_keep_step_one_in_progress() -> None:
    row = _row("HCM-INCOMPLETE-TERMS")
    row.update({
        "imported_terms_complete": 0,
        "terms_event_id": None,
        "terms_version": None,
        "terms_created_at": None,
    })

    item = OrderStageProjectionQueryService(_Repository((row,)), BUSINESS_CLOCK).query(
        StageProjectionQuery(50)
    ).items[0]

    assert item.sop_steps[0].status == "in_progress"


def test_preassignment_confirmed_dates_are_not_mislabeled_as_actual_start() -> None:
    """事前精算可先確認日期，但不代表已建立正式指派或開始服務。"""
    row = _row("PREASSIGNMENT-DATES")
    row.update({
        "assignment_count": 0,
        "assignment_active_count": 0,
        "assignment_completed_count": 0,
        "assignment_updated_at": None,
        "assignment_first_service_date": None,
        "assignment_last_service_date": None,
        "scheduling_version": None,
    })

    item = OrderStageProjectionQueryService(_Repository((row,)), BUSINESS_CLOCK).query(
        StageProjectionQuery(50)
    ).items[0]

    assert item.sop_steps[8].status == "completed"
    assert item.sop_steps[8].label == "確認事前服務日期（精算）"
    assert item.sop_steps[9].status == "unavailable"


def test_cancelled_order_has_no_active_stage_or_current_step() -> None:
    row = _row("CANCELLED-001")
    row["lifecycle_status"] = OrderLifecycleStatus.CANCELLED.value

    page = OrderStageProjectionQueryService(_Repository((row,)), BUSINESS_CLOCK).query(
        StageProjectionQuery(50)
    )
    item = page.items[0]

    assert item.lifecycle_status is OrderLifecycleStatus.CANCELLED
    assert item.current_stage_code is None
    assert item.current_step_ordinal is None
    assert sum(page.stage_counts.values()) == 0


def test_in_service_lifecycle_cannot_be_dragged_back_by_intake_gap() -> None:
    row = _row("IN-SERVICE-WITH-OLD-GAP")
    row.update({
        "lifecycle_status": OrderLifecycleStatus.IN_SERVICE.value,
        "imported_terms_complete": 0,
        "terms_event_id": None,
        "terms_version": None,
        "terms_created_at": None,
        "assignment_last_service_date": date(2026, 8, 30),
        "service_completion_identity": None,
        "service_completed_at": None,
    })

    item = OrderStageProjectionQueryService(_Repository((row,)), BUSINESS_CLOCK).query(
        StageProjectionQuery(50)
    ).items[0]

    assert item.stages[0].status == "in_progress"
    assert item.stages[5].status == "in_progress"
    assert item.current_stage_code == "active_service"
    assert item.current_step_ordinal == 10


def test_active_service_owner_fact_advances_a_stale_established_lifecycle() -> None:
    row = _row("ACTIVE-SERVICE-STALE-LIFECYCLE")
    row.update({
        "lifecycle_status": OrderLifecycleStatus.ESTABLISHED.value,
        "assignment_last_service_date": date(2026, 8, 30),
        "service_completion_identity": None,
        "service_completed_at": None,
    })

    item = OrderStageProjectionQueryService(_Repository((row,)), BUSINESS_CLOCK).query(
        StageProjectionQuery(50)
    ).items[0]

    assert item.stages[5].status == "in_progress"
    assert item.current_stage_code == "active_service"
    assert item.current_step_ordinal == 10


def test_established_order_ignores_old_matching_gap_without_replacement_lineage() -> None:
    row = _row("ESTABLISHED-WITH-OLD-MATCHING-GAP")
    row.update({
        "lifecycle_status": OrderLifecycleStatus.ESTABLISHED.value,
        "matching_plan_id": None,
        "matching_plan_version": None,
        "matching_plan_status": None,
        "matching_created_at": None,
        "candidate_pool_id": None,
        "candidate_pool_created_at": None,
        "candidate_pool_candidate_count": 0,
        "candidate_pool_contacted_count": 0,
        "candidate_pool_contacted_at": None,
        "candidate_pool_replied_count": 0,
        "candidate_pool_replied_at": None,
        "assignment_count": 0,
        "assignment_updated_at": None,
        "assignment_first_service_date": None,
        "assignment_last_service_date": None,
        "service_completion_identity": None,
        "service_completed_at": None,
    })

    item = OrderStageProjectionQueryService(_Repository((row,)), BUSINESS_CLOCK).query(
        StageProjectionQuery(50)
    ).items[0]

    assert item.stages[1].status == "unavailable"
    assert item.current_step_ordinal >= 6
    assert item.current_stage_code != "matching_willingness"


def test_service_before_replacement_resume_step_is_the_only_established_reentry() -> None:
    row = _row("ESTABLISHED-REPLACEMENT")
    row.update({
        "lifecycle_status": OrderLifecycleStatus.ESTABLISHED.value,
        "replacement_resume_step": "step_3",
        "candidate_pool_contacted_count": 0,
        "candidate_pool_contacted_at": None,
        "assignment_count": 0,
        "assignment_updated_at": None,
        "assignment_first_service_date": None,
        "assignment_last_service_date": None,
        "service_completion_identity": None,
        "service_completed_at": None,
    })

    item = OrderStageProjectionQueryService(_Repository((row,)), BUSINESS_CLOCK).query(
        StageProjectionQuery(50)
    ).items[0]

    assert item.current_stage_code == "matching_willingness"
    assert item.current_step_ordinal == 3


def test_historical_service_completion_stays_in_settlement_despite_old_gaps() -> None:
    row = _row("HISTORICAL-COMPLETED-WITH-OLD-GAP")
    row.update({
        "lifecycle_status": OrderLifecycleStatus.HISTORICAL_SERVICE_COMPLETED.value,
        "imported_terms_complete": 0,
        "terms_event_id": None,
        "terms_version": None,
        "terms_created_at": None,
        "service_completion_identity": None,
        "service_completed_at": None,
    })

    item = OrderStageProjectionQueryService(_Repository((row,)), BUSINESS_CLOCK).query(
        StageProjectionQuery(50)
    ).items[0]

    assert item.stages[0].status == "in_progress"
    assert item.current_stage_code == "settlement_payout"
    assert item.current_step_ordinal == 11


def test_rootless_historical_order_is_isolated_without_guessing_a_business_stage() -> None:
    row = _row("LEGACY-ROOTLESS-001")
    for field in (
        "import_receipt_id", "import_created_at", "terms_event_id", "terms_version",
        "terms_created_at", "candidate_pool_id", "candidate_pool_created_at",
        "candidate_pool_contacted_at", "candidate_pool_replied_at", "matching_plan_id", "matching_plan_version",
        "matching_plan_status", "matching_created_at", "matching_customer_decision",
        "matching_customer_decision_at", "willingness_contacted_at",
        "willingness_replied_at", "resume_sent_at", "staff_contract_sent_at",
        "staff_contract_signed_at", "client_contract_sent_at", "client_contract_signed_at",
        "contract_event_id", "contract_created_at", "finance_version", "deposit_updated_at",
        "confirmed_version_id", "confirmed_version", "confirmed_at", "scheduling_version",
        "assignment_updated_at", "assignment_first_service_date", "assignment_last_service_date",
        "service_start_seconds", "service_end_seconds", "service_end_day_offset",
        "service_completion_identity", "service_completed_at", "client_updated_at",
        "staff_payables_version", "staff_updated_at",
    ):
        row[field] = None
    for field in (
        "willingness_contact_attempt_count", "willingness_count", "willingness_replied_count",
        "willingness_accepted_count", "candidate_pool_candidate_count", "candidate_pool_contacted_count",
        "candidate_pool_replied_count", "resume_attempt_count", "resume_sent_count",
        "matching_segment_count", "staff_contract_sent_count", "staff_contract_signed_count",
        "client_contract_sent_count", "client_contract_signed_count", "deposit_obligation_count",
        "deposit_open_count", "assignment_count", "assignment_active_count",
        "assignment_completed_count", "client_obligation_count", "client_open_count",
        "staff_obligation_count", "staff_open_count",
    ):
        row[field] = 0

    page = OrderStageProjectionQueryService(_Repository((row,)), BUSINESS_CLOCK).query(
        StageProjectionQuery(50)
    )
    item = page.items[0]

    assert {stage.status for stage in item.stages} == {"unavailable"}
    assert item.current_stage_code is None
    assert sum(page.stage_counts.values()) == 0


def test_mysql_aggregate_decimals_and_blocked_settlement_keep_typed_owner() -> None:
    row = _row()
    for field in (
        "willingness_contact_attempt_count",
        "willingness_count",
        "willingness_replied_count",
        "willingness_accepted_count",
        "resume_attempt_count",
        "resume_sent_count",
        "matching_segment_count",
        "staff_contract_sent_count",
        "staff_contract_signed_count",
        "client_contract_sent_count",
        "client_contract_signed_count",
        "deposit_obligation_count",
        "deposit_open_count",
        "assignment_count",
        "assignment_active_count",
        "assignment_completed_count",
        "client_obligation_count",
        "client_open_count",
        "staff_obligation_count",
        "staff_open_count",
    ):
        row[field] = Decimal(row[field])
    row["staff_open_count"] = Decimal(1)

    item = OrderStageProjectionQueryService(_Repository((row,)), BUSINESS_CLOCK).query(
        StageProjectionQuery(50)
    ).items[0]

    assert item.stages[-1].status == "blocked"
    assert item.stages[-1].blockers[0].message == "Staff Payables 子投影尚未完成。"


def test_service_stage_uses_official_service_completion_not_stale_assignment_status() -> None:
    row = _row()
    row.update({"assignment_active_count": 2, "assignment_completed_count": 0})

    item = OrderStageProjectionQueryService(_Repository((row,)), BUSINESS_CLOCK).query(
        StageProjectionQuery(50)
    ).items[0]

    assert item.stages[5].status == "completed"
    assert item.sop_steps[9].status == "completed"


def test_completed_service_advances_to_settlement_even_when_settlement_roots_are_unavailable() -> None:
    row = _row()
    row.update({
        "service_completion_identity": None,
        "service_completed_at": None,
        "client_obligation_count": 0,
        "client_updated_at": None,
        "staff_obligation_count": 0,
        "staff_updated_at": None,
    })

    item = OrderStageProjectionQueryService(_Repository((row,)), BUSINESS_CLOCK).query(
        StageProjectionQuery(50)
    ).items[0]

    assert item.stages[5].status == "completed"
    assert item.stages[6].status == "unavailable"
    assert item.current_stage_code == "settlement_payout"


def test_out_of_order_service_dates_do_not_skip_the_missing_matching_stage() -> None:
    row = _row("116990823")
    row.update({
        "matching_plan_id": None,
        "matching_plan_version": None,
        "matching_plan_status": None,
        "matching_created_at": None,
        "candidate_pool_id": None,
        "candidate_pool_created_at": None,
        "candidate_pool_candidate_count": 0,
        "candidate_pool_contacted_count": 0,
        "candidate_pool_contacted_at": None,
        "candidate_pool_replied_count": 0,
        "candidate_pool_replied_at": None,
        "willingness_contact_attempt_count": 0,
        "willingness_count": 0,
        "willingness_replied_count": 0,
        "willingness_accepted_count": 0,
        "willingness_contacted_at": None,
        "willingness_replied_at": None,
        "resume_attempt_count": 0,
        "resume_sent_count": 0,
        "resume_sent_at": None,
        "matching_segment_count": 0,
        "staff_contract_sent_count": 0,
        "staff_contract_sent_at": None,
        "staff_contract_signed_count": 0,
        "staff_contract_signed_at": None,
        "client_contract_sent_count": 0,
        "client_contract_sent_at": None,
        "client_contract_signed_count": 0,
        "client_contract_signed_at": None,
        "contract_event_id": None,
        "contract_created_at": None,
        "deposit_obligation_count": 0,
        "deposit_open_count": 0,
        "deposit_updated_at": None,
        "assignment_count": 0,
        "assignment_active_count": 0,
        "assignment_completed_count": 0,
        "assignment_updated_at": None,
        "assignment_first_service_date": None,
        "assignment_last_service_date": None,
        "service_completion_identity": None,
        "service_completed_at": None,
        "client_obligation_count": 0,
        "client_open_count": 0,
        "client_updated_at": None,
        "staff_obligation_count": 0,
        "staff_open_count": 0,
        "staff_updated_at": None,
    })

    item = OrderStageProjectionQueryService(_Repository((row,)), BUSINESS_CLOCK).query(
        StageProjectionQuery(50)
    ).items[0]

    assert item.stages[0].status == "completed"
    assert item.stages[1].status == "unavailable"
    assert item.stages[4].status == "completed"
    assert item.current_stage_code == "matching_willingness"


def test_page_order_validation_uses_mysql_case_insensitive_cursor_order() -> None:
    mysql_order = (_row("WP85-single-001"), _row("WP85-UI-001"))

    page = OrderStageProjectionQueryService(
        _Repository(mysql_order), BUSINESS_CLOCK
    ).query(StageProjectionQuery(50))

    assert tuple(item.case_no for item in page.items) == (
        "WP85-single-001",
        "WP85-UI-001",
    )
    with pytest.raises(OrderStageProjectionContractError, match="duplicate or unordered"):
        OrderStageProjectionQueryService(
            _Repository(tuple(reversed(mysql_order))), BUSINESS_CLOCK
        ).query(StageProjectionQuery(50))


def test_sop_matching_and_two_party_contract_steps_use_distinct_owner_facts() -> None:
    row = _row()
    row.update({
        "willingness_replied_count": 1,
        "matching_segment_count": 2,
        "candidate_pool_candidate_count": 2,
        "candidate_pool_contacted_count": 2,
        "candidate_pool_replied_count": 1,
        "resume_attempt_count": 0,
        "resume_sent_count": 0,
        "staff_contract_sent_count": 0,
        "staff_contract_sent_at": None,
        "staff_contract_signed_count": 0,
        "staff_contract_signed_at": None,
    })

    steps = OrderStageProjectionQueryService(_Repository((row,)), BUSINESS_CLOCK).query(
        StageProjectionQuery(50)
    ).items[0].sop_steps

    assert steps[2].status == "completed"
    assert steps[3].status == "in_progress"
    assert steps[4].status == "in_progress"
    assert steps[5].status == "not_started"
    assert steps[7].status == "completed"


def test_sent_contracts_are_in_progress_until_each_party_signs() -> None:
    row = _row()
    row.update({
        "staff_contract_signed_count": 0,
        "staff_contract_signed_at": None,
        "client_contract_signed_count": 0,
        "client_contract_signed_at": None,
        "contract_event_id": None,
        "contract_created_at": None,
    })

    steps = OrderStageProjectionQueryService(_Repository((row,)), BUSINESS_CLOCK).query(
        StageProjectionQuery(50)
    ).items[0].sop_steps

    assert steps[5].status == "in_progress"
    assert steps[7].status == "in_progress"


def test_manual_signed_contract_evidence_completes_steps_without_line_sent_event() -> None:
    row = _row()
    row.update({
        "staff_contract_sent_count": 0,
        "staff_contract_sent_at": None,
        "client_contract_sent_count": 0,
        "client_contract_sent_at": None,
    })

    steps = OrderStageProjectionQueryService(_Repository((row,)), BUSINESS_CLOCK).query(
        StageProjectionQuery(50)
    ).items[0].sop_steps

    assert steps[5].status == "completed"
    assert steps[5].label == "產生月嫂服務契約並留存簽回（寄送或人工確認）"
    assert steps[7].status == "completed"
    assert steps[7].label == "產生客戶契約並留存簽回（寄送或人工確認）"


@pytest.mark.parametrize(
    "updates",
    (
        {"matching_segment_count": 1, "staff_contract_signed_count": 2},
        {"client_contract_signed_count": 2},
    ),
)
def test_contract_step_counts_still_fail_closed_when_manual_evidence_exceeds_scope(
    updates: dict[str, int],
) -> None:
    row = _row()
    row.update(updates)

    with pytest.raises(OrderStageProjectionContractError, match="SOP owner fact counts are inconsistent"):
        OrderStageProjectionQueryService(_Repository((row,)), BUSINESS_CLOCK).query(
            StageProjectionQuery(50)
        )


@pytest.mark.parametrize("mutation", [lambda row: row.pop("finance_version"), lambda row: row.update({"order_version": -1})])
def test_repository_contract_fails_closed_on_shape_or_version_drift(mutation) -> None:
    row = _row()
    mutation(row)
    with pytest.raises(OrderStageProjectionContractError):
        OrderStageProjectionQueryService(_Repository((row,)), BUSINESS_CLOCK).query(StageProjectionQuery(50))


class _Cursor:
    def __init__(self) -> None:
        self.sql = ""
        self.params: tuple[object, ...] = ()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql: str, params: tuple[object, ...]) -> None:
        self.sql = sql
        self.params = params

    def fetchall(self):
        return []


class _Connection:
    def __init__(self) -> None:
        self.last_cursor = _Cursor()

    def cursor(self):
        return self.last_cursor


def test_mysql_repository_uses_one_bounded_select_and_never_commits() -> None:
    connection = _Connection()
    rows = MySqlOrdersStageProjectionRepository(connection).fetch_page(after_case_no="CASE-009", page_size=50)
    assert rows == ()
    assert connection.last_cursor.params == ("CASE-009", "all", "訂單完成", "歷史訂單－帳務完成", 51)
    assert connection.last_cursor.sql.count("SELECT") >= 1
    assert "staff_schedule" in connection.last_cursor.sql
    assert "caregiver_candidate_contact_pools" in connection.last_cursor.sql
    assert "caregiver_candidate_contact_events" in connection.last_cursor.sql
    assert "service_start_time" in connection.last_cursor.sql
    assert "matching_notification_intents" in connection.last_cursor.sql
    assert "matching_response_events" in connection.last_cursor.sql
    assert "'manually_confirmed'" in connection.last_cursor.sql
    assert "COUNT(DISTINCT event.segment_id) = COUNT(DISTINCT segment.id)" in connection.last_cursor.sql
    assert "contract_signing_events" in connection.last_cursor.sql
    assert "signing.matching_plan_id = plan.id" in connection.last_cursor.sql
    for required_terms_clause in (
        "o.start_date IS NOT NULL",
        "o.service_days > 0",
        "o.service_hours_per_day > 0",
        "o.floor_fee IS NOT NULL",
        "o.service_start_time IS NOT NULL",
        "o.service_end_time IS NOT NULL",
        "o.service_end_day_offset IN (0, 1)",
    ):
        assert required_terms_clause in connection.last_cursor.sql
    assert "AS imported_terms_complete" in connection.last_cursor.sql
    assert "LIMIT %s" in connection.last_cursor.sql
    assert not hasattr(connection, "commit")
