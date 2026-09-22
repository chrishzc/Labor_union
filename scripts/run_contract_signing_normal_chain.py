"""Run the WP56 normal chain through typed applications only."""

from __future__ import annotations

import argparse
from argparse import Namespace
import copy
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from tempfile import TemporaryDirectory

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
CASE_NO = ""
DEPOSIT_OBLIGATION = ""
SERVICE_START = date(2030, 1, 1)
SERVICE_END = date(2030, 1, 5)
SERVICE_DAYS = 5


def run(arguments) -> dict[str, object]:
    global CASE_NO, DEPOSIT_OBLIGATION, SERVICE_START, SERVICE_END, SERVICE_DAYS
    _configure_database(arguments)
    if getattr(arguments, "resume_case", None):
        return _resume_conversion(arguments)
    CASE_NO = _scenario_case_no(arguments.scenario_id)
    DEPOSIT_OBLIGATION = f"client-obligation:{CASE_NO}:deposit"
    SERVICE_START = _requested_service_start(arguments)
    SERVICE_DAYS = _requested_service_days(arguments)
    SERVICE_END = SERVICE_START + timedelta(days=SERVICE_DAYS - 1)
    foundation = _seed_foundation(arguments)
    staff_root = _seed_staff(arguments)
    receipts = {
        "foundation": foundation,
        "staff_root": staff_root,
        "line_identities": _seed_line_identities(
            arguments,
            int(foundation["client_id"]),
            int(staff_root["staff_id"]),
        ),
    }
    staff_id = int(receipts["staff_root"]["staff_id"])
    plan = _create_matching_plan(arguments, staff_id)
    receipts["matching_plan"] = plan
    receipts["matching_acceptance"] = _accept_matching_plan(int(plan["plan_id"]))
    receipts["staff_signing"] = _sign_staff_contracts(int(plan["plan_id"]))
    if getattr(arguments, "stop_before_client_signed", False):
        receipts["client_signing"] = {"sent": _send_client_contract()}
        return {
            "contract": "labor-union-wp56-normal-chain/v1",
            "case_no": CASE_NO,
            "receipts": receipts,
        }
    receipts["client_signing"] = _sign_client_contract()
    receipts["pre_execution"] = _pre_execution_snapshot()
    receipts["deposit_reconciliation"] = _reconcile_deposit()
    if getattr(arguments, "prepare_assignment_ui", False):
        receipts["waiting_lock"] = _acquire_waiting_lock(int(plan["plan_id"]))
        return {
            "contract": "labor-union-wp56-normal-chain/v1",
            "case_no": CASE_NO,
            "receipts": receipts,
        }
    if getattr(arguments, "stop_before_conversion", False):
        return {
            "contract": "labor-union-wp56-normal-chain/v1",
            "case_no": CASE_NO,
            "receipts": receipts,
        }
    if getattr(arguments, "conversion_negative_first", False):
        receipts["assignment_negative"] = _reject_mismatched_commitment_execution(
            int(plan["plan_id"]), staff_id
        )
    if getattr(arguments, "conversion_stale_first", False):
        receipts["assignment_stale_negative"] = _reject_stale_assignment_apply(
            staff_id
        )
    if getattr(arguments, "occupancy_negative", False):
        receipts["assignment_occupancy_negative"] = _reject_occupied_assignment_plan(
            int(plan["plan_id"]), staff_id
        )
        return {
            "contract": "labor-union-wp56-normal-chain/v1",
            "case_no": CASE_NO,
            "receipts": receipts,
        }
    receipts["assignment"] = _convert_commitment_to_execution(
        int(plan["plan_id"]),
        staff_id,
        existing_lock=receipts.get("assignment_negative", {}).get("lock"),
    )
    return {"contract": "labor-union-wp56-normal-chain/v1", "case_no": CASE_NO, "receipts": receipts}


def _configure_database(arguments) -> None:
    if arguments.confirm_database != arguments.database:
        raise ValueError("confirmation must exactly match database")
    if not re.fullmatch(r"lu_test_dataset_[a-z0-9_]+", arguments.database):
        raise ValueError("database must be a disposable validation dataset")
    if os.getenv("APP_ENV", "development").strip().lower() in {"prod", "production"}:
        raise ValueError("normal chain requires a development validation profile")
    os.environ.update({"DB_HOST": arguments.host, "DB_PORT": str(arguments.port), "DB_USER": arguments.user, "DB_PASSWORD": arguments.password, "DB_DATABASE": arguments.database})
    from infrastructure.mysql.mysql_adapter import DB_CONFIG, get_connection
    from subsystems.scheduling import matching_plan_workflow

    DB_CONFIG.update({
        "host": arguments.host,
        "port": arguments.port,
        "user": arguments.user,
        "password": arguments.password,
        "database": arguments.database,
    })
    matching_plan_workflow.get_connection = get_connection


def _seed_foundation(arguments):
    from infrastructure.mysql.case_import_repository import MySqlCaseImportRepository
    from scripts.seed_validation_dataset import (
        _existing_root_case,
        _require_matching_root_case,
        apply_dataset,
        connect,
        load_dataset,
    )
    from shared_kernel.identities import IdempotencyKey

    dataset = _scenario_dataset(arguments.scenario_id)
    connection = connect(arguments)
    try:
        existing = _existing_root_case(connection, CASE_NO)
        if existing is not None:
            _require_matching_root_case(existing, dataset)
            stored = MySqlCaseImportRepository(connection).find_receipt(
                IdempotencyKey(f"dataset-case-import-{CASE_NO}")
            )
            if stored is None or stored.receipt.case_no != CASE_NO:
                raise RuntimeError("normal_chain_foundation_resume_receipt_missing")
            receipt = _receipt(stored.receipt)
            receipt["result"] = "resumed"
            return receipt
        receipt = apply_dataset(connection, dataset)
    finally:
        connection.close()
    result = _receipt(receipt)
    result["result"] = "created"
    return result


def _seed_staff(arguments):
    import pymysql
    from subsystems.validation_dataset.staff_master_source import apply_staff_master_source

    fact = _staff_source_fact(arguments.source)
    connection = pymysql.connect(
        host=arguments.host,
        port=arguments.port,
        user=arguments.user,
        password=arguments.password,
        database=arguments.database,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )
    try:
        with connection.cursor() as cursor:
            staff_id = apply_staff_master_source(cursor, fact)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
    return {"database": arguments.database, "staff_id": staff_id}


def _staff_source_fact(path: Path):
    from subsystems.validation_dataset.staff_master_source import StaffMasterSourceFact

    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("contract") != "labor-union-validation-staff-master/v1":
        raise ValueError("unsupported staff-master source contract")
    staff = payload.get("staff")
    if not isinstance(staff, dict):
        raise ValueError("staff-master source is missing")
    return StaffMasterSourceFact(
        str(staff["name"]),
        str(staff["identity_card"]),
        str(staff["phone"]),
        date.fromisoformat(str(staff["birthday"])),
        str(staff["city"]),
        int(staff["care_babies"]),
    )


def _seed_line_identities(arguments, client_id: int, staff_id: int):
    existing = _existing_line_bindings(arguments, client_id, staff_id)
    if existing == {"customer": "bound", "staff": "bound"}:
        return {"customer": "reused", "staff": "reused"}
    staff = json.loads(arguments.staff_source.read_text(encoding="utf-8"))["staff"]
    customer = _scenario_dataset(arguments.scenario_id)["root_case"]["client_attributes"]
    namespace = _line_namespace(arguments.scenario_id)
    _register_line_platform_users(namespace)
    return _bind_line_subjects(
        staff,
        customer,
        namespace,
        reuse_staff_binding=existing.get("staff") == "bound",
    )


def _line_namespace(value: object) -> str:
    text = str(value or "default").strip().lower()
    if not text or not text.replace("-", "").isalnum():
        raise ValueError("line namespace must be alphanumeric or hyphen")
    return text


def _register_line_platform_users(namespace: str) -> None:
    from domains.line.identities import LineUserId, LineWebhookEventId
    from domains.line.platform_user import LineFriendEvent, LineFriendEventType
    from infrastructure.mysql.line_unit_of_work import open_line_unit_of_work

    users = (
        ("U-validation-staff-1", f"validation-follow-staff-{namespace}"),
        (f"U-validation-client-{namespace}", f"validation-follow-client-{namespace}"),
    )
    for user, event in users:
        with open_line_unit_of_work() as unit:
            unit.platform_users.apply_friend_event(
                LineFriendEvent(
                    LineUserId(user),
                    LineWebhookEventId(event),
                    LineFriendEventType.FOLLOW,
                    datetime(2026, 7, 1, tzinfo=timezone.utc),
                )
            )
            unit.commit()


def _bind_line_subjects(
    staff: dict[str, object],
    customer: dict[str, object],
    namespace: str,
    *,
    reuse_staff_binding: bool,
) -> dict[str, object]:
    from api.dependencies.line_identity import get_line_identity_application
    from domains.line.identities import LineUserId
    from domains.line.identity_flow import LineIdentityFlowPurpose
    from subsystems.line.identity_contracts import CustomerIdentityProof, StaffIdentityProof

    get_line_identity_application.cache_clear()
    application = get_line_identity_application()
    staff_result = None if reuse_staff_binding else _bind_line_subject(
        application,
        LineIdentityFlowPurpose.STAFF_VERIFICATION,
        LineUserId("U-validation-staff-1"),
        StaffIdentityProof(
            str(staff["name"]),
            str(staff["identity_card"]),
            datetime.fromisoformat(str(staff["birthday"])).date(),
        ),
        f"staff-{namespace}",
    )
    client_result = _bind_line_subject(
        application,
        LineIdentityFlowPurpose.CUSTOMER_BINDING,
        LineUserId(f"U-validation-client-{namespace}"),
        CustomerIdentityProof(str(customer["name"]), str(customer["phone"])),
        f"client-{namespace}",
    )
    staff_status = "reused" if staff_result is None else _approve_staff_review_if_needed(staff_result, namespace)
    return {"staff": staff_status, "customer": client_result.status.value}


def _approve_staff_review_if_needed(result, namespace: str) -> str:
    if result.status.value != "pending_review":
        return result.status.value
    from api.dependencies.line_identity import get_line_identity_review_application
    from domains.line.review import LineReviewDecision
    from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
    from subsystems.line.review_contracts import DecideLineReviewCommand

    application = get_line_identity_review_application()
    snapshot = application.get(result.review_request_id)
    approved = application.decide(
        DecideLineReviewCommand(
            snapshot.request_id,
            LineReviewDecision.APPROVE,
            snapshot.version,
            ActorContext("validation-dataset-seed", ("line.identity.review",)),
            "approve synthetic staff identity evidence",
            IdempotencyKey(f"validation-contract-staff-review-approve-{namespace}"),
            CorrelationId(f"validation-contract-staff-review-approve-{namespace}"),
        )
    )
    return approved.snapshot.status.value


def _bind_line_subject(application, purpose, user, proof, suffix):
    from shared_kernel.identities import CorrelationId, IdempotencyKey

    flow = application.open_flow(
        purpose,
        user,
        IdempotencyKey(f"validation-contract-flow-{suffix}"),
        CorrelationId(f"validation-contract-flow-{suffix}"),
    )
    if purpose.value == "staff_verification":
        preview = application.preview_staff(flow.flow_id, user, proof)
        return application.apply_staff(
            flow.flow_id,
            user,
            proof,
            preview.expected_version,
            preview.preview_fingerprint,
            CorrelationId(f"validation-contract-apply-{suffix}"),
        )
    preview = application.preview_customer(flow.flow_id, user, proof)
    return application.apply_customer(
        flow.flow_id,
        user,
        proof,
        preview.expected_version,
        preview.preview_fingerprint,
        CorrelationId(f"validation-contract-apply-{suffix}"),
    )


def _existing_line_bindings(arguments, client_id: int, staff_id: int) -> dict[str, str]:
    import pymysql

    subjects = (("customer", str(client_id)), ("staff", str(staff_id)))
    connection = pymysql.connect(
        host=arguments.host,
        port=arguments.port,
        user=arguments.user,
        password=arguments.password,
        database=arguments.database,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT subject_type,binding_status FROM line_identity_role_bindings "
                "WHERE (subject_type=%s AND subject_reference=%s) "
                "OR (subject_type=%s AND subject_reference=%s)",
                (*subjects[0], *subjects[1]),
            )
            statuses: dict[str, str] = {}
            for row in cursor.fetchall():
                subject_type = str(row["subject_type"])
                status = str(row["binding_status"])
                if status == "bound" or subject_type not in statuses:
                    statuses[subject_type] = status
    finally:
        connection.close()
    return statuses


def _create_matching_plan(arguments, staff_id: int):
    import pymysql

    from subsystems.scheduling.matching_plan_workflow import create_matching_plan_version
    from infrastructure.mysql.segmented_availability_repository import (
        MySqlSegmentedAvailabilityFactsRepository,
    )

    def connect():
        return pymysql.connect(
            host=arguments.host,
            port=arguments.port,
            user=arguments.user,
            password=arguments.password,
            database=arguments.database,
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
        )

    return create_matching_plan_version(
        CASE_NO,
        [{"staff_id": staff_id, "start_date": SERVICE_START.isoformat(), "end_date": SERVICE_END.isoformat()}],
        "wp56-validation",
        "2026-08-01",
        facts_port=MySqlSegmentedAvailabilityFactsRepository(connect),
        event_key=f"wp56-matching-plan-create:{CASE_NO}",
    )


def _accept_matching_plan(plan_id: int) -> dict[str, object]:
    from domains.scheduling.matching_communication import (
        CaregiverWillingness,
        CustomerMatchingDecision,
        MatchingPlanReference,
    )
    from infrastructure.mysql.line_unit_of_work import ManagedLineMySqlUnitOfWork
    from infrastructure.mysql.mysql_adapter import get_connection
    from shared_kernel.identities import (
        ActorContext,
        CorrelationId,
        ExpectedVersion,
        IdempotencyKey,
    )
    from subsystems.line.capabilities import LineCapability
    from subsystems.scheduling.matching_notification_application import (
        MatchingNotificationApplication,
    )
    from subsystems.scheduling.matching_notification_contracts import (
        RecordManualMatchingResponseCommand,
    )

    segment_id = _plan_segment_id(plan_id)
    application = MatchingNotificationApplication(
        lambda: ManagedLineMySqlUnitOfWork(get_connection()),
        _fixed_now,
        availability_validator=lambda _state: None,
    )
    actor = ActorContext(
        "wp56-validation",
        (LineCapability.MATCHING_OVERRIDE.value,),
    )
    willing = application.record_manual_response(
        RecordManualMatchingResponseCommand(
            MatchingPlanReference(CASE_NO, plan_id, 0),
            segment_id,
            CaregiverWillingness.WILLING,
            None,
            "WP56 驗收：服務人員已確認意願",
            actor,
            ExpectedVersion(0),
            IdempotencyKey(_key("staff-willing")),
            CorrelationId(_key("staff-willing")),
        )
    )
    accepted = application.record_manual_response(
        RecordManualMatchingResponseCommand(
            MatchingPlanReference(CASE_NO, plan_id, 1),
            None,
            None,
            CustomerMatchingDecision.ACCEPTED,
            "WP56 驗收：客戶已接受正式方案",
            actor,
            ExpectedVersion(1),
            IdempotencyKey(_key("customer-accepted")),
            CorrelationId(_key("customer-accepted")),
        )
    )
    return {"staff": _receipt(willing), "customer": _receipt(accepted)}


def _resume_conversion(arguments) -> dict[str, object]:
    global CASE_NO, DEPOSIT_OBLIGATION, SERVICE_START, SERVICE_END, SERVICE_DAYS
    CASE_NO = str(arguments.resume_case)
    DEPOSIT_OBLIGATION = f"client-obligation:{CASE_NO}:deposit"
    plan_id, staff_id, start_date, end_date = _existing_matching_plan(CASE_NO)
    SERVICE_START = start_date
    SERVICE_END = end_date
    SERVICE_DAYS = (SERVICE_END - SERVICE_START).days + 1
    if getattr(arguments, "client_sign_failure_case", False):
        return {
            "contract": "labor-union-wp56-normal-chain/v1",
            "case_no": CASE_NO,
            "receipts": {"client_sign_failure": _verify_client_signing_rollback()},
        }
    if getattr(arguments, "client_sign_after_completion_failure_case", False):
        return {
            "contract": "labor-union-wp56-normal-chain/v1",
            "case_no": CASE_NO,
            "receipts": {
                "client_sign_after_completion_failure": _verify_client_signing_after_completion_rollback()
            },
        }
    if getattr(arguments, "occupancy_negative", False):
        receipt = _reject_occupied_assignment_plan(plan_id, staff_id)
        key = "assignment_occupancy_negative"
    else:
        receipt = _convert_commitment_to_execution(plan_id, staff_id)
        key = "assignment"
    return {
        "contract": "labor-union-wp56-normal-chain/v1",
        "case_no": CASE_NO,
        "receipts": {key: receipt},
    }


def _existing_matching_plan(case_no: str) -> tuple[int, int, date, date]:
    from infrastructure.mysql.mysql_adapter import get_connection

    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT plan.id,segment.staff_id,plan.start_date,plan.end_date "
                "FROM caregiver_matching_plans plan "
                "JOIN caregiver_matching_plan_segments segment ON segment.plan_id=plan.id "
                "WHERE plan.case_no=%s AND plan.status='proposed' "
                "ORDER BY plan.version DESC,segment.segment_order LIMIT 1",
                (case_no,),
            )
            row = cursor.fetchone()
    finally:
        connection.close()
    if row is None:
        raise RuntimeError("resumable_matching_plan_not_found")
    return int(row["id"]), int(row["staff_id"]), row["start_date"], row["end_date"]


def _sign_staff_contracts(plan_id: int) -> dict[str, object]:
    from api.dependencies.contract_signing import get_staff_contract_signing_application
    from shared_kernel.identities import CorrelationId, IdempotencyKey
    from subsystems.contract_signing.staff_contract_application import (
        RecordStaffSignedReturnCommand,
        SendStaffContractCommand,
    )

    segment_id = _plan_segment_id(plan_id)
    application = get_staff_contract_signing_application()
    sent = application.send(SendStaffContractCommand(CASE_NO, segment_id, "wp56-validation", IdempotencyKey(_key("staff-send")), CorrelationId(_key("staff-send")), "https://validation.invalid/contracts/staff"))
    command = RecordStaffSignedReturnCommand(CASE_NO, segment_id, b"WP56 staff signed return", "staff-signed.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "wp56-validation", IdempotencyKey(_key("staff-return")), CorrelationId(_key("staff-return")), sent.document_version_id)
    signed = application.record_signed_return(command)
    replay = application.record_signed_return(command)
    if replay != signed:
        raise RuntimeError("staff_signed_return_replay_mismatch")
    return {"sent": _receipt(sent), "signed": _receipt(signed), "replay": _receipt(replay)}


def _sign_client_contract() -> dict[str, object]:
    from api.dependencies.contract_signing import get_client_contract_signing_application
    from shared_kernel.identities import CorrelationId, IdempotencyKey
    from subsystems.contract_signing.client_contract_application import (
        RecordClientSignedReturnCommand,
    )

    sent = _send_client_contract()
    application = get_client_contract_signing_application()
    command = RecordClientSignedReturnCommand(CASE_NO, b"WP56 client signed return", "client-signed.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "wp56-validation", IdempotencyKey(_key("client-return")), CorrelationId(_key("client-return")), sent.document_version_id)
    signed = application.record_signed_return(command)
    replay = application.record_signed_return(command)
    if replay != signed:
        raise RuntimeError("client_signed_return_replay_mismatch")
    return {"sent": _receipt(sent), "signed": _receipt(signed), "replay": _receipt(replay)}


def _send_client_contract():
    from api.dependencies.contract_signing import get_client_contract_signing_application
    from shared_kernel.identities import CorrelationId, IdempotencyKey
    from subsystems.contract_signing.client_contract_application import (
        SendClientContractCommand,
    )

    application = get_client_contract_signing_application()
    return application.send(SendClientContractCommand(CASE_NO, "wp56-validation", IdempotencyKey(_key("client-send")), CorrelationId(_key("client-send")), "https://validation.invalid/contracts/client"))


def _client_sent_document_version_id() -> int:
    from infrastructure.mysql.mysql_adapter import get_connection

    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT event.document_version_id FROM contract_signing_events event "
                "JOIN contract_document_versions document ON document.id=event.document_version_id "
                "WHERE event.case_no=%s AND event.event_type='sent' "
                "AND document.document_scope='client_contract' ORDER BY event.id DESC LIMIT 1",
                (CASE_NO,),
            )
            row = cursor.fetchone()
    finally:
        connection.close()
    if row is None:
        raise RuntimeError("client_sent_document_version_missing")
    return int(row["document_version_id"])


def _verify_client_signing_rollback() -> dict[str, object]:
    import subsystems.contract_signing.client_contract_application as signing
    from infrastructure.mysql.mysql_adapter import get_connection
    from shared_kernel.identities import CorrelationId, IdempotencyKey

    key = IdempotencyKey(_key("client-return-failure"))
    application = signing.ClientContractSigningApplication(
        get_connection,
        archive_root=_archive_root(),
        now=_fixed_now,
    )
    original = signing._complete_contract_in_transaction
    signing._complete_contract_in_transaction = _raise_injected_completion_failure
    try:
        try:
            application.record_signed_return(
                signing.RecordClientSignedReturnCommand(
                    CASE_NO,
                    b"WP56 client rollback signed return",
                    "client-rollback.xlsx",
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    "wp56-validation",
                    key,
                    CorrelationId(key.value),
                    _client_sent_document_version_id(),
                )
            )
        except RuntimeError as error:
            if str(error) != "wp56_injected_completion_failure":
                raise
        else:
            raise RuntimeError("client_signing_failure_was_accepted")
    finally:
        signing._complete_contract_in_transaction = original
    observed = _client_signing_failure_snapshot(key.value)
    archive = _archive_root() / f"{CASE_NO}/client/{key.value}-signed.xlsx"
    if any(observed.values()) or archive.exists():
        raise RuntimeError("client_signing_failure_partial_write")
    return {"error_code": "wp56_injected_completion_failure", **observed, "archive_exists": False}


def _verify_client_signing_after_completion_rollback() -> dict[str, object]:
    import subsystems.contract_signing.client_contract_application as signing
    from infrastructure.mysql.mysql_adapter import get_connection
    from shared_kernel.identities import CorrelationId, IdempotencyKey

    key = IdempotencyKey(_key("client-return-after-completion-failure"))
    application = signing.ClientContractSigningApplication(
        get_connection,
        archive_root=_archive_root(),
        now=_fixed_now,
    )
    original = signing._complete_contract_in_transaction

    def complete_then_fail(*args):
        original(*args)
        raise RuntimeError("wp56_injected_after_completion_failure")

    signing._complete_contract_in_transaction = complete_then_fail
    try:
        try:
            application.record_signed_return(
                signing.RecordClientSignedReturnCommand(
                    CASE_NO,
                    b"WP56 after completion rollback signed return",
                    "client-after-completion-rollback.xlsx",
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    "wp56-validation",
                    key,
                    CorrelationId(key.value),
                    _client_sent_document_version_id(),
                )
            )
        except RuntimeError as error:
            if str(error) != "wp56_injected_after_completion_failure":
                raise
        else:
            raise RuntimeError("client_after_completion_failure_was_accepted")
    finally:
        signing._complete_contract_in_transaction = original
    observed = _client_signing_failure_snapshot(key.value)
    archive = _archive_root() / f"{CASE_NO}/client/{key.value}-signed.xlsx"
    if any(observed.values()) or archive.exists():
        raise RuntimeError("client_after_completion_failure_partial_write")
    return {
        "error_code": "wp56_injected_after_completion_failure",
        **observed,
        "archive_exists": False,
    }


def _raise_injected_completion_failure(*_args) -> None:
    raise RuntimeError("wp56_injected_completion_failure")


def _client_signing_failure_snapshot(event_key: str) -> dict[str, int]:
    from infrastructure.mysql.mysql_adapter import get_connection

    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS count FROM contract_signing_events WHERE event_key=%s", (event_key,))
            signed_events = int(cursor.fetchone()["count"])
            cursor.execute("SELECT COUNT(*) AS count FROM order_contract_flow_events WHERE case_no=%s AND event_type='contract_completed'", (CASE_NO,))
            completed_events = int(cursor.fetchone()["count"])
            cursor.execute("SELECT COUNT(*) AS count FROM client_obligations WHERE case_no=%s AND obligation_type IN ('remaining','first_payment','second_payment')", (CASE_NO,))
            remaining_obligations = int(cursor.fetchone()["count"])
    finally:
        connection.close()
    return {
        "signed_events": signed_events,
        "completed_events": completed_events,
        "remaining_obligations": remaining_obligations,
    }


def _pre_execution_snapshot() -> dict[str, int]:
    from infrastructure.mysql.mysql_adapter import get_connection

    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS count FROM case_staff_assignments WHERE case_no=%s", (CASE_NO,))
            assignments = int(cursor.fetchone()["count"])
            cursor.execute("SELECT COUNT(*) AS count FROM staff_schedule WHERE case_no=%s", (CASE_NO,))
            schedule_days = int(cursor.fetchone()["count"])
    finally:
        connection.close()
    if assignments or schedule_days:
        raise RuntimeError("pre_execution_isolation_failed")
    return {"assignments": assignments, "schedule_days": schedule_days}


def _reconcile_deposit() -> dict[str, object]:
    from api.dependencies.finance_import import build_finance_import_application
    from domains.finance_import.correction import FinanceImportCorrectionSelection
    from domains.finance_import.planning import FinanceClassificationType
    from infrastructure.mysql.anomaly_runtime import build_anomaly_runtime
    from infrastructure.mysql.finance_import_owning_domain_composite import MySqlFinanceImportOwningDomainComposite
    from infrastructure.mysql.mysql_adapter import get_connection
    from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
    from subsystems.finance_import.finance_import_anomaly_consumer import consume_finance_import_anomaly_events
    from subsystems.finance_import.correction_workflow import FinanceImportCorrectionApplyRequest
    from subsystems.finance_import.ingestion import ingest_finance_workbook
    from scripts.imports.finance_statement_normalizer import normalize_workbook
    from subsystems.orders.client_finance_outbox_consumer import consume_client_finance_orders_events

    with TemporaryDirectory(prefix="lu-wp56-deposit-") as directory:
        workbook = Path(directory) / "deposit.xlsx"
        _write_deposit_workbook(workbook)
        intake = ingest_finance_workbook(
            str(workbook),
            IdempotencyKey(_key("deposit-intake")),
            ActorContext("wp56-validation"),
            connection_factory=get_connection,
            normalizer=normalize_workbook,
        )
    connection = get_connection()
    try:
        anomaly_delivery = consume_finance_import_anomaly_events(
            connection, runtime=build_anomaly_runtime()
        )
        row_id = _finance_row_id(connection, intake.batch_identity)
        application = build_finance_import_application(connection, MySqlFinanceImportOwningDomainComposite(connection))
        selection = FinanceImportCorrectionSelection(f"finance-import-row:{row_id}", FinanceClassificationType.CLIENT_RECEIPT, (DEPOSIT_OBLIGATION,), "WP56 deposit receipt reviewed against signed contract", ("bank-statement:wp56-deposit-line-1", f"signed-contract:{CASE_NO}"))
        preview = application.preview_correction(selection, CorrelationId(_key("deposit-correction-preview")))
        receipt = application.correct_and_post(FinanceImportCorrectionApplyRequest(selection, ExpectedVersion(preview.batch_version), ExpectedVersion(preview.canonical_fact_version), ExpectedVersion(preview.alert_version), preview.fingerprint, IdempotencyKey(_key("deposit-correction-apply")), ActorContext("wp56-validation"), CorrelationId(_key("deposit-correction-apply"))))
        replay = application.correct_and_post(FinanceImportCorrectionApplyRequest(selection, ExpectedVersion(preview.batch_version), ExpectedVersion(preview.canonical_fact_version), ExpectedVersion(preview.alert_version), preview.fingerprint, IdempotencyKey(_key("deposit-correction-apply")), ActorContext("wp56-validation"), CorrelationId(_key("deposit-correction-apply"))))
        if replay != receipt:
            raise RuntimeError("finance_import_correction_replay_mismatch")
    finally:
        connection.close()
    connection = get_connection()
    try:
        orders_delivery = consume_client_finance_orders_events(connection)
    finally:
        connection.close()
    return {"batch_identity": intake.batch_identity, "row_id": row_id, "anomaly_delivery_count": anomaly_delivery.delivered_count, "reconciliation": _receipt(receipt), "replay": _receipt(replay), "orders_delivery": orders_delivery}


def _acquire_waiting_lock(plan_id: int) -> dict[str, object]:
    from subsystems.scheduling.availability_lock_acquisition_workflow import (
        acquire_caregiver_availability_lock,
        preview_caregiver_availability_lock,
    )

    lock_preview = preview_caregiver_availability_lock(CASE_NO, plan_id)
    return acquire_caregiver_availability_lock(
        CASE_NO,
        plan_id,
        _key("waiting-lock"),
        "wp56-validation",
        lock_preview["preview_fingerprint"],
    )


def _convert_commitment_to_execution(
    plan_id: int, staff_id: int, *, existing_lock=None
) -> dict[str, object]:
    from api.dependencies.assignment_plan import build_assignment_plan_application
    from domains.scheduling.assignment_plan import AssignmentPlanIntent, AssignmentPlanSegmentIntent
    from infrastructure.mysql.mysql_adapter import get_connection
    from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
    from subsystems.scheduling.assignment_plan_workflow import AssignmentPlanApplyRequest, AssignmentPlanPreviewRequest
    lock_receipt = existing_lock or _acquire_waiting_lock(plan_id)
    service_dates = tuple(SERVICE_START + timedelta(days=offset) for offset in range(SERVICE_DAYS))
    intent = AssignmentPlanIntent((AssignmentPlanSegmentIntent(staff_id, SERVICE_START, SERVICE_END, service_dates),))
    connection = get_connection()
    try:
        application = build_assignment_plan_application(connection)
        preview = application.preview(AssignmentPlanPreviewRequest(CASE_NO, intent, CorrelationId(_key("assignment-preview"))))
        receipt = application.apply(AssignmentPlanApplyRequest(CASE_NO, intent, ExpectedVersion(preview.order_version), ExpectedVersion(preview.scheduling_version), ExpectedVersion(preview.client_finance_version), ExpectedVersion(preview.payroll_version), preview.fingerprint, IdempotencyKey(_key("assignment-apply")), ActorContext("wp56-validation"), "WP56 exact commitment conversion", CorrelationId(_key("assignment-apply"))))
    finally:
        connection.close()
    return {"lock": lock_receipt, "assignment": _receipt(receipt)}


def _reject_mismatched_commitment_execution(plan_id: int, staff_id: int) -> dict[str, object]:
    from api.dependencies.assignment_plan import build_assignment_plan_application
    from domains.scheduling.assignment_plan import AssignmentPlanIntent, AssignmentPlanSegmentIntent
    from infrastructure.mysql.mysql_adapter import get_connection
    from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
    from subsystems.scheduling.assignment_plan_workflow import (
        AssignmentPlanApplyRequest,
        AssignmentPlanPreviewRequest,
        AssignmentPlanWorkflowError,
    )
    from subsystems.scheduling.availability_lock_acquisition_workflow import acquire_caregiver_availability_lock, preview_caregiver_availability_lock

    lock_preview = preview_caregiver_availability_lock(CASE_NO, plan_id)
    lock_receipt = acquire_caregiver_availability_lock(CASE_NO, plan_id, _key("waiting-lock-negative"), "wp56-validation", lock_preview["preview_fingerprint"])
    wrong_start = SERVICE_START + timedelta(days=1)
    wrong_end = SERVICE_END + timedelta(days=1)
    wrong_dates = tuple(wrong_start + timedelta(days=offset) for offset in range(SERVICE_DAYS))
    intent = AssignmentPlanIntent((AssignmentPlanSegmentIntent(staff_id, wrong_start, wrong_end, wrong_dates),))
    connection = get_connection()
    try:
        application = build_assignment_plan_application(connection)
        preview = application.preview(AssignmentPlanPreviewRequest(CASE_NO, intent, CorrelationId(_key("assignment-negative-preview"))))
        request = AssignmentPlanApplyRequest(CASE_NO, intent, ExpectedVersion(preview.order_version), ExpectedVersion(preview.scheduling_version), ExpectedVersion(preview.client_finance_version), ExpectedVersion(preview.payroll_version), preview.fingerprint, IdempotencyKey(_key("assignment-negative-apply")), ActorContext("wp56-validation"), "WP56 mismatched commitment rejection", CorrelationId(_key("assignment-negative-apply")))
        try:
            application.apply(request)
        except AssignmentPlanWorkflowError as error:
            if error.error.code != "commitment_execution_mismatch":
                raise
        else:
            raise RuntimeError("mismatched_commitment_execution_was_accepted")
    finally:
        connection.close()
    snapshot = _pre_execution_snapshot()
    converted_events = _converted_commitment_events()
    if snapshot != {"assignments": 0, "schedule_days": 0} or converted_events:
        raise RuntimeError("mismatched_commitment_execution_partial_write")
    return {
        "lock": lock_receipt,
        "error_code": "commitment_execution_mismatch",
        "post_rejection": {**snapshot, "converted_events": converted_events},
    }


def _converted_commitment_events() -> int:
    from infrastructure.mysql.mysql_adapter import get_connection

    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) AS count FROM precontract_service_commitment_events event "
                "JOIN precontract_service_commitments commitment ON commitment.id=event.commitment_id "
                "WHERE commitment.case_no=%s AND event.event_type='converted'",
                (CASE_NO,),
            )
            return int(cursor.fetchone()["count"])
    finally:
        connection.close()


def _reject_stale_assignment_apply(staff_id: int) -> dict[str, object]:
    from api.dependencies.assignment_plan import build_assignment_plan_application
    from domains.scheduling.assignment_plan import AssignmentPlanIntent, AssignmentPlanSegmentIntent
    from infrastructure.mysql.mysql_adapter import get_connection
    from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
    from subsystems.scheduling.assignment_plan_workflow import (
        AssignmentPlanApplyRequest,
        AssignmentPlanPreviewRequest,
        AssignmentPlanWorkflowError,
    )

    service_dates = tuple(SERVICE_START + timedelta(days=offset) for offset in range(SERVICE_DAYS))
    intent = AssignmentPlanIntent((AssignmentPlanSegmentIntent(staff_id, SERVICE_START, SERVICE_END, service_dates),))
    connection = get_connection()
    try:
        application = build_assignment_plan_application(connection)
        preview = application.preview(AssignmentPlanPreviewRequest(CASE_NO, intent, CorrelationId(_key("assignment-stale-preview"))))
        request = AssignmentPlanApplyRequest(CASE_NO, intent, ExpectedVersion(preview.order_version + 1), ExpectedVersion(preview.scheduling_version), ExpectedVersion(preview.client_finance_version), ExpectedVersion(preview.payroll_version), preview.fingerprint, IdempotencyKey(_key("assignment-stale-apply")), ActorContext("wp56-validation"), "WP56 stale assignment rejection", CorrelationId(_key("assignment-stale-apply")))
        try:
            application.apply(request)
        except AssignmentPlanWorkflowError as error:
            if error.error.code != "stale_version":
                raise
        else:
            raise RuntimeError("stale_assignment_apply_was_accepted")
    finally:
        connection.close()
    snapshot = _pre_execution_snapshot()
    converted_events = _converted_commitment_events()
    if snapshot != {"assignments": 0, "schedule_days": 0} or converted_events:
        raise RuntimeError("stale_assignment_apply_partial_write")
    return {
        "error_code": "stale_version",
        "post_rejection": {**snapshot, "converted_events": converted_events},
    }


def _reject_occupied_assignment_plan(plan_id: int, staff_id: int) -> dict[str, object]:
    from api.dependencies.assignment_plan import build_assignment_plan_application
    from domains.scheduling.assignment_plan import AssignmentPlanIntent, AssignmentPlanSegmentIntent
    from infrastructure.mysql.mysql_adapter import get_connection
    from shared_kernel.identities import CorrelationId
    from subsystems.scheduling.assignment_plan_workflow import (
        AssignmentPlanPreviewRequest,
        AssignmentPlanWorkflowError,
    )
    from subsystems.scheduling.availability_lock_acquisition_workflow import acquire_caregiver_availability_lock, preview_caregiver_availability_lock

    lock_preview = preview_caregiver_availability_lock(CASE_NO, plan_id)
    try:
        lock_receipt = acquire_caregiver_availability_lock(CASE_NO, plan_id, _key("waiting-lock-occupancy"), "wp56-validation", lock_preview["preview_fingerprint"])
    except ValueError as error:
        conflicts = _availability_lock_conflicts(error)
        if not conflicts:
            raise
        snapshot = _pre_execution_snapshot()
        converted_events = _converted_commitment_events()
        if snapshot != {"assignments": 0, "schedule_days": 0} or converted_events:
            raise RuntimeError("occupied_assignment_plan_partial_write")
        return {
            "error_code": "availability_lock_conflict",
            "typed_error_live_drift": True,
            "conflict_count": len(conflicts),
            "post_rejection": {**snapshot, "converted_events": converted_events},
        }
    service_dates = tuple(SERVICE_START + timedelta(days=offset) for offset in range(SERVICE_DAYS))
    intent = AssignmentPlanIntent((AssignmentPlanSegmentIntent(staff_id, SERVICE_START, SERVICE_END, service_dates),))
    connection = get_connection()
    try:
        application = build_assignment_plan_application(connection)
        try:
            application.preview(AssignmentPlanPreviewRequest(CASE_NO, intent, CorrelationId(_key("assignment-occupancy-preview"))))
        except AssignmentPlanWorkflowError as error:
            if error.error.code != "staff_occupancy_conflict":
                raise
        else:
            raise RuntimeError("occupied_assignment_plan_was_accepted")
    finally:
        connection.close()
    snapshot = _pre_execution_snapshot()
    converted_events = _converted_commitment_events()
    if snapshot != {"assignments": 0, "schedule_days": 0} or converted_events:
        raise RuntimeError("occupied_assignment_plan_partial_write")
    return {
        "lock": lock_receipt,
        "error_code": "staff_occupancy_conflict",
        "post_rejection": {**snapshot, "converted_events": converted_events},
    }


def _availability_lock_conflicts(error: ValueError) -> tuple[object, ...]:
    try:
        value = json.loads(str(error))
    except json.JSONDecodeError:
        return ()
    conflicts = value.get("conflicts") if isinstance(value, dict) else None
    return tuple(conflicts) if isinstance(conflicts, list) else ()


def _plan_segment_id(plan_id: int) -> int:
    from infrastructure.mysql.mysql_adapter import get_connection

    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT id FROM caregiver_matching_plan_segments WHERE plan_id=%s ORDER BY segment_order", (plan_id,))
            row = cursor.fetchone()
    finally:
        connection.close()
    if row is None:
        raise RuntimeError("matching_plan_segment_missing")
    return int(row["id"])


def _finance_row_id(connection, batch_identity: str) -> int:
    with connection.cursor() as cursor:
        cursor.execute("SELECT event.finance_import_row_id FROM finance_import_batch_contracts contract JOIN finance_import_classification_events event ON event.batch_id=contract.batch_id WHERE contract.batch_identity=%s", (batch_identity,))
        row = cursor.fetchone()
    if row is None:
        raise RuntimeError("finance_import_row_missing")
    return int(row["finance_import_row_id"])


def _write_deposit_workbook(path: Path) -> None:
    transaction_date = SERVICE_START.strftime("%Y/%m/%d")
    pd.DataFrame([["說明"], ["序號", "交易日期", "交易時間", "帳務日期", "摘要", "支出金額", "存入金額", "帳戶餘額", "備註"], ["0001", transaction_date, "09:08:07", transaction_date, "轉帳", "", "16000", "16000", f"WP56 client deposit receipt {CASE_NO}"]]).to_excel(path, sheet_name="交易明細", index=False, header=False)


def _archive_root() -> Path:
    root = PROJECT_ROOT / "scratch" / "wp56-normal-chain" / CASE_NO / "contract-archive"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _fixed_now() -> datetime:
    return datetime(2026, 8, 1, tzinfo=timezone.utc)


def _receipt(value) -> dict[str, object]:
    return {name: getattr(value, name) for name in value.__dataclass_fields__}


def _scenario_case_no(scenario_id: str) -> str:
    digest = hashlib.sha256(scenario_id.encode("utf-8")).hexdigest()[:12].upper()
    return f"WP56-{digest}"


def _scenario_service_start(scenario_id: str) -> date:
    offset = int(hashlib.sha256(scenario_id.encode("utf-8")).hexdigest()[:8], 16) % 300
    return date(2030, 1, 1) + timedelta(days=offset * 7)


def _requested_service_start(arguments) -> date:
    value = getattr(arguments, "service_start", None)
    return date.fromisoformat(value) if value else _scenario_service_start(arguments.scenario_id)


def _requested_service_days(arguments) -> int:
    service_days = int(getattr(arguments, "service_days", 5))
    if service_days < 1:
        raise ValueError("service_days_must_be_positive")
    return service_days


def _key(label: str) -> str:
    return f"wp56-{CASE_NO.lower()}-{label}"


def _scenario_dataset(scenario_id: str) -> dict[str, object]:
    from scripts.seed_validation_dataset import DEFAULT_MANIFEST, load_dataset

    dataset = copy.deepcopy(load_dataset(DEFAULT_MANIFEST))
    root = dataset["root_case"]
    client = root["client_attributes"]
    suffix = hashlib.sha256(scenario_id.encode("utf-8")).hexdigest()[:8]
    root["case_no"] = CASE_NO
    client["case_no"] = CASE_NO
    client["name"] = f"WP56 驗收客戶 {suffix}"
    client["phone"] = "09" + str(int(suffix, 16)).zfill(8)[-8:]
    client["city"] = "臺北市"
    client["address"] = "中正區測試路 56 號"
    client["service_type"] = "連續服務"
    order = root["order_root_facts"]
    order["service_days"] = SERVICE_DAYS
    order["planned_start_date"] = SERVICE_START.isoformat()
    order["planned_end_date"] = SERVICE_END.isoformat()
    terms = root["client_payment_terms"]
    terms["deposit_due_date"] = (SERVICE_START - timedelta(days=7)).isoformat()
    terms["first_payment_due_date"] = SERVICE_START.isoformat()
    dataset["dataset_id"] = f"wp56-normal-chain-{scenario_id}"
    return dataset


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", required=True, type=int)
    parser.add_argument("--user", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--database", required=True)
    parser.add_argument("--confirm-database", required=True)
    parser.add_argument("--scenario-id", required=True)
    parser.add_argument("--manifest", type=Path, default=PROJECT_ROOT / "validation" / "datasets" / "dataset_v1_foundation.json")
    parser.add_argument("--source", type=Path, default=PROJECT_ROOT / "validation" / "external_inputs" / "contract_signing_staff_master_v1.json")
    parser.add_argument("--staff-source", type=Path, default=PROJECT_ROOT / "validation" / "external_inputs" / "contract_signing_staff_master_v1.json")
    parser.add_argument("--conversion-negative-first", action="store_true")
    parser.add_argument("--conversion-stale-first", action="store_true")
    parser.add_argument("--occupancy-negative", action="store_true")
    parser.add_argument("--service-start")
    parser.add_argument("--service-days", type=int, default=5)
    parser.add_argument("--stop-before-conversion", action="store_true")
    parser.add_argument("--prepare-assignment-ui", action="store_true")
    parser.add_argument("--resume-case")
    parser.add_argument("--stop-before-client-signed", action="store_true")
    parser.add_argument("--client-sign-failure-case", action="store_true")
    parser.add_argument("--client-sign-after-completion-failure-case", action="store_true")
    print(json.dumps(run(parser.parse_args()), ensure_ascii=False, default=str, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
