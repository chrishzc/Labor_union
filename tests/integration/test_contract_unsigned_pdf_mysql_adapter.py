"""
File: test_contract_unsigned_pdf_mysql_adapter.py
Description: 在指定 1005 candidate 驗證未簽 PDF lineage、來源欄位契約與 caller-owned transaction。
"""

from __future__ import annotations

from datetime import datetime, timezone
import os
from uuid import uuid4

import pymysql
import pytest

from infrastructure.db.contract_unsigned_pdf_repository import (
    MySqlContractUnsignedPdfRepository,
)
from shared_kernel.identities import ActorContext
from subsystems.controlled_files.workflow import (
    ControlledFileApplyOutcome,
    ControlledFileApplyReceipt,
    ControlledFileOwner,
    ControlledFilePurpose,
    ControlledFileReadback,
)


_EXPECTED_DATABASE = "lu_test_contract_o2_candidate_1005_u3"
_DATABASE = os.getenv("LABOR_UNION_TEST_MYSQL_DATABASE", "").strip()
_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
pytestmark = pytest.mark.skipif(
    not _DATABASE,
    reason="requires explicit LABOR_UNION_TEST_MYSQL_* candidate configuration",
)


def _connection() -> pymysql.Connection:
    if _DATABASE != _EXPECTED_DATABASE:
        pytest.fail(
            "O2 integration test refuses every database except the approved 1005 candidate"
        )
    return pymysql.connect(
        host=os.environ["LABOR_UNION_TEST_MYSQL_HOST"],
        port=int(os.environ["LABOR_UNION_TEST_MYSQL_PORT"]),
        user=os.environ["LABOR_UNION_TEST_MYSQL_USER"],
        password=os.environ["LABOR_UNION_TEST_MYSQL_PASSWORD"],
        database=_DATABASE,
        charset="utf8mb4",
        autocommit=False,
        cursorclass=pymysql.cursors.DictCursor,
    )


def _count_scenario(connection: pymysql.Connection, case_no: str) -> int:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT (SELECT COUNT(*) FROM clients WHERE case_no=%s) + "
            "(SELECT COUNT(*) FROM controlled_file_staging_objects "
            "WHERE owner_type='contract_signing' AND subject_reference=%s) AS owned_rows",
            (case_no, case_no),
        )
        return int(cursor.fetchone()["owned_rows"])


def _assert_approved_target(connection: pymysql.Connection) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT DATABASE() AS database_name, @@hostname AS server_hostname"
        )
        target = cursor.fetchone()
    assert target["database_name"] == _EXPECTED_DATABASE
    assert str(target["server_hostname"]).strip()


def _seed_case(connection: pymysql.Connection, token: str) -> dict[str, object]:
    case_no = f"O2I-{token[:20]}"
    digest = token * 2
    with connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO clients (case_no,name,phone,city,address,service_time,service_type) "
            "VALUES (%s,'O2 client','0900000000','Test City','Test Address','day','care')",
            (case_no,),
        )
        client_id = int(cursor.lastrowid)
        cursor.execute(
            "INSERT INTO staff (name,identity_card,phone) VALUES "
            "('O2 staff',%s,'0900000001')",
            (f"O2-{token[:16]}",),
        )
        staff_id = int(cursor.lastrowid)
        cursor.execute(
            "INSERT INTO orders "
            "(case_no,client_id,status,service_days,service_hours_per_day,start_date,end_date) "
            "VALUES (%s,%s,'洽談中',20,8,'2026-09-01','2026-09-20')",
            (case_no, client_id),
        )
        cursor.execute(
            "INSERT INTO caregiver_matching_plans "
            "(case_no,version,status,is_active,start_date,end_date,created_by) "
            "VALUES (%s,1,'draft',1,'2026-09-01','2026-09-20','o2-integration')",
            (case_no,),
        )
        plan_id = int(cursor.lastrowid)
        cursor.execute(
            "INSERT INTO caregiver_matching_plan_segments "
            "(plan_id,segment_order,staff_id,assigned_start_date,assigned_end_date) "
            "VALUES (%s,1,%s,'2026-09-01','2026-09-20')",
            (plan_id, staff_id),
        )
        segment_id = int(cursor.lastrowid)
        cursor.execute(
            "INSERT INTO media_assets "
            "(category,owner_type,owner_id,storage_provider,storage_key,original_filename,"
            "mime_type,file_size,sha256) VALUES "
            "('contract','contract_signing',%s,'local',%s,'source.xlsx',%s,8,%s)",
            (case_no, f"o2-integration/{token}/source.xlsx", _XLSX_MIME, digest),
        )
        source_asset_id = int(cursor.lastrowid)
        cursor.execute(
            "INSERT INTO contract_document_versions "
            "(case_no,document_scope,document_role,matching_plan_id,matching_segment_id,"
            "document_target_key,template_key,template_sha256,mapping_sha256,"
            "facts_snapshot_sha256,media_asset_id,version_number,created_by) VALUES "
            "(%s,'staff_segment','template_generated',%s,%s,%s,'staff-contract-v1',"
            "%s,%s,%s,%s,1,'o2-integration')",
            (
                case_no,
                plan_id,
                segment_id,
                f"staff-segment:{segment_id}",
                digest,
                "b" * 64,
                "c" * 64,
                source_asset_id,
            ),
        )
        source_document_id = int(cursor.lastrowid)
        object_key = (
            f"unsigned-contract:{source_document_id}:libreoffice-headless-v1"
        )
        staging_id = "cfs_" + token
        file_id = "cf_" + token
        cursor.execute(
            "INSERT INTO controlled_file_staging_objects "
            "(staging_id,storage_locator,owner_type,subject_reference,object_key,purpose,"
            "logical_folder,original_filename,content_type,size_bytes,content_sha256,"
            "staging_state,staging_version,idempotency_key,command_fingerprint,"
            "created_by_actor,expires_at_utc,applied_at_utc) VALUES "
            "(%s,%s,'contract_signing',%s,%s,'unsigned_contract','contracts/unsigned',"
            "'unsigned.pdf','application/pdf',18,%s,'applied',1,%s,%s,'o2-integration',"
            "DATE_ADD(CURRENT_TIMESTAMP(6),INTERVAL 1 DAY),CURRENT_TIMESTAMP(6))",
            (
                staging_id,
                f"o2-integration/{token}/staged.pdf",
                case_no,
                object_key,
                digest,
                f"o2.integration.{token}",
                "d" * 64,
            ),
        )
        staging_row_id = int(cursor.lastrowid)
        cursor.execute(
            "INSERT INTO controlled_file_objects "
            "(opaque_object_id,source_staging_id,owner_type,subject_reference,object_key,"
            "purpose,logical_folder,filename,storage_locator,content_type,size_bytes,"
            "content_sha256,version_number,created_by_actor) VALUES "
            "(%s,%s,'contract_signing',%s,%s,'unsigned_contract','contracts/unsigned',"
            "'unsigned.pdf',%s,'application/pdf',18,%s,1,'o2-integration')",
            (
                file_id,
                staging_row_id,
                case_no,
                object_key,
                f"o2-integration/{token}/active.pdf",
                digest,
            ),
        )
        controlled_file_id = int(cursor.lastrowid)
        cursor.execute(
            "INSERT INTO contract_external_signing_sessions "
            "(external_signing_session_id,case_no,matching_plan_id,"
            "current_document_set_sha256,session_state,activated_by_actor) "
            "VALUES (%s,%s,%s,%s,'staff_reporting','o2-integration')",
            ("ces_" + token, case_no, plan_id, digest),
        )
        session_id = int(cursor.lastrowid)
    return {
        "case_no": case_no,
        "digest": digest,
        "file_id": file_id,
        "object_key": object_key,
        "plan_id": plan_id,
        "segment_id": segment_id,
        "staff_id": staff_id,
        "source_document_id": source_document_id,
        "staging_row_id": staging_row_id,
        "controlled_file_id": controlled_file_id,
        "session_id": session_id,
    }


@pytest.fixture
def scenario():
    token = uuid4().hex
    case_no = f"O2I-{token[:20]}"
    connection = _connection()
    verifier = _connection()
    try:
        _assert_approved_target(connection)
        assert _count_scenario(connection, case_no) == 0
        seeded = _seed_case(connection, token)
        yield connection, verifier, seeded
    finally:
        connection.rollback()
        connection.close()
        try:
            assert _count_scenario(verifier, case_no) == 0
        finally:
            verifier.close()


def test_1005_manual_source_columns_and_unsigned_controlled_fk(scenario):
    connection, _, seeded = scenario
    token = seeded["file_id"][3:]
    digest = seeded["digest"]
    with connection.cursor() as cursor:
        cursor.execute("SAVEPOINT invalid_manual")
        with pytest.raises(pymysql.MySQLError) as captured:
            cursor.execute(
                "INSERT INTO contract_external_completion_reports "
                "(report_id,external_signing_session_id,case_no,report_scope,"
                "matching_segment_id,document_version_id,reporter_subject_type,"
                "reporter_subject_reference,source_kind,source_event_identity,"
                "source_payload_sha256,idempotency_key,command_fingerprint,"
                "expected_status_version,resulting_status_version,occurred_at_utc,actor_ref) "
                "VALUES (%s,%s,%s,'staff',%s,%s,'staff',%s,'manual_attested',%s,%s,%s,%s,"
                "0,1,CURRENT_TIMESTAMP(6),'o2-integration')",
                (
                    "cer_" + token,
                    seeded["session_id"],
                    seeded["case_no"],
                    seeded["segment_id"],
                    seeded["source_document_id"],
                    str(seeded["staff_id"]),
                    f"manual-invalid:{token}",
                    digest,
                    f"o2.manual.invalid.{token}",
                    "e" * 64,
                ),
            )
        assert captured.value.args[0] == 3819
        assert "chk_contract_external_report_source" in str(captured.value)
        cursor.execute("ROLLBACK TO SAVEPOINT invalid_manual")

        cursor.execute("SAVEPOINT valid_manual")
        cursor.execute(
            "INSERT INTO contract_external_completion_reports "
            "(report_id,external_signing_session_id,case_no,report_scope,"
            "matching_segment_id,document_version_id,reporter_subject_type,"
            "reporter_subject_reference,source_kind,source_event_identity,"
            "source_payload_sha256,manual_confirmation_method,manual_reason,"
            "manual_evidence_reference,manual_evidence_sha256,idempotency_key,"
            "command_fingerprint,expected_status_version,resulting_status_version,"
            "occurred_at_utc,actor_ref) VALUES "
            "(%s,%s,%s,'staff',%s,%s,'staff',%s,'manual_attested',%s,%s,"
            "'voice-confirmed','verification test','receipt:test',%s,%s,%s,0,1,"
            "CURRENT_TIMESTAMP(6),'o2-integration')",
            (
                "cer_" + token,
                seeded["session_id"],
                seeded["case_no"],
                seeded["segment_id"],
                seeded["source_document_id"],
                str(seeded["staff_id"]),
                f"manual-valid:{token}",
                digest,
                "f" * 64,
                f"o2.manual.valid.{token}",
                "1" * 64,
            ),
        )
        cursor.execute(
            "SELECT line_inbox_event_id,verified_line_user_id,verified_binding_version,"
            "manual_confirmation_method,manual_reason,manual_evidence_reference,"
            "manual_evidence_sha256 FROM contract_external_completion_reports "
            "WHERE report_id=%s",
            ("cer_" + token,),
        )
        row = cursor.fetchone()
        assert row["line_inbox_event_id"] is None
        assert row["verified_line_user_id"] is None
        assert row["verified_binding_version"] is None
        assert all(row[name] is not None for name in (
            "manual_confirmation_method",
            "manual_reason",
            "manual_evidence_reference",
            "manual_evidence_sha256",
        ))
        cursor.execute("ROLLBACK TO SAVEPOINT valid_manual")

        line_user_id = f"U-o2-{token}"
        cursor.execute(
            "INSERT INTO line_identity_bindings "
            "(line_user_id,binding_status,subject_type,subject_reference,aggregate_version) "
            "VALUES (%s,'bound','staff',%s,1)",
            (line_user_id, str(seeded["staff_id"])),
        )
        cursor.execute(
            "INSERT INTO line_inbox_events "
            "(event_identity,destination_id,event_type,source_type,source_identity,"
            "source_user_id,occurred_at_utc,payload_fingerprint,payload_snapshot,"
            "identity_source,processing_status) VALUES "
            "(%s,'o2-test','message','user',%s,%s,CURRENT_TIMESTAMP(6),%s,"
            "JSON_OBJECT('kind','verification'),'provider','processed')",
            (f"o2-line:{token}", line_user_id, line_user_id, "2" * 64),
        )
        inbox_id = int(cursor.lastrowid)
        cursor.execute(
            "INSERT INTO contract_external_completion_reports "
            "(report_id,external_signing_session_id,case_no,report_scope,"
            "matching_segment_id,document_version_id,reporter_subject_type,"
            "reporter_subject_reference,source_kind,source_event_identity,"
            "source_payload_sha256,line_inbox_event_id,verified_line_user_id,"
            "verified_binding_version,idempotency_key,command_fingerprint,"
            "expected_status_version,resulting_status_version,occurred_at_utc,actor_ref) "
            "VALUES (%s,%s,%s,'staff',%s,%s,'staff',%s,'verified_line',%s,%s,%s,%s,1,"
            "%s,%s,0,1,CURRENT_TIMESTAMP(6),'o2-integration')",
            (
                "cer_" + token,
                seeded["session_id"],
                seeded["case_no"],
                seeded["segment_id"],
                seeded["source_document_id"],
                str(seeded["staff_id"]),
                f"line-valid:{token}",
                digest,
                inbox_id,
                line_user_id,
                f"o2.line.valid.{token}",
                "3" * 64,
            ),
        )
        cursor.execute(
            "SELECT line_inbox_event_id,verified_line_user_id,verified_binding_version,"
            "manual_confirmation_method,manual_reason,manual_evidence_reference,"
            "manual_evidence_sha256 FROM contract_external_completion_reports "
            "WHERE report_id=%s",
            ("cer_" + token,),
        )
        row = cursor.fetchone()
        assert row["line_inbox_event_id"] == inbox_id
        assert row["verified_line_user_id"] == line_user_id
        assert row["verified_binding_version"] == 1
        assert all(row[name] is None for name in (
            "manual_confirmation_method",
            "manual_reason",
            "manual_evidence_reference",
            "manual_evidence_sha256",
        ))

        cursor.execute("SAVEPOINT invalid_fk")
        with pytest.raises(pymysql.IntegrityError) as fk_error:
            cursor.execute(
                "INSERT INTO controlled_file_objects "
                "(opaque_object_id,source_staging_id,owner_type,subject_reference,object_key,"
                "purpose,logical_folder,filename,storage_locator,content_type,size_bytes,"
                "content_sha256,version_number,created_by_actor) VALUES "
                "(%s,18446744073709551614,'contract_signing',%s,%s,'unsigned_contract',"
                "'contracts/unsigned','fk.pdf',%s,'application/pdf',18,%s,1,'o2-integration')",
                (
                    "cf_" + uuid4().hex,
                    seeded["case_no"],
                    f"unsigned-contract:{seeded['source_document_id']}:fk-test",
                    f"o2-integration/{token}/fk.pdf",
                    digest,
                ),
            )
        assert fk_error.value.args[0] == 1452
        assert "fk_controlled_file_object_staging" in str(fk_error.value)
        cursor.execute("ROLLBACK TO SAVEPOINT invalid_fk")

        cursor.execute(
            "SELECT purpose,source_staging_id FROM controlled_file_objects "
            "WHERE id=%s",
            (seeded["controlled_file_id"],),
        )
        controlled = cursor.fetchone()
    assert controlled == {
        "purpose": "unsigned_contract",
        "source_staging_id": seeded["staging_row_id"],
    }


def test_repository_current_exact_lineage_and_outer_rollback(scenario):
    connection, verifier, seeded = scenario
    repository = MySqlContractUnsignedPdfRepository(connection)
    source = repository.lock_source_for_persistence(
        seeded["case_no"], seeded["source_document_id"]
    )
    assert source.is_current is True
    readback = ControlledFileReadback(
        file_id=seeded["file_id"],
        owner=ControlledFileOwner.CONTRACT_SIGNING,
        purpose=ControlledFilePurpose.UNSIGNED_CONTRACT,
        subject_reference=seeded["case_no"],
        filename="unsigned.pdf",
        logical_folder="contracts/unsigned",
        version=1,
        sha256_digest=seeded["digest"],
        mime_type="application/pdf",
        size_bytes=18,
        status="active",
        applied_at=datetime.now(timezone.utc),
    )
    receipt = ControlledFileApplyReceipt(
        "cfr_" + uuid4().hex,
        ControlledFileApplyOutcome.CREATED,
        readback,
    )

    persisted_id = repository.register_persisted_pdf(
        source=source,
        controlled_file_receipt=receipt,
        renderer_identity="libreoffice-headless-v1",
        actor=ActorContext("admin:7"),
    )

    current = repository.load_current_pdf(seeded["case_no"], persisted_id)
    assert current is not None
    assert current.document_version_id == persisted_id
    assert current.object_reference == seeded["file_id"]
    assert repository.load_current_pdf(
        seeded["case_no"], seeded["source_document_id"]
    ) is None
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT document.version_number,document.replaces_document_version_id,"
            "asset.storage_key,object_row.object_key,object_row.purpose "
            "FROM contract_document_versions document "
            "JOIN media_assets asset ON asset.id=document.media_asset_id "
            "JOIN controlled_file_objects object_row "
            "ON object_row.opaque_object_id=asset.storage_key "
            "WHERE document.id=%s",
            (persisted_id,),
        )
        lineage = cursor.fetchone()
    assert lineage == {
        "version_number": 2,
        "replaces_document_version_id": seeded["source_document_id"],
        "storage_key": seeded["file_id"],
        "object_key": seeded["object_key"],
        "purpose": "unsigned_contract",
    }

    assert _count_scenario(verifier, seeded["case_no"]) == 0
    connection.rollback()
    assert _count_scenario(verifier, seeded["case_no"]) == 0
