"""Case Import-owned correction contract preserving imported originals."""

from contextlib import AbstractContextManager

import pytest

from domains.orders.lifecycle import OrderLifecycleStatus
from infrastructure.mysql.beclass_correction_repository import MySqlBeClassCorrectionRepository
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from subsystems.case_import.beclass_correction_workflow import (
    BeClassCorrectionConflict,
    BeClassCorrectionSnapshot,
    BeClassCorrectionWorkflow,
    allows_manual_beclass_source,
)


class _Uow(AbstractContextManager):
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def commit(self):
        pass


class _Repository:
    def __init__(self, *, manual=False):
        self.original = {"name": "原始姓名", "phone": "0911111111"}
        self.corrections = {}
        self.version = 0
        self.manual = manual
        self.claims = {}
        self.receipts = {}

    def load(self, case_no, *, for_update):
        if case_no != "CASE-001":
            return None
        return {"beclass_record_id": None if self.manual and self.version == 0 else 12, "case_no": case_no, "aggregate_version": self.version, "original": dict(self.original), "corrections": dict(self.corrections), "source_kind": "admin_manual" if self.manual else "imported"}

    def claim(self, *, key, command_fingerprint, **_):
        previous = self.claims.setdefault(key.value, command_fingerprint.value)
        if previous != command_fingerprint.value:
            raise ValueError("idempotency_mismatch")

    def load_receipt(self, key, *, for_update):
        return self.receipts.get(key.value)

    def persist(self, *, snapshot, after, **_):
        self.corrections = dict(after)
        self.version = snapshot.version + 1
        return 12, self.version

    def save_receipt(self, *, key, command_fingerprint, result, **_):
        self.receipts[key.value] = {"request_fingerprint": command_fingerprint.value, "result": dict(result)}


def test_beclass_correction_preserves_original_and_replays_exactly_once():
    repository = _Repository()
    workflow = BeClassCorrectionWorkflow(repository, _Uow)
    preview = workflow.preview("CASE-001", {"phone": "0922222222"}, ExpectedVersion(0))
    receipt = workflow.apply("CASE-001", {"phone": "0922222222"}, ExpectedVersion(0), preview.preview_fingerprint, IdempotencyKey("beclass-1"), ActorContext("admin:9"), "依原表單核對", CorrelationId("beclass-corr-1"))
    assert receipt.resulting_version == 1
    assert receipt.readback.original["phone"] == "0911111111"
    assert receipt.readback.effective["phone"] == "0922222222"
    assert workflow.apply("CASE-001", {"phone": "0922222222"}, ExpectedVersion(0), preview.preview_fingerprint, IdempotencyKey("beclass-1"), ActorContext("admin:9"), "依原表單核對", CorrelationId("beclass-corr-1")).replayed
    with pytest.raises(BeClassCorrectionConflict, match="stale_version"):
        workflow.preview("CASE-001", {"phone": "0933333333"}, ExpectedVersion(0))


def test_beclass_correction_accepts_only_canonical_multi_birth_count():
    repository = _Repository()
    repository.original["multi_birth_count"] = None
    workflow = BeClassCorrectionWorkflow(repository, _Uow)

    preview = workflow.preview(
        "CASE-001", {"multi_birth_count": "雙胞胎"}, ExpectedVersion(0)
    )

    assert preview.before == {"multi_birth_count": None}
    assert preview.after == {"multi_birth_count": "雙胞胎"}
    with pytest.raises(ValueError, match="beclass_multi_birth_count_invalid"):
        workflow.preview(
            "CASE-001", {"multi_birth_count": "第二胎"}, ExpectedVersion(0)
        )
    with pytest.raises(ValueError, match="beclass_value_cannot_be_empty"):
        workflow.preview(
            "CASE-001", {"multi_birth_count": None}, ExpectedVersion(0)
        )


def test_manual_beclass_can_be_created_without_an_imported_record():
    repository = _Repository(manual=True)
    repository.original = {"name": None, "phone": None, "multi_birth_count": None}
    workflow = BeClassCorrectionWorkflow(repository, _Uow)
    preview = workflow.preview(
        "CASE-001",
        {"name": "歷史客戶", "multi_birth_count": "雙胞胎"},
        ExpectedVersion(0),
    )

    receipt = workflow.apply(
        "CASE-001",
        {"name": "歷史客戶", "multi_birth_count": "雙胞胎"},
        ExpectedVersion(0),
        preview.preview_fingerprint,
        IdempotencyKey("manual-beclass-1"),
        ActorContext("admin:9"),
        "歷史案件後台補登",
        CorrelationId("manual-beclass-corr-1"),
    )

    assert receipt.beclass_record_id == 12
    assert receipt.readback.source_kind == "admin_manual"
    assert receipt.readback.effective["multi_birth_count"] == "雙胞胎"


def test_every_canonical_order_status_allows_manual_beclass_source() -> None:
    assert all(
        allows_manual_beclass_source(status.value)
        for status in OrderLifecycleStatus
    )
    assert allows_manual_beclass_source("unknown-status") is False


class _SqlCursor:
    def __init__(self, responses=None):
        self.responses = iter(responses or [
            {"case_no": "CASE-001", "status": "歷史訂單－服務完成"},
            ({"beclass_record_id": 12, "case_no": "CASE-001", "record_origin": "imported", "name": "原始姓名", "email": None, "phone": "0911111111", "tel": None, "ext": None, "city": None, "zip_code": None, "address": None, "admin_notes": None},),
            {"aggregate_version": 3, "effective_values_json": '{"phone":"0922222222"}'},
        ])
        self.statements = []
        self.current = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, statement, parameters):
        self.statements.append((" ".join(statement.split()), parameters))
        self.current = next(self.responses)

    def fetchone(self):
        return self.current

    def fetchall(self):
        return self.current


class _SqlConnection:
    def __init__(self, responses=None):
        self.cursor_instance = _SqlCursor(responses)

    def cursor(self):
        return self.cursor_instance


def test_beclass_mysql_correction_locks_unique_bound_case_not_import_query_number():
    connection = _SqlConnection()

    snapshot = MySqlBeClassCorrectionRepository(connection).load("CASE-001", for_update=True)

    statements = [statement for statement, _ in connection.cursor_instance.statements]
    assert "FROM orders WHERE case_no=%s FOR UPDATE" in statements[0]
    assert "WHERE bound_case_no=%s" in statements[1]
    assert "ORDER BY id LIMIT 2 FOR UPDATE" in statements[1]
    assert "query_no" not in " ".join(statements)
    assert snapshot["corrections"] == {"phone": "0922222222"}


def test_beclass_mysql_correction_exposes_empty_manual_source_for_historical_order():
    connection = _SqlConnection([
        {"case_no": "CASE-HISTORY", "status": "歷史訂單－帳務完成"},
        (),
    ])

    snapshot = MySqlBeClassCorrectionRepository(connection).load(
        "CASE-HISTORY", for_update=False
    )

    assert snapshot == {
        "beclass_record_id": None,
        "case_no": "CASE-HISTORY",
        "aggregate_version": 0,
        "original": {
            "name": None, "email": None, "phone": None, "tel": None,
            "ext": None, "city": None, "zip_code": None, "address": None,
            "admin_notes": None, "multi_birth_count": None,
        },
        "corrections": {},
        "source_kind": "admin_manual",
    }


def test_beclass_mysql_correction_exposes_empty_manual_source_for_current_order():
    connection = _SqlConnection([
        {"case_no": "CASE-CURRENT", "status": "洽談中"},
        (),
    ])

    assert MySqlBeClassCorrectionRepository(connection).load(
        "CASE-CURRENT", for_update=False
    ) == {
        "beclass_record_id": None,
        "case_no": "CASE-CURRENT",
        "aggregate_version": 0,
        "original": {
            "name": None, "email": None, "phone": None, "tel": None,
            "ext": None, "city": None, "zip_code": None, "address": None,
            "admin_notes": None, "multi_birth_count": None,
        },
        "corrections": {},
        "source_kind": "admin_manual",
    }


def test_beclass_mysql_correction_creates_a_marked_manual_container_on_first_apply():
    class _PersistCursor:
        lastrowid = 44

        def __init__(self):
            self.statements = []

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def execute(self, statement, parameters):
            self.statements.append((" ".join(statement.split()), parameters))

    class _PersistConnection:
        def __init__(self):
            self.cursor_instance = _PersistCursor()

        def cursor(self):
            return self.cursor_instance

    connection = _PersistConnection()
    snapshot = BeClassCorrectionSnapshot(
        None,
        "CASE-HISTORY",
        0,
        {"name": None},
        {"name": None},
        "admin_manual",
    )

    result = MySqlBeClassCorrectionRepository(connection).persist(
        snapshot=snapshot,
        after={"name": "歷史客戶"},
        actor=ActorContext("admin:9"),
        reason="歷史案件後台補登",
        key=IdempotencyKey("manual-beclass-1"),
        correlation_id=CorrelationId("manual-beclass-corr-1"),
    )

    assert result == (44, 1)
    first_statement, first_parameters = connection.cursor_instance.statements[0]
    assert "INSERT INTO beclass_records (bound_case_no,record_origin)" in first_statement
    assert "'admin_manual'" in first_statement
    assert first_parameters == ("CASE-HISTORY",)
    assert connection.cursor_instance.statements[1][1][0] == 44
    assert connection.cursor_instance.statements[2][1][0] == 44
