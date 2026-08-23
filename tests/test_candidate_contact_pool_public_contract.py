"""File: test_candidate_contact_pool_public_contract.py
Description: 驗證候選聯繫池 public schema 的日期、alias、closed 與 mutation contracts。
"""

from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from pydantic import ValidationError

import api.routes.candidate_contact_pool as candidate_contact_pool_route
from api.schemas.candidate_contact_pool import (
    AddCandidatesRequest,
    AddCandidatesResult,
    CandidateContactPoolView,
    CandidateContactView,
    CandidateInput,
    CandidateInformationDeliveryView,
    CandidateWillingnessResult,
    SendCandidateInformationResult,
)
from subsystems.scheduling.candidate_contact_pool_workflow import (
    CandidateContactEntryState,
    CandidateContactPoolState,
    CandidateInformationDelivery,
    CandidateInformationState,
)


def test_candidate_input_dates_are_iso_and_closed() -> None:
    candidate = CandidateInput(
        staff_id=7,
        start_date=date(2026, 9, 1),
        end_date=date(2026, 9, 3),
    )

    assert "2026-09-01" in candidate.model_dump_json()
    with pytest.raises(ValidationError):
        CandidateInput(
            staff_id=7,
            start_date="2026-09-03",
            end_date="2026-09-01",
        )
    with pytest.raises(ValidationError):
        CandidateInput(
            staff_id=7,
            start_date="2026-09-01",
            end_date="2026-09-03",
            unknown_field=True,
        )


def test_candidate_pool_view_preserves_information_aliases_and_is_closed() -> None:
    pool = CandidateContactPoolView.model_validate(
        {
            "pool_id": 3,
            "case_no": "CASE-001",
            "candidates": [
                {
                    "id": 8,
                    "staff_id": 7,
                    "service_start_date": "2026-09-01",
                    "service_end_date": "2026-09-03",
                    "status": "active",
                    "created_at": "2026-08-22T10:00:00+08:00",
                    "staff_name": "王小美",
                    "willingness": "pending",
                    "reason": None,
                    "information": {
                        "1": {
                            "status": "queued",
                            "sent_at": "2026-08-22T10:01:00+08:00",
                        },
                        "2": None,
                    },
                }
            ],
        }
    )

    dumped = pool.model_dump(by_alias=True)
    assert dumped["candidates"][0]["information"]["1"]["status"] == "queued"
    assert dumped["candidates"][0]["information"]["2"] is None
    with pytest.raises(ValidationError):
        CandidateContactPoolView.model_validate(
            {
                **dumped,
                "candidates": [{**dumped["candidates"][0], "phone": "0912"}],
            }
        )


def test_mutation_results_are_closed_and_replay_line_task_is_nullable() -> None:
    with pytest.raises(ValidationError):
        SendCandidateInformationResult(status="queued", event_id=1)
    with pytest.raises(ValidationError):
        CandidateWillingnessResult(status="recorded", event_id=1, extra_field=True)

    result = SendCandidateInformationResult(
        status="idempotent_replay",
        event_id=1,
        line_task_id=None,
    )
    assert result.line_task_id is None


def test_add_route_sends_iso_dates_and_returns_typed_result(monkeypatch) -> None:
    received: dict[str, object] = {}

    def fake_add_candidates(case_no, candidates, actor, event_key):
        received.update(
            case_no=case_no,
            candidates=candidates,
            actor=actor,
            event_key=event_key,
        )
        return {"pool_id": 3, "candidate_ids": [8], "status": "recorded"}

    monkeypatch.setattr(
        candidate_contact_pool_route.workflow,
        "add_candidates",
        fake_add_candidates,
    )
    request = AddCandidatesRequest(
        actor="admin",
        event_key="candidate-add-1",
        candidates=[
            {
                "staff_id": 8,
                "start_date": "2026-09-01",
                "end_date": "2026-09-03",
            }
        ],
    )

    response = candidate_contact_pool_route.add_candidate_contact_pool_entries(
        "CASE-001", request, SimpleNamespace(username="admin")
    )

    assert received["candidates"] == [
        {"staff_id": 8, "start_date": "2026-09-01", "end_date": "2026-09-03"}
    ]
    assert isinstance(response.data, AddCandidatesResult)
    assert not isinstance(response.data, dict)


def test_candidate_router_openapi_uses_closed_typed_response_components() -> None:
    app = FastAPI()
    app.include_router(candidate_contact_pool_route.router)
    schema = app.openapi()
    paths = schema["paths"]
    operations = (
        paths["/api/v1/orders/{case_no}/candidate-contact-pool"]["get"],
        paths["/api/v1/orders/{case_no}/candidate-contact-pool/candidates"]["post"],
        paths[
            "/api/v1/orders/{case_no}/candidate-contact-pool/candidates/{candidate_id}/information"
        ]["post"],
        paths[
            "/api/v1/orders/{case_no}/candidate-contact-pool/candidates/{candidate_id}/willingness"
        ]["put"],
    )
    for operation in operations:
        response_schema = operation["responses"]["200"]["content"]["application/json"][
            "schema"
        ]
        assert response_schema["$ref"].startswith("#/components/schemas/")
        assert "dict" not in response_schema["$ref"].lower()

    components = schema["components"]["schemas"]
    for name in (
        "CandidateContactPoolView",
        "AddCandidatesResult",
        "SendCandidateInformationResult",
        "CandidateWillingnessResult",
    ):
        assert components[name]["additionalProperties"] is False


def test_typed_pool_state_validates_as_view_and_query_route_returns_typed_data(
    monkeypatch,
) -> None:
    now = datetime(2026, 8, 22, 10, 0, tzinfo=timezone.utc)
    state = CandidateContactPoolState(
        pool_id=None,
        case_no="CASE-1",
        candidates=(
            CandidateContactEntryState(
                id=8,
                staff_id=7,
                service_start_date=date(2026, 9, 1),
                service_end_date=date(2026, 9, 3),
                status="active",
                created_at=now,
                staff_name="王小美",
                willingness="pending",
                reason=None,
                information=CandidateInformationState(
                    information_1=CandidateInformationDelivery("queued", now),
                    information_2=None,
                ),
            ),
        ),
    )

    view = CandidateContactPoolView.model_validate(state)

    assert isinstance(view.candidates[0], CandidateContactView)
    assert isinstance(
        view.candidates[0].information.information_1,
        CandidateInformationDeliveryView,
    )
    assert view.model_dump(by_alias=True)["candidates"][0]["information"]["1"][
        "status"
    ] == "queued"
    assert not isinstance(view.candidates[0], dict)
    assert not isinstance(view.candidates[0].information.information_1, dict)

    monkeypatch.setattr(
        candidate_contact_pool_route.workflow,
        "query_pool",
        lambda case_no: state,
    )
    response = candidate_contact_pool_route.query_candidate_contact_pool(
        "CASE-1", SimpleNamespace(username="admin")
    )
    assert isinstance(response.data, CandidateContactPoolView)
