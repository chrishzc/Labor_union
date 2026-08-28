"""
File: test_historical_completion_api.py
Description: 驗證 HOB-E authenticated GET 與 typed API projection contract。
"""

from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies.admin_auth import require_historical_order_review_remediator
from api.dependencies.historical_completion import get_historical_completion_application
from api.routes.historical_completion import _projection_payload, router
from api.schemas.historical_completion import HistoricalCompletionView


def _projection(case_no="CASE-1"):
    source = SimpleNamespace(
        kind=SimpleNamespace(value="staff_obligation"),
        identity="obligation:1",
        version=2,
    )
    return SimpleNamespace(
        case_no=case_no,
        state=SimpleNamespace(value="blocked"),
        step_11_status="blocked",
        step_11_completed=False,
        historical_alerts_completed=False,
        active_alerts=(
            SimpleNamespace(
                code="client_finance_settlement_open",
                owner=SimpleNamespace(value="client_finance"),
                field_path="client_finance.open_obligation_count",
                referral=SimpleNamespace(value="client_finance.settlement"),
                message="Client Finance has unsettled obligations",
            ),
        ),
        owner_versions=(("orders", 3), ("client_finance", 4)),
        owner_source_versions=(source,),
        source_fingerprint=SimpleNamespace(value="a" * 64),
        projection_fingerprint=SimpleNamespace(value="b" * 64),
    )


def test_projection_payload_matches_strict_api_view() -> None:
    view = HistoricalCompletionView.model_validate(_projection_payload(_projection()))

    assert view.case_no == "CASE-1"
    assert not view.step_11_completed
    assert view.active_alerts[0].referral == "client_finance.settlement"
    assert view.owner_source_versions[0].identity == "obligation:1"
    assert view.owner_versions[0].version == "3"
    assert view.owner_source_versions[0].version == "2"


def test_projection_payload_preserves_signed_bigint_versions_losslessly() -> None:
    projection = _projection()
    projection.owner_versions = (("orders", 9_223_372_036_854_775_807),)
    projection.owner_source_versions[0].version = 9_007_199_254_740_993

    view = HistoricalCompletionView.model_validate(_projection_payload(projection))

    assert view.owner_versions[0].version == "9223372036854775807"
    assert view.owner_source_versions[0].version == "9007199254740993"


def test_authenticated_route_queries_exact_case_and_returns_typed_view() -> None:
    calls = []

    class Application:
        def query(self, case_no, correlation_id):
            calls.append((case_no, correlation_id.value))
            return _projection(case_no)

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_historical_order_review_remediator] = lambda: object()
    app.dependency_overrides[get_historical_completion_application] = Application

    response = TestClient(app).get(
        "/api/v1/orders/CASE-1/historical-completion",
        headers={"X-Correlation-ID": "api-test:historical-completion"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["case_no"] == "CASE-1"
    assert response.json()["data"]["active_alerts"][0]["owner"] == "client_finance"
    assert calls == [("CASE-1", "api-test:historical-completion")]
