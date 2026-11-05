"""The existing formal writers and LINE binding commit atomically after a Redis human claim."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
import os
from uuid import uuid4

import pymysql
import pytest

from importlib import import_module
_source = import_module("tests.domains.case-import.subsystems.case-import.integration.test_non_citizen_registration_mysql")
nc_database = _source.nc_database
_registration_intent = _source._registration_intent
from domains.case_import.provisional_registration import build_provisional_registration_candidate
from infrastructure.mysql.line_unit_of_work import ManagedLineMySqlUnitOfWork
from infrastructure.mysql.provisional_registration_repository import MySqlProvisionalRegistrationRepository
from shared_kernel.identities import CorrelationId
from subsystems.case_import.registration_staging import StagedRegistration
from subsystems.line.identity_application import LineIdentityApplication


pytestmark = pytest.mark.skipif(os.getenv("NON_CITIZEN_MYSQL") != "1", reason="isolated localhost MySQL opt-in")


def staged(*, non_citizen=True):
    now = datetime(2026, 11, 5, tzinfo=timezone.utc)
    intent = _registration_intent()
    if not non_citizen:
        intent = replace(intent, registration_kind="subsidy")
    candidate = build_provisional_registration_candidate(intent)
    return StagedRegistration(100000 + int(uuid4().hex[:7], 16), 2, "approving", now,
        now + timedelta(days=14), candidate.registration_kind, candidate, uuid4().hex, "synthetic-admin")


def application(config):
    now = lambda: datetime(2026, 11, 5, tzinfo=timezone.utc)
    def uow():
        connection = pymysql.connect(**config)
        unit = ManagedLineMySqlUnitOfWork(connection)
        unit.provisional_registrations = MySqlProvisionalRegistrationRepository(connection, now=now)
        return unit
    return LineIdentityApplication(uow, now)


@pytest.mark.parametrize("non_citizen", [True, False])
def test_approval_commits_minimal_parent_account_and_binding_once(nc_database, non_citizen):
    item = staged(non_citizen=non_citizen)
    app = application(nc_database)
    with pymysql.connect(**nc_database) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) n FROM provisional_client_registrations WHERE id=%s", (item.registration_id,))
        assert cursor.fetchone()["n"] == 0
    first = app.approve_staged_registration(item, CorrelationId("synthetic-staged-approval"))
    second = app.approve_staged_registration(item, CorrelationId("synthetic-staged-replay"))
    assert first == second == app.registration_approval_receipt(item.registration_id, item.operation_id)
    assert bool(first["case_no"]) is non_citizen
    with pymysql.connect(**nc_database) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT application_payload,application_version FROM provisional_client_registrations WHERE id=%s", (item.registration_id,))
        parent = cursor.fetchone()
        assert parent["application_payload"] is None and parent["application_version"] == 2
        cursor.execute("SELECT refund_bank_code,refund_account_no,survey_details FROM beclass_records WHERE id=%s", (first["beclass_record_id"],))
        account = cursor.fetchone()
        assert account["refund_bank_code"] == item.candidate.beclass_payload["refund_bank_code"]
        assert account["refund_account_no"] == item.candidate.beclass_payload["refund_account_no"]
        survey = json.loads(account["survey_details"])
        assert "銀行帳號" not in survey and "服務時間內是否有其他寶寶" in survey
        cursor.execute("SELECT result_snapshot FROM admin_command_receipts WHERE command_family='registration_approval/v1' AND idempotency_key=%s", (item.operation_id,))
        saved = cursor.fetchone()["result_snapshot"]
        assert "survey_details" not in str(saved) and "refund_account_no" not in str(saved)


def test_downstream_failure_rolls_back_parent_roots_and_receipt(nc_database, monkeypatch):
    item = staged()
    def fail(*_args, **_kwargs):
        raise RuntimeError("synthetic post-owner failure")
    monkeypatch.setattr(LineIdentityApplication, "_apply_customer_candidate", fail)
    with pytest.raises(RuntimeError, match="synthetic post-owner"):
        application(nc_database).approve_staged_registration(item, CorrelationId("synthetic-staged-rollback"))
    with pymysql.connect(**nc_database) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) n FROM provisional_client_registrations WHERE id=%s", (item.registration_id,))
        assert cursor.fetchone()["n"] == 0
        cursor.execute("SELECT COUNT(*) n FROM clients WHERE line_user_id=%s", (item.candidate.line_user_id,))
        assert cursor.fetchone()["n"] == 0
        cursor.execute("SELECT COUNT(*) n FROM admin_command_receipts WHERE command_family='registration_approval/v1' AND idempotency_key=%s", (item.operation_id,))
        assert cursor.fetchone()["n"] == 0
