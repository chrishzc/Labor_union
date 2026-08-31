# -*- coding: utf-8 -*-
"""
File: import_client_hcm.py
Description: 提供 HCM typed Web intake 共用正規化；舊 CLI 寫入固定退役。
"""
import sys
import os
import re
from datetime import date, datetime, timedelta

import pymysql
import pandas as pd
from dotenv import load_dotenv

# 確保中文輸出編碼正確
try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.append(ROOT)

from domains.case_import.client_import_validation import (
    HCM_REQUIRED_HEADERS,
    validate_hcm_row,
)
from domains.case_import.case_import import (
    HcmIdentityResolution,
    fingerprint_case_import_source,
)
from api.dependencies.case_import import build_case_import_application
from infrastructure.mysql.hcm_import_review_repository import MySqlHcmImportReviewRepository
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from subsystems.case_import.beclass_review_intake import fingerprint_workbook
from subsystems.case_import.hcm_import_review_intake import record_hcm_import_review
from subsystems.case_import.hcm_adapter import (
    build_hcm_case_import_intent,
    build_hcm_partial_case_import_intent,
    calculate_hcm_service_end_date,
    parse_hcm_service_time,
)
from infrastructure.mysql.hcm_beclass_reconciliation_adapter import (
    MySqlHcmBeClassReconciliationAdapter,
)
from infrastructure.mysql.case_pairing_anomaly_recheck_sink import (
    MySqlCasePairingAnomalyRecheckSink,
)
from shared_kernel.identities import (
    ActorContext,
    CorrelationId,
    ExpectedVersion,
    IdempotencyKey,
)
from subsystems.case_import.case_import_workflow import (
    ApplyCaseImport,
    CaseImportWorkflowError,
)
from subsystems.case_import.hcm_beclass_reconciliation import (
    CaseImportReconciliationApplication,
)

# Local operator compatibility only. Missing database settings fail closed.
load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

_REQUIRED_DATABASE_SETTINGS = ("DB_HOST", "DB_USER", "DB_PASSWORD", "DB_DATABASE")

# 欄位映射關係 (與舊 import_excel.py 一致，但移除 案件狀態 映射以免覆寫 status)
CLIENTS_FIELD_MAPPING = {
    '項次': 'seq_num',
    '不符合原因': 'reject_reason',
    '查詢序號(案件編號)': 'case_no',
    '報名時間(建檔)': 'created_at',
    'IP位址': 'ip_address',
    '姓名': 'name',
    '性別': 'gender',
    '行動電話': 'phone',
    '縣市': 'city',
    '地址': 'address',
    '身分資格': 'identity_status',
    '服務時間': 'service_time',
    '預產期/預計服務開始月份': 'due_month',
    '預計服務日期': 'service_start_date',
    '其他事項': 'notes',
    '希望服務天數': 'service_days',
    '居住型態': 'residence_type',
    '生產方式': 'delivery_type',
    '服務方式': 'service_type',
    '寶寶資訊': 'baby_info',
    'LINE ID': 'line_id',
    '管理者註記事項': 'admin_notes'
}

def clean_phone(phone_val):
    if pd.isna(phone_val) or not phone_val:
        return None
    phone = str(phone_val).replace(" ", "").replace("-", "").strip()
    phone = re.sub(r'(?<!^)\D', '', phone)
    if phone.startswith("+886"):
        phone = "0" + phone[4:]
    elif phone.startswith("886"):
        phone = "0" + phone[3:]
    if len(phone) == 9 and phone.startswith("9"):
        phone = "0" + phone
    return phone

def clean_city_and_address(city_val, address_val):
    city = str(city_val).strip() if pd.notna(city_val) else ""
    address = str(address_val).strip() if pd.notna(address_val) else ""
    city = city.replace("臺", "台")
    address = address.replace("臺", "台")

    if not city and len(address) >= 3:
        for possible_city in ["台北市", "新北市", "桃園市", "台中市", "台南市", "高雄市", "基隆市", "新竹市", "嘉義市", "新竹縣", "苗栗縣", "彰化縣", "南投縣", "雲林縣", "嘉義縣", "屏東縣", "宜蘭縣", "花蓮縣", "台東縣", "澎湖縣", "金門縣", "連江縣"]:
            if address.startswith(possible_city):
                city = possible_city
                break

    if city in ["台北", "新北", "桃園", "台中", "台南", "高雄"]:
        city = city + "市"
    elif city in ["新竹", "苗栗", "彰化", "南投", "雲林", "嘉義", "屏東", "宜蘭", "花蓮", "台東", "澎湖", "金門", "連江"]:
        city = city + "縣"

    return city, address

def clean_data(val, col_name):
    if pd.isna(val):
        return None
    if col_name in ['seq_num', 'service_days']:
        try:
            return int(val)
        except:
            return None
    return str(val).strip()


def _parse_date(value):
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    roc_dt = _parse_roc_datetime(value)
    if roc_dt:
        return roc_dt.date()
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.date()



def _parse_roc_datetime(text):
    text = str(text).strip()
    pattern = r"^\s*(\d{2,4})[\/\-.](\d{1,2})[\/\-.](\d{1,2})(?:\s+(\d{1,2}):(\d{2})(?::(\d{2})(?:\.\d+)?)?)?\s*$"
    match = re.match(pattern, text)
    if not match:
        return None
    year, month, day, hour, minute, second = match.groups()
    year = int(year)
    if year < 1911:
        year += 1911

    hour = int(hour) if hour else 0
    minute = int(minute) if minute else 0
    second = int(second) if second else 0
    extra_days = 0
    if hour == 24:
        hour = 0
        extra_days = 1
    elif hour > 24:
        return None

    from datetime import datetime, timezone
    try:
        dt = datetime(
            year,
            int(month),
            int(day),
            hour,
            minute,
            second,
        )
        if extra_days:
            dt += timedelta(days=1)
        return dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _parse_datetime(value):
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    roc_dt = _parse_roc_datetime(value)
    if roc_dt:
        return roc_dt
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return None
    if parsed.tzinfo is None:
        from datetime import timezone
        parsed = parsed.tz_localize(timezone.utc)
    return parsed.to_pydatetime()


def _load_holiday_dates(cursor):
    cursor.execute("SELECT holiday_date FROM holidays")
    return {
        parsed
        for row in cursor.fetchall()
        if (parsed := _parse_date(row["holiday_date"])) is not None
    }


def _calculate_service_end_date(start_date, service_days, service_type, holiday_dates):
    if start_date is None or not service_days:
        return None
    return calculate_hcm_service_end_date(start_date, service_days, service_type, holiday_dates)


def _result(inserted=0, inserted_with_warning=0, exact_replay=0, review_required=0, failed=0):
    return {
        "inserted": inserted,
        "inserted_with_warning": inserted_with_warning,
        "exact_replay": exact_replay,
        "review_required": review_required,
        "failed": failed,
    }


def process_import(excel_path):
    if not os.path.exists(excel_path):
        print(f"錯誤：找不到 Excel 檔案：{excel_path}")
        return _result(review_required=1)

    frame = _load_hcm_frame(excel_path)
    if frame is None:
        return _result(review_required=1)

    connection = _connect_database()
    if connection is None:
        return _result(failed=1)
    try:
        return _process_import_rows(frame, connection, excel_path)
    finally:
        connection.close()


def _load_hcm_frame(excel_path):
    print(f"解析 Excel 檔案：{excel_path} ...")
    with pd.ExcelFile(excel_path) as workbook:
        candidates = _hcm_sheet_candidates(workbook)
    if not candidates:
        print("沒有工作表符合 HCM 必要欄位契約。跳過此檔案。")
        return None
    if len(candidates) > 1:
        print("有多個工作表符合 HCM 必要欄位契約，無法安全自動選擇。跳過此檔案。")
        return None
    target_sheet, frame = candidates[0]
    frame.attrs["source_sheet"] = target_sheet
    print(f"已依欄位契約選取工作表，共有 {len(frame)} 筆資料，準備匯入...")
    return frame


def _hcm_sheet_candidates(workbook):
    candidates = []
    for sheet_name in workbook.sheet_names:
        frame = workbook.parse(sheet_name=sheet_name, dtype=object)
        actual_headers = {str(column).strip() for column in frame.columns}
        if not frame.dropna(how="all").empty and HCM_REQUIRED_HEADERS <= actual_headers:
            candidates.append((sheet_name, frame))
    return candidates


def _connect_database():
    try:
        connection = pymysql.connect(
            **_database_config(),
            cursorclass=pymysql.cursors.DictCursor,
        )
        cursor = connection.cursor()
        cursor.execute("SET NAMES utf8mb4;")
        return connection
    except Exception as error:
        print(f"資料庫連線失敗：{error}")
        return None


def _database_config():
    missing = [name for name in _REQUIRED_DATABASE_SETTINGS if not os.getenv(name, "").strip()]
    if missing:
        raise RuntimeError(f"hcm_import_database_config_missing:{','.join(missing)}")
    database = os.environ["DB_DATABASE"].strip()
    allowed = {
        item.strip()
        for item in os.getenv("IMPORT_ALLOWED_DATABASES", "").split(",")
        if item.strip()
    }
    if not allowed or database not in allowed:
        raise RuntimeError("hcm_import_database_target_not_allowed")
    return {
        "host": os.environ["DB_HOST"].strip(),
        "port": int(os.getenv("DB_PORT", "3306")),
        "user": os.environ["DB_USER"].strip(),
        "password": os.environ["DB_PASSWORD"],
        "database": database,
        "charset": "utf8mb4",
    }


# Kept cohesive because it owns the one batch-level rollback and result tally.
def _process_import_rows(frame, connection, excel_path):
    return _process_import_rows_with_boundary(
        frame, connection, excel_path, whole_workbook=False,
    )


def _process_import_rows_with_boundary(frame, connection, excel_path, *, whole_workbook):
    counts = _result()
    row_outcomes = []
    application = build_case_import_application(connection)
    cursor = connection.cursor()
    source_digest = fingerprint_workbook(excel_path)
    source_sheet = str(frame.attrs.get("source_sheet") or "HCM")
    try:
        for ordinal, (_, row) in enumerate(frame.iterrows(), start=1):
            if whole_workbook:
                outcome = _import_row(
                    row,
                    ordinal,
                    cursor,
                    application,
                    excel_path,
                    connection=connection,
                    source_digest=source_digest,
                    source_sheet=source_sheet,
                    detailed=True,
                    current_uow=True,
                )
            else:
                outcome = application.execute_in_uow(
                    lambda row=row, ordinal=ordinal: _import_row(
                        row,
                        ordinal,
                        cursor,
                        application,
                        excel_path,
                        connection=connection,
                        source_digest=source_digest,
                        source_sheet=source_sheet,
                        detailed=True,
                        current_uow=True,
                    )
                )
            counts[outcome["outcome"]] += 1
            row_outcomes.append(outcome)
    except Exception as error:
        if whole_workbook:
            # The workbook application owns this transaction.  Do not turn a
            # partial write into a committed failed receipt; its context must
            # roll every row, review, claim, and receipt back together.
            raise
        _report_import_failure(error)
        counts["failed"] = 1
        counts["row_outcomes"] = row_outcomes
        return counts
    _report_import_success(counts)
    counts["row_outcomes"] = row_outcomes
    return counts


class HcmLegacyRowIntake:
    """Temporary adapter exposing existing HCM normalization to typed Web composition."""

    def __init__(self, connection) -> None:
        self._connection = connection

    def load_frame(self, source_path: str):
        return _load_hcm_frame(source_path)

    def import_rows(self, frame, source_path: str) -> dict[str, object]:
        return _process_import_rows(frame, self._connection, source_path)

    def import_rows_in_current_uow(self, frame, source_path: str) -> dict[str, object]:
        """Import HCM rows while borrowing the workbook application UoW."""
        return _process_import_rows_with_boundary(
            frame, self._connection, source_path, whole_workbook=True,
        )

    def preview_rows(self, frame, source_path: str) -> dict[str, int]:
        outcomes = {"ready": 0, "ready_with_warning": 0, "review_required": 0}
        for _, row in frame.iterrows():
            record = _normalized_record(row)
            validation_errors = validate_hcm_row(row.to_dict())
            if not record.get("case_no") or not isinstance(record.get("created_at"), datetime):
                outcomes["review_required"] += 1
                continue
            outcome = "ready_with_warning" if validation_errors else "ready"
            outcomes[outcome] += 1
        return outcomes


# Kept cohesive because every row gate must resolve to one observable outcome.
def _import_row(
    row,
    ordinal,
    cursor,
    application,
    excel_path,
    *,
    connection=None,
    source_digest=None,
    source_sheet="HCM",
    detailed=False,
    current_uow=False,
):
    raw_row = row.to_dict()
    record = _normalized_record(row)
    case_no = record.get("case_no")
    if not case_no:
        problem_identity = _persist_hcm_review(
            connection,
            source_digest,
            source_sheet,
            ordinal,
            raw_row,
            None,
            {"查詢序號(案件編號)": "case_import_case_no_required"},
        )
        errors = {"查詢序號(案件編號)": "case_import_case_no_required"}
        return _row_outcome("review_required", ordinal, None, errors, problem_identity, detailed)
    validation_errors = validate_hcm_row(raw_row)
    if not isinstance(record.get("created_at"), datetime):
        validation_errors["報名時間(建檔)"] = "報名時間(建檔) 格式無法轉成 datetime"
    try:
        intent = _hcm_import_intent(cursor, record, validation_errors)
        correlation = CorrelationId(f"hcm-case-import:{case_no}:{ordinal}")
        identity_resolution = application.resolve_hcm_identity(
            str(case_no), str(record.get("ip_address") or "").strip(),
            str(record.get("name") or "").strip(),
        )
        if identity_resolution is HcmIdentityResolution.EXISTING_MATCH:
            outcome = _replay_existing_hcm_case(
                application,
                intent,
                correlation,
                excel_path,
                connection,
                source_digest,
                source_sheet,
                ordinal,
                raw_row,
                current_uow=current_uow,
            )
            return _row_outcome(outcome, ordinal, str(case_no), {}, None, detailed)
        preview = application.preview(intent, correlation)
        command = _apply_command(intent, preview, correlation, excel_path)
        _apply_case_import(application, command, current_uow=current_uow)
        warning_errors = _hcm_warning_errors(validation_errors, identity_resolution)
        problem_identity = None
        if warning_errors:
            problem_identity = _persist_hcm_review(
                connection, source_digest, source_sheet, ordinal, raw_row, case_no, warning_errors,
            )
        if current_uow:
            _reconcile_without_rolling_back_hcm(
                connection, str(case_no), in_current_uow=True,
            )
        else:
            _reconcile_without_rolling_back_hcm(connection, str(case_no))
        outcome = "inserted_with_warning" if warning_errors else "inserted"
        return _row_outcome(outcome, ordinal, str(case_no), warning_errors, problem_identity, detailed)
    except CaseImportWorkflowError as error:
        outcome = _workflow_error_outcome(error)
        problem_identity = None
        errors = {"case_import": error.error.code}
        if outcome == "review_required":
            problem_identity = _persist_hcm_review(
                connection,
                source_digest,
                source_sheet,
                ordinal,
                raw_row,
                case_no,
                errors,
            )
        return _row_outcome(outcome, ordinal, str(case_no), errors, problem_identity, detailed)
    except Exception:
        raise


def _row_outcome(outcome, source_row, case_no, errors, problem_identity, detailed):
    if not detailed:
        return outcome
    return {
        "source_row": int(source_row),
        "case_no": None if case_no is None else str(case_no),
        "outcome": str(outcome),
        "problem_identity": problem_identity,
        "problem_fields": sorted(str(field) for field in errors),
        "issue_codes": list(_hcm_review_issue_codes(errors)) if errors else [],
        "referral_occurrence_identities": [],
    }


def _persist_hcm_review(
    connection,
    source_digest,
    source_sheet,
    ordinal,
    raw_row,
    case_no,
    validation_errors,
):
    if connection is None or source_digest is None:
        return None
    issue_codes = _hcm_review_issue_codes(validation_errors)
    identity = record_hcm_import_review(
        connection,
        source_content_digest=source_digest,
        source_sheet=source_sheet,
        source_row=ordinal,
        case_identity=case_no,
        issue_codes=issue_codes,
        evidence_snapshot=_privacy_safe_hcm_evidence(raw_row, validation_errors),
        repository=MySqlHcmImportReviewRepository(connection),
    )
    return identity


def _hcm_review_issue_codes(validation_errors):
    return tuple(
        _hcm_review_issue_code(field, validation_errors[field])
        for field in sorted(validation_errors)
    )


def _hcm_review_issue_code(field, error_code):
    if field == "case_import":
        return f"hcm_case_import:{error_code}"
    if field == "hcm_identity":
        return f"hcm_identity:{error_code}"
    if "不可空" in str(error_code):
        return f"hcm_field_missing:{field}"
    return f"hcm_field_invalid:{field}"


def _privacy_safe_hcm_evidence(raw_row, validation_errors):
    return {
        "invalid_field_count": len(validation_errors),
        "source_field_count": len(raw_row),
        "has_case_identity": bool(str(raw_row.get("查詢序號(案件編號)") or "").strip()),
    }


def _hcm_import_intent(cursor, record, validation_errors):
    if validation_errors:
        return build_hcm_partial_case_import_intent(_partial_hcm_record(record, validation_errors))
    return _case_import_intent(cursor, record)


def _partial_hcm_record(record, validation_errors):
    partial_record = dict(record)
    for source_field in validation_errors:
        target_field = CLIENTS_FIELD_MAPPING.get(source_field)
        if target_field is not None:
            partial_record[target_field] = None
    return partial_record


def _hcm_warning_errors(validation_errors, identity_resolution):
    warnings = dict(validation_errors)
    if identity_resolution is HcmIdentityResolution.UNIQUE_CANDIDATE:
        warnings["hcm_identity"] = "hcm_unique_candidate"
    if identity_resolution is HcmIdentityResolution.CONFLICT:
        warnings["hcm_identity"] = "hcm_duplicate_application"
    if identity_resolution is HcmIdentityResolution.AMBIGUOUS:
        warnings["hcm_identity"] = "hcm_identity_ambiguous"
    return warnings


def _workflow_error_outcome(error):
    # A stale or mismatched command must leave no claim, review, or partial
    # root behind.  Let the application-owned UoW roll back the whole attempt.
    if error.error.code in {
        "case_import_candidate_stale",
        "idempotency_mismatch",
        "idempotency_evidence_incomplete",
    }:
        raise error
    review_categories = {"validation", "domain_blocked", "conflict"}
    if error.error.category.value in review_categories:
        return "review_required"
    raise error


def _reconcile_without_rolling_back_hcm(connection, case_no, *, in_current_uow=False):
    if connection is None:
        return "not_run"
    try:
        reconciliation = CaseImportReconciliationApplication(
            MySqlHcmBeClassReconciliationAdapter(
                connection, MySqlCasePairingAnomalyRecheckSink(connection)
            ),
            # The current-UoW path never evaluates this factory.  The
            # fallback is retained for private legacy callers and keeps the
            # transaction owner in the Case Import application layer.
            lambda: build_case_import_application(connection).unit_of_work_factory(),
        )
        if in_current_uow:
            result = reconciliation.reconcile_in_current_uow(case_no)
        else:
            result = reconciliation.reconcile(case_no)
    except Exception as error:
        if in_current_uow:
            # A reconciliation failure is part of the current HCM command;
            # let the application UoW roll back the Case Import roots, review,
            # and receipt together.
            raise
        print(f"[配對待重試] HCM root 已建立；reconciliation稍後重試：{type(error).__name__}")
        return "failed_retryable"
    print(f"[配對狀態] {result.status}")
    return result.status


def _report_import_failure(error):
    import traceback

    traceback.print_exc()
    print(f"目前來源列失敗並已回滾；先前已提交的 terminal rows 保留：{error}")


def _report_import_success(counts):
    print(
        "匯入成功：新增 "
        f"{counts['inserted']} 筆，exact replay {counts['exact_replay']} 筆，"
        f"待確認 {counts['review_required']} 筆。"
    )


def _replay_existing_hcm_case(
    application,
    intent,
    correlation,
    excel_path,
    connection,
    source_digest,
    source_sheet,
    ordinal,
    raw_row,
    *,
    current_uow=False,
):
    key = IdempotencyKey(f"case-import:{intent.case_no}")
    stored = application.find_receipt(key)
    source_matches = (
        stored is not None
        and stored.receipt.source_fingerprint == fingerprint_case_import_source(intent)
    )
    if not source_matches:
        _persist_hcm_review(
            connection,
            source_digest,
            source_sheet,
            ordinal,
            raw_row,
            intent.case_no,
            {"case_import": "case_import_existing_source_conflict"},
        )
        return "review_required"
    command = ApplyCaseImport(
        intent,
        ExpectedVersion(0),
        stored.receipt.preview_fingerprint,
        key,
        ActorContext("import-client-hcm"),
        f"Import negotiated HCM case from {os.path.basename(excel_path)}.",
        correlation,
    )
    _apply_case_import(application, command, current_uow=current_uow)
    if current_uow:
        _reconcile_without_rolling_back_hcm(
            connection, intent.case_no, in_current_uow=True,
        )
    else:
        _reconcile_without_rolling_back_hcm(connection, intent.case_no)
    return "exact_replay"


def _apply_case_import(application, command, *, current_uow):
    if current_uow and hasattr(application, "apply_in_current_uow"):
        return application.apply_in_current_uow(command)
    return application.apply(command)


def normalize_hcm_row(row):
    """Return canonical HCM field values for both legacy import and owner correction."""
    record = {
        db_column: clean_data(row[excel_column], db_column)
        for excel_column, db_column in CLIENTS_FIELD_MAPPING.items()
        if excel_column in row
    }
    if "phone" in record:
        record["phone"] = clean_phone(record["phone"])
    city, address = clean_city_and_address(
        record.get("city"),
        record.get("address"),
    )
    record["city"], record["address"] = city, address
    record["created_at"] = _parse_datetime(row.get("報名時間(建檔)"))
    record["due_month"] = _parse_date(row.get("預產期/預計服務開始月份"))
    record["service_start_date"] = _parse_date(row.get("預計服務日期"))
    
    svc_type = record.get("service_type")
    if svc_type == "周休二日":
        record["service_type"] = "週休2日"
    elif svc_type in ["休周日", "休周六"]:
        record["service_type"] = "週休1日"
        
    return record


def _normalized_record(row):
    """Compatibility alias for legacy callers; new owner code uses normalize_hcm_row."""
    return normalize_hcm_row(row)


def _case_import_intent(cursor, record):
    start_date = record.get("service_start_date")
    service_days = record.get("service_days")
    if type(start_date) is not date or not isinstance(service_days, int):
        raise ValueError("case_import_service_terms_required")
    holidays = _load_holiday_dates(cursor)
    end_date = _calculate_service_end_date(
        start_date,
        service_days,
        record.get("service_type"),
        holidays,
    )
    if end_date is None:
        raise ValueError("case_import_planned_end_date_required")
    return build_hcm_case_import_intent(
        record,
        end_date,
        requires_cooking=None,
    )


def _apply_command(intent, preview, correlation, source_file):
    return ApplyCaseImport(
        intent,
        ExpectedVersion(preview.import_version),
        preview.fingerprint,
        IdempotencyKey(f"case-import:{intent.case_no}"),
        ActorContext("import-client-hcm"),
        f"Import negotiated HCM case from {os.path.basename(source_file)}.",
        correlation,
    )
