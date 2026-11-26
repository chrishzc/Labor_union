"""The existing formal writers and LINE binding commit atomically after a Redis human claim."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
import os
from typing import Mapping
from uuid import uuid4

import pymysql
import pytest

from importlib import import_module
_source = import_module("tests.domains.case-import.subsystems.case-import.integration.test_non_citizen_registration_mysql")
nc_database = _source.nc_database
_registration_intent = _source._registration_intent
from domains.case_import.provisional_registration import (
    ProvisionalRegistrationCandidate, ProvisionalRegistrationIntent, build_provisional_registration_candidate,
)
from infrastructure.mysql.client_registry_query_repository import MySqlClientRegistryQueryRepository
from infrastructure.mysql.line_unit_of_work import ManagedLineMySqlUnitOfWork
from infrastructure.mysql.provisional_registration_repository import MySqlProvisionalRegistrationRepository
from shared_kernel.identities import CorrelationId
from subsystems.case_import.registration_staging import (
    RegistrationApprovalReceipt, RegistrationReviewApplication, StagedRegistration,
)
from subsystems.client_profile.registry_query import ClientRegistryQueryApplication
from subsystems.line.identity_application import LineIdentityApplication


pytestmark = pytest.mark.skipif(os.getenv("NON_CITIZEN_MYSQL") != "1", reason="isolated localhost MySQL opt-in")


def staged(*, non_citizen: bool = True) -> StagedRegistration:
    now = datetime(2026, 11, 5, tzinfo=timezone.utc)
    intent: ProvisionalRegistrationIntent = _registration_intent()
    intent = replace(intent, survey_details={**intent.survey_details, "代購食材": "自行準備"})
    if not non_citizen:
        intent = replace(intent, registration_kind="subsidy", passbook_image_id="pbk_synthetic_cover")
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


def test_no_passbook_non_citizen_approval_completes_and_replays_original_case(
    nc_database: Mapping[str, object],
) -> None:
    item = staged()
    candidate = item.candidate
    operation_id = item.operation_id
    assert candidate is not None and operation_id is not None
    survey = candidate.beclass_payload["survey_details"]
    assert isinstance(survey, dict)
    assert "passbook_image_id" not in survey["_liff_meta"]

    class Staging:
        def __init__(self) -> None:
            self.snapshot = replace(item, status="pending", version=1, operation_id=None, actor=None)

        def submit(self, candidate: ProvisionalRegistrationCandidate, submission_id: str) -> StagedRegistration:
            raise AssertionError("Review must use the existing pending application")

        def get(self, registration_id: int) -> StagedRegistration:
            assert registration_id == item.registration_id
            return self.snapshot

        def pending(self, *, after_id: int = 0, limit: int = 50) -> tuple[StagedRegistration, ...]:
            return (self.snapshot,) if self.snapshot.status == "pending" else ()

        def claim_approval(self, registration_id: int, expected_version: int, actor: str) -> StagedRegistration:
            assert registration_id == item.registration_id
            if self.snapshot.status == "pending":
                assert expected_version == 1 and actor == item.actor
                self.snapshot = item
            return self.snapshot

        def reject(self, registration_id: int, expected_version: int, actor: str) -> StagedRegistration:
            raise AssertionError("Approval must not reject the pending application")

        def complete(self, registration_id: int, operation_id: str, receipt: RegistrationApprovalReceipt) -> StagedRegistration:
            assert registration_id == item.registration_id and operation_id == item.operation_id
            assert self.snapshot.status == "approving"
            self.snapshot = replace(
                self.snapshot, status="approved", candidate=None, case_no=receipt["case_no"],
                client_id=receipt["client_id"], beclass_record_id=receipt["beclass_record_id"],
                approved_at_utc=datetime.fromisoformat(receipt["approved_at_utc"]),
            )
            return self.snapshot

        def processing_ids(self, *, limit: int = 100) -> tuple[int, ...]:
            return (item.registration_id,) if self.snapshot.status == "approving" else ()

        def delete_passbook_image(self, image_id: str) -> None:
            raise AssertionError("There is no staged passbook to delete")

    formal = application(nc_database)
    review = RegistrationReviewApplication(Staging(), formal)
    first = review.approve_registration(item.registration_id, 1, "synthetic-admin", CorrelationId("synthetic-no-passbook"))
    receipt = formal.registration_approval_receipt(item.registration_id, operation_id)
    assert first.status == "approved" and first.candidate is None
    assert receipt is not None
    case_no = first.case_no
    assert case_no is not None and case_no.startswith("A115")
    assert first.client_id == receipt["client_id"]
    assert first.beclass_record_id == receipt["beclass_record_id"]
    assert first.approved_at_utc == datetime.fromisoformat(receipt["approved_at_utc"])
    assert case_no == receipt["case_no"]
    assert review.registration_application(item.registration_id) == first
    assert review.approve_registration(item.registration_id, 1, "synthetic-admin", CorrelationId("synthetic-no-passbook-review-replay")) == first
    assert formal.approve_staged_registration(item, CorrelationId("synthetic-no-passbook-sql-replay")) == receipt
    with pymysql.connect(**nc_database) as connection, connection.cursor() as cursor:
        registry = ClientRegistryQueryApplication(MySqlClientRegistryQueryRepository(connection))
        detail = registry.query(case_no)
        assert detail.case_no == case_no
        assert detail.client.client_id == first.client_id
        assert detail.beclass.record_id == first.beclass_record_id
        cursor.execute("SELECT case_no FROM orders WHERE client_id=%s", (first.client_id,))
        assert [row["case_no"] for row in cursor.fetchall()] == [case_no]
        cursor.execute(
            "SELECT COUNT(*) n FROM admin_command_receipts WHERE command_family='registration_approval/v1' AND idempotency_key=%s",
            (operation_id,),
        )
        assert cursor.fetchone()["n"] == 1
        cursor.execute("SELECT COUNT(*) n FROM clients WHERE line_user_id=%s", (candidate.line_user_id,))
        assert cursor.fetchone()["n"] == 1


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


def test_refund_correction_keeps_original_and_masks_events_and_receipts(nc_database):
    from infrastructure.mysql.beclass_correction_repository import MySqlBeClassCorrectionRepository
    from infrastructure.mysql.beclass_refund_account import load_effective_refund_account
    from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
    from subsystems.case_import.beclass_correction_workflow import BeClassCorrectionWorkflow
    from shared_kernel.identities import ActorContext, ExpectedVersion, IdempotencyKey
    item = staged()
    approved = application(nc_database).approve_staged_registration(item, CorrelationId("synthetic-refund-source"))
    new_account = "000011112222"
    with pymysql.connect(**nc_database) as connection:
        repository = MySqlBeClassCorrectionRepository(connection)
        workflow = BeClassCorrectionWorkflow(repository, lambda: MySqlUnitOfWork(connection))
        snapshot = workflow.query(approved["case_no"])
        preview = workflow.preview(approved["case_no"], {"refund_account_no":new_account}, ExpectedVersion(snapshot.version))
        receipt = workflow.apply(approved["case_no"], {"refund_account_no":new_account}, ExpectedVersion(snapshot.version),
            preview.preview_fingerprint, IdempotencyKey("synthetic-refund-"+uuid4().hex), ActorContext("synthetic-admin"),
            "合成帳戶更正", CorrelationId("synthetic-refund-correction"))
        with connection.cursor() as cursor:
            account = load_effective_refund_account(cursor, approved["case_no"])
            assert account.account_no == new_account
            cursor.execute("SELECT refund_account_no FROM beclass_records WHERE id=%s", (approved["beclass_record_id"],))
            assert cursor.fetchone()["refund_account_no"] == item.candidate.beclass_payload["refund_account_no"]
            cursor.execute("SELECT before_values_json,after_values_json FROM beclass_record_correction_events WHERE beclass_record_id=%s", (approved["beclass_record_id"],))
            event = cursor.fetchone()
            assert new_account not in str(event)
            assert item.candidate.beclass_payload["refund_account_no"] not in str(event)
            cursor.execute("SELECT result_snapshot FROM admin_command_receipts WHERE command_family='client_beclass_correction/v1' AND idempotency_key=%s", (receipt.idempotency_key.value,))
            assert new_account not in str(cursor.fetchone())
