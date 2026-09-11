from domains.scheduling.candidate_contact_response import (
    CandidateContactState,
    CandidateIssueCategory,
    CandidateIssueMode,
    CandidatePoolResolution,
    CandidateResponseKind,
    parse_candidate_response,
    resolve_candidate_pool,
)


def test_seven_categories_are_machine_readable_and_keep_all_adjustment_criteria():
    issues = [
        {
            "category": category.value,
            "mode": "condition_adjustment",
            "detail": f"{category.value} 的可接受條件",
        }
        for category in CandidateIssueCategory
    ]

    response = parse_candidate_response(no_interest=False, issues=issues)

    payload = response.as_payload()
    assert response.response_kind is CandidateResponseKind.COORDINATION_REQUESTED
    assert len(payload["issues"]) == 7
    assert payload["willingness"] == "unwilling"
    assert payload["reason_code"] == "service_region"
    assert "confirmed_service_dates" in payload["affected_criteria"]
    assert "requires_cooking" in payload["affected_criteria"]


def test_information_question_stays_pending_until_customer_answer():
    response = parse_candidate_response(
        no_interest=False,
        issues=[
            {
                "category": "transport_parking_floor",
                "mode": CandidateIssueMode.INFORMATION_QUESTION.value,
                "detail": "請問附近有停車位嗎？",
            }
        ],
    )

    assert response.has_information_questions is True
    assert response.has_condition_adjustments is False
    assert response.as_payload()["willingness"] == "pending"


def test_no_interest_is_exclusive_and_requires_no_free_text():
    response = parse_candidate_response(no_interest=True, issues=[])

    assert response.response_kind is CandidateResponseKind.NO_INTEREST
    assert response.as_payload()["reason_code"] == "no_interest"


def test_initial_search_without_contacted_candidates_does_not_create_followup():
    assert (
        resolve_candidate_pool((), has_condition_adjustments=False)
        is CandidatePoolResolution.OPEN
    )


def test_completed_contacted_pool_routes_by_adjustment_and_willingness():
    terminal = (CandidateContactState.TERMINAL, CandidateContactState.TERMINAL)

    assert (
        resolve_candidate_pool(terminal, has_condition_adjustments=False)
        is CandidatePoolResolution.UNION_MANUAL_FOLLOWUP
    )
    assert (
        resolve_candidate_pool(terminal, has_condition_adjustments=True)
        is CandidatePoolResolution.CUSTOMER_ADJUSTMENT
    )
    assert (
        resolve_candidate_pool(
            (CandidateContactState.TERMINAL, CandidateContactState.WILLING),
            has_condition_adjustments=False,
        )
        is CandidatePoolResolution.WILLING
    )
    assert (
        resolve_candidate_pool(
            (CandidateContactState.TERMINAL, CandidateContactState.WAITING_CUSTOMER),
            has_condition_adjustments=False,
        )
        is CandidatePoolResolution.OPEN
    )
