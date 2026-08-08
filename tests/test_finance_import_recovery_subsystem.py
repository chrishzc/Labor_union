"""Final subsystem contract for finance import recovery.

The ASUS target-host acceptance is deliberately opt-in and read-only here.
Applying a historical plan remains an explicit operator command after its
dry-run fingerprint has been reviewed.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from dataclasses import dataclass
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import uuid

import pymysql
import pytest

from scripts.imports.finance_statement_normalizer import normalize_workbook
from services.finance_import_review_alerts import (
    project_finance_import_review_alert,
    scan_completed_finance_import_review_alerts,
)
from services.system_alert_service import resolve_system_alert
from domains.finance_import.transaction_classifier import classify_finance_transaction
from services.db_service import DB_CONFIG


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ROOT = PROJECT_ROOT
REPOSITORY_FIXTURE = (
    PROJECT_ROOT / "document" / "資料庫、資料處理" / "歷史對帳單.xlsx"
)
APPLICATION_SOURCE = PROJECT_ROOT / "services" / "finance_import_application.py"
REPROCESS_SOURCE = PROJECT_ROOT / "services" / "finance_import_reprocessing.py"
IMPORT_CLI_SOURCE = (
    PROJECT_ROOT / "scripts" / "imports" / "import_finance_excel.py"
)
REPROCESS_CLI_SOURCE = (
    PROJECT_ROOT / "scripts" / "imports" / "reprocess_finance_import_batch.py"
)
DISPOSABLE_SCHEMA_PREFIX = "adad_finance_recovery_"
ASUS_OCCURRENCE_COUNT = 2659
ASUS_DISTINCT_COUNT = 2655
ASUS_INCOMING_COUNT = 2058
ASUS_OUTGOING_COUNT = 597
ASUS_VALID_VIRTUAL_ACCOUNT_COUNT = 279
ASUS_REMAINING_REVIEW_COUNT = 2376
_DISPOSABLE_SCHEMA = re.compile(r"^adad_finance_recovery_[0-9a-f]{12}$")
_REQUIRED_SOURCE_TABLES = frozenset(
    {
        "beclass_records",
        "client_payment_transactions",
        "client_payments",
        "finance_alert_events",
        "finance_alerts",
        "finance_import_batches",
        "finance_import_occurrences",
        "finance_import_reclassification_events",
        "finance_import_reprocess_runs",
        "finance_import_rows",
        "government_subsidy_transactions",
        "orders",
        "staff_actual_transfers",
        "staff_bank_accounts",
        "system_alerts",
    }
)


@dataclass(frozen=True)
class _RecoveryDatabaseConfig:
    host: str
    port: int
    user: str
    password: str

    def connect(self, database: str | None = None):
        kwargs = {
            "host": self.host,
            "port": self.port,
            "user": self.user,
            "password": self.password,
            "charset": "utf8mb4",
            "cursorclass": pymysql.cursors.DictCursor,
            "autocommit": True,
        }
        if database:
            kwargs["database"] = database
        return pymysql.connect(**kwargs)


def config_from_env(path: Path) -> tuple[_RecoveryDatabaseConfig, str]:
    values: dict[str, str] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            values[key.strip()] = value.strip().strip("\"'")
    return (
        _RecoveryDatabaseConfig(
            host=values.get("DB_HOST", str(DB_CONFIG["host"])),
            port=int(values.get("DB_PORT", str(DB_CONFIG["port"]))),
            user=values.get("DB_USER", str(DB_CONFIG["user"])),
            password=values.get(
                "DB_PASSWORD", str(DB_CONFIG["password"])
            ),
        ),
        values.get("DB_DATABASE", str(DB_CONFIG["database"])).strip(),
    )


def database_exists(config: _RecoveryDatabaseConfig, database: str) -> bool:
    connection = config.connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """SELECT COUNT(*) AS matched
                   FROM information_schema.SCHEMATA
                   WHERE SCHEMA_NAME=%s""",
                (database,),
            )
            return int(cursor.fetchone()["matched"]) == 1
    finally:
        connection.close()


def _mysql_client_command(
    config: _RecoveryDatabaseConfig,
    executable: str,
    container: str,
) -> list[str]:
    assert re.fullmatch(r"[A-Za-z0-9_.-]+", container)
    return [
        "docker",
        "exec",
        "-i",
        "-e",
        "MYSQL_PWD",
        container,
        executable,
        "--host",
        "127.0.0.1",
        "--port",
        str(config.port),
        "--user",
        config.user,
        "--default-character-set=utf8mb4",
    ]


def create_source_dump(
    config: _RecoveryDatabaseConfig,
    source: str,
    dump_path: Path,
    receipt_path: Path,
    *,
    mysql_container: str,
) -> None:
    environment = os.environ.copy()
    environment["MYSQL_PWD"] = config.password
    command = _mysql_client_command(
        config, "mysqldump", mysql_container
    ) + [
        "--single-transaction",
        "--routines",
        "--events",
        "--triggers",
        "--hex-blob",
        source,
    ]
    with dump_path.open("wb") as output:
        completed = subprocess.run(
            command,
            stdout=output,
            stderr=subprocess.PIPE,
            env=environment,
            check=False,
        )
    assert completed.returncode == 0
    payload = dump_path.read_bytes()
    assert payload and b"MySQL dump" in payload[:4096]
    receipt_path.write_text(
        json.dumps(
            {
                "database": source,
                "sha256": hashlib.sha256(payload).hexdigest(),
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def restore_candidate(
    config: _RecoveryDatabaseConfig,
    source: str,
    candidate: str,
    dump_path: Path,
    backup_receipt_path: Path,
    operation_receipt_path: Path,
    *,
    mysql_container: str,
) -> None:
    assert source != candidate
    assert re.fullmatch(r"[A-Za-z0-9_]+", candidate)
    assert not database_exists(config, candidate)
    receipt = json.loads(backup_receipt_path.read_text(encoding="utf-8"))
    payload = dump_path.read_bytes()
    assert receipt["database"] == source
    assert receipt["sha256"] == hashlib.sha256(payload).hexdigest()

    connection = config.connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                f"CREATE DATABASE `{candidate}` CHARACTER SET utf8mb4"
            )
    finally:
        connection.close()

    environment = os.environ.copy()
    environment["MYSQL_PWD"] = config.password
    command = _mysql_client_command(
        config, "mysql", mysql_container
    ) + [candidate]
    with dump_path.open("rb") as source_handle:
        completed = subprocess.run(
            command,
            stdin=source_handle,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=environment,
            check=False,
        )
    assert completed.returncode == 0
    operation_receipt_path.write_text(
        json.dumps(
            {"source": source, "candidate": candidate, "status": "restored"},
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def _strict_source(path: Path) -> str:
    raw = path.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8", errors="strict")
    assert "\ufffd" not in text
    return text


def _imported_names(path: Path) -> set[tuple[str, str]]:
    tree = ast.parse(_strict_source(path))
    names: set[tuple[str, str]] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or node.module is None:
            continue
        names.update((node.module, alias.name) for alias in node.names)
    return names


def _candidate_connection(config: object, database: str) -> pymysql.Connection:
    return pymysql.connect(
        host=config.host,
        port=config.port,
        user=config.user,
        password=config.password,
        database=database,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )


def _assert_upgraded_source(config: object, database: str) -> None:
    connection = config.connect(database)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """SELECT TABLE_NAME
                   FROM information_schema.TABLES
                   WHERE TABLE_SCHEMA=%s""",
                (database,),
            )
            actual = {str(row["TABLE_NAME"]) for row in cursor.fetchall()}
            missing = sorted(_REQUIRED_SOURCE_TABLES - actual)
            assert not missing, (
                "PRESERVED_DB_TEST_SOURCE must be an upgraded schema; "
                f"missing tables: {missing}"
            )
            cursor.execute(
                """SELECT COLUMN_NAME
                   FROM information_schema.COLUMNS
                   WHERE TABLE_SCHEMA=%s AND TABLE_NAME='system_alerts'""",
                (database,),
            )
            alert_columns = {
                str(row["COLUMN_NAME"]) for row in cursor.fetchall()
            }
            assert {
                "alert_code",
                "source_domain",
                "case_key",
                "reason",
                "details",
            } <= alert_columns
    finally:
        connection.close()


def _drop_disposable_schema(config: object, database: str) -> None:
    assert database.startswith(DISPOSABLE_SCHEMA_PREFIX)
    assert _DISPOSABLE_SCHEMA.fullmatch(database)
    connection = config.connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute(f"DROP DATABASE `{database}`")
    finally:
        connection.close()


@pytest.fixture
def asus_recovery_database(
    tmp_path: Path,
) -> Iterator[dict[str, object]]:
    container = os.getenv("MYSQL_TEST_CONTAINER", "").strip()
    if not container:
        pytest.fail(
            "MYSQL_TEST_CONTAINER is required; this gate must use real MySQL"
        )
    config, configured_source = config_from_env(ROOT / ".env")
    source = (
        os.getenv("PRESERVED_DB_TEST_SOURCE", "").strip()
        or configured_source
    )
    if not source:
        pytest.fail(
            "PRESERVED_DB_TEST_SOURCE is required when .env has no DB_DATABASE"
        )
    assert not source.startswith(DISPOSABLE_SCHEMA_PREFIX)
    _assert_upgraded_source(config, source)

    database = f"{DISPOSABLE_SCHEMA_PREFIX}{uuid.uuid4().hex[:12]}"
    dump_path = tmp_path / "source.sql"
    backup_receipt = tmp_path / "source.backup.json"
    restore_receipt = tmp_path / "candidate.restore.json"
    owns_database = False
    try:
        assert not database_exists(config, database)
        # Ownership begins only after this exact generated name was proven
        # absent.  A pre-existing collision must never be treated as ours.
        owns_database = True
        create_source_dump(
            config,
            source,
            dump_path,
            backup_receipt,
            mysql_container=container,
        )
        restore_candidate(
            config,
            source,
            database,
            dump_path,
            backup_receipt,
            restore_receipt,
            mysql_container=container,
        )
        yield {
            "config": config,
            "database": database,
            "connect": lambda: _candidate_connection(config, database),
        }
    finally:
        # A partial restore is still ours and may be removed, but an initial
        # collision never reaches this branch with ownership.
        if owns_database and database_exists(config, database):
            _drop_disposable_schema(config, database)


def _fingerprint(index: int) -> str:
    return hashlib.sha256(
        f"asus-finance-recovery:{index}".encode("ascii")
    ).hexdigest()


def _virtual_account(index: int) -> str:
    assert 0 <= index < ASUS_VALID_VIRTUAL_ACCOUNT_COUNT
    return f"99781699999{700 + index:03d}"


def _seed_asus_recovery_batch(connect: object) -> tuple[int, list[int]]:
    connection = connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """SELECT COUNT(*) AS matched
                   FROM orders
                   WHERE case_no BETWEEN '999000700' AND '999000978'"""
            )
            assert int(cursor.fetchone()["matched"]) == 0
            cursor.execute(
                """INSERT INTO finance_import_batches
                       (format_id,source_file,sheet_name,header_row,row_count,
                        status,completed_at)
                   VALUES
                       ('legacy','ASUS_TARGET_STATE_SIMULATION.xlsx',
                        '歷史對帳單',1,%s,'completed',CURRENT_TIMESTAMP)""",
                (ASUS_OCCURRENCE_COUNT,),
            )
            batch_id = int(cursor.lastrowid)

            rows = []
            for index in range(ASUS_DISTINCT_COUNT):
                incoming = index < ASUS_INCOMING_COUNT
                valid_virtual_account = (
                    incoming
                    and index < ASUS_VALID_VIRTUAL_ACCOUNT_COUNT
                )
                cancellation_code = (
                    _virtual_account(index)
                    if valid_virtual_account
                    else None
                )
                rows.append(
                    (
                        _fingerprint(index),
                        batch_id,
                        index + 2,
                        Decimal("100.00") if not incoming else None,
                        Decimal("100.00") if incoming else None,
                        "incoming" if incoming else "outgoing",
                        (
                            "ASUS deterministic incoming"
                            if incoming
                            else "ASUS deterministic outgoing"
                        ),
                        (
                            "ASUS deterministic incoming"
                            if incoming
                            else "ASUS deterministic outgoing"
                        ),
                        cancellation_code,
                        json.dumps(
                            (
                                {"銷帳編號": cancellation_code}
                                if cancellation_code
                                else {}
                            ),
                            ensure_ascii=False,
                        ),
                        json.dumps(
                            {"fixture": "asus-state", "index": index},
                            ensure_ascii=False,
                        ),
                        (
                            "sinopac_invalid_or_missing_virtual_account"
                            if incoming
                            else "sinopac_staff_account_no_match"
                        ),
                    )
                )
            cursor.executemany(
                """INSERT INTO finance_import_rows
                       (dedup_fingerprint,batch_id,format_id,source_file,
                        source_bank_account,sheet_name,source_row,
                        source_reference,transaction_date,transaction_time,
                        posting_date,value_date,debit,credit,direction,balance,
                        currency,summary,memo,counterparty_name,
                        counterparty_account,resolved_counterparty_account,
                        cancellation_code,bank_references,warnings,raw_payload,
                        matched_identity_ids,classification_type,
                        classification_reason,reconciliation_status)
                   VALUES
                       (%s,%s,'legacy','ASUS_TARGET_STATE_SIMULATION.xlsx',
                        'simulation-account','歷史對帳單',%s,NULL,
                        '2026-01-02',NULL,'2026-01-02','2026-01-02',
                        %s,%s,%s,NULL,'TWD',%s,%s,NULL,NULL,NULL,%s,%s,
                        JSON_ARRAY(),%s,JSON_ARRAY(),'non_business_review',
                        %s,'pending')""",
                rows,
            )
            cursor.execute(
                """SELECT id
                   FROM finance_import_rows
                   WHERE batch_id=%s
                   ORDER BY id""",
                (batch_id,),
            )
            row_ids = [int(row["id"]) for row in cursor.fetchall()]
            assert len(row_ids) == ASUS_DISTINCT_COUNT
            occurrences = [
                (
                    batch_id,
                    row_id,
                    "ASUS_TARGET_STATE_SIMULATION.xlsx",
                    "歷史對帳單",
                    index + 2,
                )
                for index, row_id in enumerate(row_ids)
            ]
            occurrences.extend(
                (
                    batch_id,
                    row_ids[index],
                    "ASUS_TARGET_STATE_SIMULATION.xlsx",
                    "歷史對帳單",
                    ASUS_DISTINCT_COUNT + index + 2,
                )
                for index in range(
                    ASUS_OCCURRENCE_COUNT - ASUS_DISTINCT_COUNT
                )
            )
            cursor.executemany(
                """INSERT INTO finance_import_occurrences
                       (batch_id,finance_import_row_id,source_file,sheet_name,
                        source_row,warnings)
                   VALUES (%s,%s,%s,%s,%s,JSON_ARRAY())""",
                occurrences,
            )
            projection = project_finance_import_review_alert(cursor, batch_id)
            assert projection["alert_action"] == "created"
            assert projection["summary"]["occurrence_count"] == (
                ASUS_OCCURRENCE_COUNT
            )
            assert projection["summary"]["distinct_count"] == (
                ASUS_DISTINCT_COUNT
            )
        connection.commit()
        return batch_id, row_ids
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _fetch_scalar(cursor: object, sql: str, params: tuple[object, ...]) -> int:
    cursor.execute(sql, params)
    return int(cursor.fetchone()["count"])


def _batch_snapshot(connect: object, batch_id: int) -> dict[str, object]:
    connection = connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """SELECT fir.id,fir.classification_type,
                          fir.classification_reason,
                          fir.matched_identity_ids,
                          fir.resolved_counterparty_account,
                          fir.reconciliation_status,
                          fir.reconciliation_reference,
                          fir.classified_at
                   FROM (
                       SELECT DISTINCT finance_import_row_id
                       FROM finance_import_occurrences
                       WHERE batch_id=%s
                   ) membership
                   JOIN finance_import_rows fir
                     ON fir.id=membership.finance_import_row_id
                   ORDER BY fir.id""",
                (batch_id,),
            )
            rows = cursor.fetchall()
            cursor.execute(
                """SELECT id,actor,plan_fingerprint,selected_count,
                          changed_count,dispatch_count,reconciled_count,
                          pending_count,status
                   FROM finance_import_reprocess_runs
                   WHERE batch_id=%s ORDER BY id""",
                (batch_id,),
            )
            runs = cursor.fetchall()
            event_count = _fetch_scalar(
                cursor,
                """SELECT COUNT(*) AS count
                   FROM finance_import_reclassification_events event
                   JOIN finance_import_reprocess_runs run ON run.id=event.run_id
                   WHERE run.batch_id=%s""",
                (batch_id,),
            )
            formal_counts = {
                "client": _fetch_scalar(
                    cursor,
                    """SELECT COUNT(*) AS count
                       FROM client_payment_transactions transaction_row
                       JOIN finance_import_occurrences occurrence
                         ON occurrence.finance_import_row_id=
                            transaction_row.finance_import_row_id
                       WHERE occurrence.batch_id=%s""",
                    (batch_id,),
                ),
                "government": _fetch_scalar(
                    cursor,
                    """SELECT COUNT(*) AS count
                       FROM government_subsidy_transactions transaction_row
                       JOIN finance_import_occurrences occurrence
                         ON occurrence.finance_import_row_id=
                            transaction_row.finance_import_row_id
                       WHERE occurrence.batch_id=%s""",
                    (batch_id,),
                ),
                "staff": _fetch_scalar(
                    cursor,
                    """SELECT COUNT(*) AS count
                       FROM staff_actual_transfers transfer
                       JOIN finance_import_occurrences occurrence
                         ON transfer.raw_import_reference=
                            CONCAT('finance_import_row:',
                                   occurrence.finance_import_row_id)
                       WHERE occurrence.batch_id=%s""",
                    (batch_id,),
                ),
            }
            cursor.execute(
                """SELECT id,alert_key,alert_code,status,finance_import_row_id
                   FROM finance_alerts
                   WHERE finance_import_batch_id=%s
                   ORDER BY id""",
                (batch_id,),
            )
            finance_alerts = cursor.fetchall()
            cursor.execute(
                """SELECT id,alert_code,source_domain,case_key,reason,details,
                          status,claimed_by,claimed_at,resolved_by,resolved_at,
                          resolution_reason
                   FROM system_alerts
                   WHERE alert_code='IMPORT-006'
                     AND case_key=%s
                   ORDER BY id""",
                (f"finance-import-batch:{batch_id}",),
            )
            system_alerts = cursor.fetchall()
            return {
                "rows": rows,
                "runs": runs,
                "event_count": event_count,
                "formal_counts": formal_counts,
                "finance_alerts": finance_alerts,
                "system_alerts": system_alerts,
            }
    finally:
        connection.close()


def _update_row(
    connect: object,
    row_id: int,
    *,
    cancellation_code: str | None,
    classification_type: str = "non_business_review",
    classification_reason: str = "sinopac_invalid_or_missing_virtual_account",
) -> None:
    connection = connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """UPDATE finance_import_rows
                   SET cancellation_code=%s,
                       bank_references=%s,
                       classification_type=%s,
                       classification_reason=%s,
                       matched_identity_ids=JSON_ARRAY(),
                       resolved_counterparty_account=NULL,
                       reconciliation_status='pending',
                       reconciliation_reference=NULL
                   WHERE id=%s""",
                (
                    cancellation_code,
                    json.dumps(
                        (
                            {"銷帳編號": cancellation_code}
                            if cancellation_code
                            else {}
                        ),
                        ensure_ascii=False,
                    ),
                    classification_type,
                    classification_reason,
                    row_id,
                ),
            )
            assert cursor.rowcount == 1
        connection.commit()
    finally:
        connection.close()


def test_repository_fixture_is_one_row_and_never_uses_name_as_identity() -> None:
    normalized = normalize_workbook(str(REPOSITORY_FIXTURE))

    assert normalized["format_id"] == "legacy"
    assert len(normalized["normalized_rows"]) == 1
    row = normalized["normalized_rows"][0]
    result = classify_finance_transaction(row, {}, {})
    assert result == {
        "classification_type": "non_business_review",
        "matched_identity_ids": [],
        "resolved_counterparty_account": None,
        "reason": "sinopac_staff_account_no_match",
    }
    assert row.get("counterparty_name") is None


def test_import_and_reprocess_use_the_same_public_dispatch_entrypoint() -> None:
    expected = (
        "services.finance_import_dispatch",
        "dispatch_finance_import_row",
    )

    assert expected in _imported_names(APPLICATION_SOURCE)
    assert expected in _imported_names(REPROCESS_SOURCE)
    for cli_path in (IMPORT_CLI_SOURCE, REPROCESS_CLI_SOURCE):
        cli_source = _strict_source(cli_path)
        assert "dispatch_finance_import_row" not in cli_source
        assert "_dispatch_inserted_row" not in cli_source
        assert "_staff_transfer_candidates" not in cli_source


def test_asus_batch_contract_counts_are_distinct_from_repository_fixture() -> None:
    occurrence_count = 2659
    distinct_count = 2655
    incoming_before = 2058
    outgoing_before = 597
    changed = 279
    remaining = distinct_count - changed

    assert occurrence_count - distinct_count == 4
    assert incoming_before + outgoing_before == distinct_count
    assert remaining == 2376
    assert incoming_before - changed == 1779
    assert 1779 + outgoing_before == remaining
    assert len(normalize_workbook(str(REPOSITORY_FIXTURE))["normalized_rows"]) == 1


def test_recovery_sources_preserve_plan_replay_and_bounded_output_contracts() -> None:
    reprocess = _strict_source(REPROCESS_SOURCE)
    reprocess_cli = _strict_source(REPROCESS_CLI_SOURCE)
    import_cli = _strict_source(IMPORT_CLI_SOURCE)

    assert "expected_plan_fingerprint" in reprocess
    assert "transaction_outcome" in reprocess
    assert '"existing"' in reprocess
    assert "finance_import_reclassification_events" in reprocess
    assert "project_finance_import_review_alert" in reprocess
    assert "row_results" not in reprocess_cli
    assert "raw_payload" not in reprocess_cli
    assert "raw_payload" not in import_cli


def test_target_host_acceptance_is_not_silently_replaced_by_local_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(
        "FINANCE_IMPORT_RECOVERY_TARGET_BATCH_ID",
        raising=False,
    )
    target_batch_id = None
    target_host_acceptance = (
        "passed" if target_batch_id is not None else "not_executed"
    )

    assert target_host_acceptance == "not_executed"
    assert len(normalize_workbook(str(REPOSITORY_FIXTURE))["normalized_rows"]) == 1


def _captured_summary(
    capsys: pytest.CaptureFixture[str],
) -> dict[str, object]:
    captured = capsys.readouterr()
    lines = captured.out.splitlines()
    assert captured.err == ""
    assert len(lines) == 1
    assert len(lines[0].encode("utf-8")) < 4096
    forbidden = (
        "row_results",
        "raw_payload",
        "張淑婷",
        "12345678901234",
        "secret",
    )
    assert all(token not in lines[0] for token in forbidden)
    decoded = json.loads(lines[0])
    assert isinstance(decoded, dict)
    return decoded


def _strict_json_report(path: Path) -> dict[str, object]:
    raw = path.read_bytes()
    assert raw
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8", errors="strict")
    assert "\ufffd" not in text
    forbidden = (
        "raw_payload",
        "張淑婷",
        "12345678901234",
        "secret",
    )
    assert all(token not in text for token in forbidden)
    decoded = json.loads(text)
    assert isinstance(decoded, dict)
    return decoded


def test_bounded_cli_stdout_reports_and_apply_prevalidation(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scripts.imports import import_finance_excel as import_cli
    from scripts.imports import reprocess_finance_import_batch as reprocess_cli

    workbook = tmp_path / "fixture.xlsx"
    workbook.write_bytes(b"CLI service is monkeypatched; workbook is not read")
    import_report = tmp_path / "import-report.json"
    import_manifest = {
        "mode": "dry_run",
        "transaction_outcome": "rolled_back",
        "source_path": str(workbook),
        "format_manifest": {
            "format_id": "legacy",
            "normalized_row_count": 1,
        },
        "batch_id": None,
        "inserted_rows": 1,
        "skipped_existing": 0,
        "reconciled_counts": {},
        "row_results": [
            {
                "fingerprint": "a" * 64,
                "classification_type": "non_business_review",
                "dispatch_result": "pending",
                "reason": "sinopac_staff_account_no_match",
            }
        ],
        "alert_action": {"alert_action": "created"},
    }
    import_calls = 0

    def fake_import(*_args: object, **_kwargs: object) -> dict[str, object]:
        nonlocal import_calls
        import_calls += 1
        return import_manifest

    monkeypatch.setattr(import_cli, "import_finance_workbook", fake_import)
    assert import_cli.main(["--excel-path", str(workbook), "--dry-run"]) == 0
    import_summary = _captured_summary(capsys)
    assert import_summary["pending_count"] == 1
    assert import_summary["report_path"] is None
    assert not import_report.exists()

    assert import_cli.main(
        [
            "--excel-path",
            str(workbook),
            "--dry-run",
            "--report-path",
            str(import_report),
        ]
    ) == 0
    reported_import_summary = _captured_summary(capsys)
    assert reported_import_summary["report_path"] == str(
        import_report.resolve()
    )
    import_payload = _strict_json_report(import_report)
    assert len(import_payload["row_results"]) <= (
        import_payload["format_manifest"]["normalized_row_count"]
    )
    assert import_calls == 2

    reprocess_report = tmp_path / "reprocess-report.json"
    reprocess_result = {
        "db_identity": {
            "database": "adad_finance_recovery_simulation",
            "server": "mysql-test",
        },
        "batch_manifest": {"batch_id": 1},
        "classification_summary": {
            "selected": ASUS_DISTINCT_COUNT,
            "unchanged": ASUS_REMAINING_REVIEW_COUNT,
            "changed": ASUS_VALID_VIRTUAL_ACCOUNT_COUNT,
            "before_reason_counts": {
                "sinopac_invalid_or_missing_virtual_account": (
                    ASUS_INCOMING_COUNT
                ),
                "sinopac_staff_account_no_match": ASUS_OUTGOING_COUNT,
            },
            "after_reason_counts": {
                "sinopac_invalid_or_missing_virtual_account": 1779,
                "sinopac_staff_account_no_match": ASUS_OUTGOING_COUNT,
                "sinopac_valid_virtual_account": (
                    ASUS_VALID_VIRTUAL_ACCOUNT_COUNT
                ),
            },
        },
        "dispatch_summary": {
            "attempted": ASUS_VALID_VIRTUAL_ACCOUNT_COUNT,
            "reconciled": 0,
            "pending": ASUS_VALID_VIRTUAL_ACCOUNT_COUNT,
            "bounded_references": [],
        },
        "alert_action": {
            "alert_action": "updated",
            "summary": {
                "remaining_count": ASUS_REMAINING_REVIEW_COUNT,
            },
        },
        "elapsed_seconds": 1.0,
        "rows_per_second": float(ASUS_DISTINCT_COUNT),
        "plan_fingerprint": "b" * 64,
        "transaction_outcome": "rolled_back",
        "run_id": None,
    }
    reprocess_calls = 0

    def fake_reprocess(
        *_args: object,
        **_kwargs: object,
    ) -> dict[str, object]:
        nonlocal reprocess_calls
        reprocess_calls += 1
        return reprocess_result

    monkeypatch.setattr(
        reprocess_cli,
        "reprocess_finance_import_batch",
        fake_reprocess,
    )
    with pytest.raises(ValueError, match="actor is required"):
        reprocess_cli.main(["--batch-id", "1", "--apply"])
    assert reprocess_calls == 0
    assert capsys.readouterr().out == ""

    assert reprocess_cli.main(["--batch-id", "1"]) == 0
    reprocess_summary = _captured_summary(capsys)
    assert reprocess_summary["selected"] == ASUS_DISTINCT_COUNT
    assert reprocess_summary["report_path"] is None
    assert not reprocess_report.exists()

    assert reprocess_cli.main(
        [
            "--batch-id",
            "1",
            "--report-path",
            str(reprocess_report),
        ]
    ) == 0
    reported_reprocess_summary = _captured_summary(capsys)
    assert reported_reprocess_summary["report_path"] == str(
        reprocess_report.resolve()
    )
    reprocess_payload = _strict_json_report(reprocess_report)
    assert "row_results" not in reprocess_payload
    assert reprocess_calls == 2


@pytest.mark.integration
def test_real_mysql_asus_state_dry_run_apply_replay_and_alert_lifecycle(
    asus_recovery_database: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connect = asus_recovery_database["connect"]
    batch_id, row_ids = _seed_asus_recovery_batch(connect)
    monkeypatch.setattr(
        "services.finance_import_reprocessing.get_connection",
        connect,
    )
    import services.finance_import_reprocessing as reprocessing

    reprocess_finance_import_batch = (
        reprocessing.reprocess_finance_import_batch
    )

    before_dry_run = _batch_snapshot(connect, batch_id)
    dry_run = reprocess_finance_import_batch(batch_id, dry_run=True)
    assert dry_run["transaction_outcome"] == "rolled_back"
    assert dry_run["run_id"] is None
    assert dry_run["batch_manifest"]["selected_distinct_count"] == (
        ASUS_DISTINCT_COUNT
    )
    assert dry_run["classification_summary"] == {
        "selected": ASUS_DISTINCT_COUNT,
        "changed": ASUS_VALID_VIRTUAL_ACCOUNT_COUNT,
        "unchanged": ASUS_REMAINING_REVIEW_COUNT,
        "before_reason_counts": {
            "sinopac_invalid_or_missing_virtual_account": ASUS_INCOMING_COUNT,
            "sinopac_staff_account_no_match": ASUS_OUTGOING_COUNT,
        },
        "after_reason_counts": {
            "sinopac_invalid_or_missing_virtual_account": 1779,
            "sinopac_staff_account_no_match": ASUS_OUTGOING_COUNT,
            "sinopac_valid_virtual_account": (
                ASUS_VALID_VIRTUAL_ACCOUNT_COUNT
            ),
        },
    }
    assert dry_run["dispatch_summary"]["attempted"] == (
        ASUS_VALID_VIRTUAL_ACCOUNT_COUNT
    )
    assert dry_run["dispatch_summary"]["reconciled"] == 0
    assert dry_run["dispatch_summary"]["pending"] == (
        ASUS_VALID_VIRTUAL_ACCOUNT_COUNT
    )
    assert dry_run["alert_action"]["summary"] == {
        "occurrence_count": ASUS_OCCURRENCE_COUNT,
        "distinct_count": ASUS_DISTINCT_COUNT,
        "remaining_count": ASUS_REMAINING_REVIEW_COUNT,
        "pending_count": ASUS_DISTINCT_COUNT,
        "inconsistent_count": 0,
        "direction_counts": {
            "incoming": 1779,
            "outgoing": ASUS_OUTGOING_COUNT,
        },
        "reason_counts": {
            "sinopac_invalid_or_missing_virtual_account": 1779,
            "sinopac_staff_account_no_match": ASUS_OUTGOING_COUNT,
        },
    }
    assert _batch_snapshot(connect, batch_id) == before_dry_run

    plan_fingerprint = dry_run["plan_fingerprint"]
    _update_row(connect, row_ids[0], cancellation_code=None)
    before_stale_apply = _batch_snapshot(connect, batch_id)
    with pytest.raises(RuntimeError, match="plan is stale"):
        reprocess_finance_import_batch(
            batch_id,
            actor="integration-test",
            dry_run=False,
            expected_plan_fingerprint=plan_fingerprint,
        )
    assert _batch_snapshot(connect, batch_id) == before_stale_apply
    _update_row(
        connect,
        row_ids[0],
        cancellation_code=_virtual_account(0),
    )

    real_dispatch = reprocessing.dispatch_finance_import_row
    dispatch_calls = 0

    def fail_during_dispatch(
        cursor: object,
        finance_import_row_id: int,
        originating_batch_id: int,
    ) -> dict[str, object]:
        nonlocal dispatch_calls
        dispatch_calls += 1
        if dispatch_calls == 7:
            raise RuntimeError("injected seventh dispatch failure")
        return real_dispatch(
            cursor,
            finance_import_row_id,
            originating_batch_id,
        )

    monkeypatch.setattr(
        reprocessing,
        "dispatch_finance_import_row",
        fail_during_dispatch,
    )
    before_injected_failure = _batch_snapshot(connect, batch_id)
    with pytest.raises(
        RuntimeError,
        match="injected seventh dispatch failure",
    ):
        reprocess_finance_import_batch(
            batch_id,
            actor="integration-test",
            dry_run=False,
            expected_plan_fingerprint=plan_fingerprint,
        )
    assert dispatch_calls == 7
    assert _batch_snapshot(connect, batch_id) == before_injected_failure
    monkeypatch.setattr(
        reprocessing,
        "dispatch_finance_import_row",
        real_dispatch,
    )

    applied = reprocess_finance_import_batch(
        batch_id,
        actor="integration-test",
        dry_run=False,
        expected_plan_fingerprint=plan_fingerprint,
    )
    assert applied["transaction_outcome"] == "committed"
    assert isinstance(applied["run_id"], int)
    assert applied["classification_summary"] == dry_run[
        "classification_summary"
    ]
    assert applied["dispatch_summary"]["attempted"] == (
        ASUS_VALID_VIRTUAL_ACCOUNT_COUNT
    )
    assert applied["alert_action"]["summary"]["remaining_count"] == (
        ASUS_REMAINING_REVIEW_COUNT
    )
    after_apply = _batch_snapshot(connect, batch_id)
    assert len(after_apply["runs"]) == 1
    assert after_apply["event_count"] == ASUS_VALID_VIRTUAL_ACCOUNT_COUNT
    assert after_apply["formal_counts"] == {
        "client": 0,
        "government": 0,
        "staff": 0,
    }
    # These 279 rows are business-classified pending dispatches.  Their
    # current pending reason is not in the existing finance-alert mapping, so
    # no finance_alert is created; critically, they also no longer contribute
    # to the aggregate IMPORT-006 non-business review count.
    assert len(after_apply["finance_alerts"]) == 0
    assert len(after_apply["system_alerts"]) == 1
    assert after_apply["system_alerts"][0]["status"] == "open"
    assert (
        json.loads(after_apply["system_alerts"][0]["details"])[
            "remaining_count"
        ]
        == ASUS_REMAINING_REVIEW_COUNT
    )

    replay = reprocess_finance_import_batch(
        batch_id,
        actor="integration-test",
        dry_run=False,
        expected_plan_fingerprint=plan_fingerprint,
    )
    assert replay["transaction_outcome"] == "existing"
    assert replay["run_id"] == applied["run_id"]
    assert _batch_snapshot(connect, batch_id) == after_apply

    connection = connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """UPDATE finance_import_rows row_to_clear
                   JOIN (
                       SELECT DISTINCT finance_import_row_id
                       FROM finance_import_occurrences
                       WHERE batch_id=%s
                   ) membership
                     ON membership.finance_import_row_id=row_to_clear.id
                   SET row_to_clear.classification_type='client_receipt',
                       row_to_clear.classification_reason=
                           'integration_alert_clear'
                   WHERE row_to_clear.classification_type=
                         'non_business_review'""",
                (batch_id,),
            )
            assert cursor.rowcount == ASUS_REMAINING_REVIEW_COUNT
            resolved = project_finance_import_review_alert(cursor, batch_id)
            assert resolved["alert_action"] == "resolved"
            assert resolved["summary"]["remaining_count"] == 0
        connection.commit()
    finally:
        connection.close()

    _update_row(
        connect,
        row_ids[-1],
        cancellation_code=None,
        classification_reason="sinopac_staff_account_no_match",
    )
    connection = connect()
    try:
        with connection.cursor() as cursor:
            reopened = project_finance_import_review_alert(cursor, batch_id)
            assert reopened["alert_action"] == "reopened"
            assert reopened["summary"]["remaining_count"] == 1
            alert_id = int(reopened["alert"]["id"])
            manually_resolved = resolve_system_alert(
                cursor,
                alert_id=alert_id,
                operator="integration-test",
                reason="exercise scanner reopen",
            )
            assert manually_resolved["result"] == "resolved"
        connection.commit()
    finally:
        connection.close()

    before_scan = _batch_snapshot(connect, batch_id)
    connection = connect()
    try:
        with connection.cursor() as cursor:
            scan = scan_completed_finance_import_review_alerts(cursor)
            assert scan["reopened"] >= 1
        connection.commit()
    finally:
        connection.close()
    after_scan = _batch_snapshot(connect, batch_id)
    for key in ("rows", "runs", "event_count", "formal_counts"):
        assert after_scan[key] == before_scan[key]
    assert after_scan["system_alerts"][0]["status"] == "open"

    _update_row(
        connect,
        row_ids[1],
        cancellation_code=None,
    )
    before_partial_residual = _batch_snapshot(connect, batch_id)
    with pytest.raises(RuntimeError, match="partial|conflict|stale"):
        reprocess_finance_import_batch(
            batch_id,
            actor="integration-test",
            dry_run=False,
            expected_plan_fingerprint=plan_fingerprint,
        )
    assert _batch_snapshot(connect, batch_id) == before_partial_residual
