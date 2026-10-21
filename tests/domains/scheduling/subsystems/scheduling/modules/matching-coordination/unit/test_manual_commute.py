"""Manual-only effects, durable accounting, provider privacy and billing month oracles."""
import json
from datetime import datetime, timezone
from io import BytesIO
from types import SimpleNamespace
from urllib.error import HTTPError, URLError

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from api.routes import commute
from infrastructure.http.google_routes import GoogleRoutesProvider
from shared_kernel.durable_job_queue import DurableJobCommand, DurableJobLease
from subsystems.scheduling.commute_query import (
    COMMAND_TYPE, CommuteApplication, CommuteError, CommuteHistoryRecord, PreparedQuery, RouteResult, billing_period, estimated_cost,
)

NOW = datetime(2026, 10, 21, 3, tzinfo=timezone.utc)


class MemoryRepository:
    def __init__(self):
        self.events, self.rows, self.seen = [], [], set()
        self.reconciliation = None

    def begin(self): self.events.append("begin")
    def commit(self): self.events.append("commit")
    def rollback(self): self.events.append("rollback")

    def prepare(self, command, now):
        if command.command_identity in self.seen:
            return PreparedQuery(None)
        self.seen.add(command.command_identity)
        self.rows.append(dict(at=now, billing="unknown"))
        return PreparedQuery(DurableJobLease(command.job_id, "lease", command, 1), "起點測試地址", "終點測試地址")

    def finish(self, lease, result):
        self.rows[-1]["billing"] = result.billing
        self.events.append("finish")

    def usage(self, start, end):
        return [row for row in self.rows if start <= row["at"] < end], self.reconciliation

    def reconcile(self, command): self.events.append("reconcile")

    def history(self, case_no):
        self.events.append(("history", case_no))
        return [CommuteHistoryRecord("history-one", NOW, 7, "測試月嫂", "failed", "未取得可顯示的機車路線。")]


def command(key="one"):
    return DurableJobCommand(key, f"commute:{key}", COMMAND_TYPE, 1,
        dict(case_no="CASE-DEMO", staff_id=7, event_key=key), "admin_user_id:1", "test", 1)


def application(configured=True, result=RouteResult("ready", "billable", 8600, 1320)):
    repository = MemoryRepository()
    def compute(origin, destination):
        assert repository.events[-1] == "commit", "must commit claim before Google call"
        repository.events.append("google")
        return result
    provider = SimpleNamespace(configured=configured, compute=compute)
    return CommuteApplication(repository, repository, provider), repository


def test_manual_single_query_commits_before_provider_and_same_key_does_not_bill_twice():
    app, repo = application()
    assert app.monthly_usage(NOW)["local_requests"] == 0
    assert "google" not in repo.events  # Mounting / reading usage has no external effect.
    result = app.query(command(), NOW)
    assert result["distance_meters"] == 8600
    assert app.query(command(), NOW)["status"] == "already_requested"
    assert repo.events.count("google") == 1
    assert app.monthly_usage(NOW)["free_remaining"] == 999
    assert all("address" not in key and "distance" not in key for key in command().payload)


def test_not_configured_does_not_reserve_or_consume_usage():
    app, repo = application(configured=False)
    with pytest.raises(CommuteError, match="尚未設定"):
        app.query(command(), NOW)
    assert repo.events == []
    assert app.monthly_usage(NOW)["free_used"] == 0


def test_address_rejected_before_request_rolls_back_without_google():
    app, repo = application()
    def missing(*args): raise CommuteError("commute_address_missing", "地址缺漏")
    repo.prepare = missing
    with pytest.raises(CommuteError): app.query(command(), NOW)
    assert repo.events == ["begin", "rollback"]


@pytest.mark.parametrize("result,used,remaining,pending", [
    (RouteResult("unknown", "unknown"), 0, 999, 1),
    (RouteResult("no_route", "billable"), 1, 999, 0),
    (RouteResult("failed", "not_billable"), 0, 1000, 0),
])
def test_failures_are_accounted_without_blind_retry(result, used, remaining, pending):
    app, repo = application(result=result)
    app.query(command(), NOW)
    totals = app.monthly_usage(NOW)
    assert (totals["free_used"], totals["free_remaining"], totals["uncertain_requests"]) == (used, remaining, pending)
    assert repo.events.count("google") == 1


def test_reconciled_account_total_does_not_double_count_earlier_local_calls():
    app, repo = application()
    cutoff = NOW.replace(hour=2)
    repo.rows = [dict(at=NOW.replace(hour=1), billing="billable"), dict(at=NOW, billing="billable"), dict(at=NOW, billing="unknown")]
    repo.reconciliation = dict(count=1200, through=cutoff, at=NOW)
    totals = app.monthly_usage(NOW)
    assert totals["estimated_billable"] == 1201
    assert totals["paid_requests"] == 201
    assert totals["free_remaining"] == 0
    assert totals["verified_count"] == 1200


def test_month_boundary_uses_pacific_time_and_handles_dst():
    assert billing_period(datetime(2026, 10, 1, 6, 59, tzinfo=timezone.utc))[0] == "2026-09"
    month, start, end = billing_period(datetime(2026, 10, 1, 7, tzinfo=timezone.utc))
    assert month == "2026-10" and start.hour == 7
    assert end == datetime(2026, 11, 1, 7, tzinfo=timezone.utc)
    assert billing_period(datetime(2026, 11, 15, tzinfo=timezone.utc))[2].hour == 8


@pytest.mark.parametrize("count,cost", [(0,"0.00"),(1000,"0.00"),(2000,"15.00"),(5000,"60.00"),(10000,"135.00"),(100001,"1485.01")])
def test_free_allowance_and_volume_prices(count, cost):
    assert estimated_cost(count) == cost


def test_provider_uses_motorcycle_mode_fieldmask_and_does_not_return_vendor_payload():
    requests = []
    def send(request, timeout):
        requests.append(request)
        assert timeout == 15
        return BytesIO(json.dumps({"routes":[{"distanceMeters":8600,"duration":"1320s","extra":"unneeded"}]}).encode())
    result = GoogleRoutesProvider("test-only-key", send).compute("測試起點", "測試終點")
    assert len(requests) == 1
    payload = json.loads(requests[0].data)
    assert payload["travelMode"] == "TWO_WHEELER"
    assert payload["routingPreference"] == "TRAFFIC_AWARE_OPTIMAL"
    assert payload["origin"] == {"address": "測試起點"}
    assert payload["destination"] == {"address": "測試終點"}
    assert "departureTime" not in payload  # Google defaults to the request time.
    assert requests[0].get_header("X-goog-fieldmask") == "routes.distanceMeters,routes.duration"
    assert result == RouteResult("ready", "billable", 8600, 1320)
    assert "test-only-key" not in repr(result) and "測試起點" not in repr(result)


def test_provider_decodes_omitted_zero_distance_from_google_protojson_defaults():
    def send(*args, **kwargs):
        return BytesIO(b'{"routes":[{"duration":"0s"}]}')
    result = GoogleRoutesProvider("test-only-key", send).compute("origin", "destination")
    assert result.status == "ready"
    assert result.distance_meters == 0
    assert result.duration_seconds == 0
    assert result.billing == "billable"
    assert "零距離" in result.message


@pytest.mark.parametrize("route", [{}, {"distanceMeters":0}, {"duration":None}, {"duration":"invalid"}, {"distanceMeters":None,"duration":"0s"}])
def test_provider_does_not_invent_a_zero_route_from_invalid_or_missing_duration(route):
    def send(*args, **kwargs):
        return BytesIO(json.dumps({"routes":[route]}).encode())
    result = GoogleRoutesProvider("test-only-key", send).compute("origin", "destination")
    assert result.status == "failed"
    assert result.distance_meters is None and result.duration_seconds is None
    assert result.billing == "billable"


@pytest.mark.parametrize("code,billing", [(403,"not_billable"),(429,"not_billable"),(503,"not_billable"),(400,"unknown"),(404,"unknown")])
def test_provider_http_failure_billing_and_sanitized_messages(code, billing):
    def send(*args, **kwargs):
        raise HTTPError("https://routes.googleapis.com", code, "private upstream details", {}, None)
    result = GoogleRoutesProvider("test-key", send).compute("private origin", "private destination")
    assert result.billing == billing
    assert "private" not in repr(result)


def test_provider_timeout_and_invalid_success_are_not_silently_free():
    def timeout(*args, **kwargs): raise URLError("private connection details")
    assert GoogleRoutesProvider("test-key", timeout).compute("a", "b").billing == "unknown"
    invalid = lambda *args, **kwargs: BytesIO(b'{"routes":[{"distanceMeters":-1,"duration":"1s"}]}')
    assert GoogleRoutesProvider("test-key", invalid).compute("a", "b").billing == "billable"


def test_invalid_credential_header_does_not_escape_as_a_secret_bearing_exception():
    def send(*args, **kwargs): raise ValueError('invalid header: test-only-private-key')
    result = GoogleRoutesProvider('test-only-private-key', send).compute('private origin', 'private destination')
    assert result.billing == 'unknown'
    assert 'private' not in repr(result)


def client(app):
    api = FastAPI()
    api.include_router(commute.router)
    api.dependency_overrides[commute.get_commute_application] = lambda: app
    api.dependency_overrides[commute.require_system_admin] = lambda: SimpleNamespace(id=1, username="demo", role="system_admin")
    return TestClient(api)


def test_api_accepts_only_one_explicit_person_and_never_calls_provider_on_usage_get():
    app, repo = application()
    with client(app) as http:
        response = http.get('/api/v1/scheduling/commute-usage')
        assert response.status_code == 200 and response.headers['cache-control'] == 'no-store'
        assert 'google' not in repo.events
        assert http.post('/api/v1/orders/DEMO/caregivers/7/commute', json={"event_key":"one", "staff_ids":[7,8]}).status_code == 422
        response = http.post('/api/v1/orders/DEMO/caregivers/7/commute', json={"event_key":"one"})
        assert response.status_code == 200 and response.json()['data']['staff_id'] == 7
        assert repo.events.count('google') == 1


def test_api_refuses_billing_reconciliation_without_timezone():
    app, _ = application()
    with client(app) as http:
        response = http.post('/api/v1/scheduling/commute-usage/reconciliation', json={
            "event_key":"one", "month":"2026-10", "count":312, "through":"2026-10-21T10:00:00"})
        assert response.status_code == 422


def test_api_history_is_case_scoped_metadata_only_and_never_calls_google_or_writes():
    app, repo = application(configured=False)
    with client(app) as http:
        response = http.get('/api/v1/orders/CASE-DEMO/commute-history')
        assert response.status_code == 200
        assert response.headers['cache-control'] == 'no-store'
        data = response.json()['data']
        assert data['case_no'] == 'CASE-DEMO'
        assert data['records'] == [dict(record_id='history-one', queried_at=NOW.isoformat(),
            staff_id=7, staff_name='測試月嫂', status='failed', message='未取得可顯示的機車路線。')]
    assert repo.events == [('history', 'CASE-DEMO')]


def test_api_configuration_failure_is_typed_and_does_not_spend():
    app, repo = application(configured=False)
    with client(app) as http:
        response = http.post('/api/v1/orders/DEMO/caregivers/7/commute', json={"event_key":"one"})
        assert response.status_code == 503
        assert response.json()['detail']['error']['code'] == 'commute_not_configured'
        assert repo.events == []


def test_routes_require_admin_before_querying_or_reconciling():
    app, repo = application()
    api = FastAPI()
    api.include_router(commute.router)
    def denied(): raise HTTPException(403, 'admin required')
    api.dependency_overrides[commute.require_system_admin] = denied
    api.dependency_overrides[commute.get_commute_application] = lambda: app
    with TestClient(api) as http:
        assert http.get('/api/v1/scheduling/commute-usage').status_code == 403
        assert http.get('/api/v1/orders/DEMO/commute-history').status_code == 403
        assert http.post('/api/v1/orders/DEMO/caregivers/7/commute',json={'event_key':'one'}).status_code == 403
        assert http.post('/api/v1/scheduling/commute-usage/reconciliation',json={
            'event_key':'one','month':'2026-10','count':1,'through':'2026-10-21T03:00:00Z'}).status_code == 403
    assert repo.events == []
