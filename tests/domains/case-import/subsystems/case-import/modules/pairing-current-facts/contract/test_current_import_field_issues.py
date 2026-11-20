"""Current owner edits resolve accepted import warnings independently."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies.admin_auth import require_admin
from api.dependencies.import_field_issues import get_import_field_issues_query
from api.routes.import_field_issues import router
from domains.case_import.import_field_issues import current_beclass_field_issues, current_hcm_field_issue
from subsystems.case_import.current_import_field_issues import CurrentImportFieldIssuesQuery


BANK_CODE = "client_field_invalid:補助款退款:銀行代號+分行代號"
ACCOUNT_CODE = "client_field_invalid:銀行帳號"


def test_bank_current_values_resolve_independently_and_preserve_original_codes():
    codes = (BANK_CODE, ACCOUNT_CODE)
    values = {"refund_bank_code": None, "refund_account_no": None}
    assert {issue.field for issue in current_beclass_field_issues(codes, values, {})} == {"refund_bank_code", "refund_account_no"}
    values["refund_bank_code"] = "0041234"
    issues = current_beclass_field_issues(codes, values, {})
    assert [issue.field for issue in issues] == ["refund_account_no"]
    values["refund_account_no"] = "00123456789"
    assert current_beclass_field_issues(codes, values, {}) == ()
    assert codes == (BANK_CODE, ACCOUNT_CODE)
    values["refund_account_no"] = "中文00123456789"
    assert current_beclass_field_issues(codes, values, {})[0].field == "refund_account_no"
    values["refund_account_no"] = None
    assert current_beclass_field_issues(codes, values, {}, cleared_fields=frozenset({"refund_account_no"})) == ()


def test_profile_is_only_current_owner_for_source_email_city():
    codes = ("client_field_invalid:Email", "client_field_invalid:縣市")
    issues = current_beclass_field_issues(codes, {}, {"email": None, "city": None})
    assert {(issue.source, issue.owner) for issue in issues} == {("client_beclass", "client_profile")}
    assert current_beclass_field_issues(codes, {}, {"email": "valid@example.invalid", "city": "新竹縣竹北市"}) == ()
    assert [issue.field for issue in current_beclass_field_issues(codes, {}, {"email": "invalid", "city": "新竹縣竹北市"})] == ["email"]


class Repository:
    def __init__(self):
        self.current = {"A": (), "B": (current_hcm_field_issue("email", "hcm_field_invalid:email"),), "C": ()}

    def candidate_case_nos(self, *, offset, limit, case_no):
        candidates = [number for number in self.current if case_no is None or number == case_no]
        return tuple(candidates[offset:offset + limit])

    def query_case(self, case_no):
        return self.current[case_no]


def test_empty_resolved_candidate_page_preserves_successor_and_fresh_query():
    repository = Repository()
    query = CurrentImportFieldIssuesQuery(repository)
    assert query.query_page(1, 1).as_dict() == {"items": [], "next_page": 2, "total": None}
    page = query.query_page(2, 1)
    assert page.items[0].case_no == "B"
    assert page.next_page == 3
    repository.current["B"] = ()
    assert query.query_case("B") == ()
    assert query.query_page(1, 20, "B").items == ()


def test_repository_failure_propagates_instead_of_empty_success():
    class Broken(Repository):
        def query_case(self, case_no):
            raise RuntimeError("owner unavailable")
    with pytest.raises(RuntimeError, match="owner unavailable"):
        CurrentImportFieldIssuesQuery(Broken()).query_page(1, 10)


@pytest.mark.parametrize("page,size", [(0, 1), (True, 1), (1, 101), (1, 0)])
def test_query_rejects_unbounded_or_invalid_pages(page, size):
    with pytest.raises(ValueError):
        CurrentImportFieldIssuesQuery(Repository()).query_page(page, size)


def test_http_query_requires_auth_and_bounds_page():
    app = FastAPI()
    app.include_router(router)
    query = CurrentImportFieldIssuesQuery(Repository())
    app.dependency_overrides[get_import_field_issues_query] = lambda: query
    with TestClient(app) as client:
        assert client.get("/api/v1/case-import/field-issues").status_code in {401, 403}
        app.dependency_overrides[require_admin] = lambda: object()
        response = client.get("/api/v1/case-import/field-issues", params={"case_no": "B"})
        assert response.status_code == 200
        assert response.json()["data"]["items"][0]["issues"][0] == {
            "source": "hcm", "owner": "client_profile", "field": "email", "source_field": "email",
            "code": "hcm_field_invalid:email", "message": "email尚未完成，請補正或依原進件流程確認略過。",
        }
        assert client.get("/api/v1/case-import/field-issues?page_size=101").status_code == 422
        assert client.get("/api/v1/case-import/field-issues?page=0").status_code == 422


class Cursor:
    def __init__(self, connection):
        self.connection = connection
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def execute(self, sql, params):
        self.connection.calls.append((sql, params))
        self.result = self.connection.results.pop(0)
    def fetchone(self):
        return self.result
    def fetchall(self):
        return self.result


class Connection:
    def __init__(self, results):
        self.results = list(results)
        self.calls = []
    def cursor(self):
        return Cursor(self)


def test_mysql_accepted_receipt_binding_and_current_correction_are_both_required():
    from infrastructure.mysql.import_field_issues_repository import MySqlImportFieldIssuesRepository
    connection = Connection([
        None,
        [{"id": 17, "refund_bank_code": None, "refund_account_no": None,
          "issue_codes": [BANK_CODE, ACCOUNT_CODE]}],
        {"email": "client@example.invalid", "city": "新竹縣竹北市"},
        [{"id": 17}],
        {"aggregate_version": 1, "effective_values_json": '{"refund_bank_code":"0041234"}'},
        [_correction_receipt(1, ["refund_bank_code"])],
    ])
    issues = MySqlImportFieldIssuesRepository(connection).query_case("CASE-17")
    assert [issue.field for issue in issues] == ["refund_account_no"]
    sql = connection.calls[1][0]
    assert "$.root_id" in sql and "$.review_identity" in sql
    assert "$.outcome'))='created'" in sql
    assert "source.bound_case_no=%s" in sql
    assert "source.query_no" not in sql
    receipt_sql, receipt_params = connection.calls[-1]
    assert "$.beclass_record_id" in receipt_sql and "$.case_no" in receipt_sql
    assert "$.resulting_version" in receipt_sql and "BETWEEN 1 AND %s" in receipt_sql
    assert receipt_params == ("client_beclass_correction/v1", "17", "CASE-17", 1)


def _correction_receipt(version, fields, *, record_id=17, case_no="CASE-17"):
    return {"result_snapshot": {"beclass_record_id": record_id, "case_no": case_no,
                                "resulting_version": version, "changed_fields": fields}}


def _mysql_bank_issues(corrections, receipts, *, version=1):
    from infrastructure.mysql.import_field_issues_repository import MySqlImportFieldIssuesRepository
    connection = Connection([
        None,
        [{"id": 17, "refund_bank_code": None, "refund_account_no": None,
          "issue_codes": [BANK_CODE, ACCOUNT_CODE]}],
        {"email": "client@example.invalid", "city": "新竹縣竹北市"},
        [{"id": 17}],
        {"aggregate_version": version, "effective_values_json": corrections},
        receipts,
    ])
    return MySqlImportFieldIssuesRepository(connection).query_case("CASE-17")


@pytest.mark.parametrize("changes", [
    {"holiday_double_pay": True}, {"holiday_double_pay": False},
    {"holiday_double_pay": None}, {"admin_notes": "已確認意願"},
])
def test_mysql_unrelated_full_snapshot_save_keeps_both_bank_warnings(changes):
    issues = _mysql_bank_issues(
        {"refund_bank_code": None, "refund_account_no": None, **changes},
        [_correction_receipt(1, list(changes))],
    )
    assert {issue.code for issue in issues} == {BANK_CODE, ACCOUNT_CODE}


@pytest.mark.parametrize("field,value,remaining", [
    ("refund_bank_code", "0041234", "refund_account_no"),
    ("refund_account_no", "00123456789", "refund_bank_code"),
    ("refund_bank_code", None, "refund_account_no"),
    ("refund_account_no", None, "refund_bank_code"),
])
def test_mysql_receipted_bank_edit_or_optional_clear_resolves_only_that_field(field, value, remaining):
    issues = _mysql_bank_issues(
        {"refund_bank_code": None, "refund_account_no": None, field: value},
        [_correction_receipt(1, [field])],
    )
    assert [issue.field for issue in issues] == [remaining]


def test_mysql_prior_bank_clear_survives_later_unrelated_full_snapshot_save():
    issues = _mysql_bank_issues(
        {"refund_bank_code": None, "refund_account_no": None, "holiday_double_pay": False},
        [_correction_receipt(1, ["refund_account_no"]),
         _correction_receipt(2, ["holiday_double_pay"])], version=2,
    )
    assert [issue.field for issue in issues] == ["refund_bank_code"]


@pytest.mark.parametrize("receipts", [
    [], [_correction_receipt(1, ["refund_bank_code", "refund_account_no"], record_id=99)],
    [_correction_receipt(1, ["refund_bank_code", "refund_account_no"], case_no="OTHER")],
    [_correction_receipt(2, ["refund_bank_code", "refund_account_no"])],
    [_correction_receipt(0, ["refund_bank_code", "refund_account_no"])],
    [_correction_receipt(True, ["refund_bank_code", "refund_account_no"])],
])
def test_mysql_snapshot_cannot_claim_correction_without_matching_committed_receipt(receipts):
    issues = _mysql_bank_issues(
        {"refund_bank_code": "0041234", "refund_account_no": "00123456789"}, receipts,
    )
    assert {issue.code for issue in issues} == {BANK_CODE, ACCOUNT_CODE}


def test_mysql_receipted_invalid_bank_value_keeps_warning():
    issues = _mysql_bank_issues(
        {"refund_bank_code": "中文", "refund_account_no": None},
        [_correction_receipt(1, ["refund_bank_code"])],
    )
    assert {issue.code for issue in issues} == {BANK_CODE, ACCOUNT_CODE}


def test_mysql_receipted_bank_values_keep_leading_zeroes(monkeypatch):
    import infrastructure.mysql.import_field_issues_repository as module
    projected = []
    original = module.current_beclass_field_issues

    def capture(codes, values, profile, **kwargs):
        projected.append(dict(values))
        return original(codes, values, profile, **kwargs)

    monkeypatch.setattr(module, "current_beclass_field_issues", capture)
    assert _mysql_bank_issues(
        {"refund_bank_code": "0041234", "refund_account_no": "00123456789"},
        [_correction_receipt(1, ["refund_bank_code", "refund_account_no"])],
    ) == ()
    assert projected == [{"refund_bank_code": "0041234", "refund_account_no": "00123456789"}]


def test_mysql_current_hcm_query_reuses_skip_and_root_rules(monkeypatch):
    from infrastructure.mysql.hcm_resubmission_repository import MySqlHcmResubmissionRepository
    connection = Connection([{"review_identity": "review:hcm"}])
    repository = MySqlHcmResubmissionRepository(connection)
    monkeypatch.setattr(repository, "_load_review_row", lambda identity: {
        "review_identity": identity, "issue_codes": ["hcm_field_invalid:email", "hcm_field_missing:姓名"],
        "clients_email": "valid@example.invalid", "clients_name": None,
    })
    monkeypatch.setattr(repository, "_review_progress", lambda identity: {"skipped_fields": {"姓名"}})
    assert repository.query_current_field_issues("CASE-17") == ()
    assert "NOT EXISTS" in connection.calls[0][0]
