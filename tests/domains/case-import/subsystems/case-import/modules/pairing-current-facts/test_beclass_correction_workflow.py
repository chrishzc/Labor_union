"""Case Import-owned correction contract preserving imported originals."""

from contextlib import AbstractContextManager

import pytest

from infrastructure.mysql.beclass_correction_repository import MySqlBeClassCorrectionRepository
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from subsystems.case_import.beclass_correction_workflow import BeClassCorrectionConflict, BeClassCorrectionWorkflow


class _Uow(AbstractContextManager):
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def commit(self):
        pass


class _Repository:
    def __init__(self):
        self.original = {"name": "原始姓名", "phone": "0911111111"}
        self.corrections = {}
        self.version = 0
        self.claims = {}
        self.receipts = {}

    def load(self, case_no, *, for_update):
        if case_no != "CASE-001":
            return None
        return {"beclass_record_id": 12, "case_no": case_no, "aggregate_version": self.version, "original": dict(self.original), "corrections": dict(self.corrections)}

    def claim(self, *, key, command_fingerprint, **_):
        previous = self.claims.setdefault(key.value, command_fingerprint.value)
        if previous != command_fingerprint.value:
            raise ValueError("idempotency_mismatch")

    def load_receipt(self, key, *, for_update):
        return self.receipts.get(key.value)

    def persist(self, *, snapshot, after, **_):
        self.corrections = dict(after)
        self.version = snapshot.version + 1
        return self.version

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


class _SqlCursor:
    def __init__(self):
        self.responses = iter([
            ({"beclass_record_id": 12, "case_no": "CASE-001", "name": "原始姓名", "email": None, "phone": "0911111111", "tel": None, "ext": None, "city": None, "zip_code": None, "address": None, "admin_notes": None},),
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
    def __init__(self):
        self.cursor_instance = _SqlCursor()

    def cursor(self):
        return self.cursor_instance


def test_beclass_mysql_correction_locks_unique_bound_case_not_import_query_number():
    connection = _SqlConnection()

    snapshot = MySqlBeClassCorrectionRepository(connection).load("CASE-001", for_update=True)

    statements = [statement for statement, _ in connection.cursor_instance.statements]
    assert "WHERE bound_case_no=%s" in statements[0]
    assert "ORDER BY id LIMIT 2 FOR UPDATE" in statements[0]
    assert "query_no" not in " ".join(statements)
    assert snapshot["corrections"] == {"phone": "0922222222"}
