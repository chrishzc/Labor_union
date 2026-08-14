"""
File: hcm_adapter.py
Description: 將已驗證 HCM facts 轉成可保留未知料理條款的 typed Case Import intent。
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
import re
from typing import Mapping

from domains.bootstrap.case_architecture import (
    CaseArchitectureBootstrapIntent,
    ClientPaymentTermsRootFacts,
)
from domains.case_import.case_import import (
    CaseImportIntent,
    ClientImportAttribute,
    ImportedOrderRootFacts,
)
from shared_kernel.money import MoneyNTD


CLIENT_PAYMENT_POLICY_VERSION = "client-approved-v1"
PAYROLL_POLICY_VERSION = "approved-rates-v1"
_CLIENT_RATE_BY_IDENTITY = {"一般市民": 300, "低收入戶": 350, "中低收入戶": 350, "非市民": 320, "補助市民": 350}
_SUBSIDIZED_IDENTITIES = frozenset({"中低收入戶", "低收入戶", "補助市民"})
_EXPLICIT_HOURS_PATTERN = re.compile(r"(?P<hours>\d{1,2})\s*小時")
_CLOCK_PATTERN = re.compile(r"(?P<hour>[01]?\d|2[0-3]):(?P<minute>[0-5]\d)")


def build_hcm_case_import_intent(
    record: Mapping[str, object], planned_end_date: date, *, requires_cooking: bool | None = None
) -> CaseImportIntent:
    case_no = _required_text(record, "case_no")
    identity_status = _required_text(record, "identity_status")
    planned_start_date = _required_date(record, "service_start_date")
    created_at = _required_created_at(record.get("created_at"))
    order = _order_root_facts(
        record, case_no, planned_end_date, requires_cooking=requires_cooking
    )
    bootstrap = build_approved_case_architecture_bootstrap_intent(
        case_no, identity_status, created_at, planned_start_date
    )
    return CaseImportIntent(case_no, _client_attributes(record), order, bootstrap)


def build_hcm_partial_case_import_intent(record: Mapping[str, object]) -> CaseImportIntent:
    case_no = _required_text(record, "case_no")
    return CaseImportIntent(case_no, _client_attributes(record), None, None)


def _order_root_facts(
    record, case_no, planned_end_date, *, requires_cooking
) -> ImportedOrderRootFacts:
    service_hours, start_time, end_time, end_offset = parse_hcm_service_time(
        _required_text(record, "service_time")
    )
    return ImportedOrderRootFacts(
        case_no,
        _required_positive_integer(record, "service_days"),
        service_hours,
        _required_date(record, "service_start_date"),
        planned_end_date,
        start_time,
        end_time,
        end_offset,
        requires_cooking,
    )


def build_approved_case_architecture_bootstrap_intent(
    case_no, identity_status, created_at, start_date
) -> CaseArchitectureBootstrapIntent:
    rate = _CLIENT_RATE_BY_IDENTITY.get(identity_status)
    if rate is None:
        raise ValueError("invalid_case_import_identity_policy")
    deposit_days = 0 if identity_status in _SUBSIDIZED_IDENTITIES else 5
    terms = ClientPaymentTermsRootFacts(
        CLIENT_PAYMENT_POLICY_VERSION,
        MoneyNTD(rate),
        deposit_days,
        created_at.date() + timedelta(days=3),
        start_date,
    )
    return CaseArchitectureBootstrapIntent(case_no, terms, PAYROLL_POLICY_VERSION)


def parse_hcm_service_time(value: str) -> tuple[int, time, time, int]:
    """Parse HCM source service terms for both new-case and historical-update lanes."""
    return _service_time_facts(value)


def _client_attributes(record):
    return tuple(
        ClientImportAttribute(str(name), _normalize_value(value))
        for name, value in sorted(record.items())
        if _is_client_attribute_value(value)
    )


def _is_client_attribute_value(value: object) -> bool:
    return value is None or (
        not isinstance(value, bool) and isinstance(value, (str, int, date, datetime))
    )


def _service_time_facts(value):
    hours_match = _EXPLICIT_HOURS_PATTERN.search(value)
    clocks = tuple(_clock(match) for match in _CLOCK_PATTERN.finditer(value))
    if hours_match is None or len(clocks) != 2:
        raise ValueError("case_import_service_time_incomplete")
    service_hours = int(hours_match.group("hours"))
    end_offset = 1 if re.search(r"(次日|翌日|\+1)", value) else 0
    if clocks[1] <= clocks[0] and end_offset == 0:
        raise ValueError("case_import_service_time_incomplete")
    return service_hours, clocks[0], clocks[1], end_offset


def _clock(match) -> time:
    return time(int(match.group("hour")), int(match.group("minute")))


def _required_text(record, name):
    value = record.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"case_import_{name}_required")
    return value.strip()


def _required_date(record, name):
    value = record.get(name)
    if type(value) is not date:
        raise ValueError(f"case_import_{name}_required")
    return value


def _required_created_at(value):
    if type(value) is datetime:
        return value
    if type(value) is date:
        return datetime.combine(value, time.min)
    raise ValueError("case_import_created_at_required")


def _required_positive_integer(record, name):
    value = record.get(name)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"case_import_{name}_required")
    return value


def _normalize_value(value):
    return value.strip() if isinstance(value, str) else value


__all__ = [
    "CLIENT_PAYMENT_POLICY_VERSION",
    "PAYROLL_POLICY_VERSION",
    "build_approved_case_architecture_bootstrap_intent",
    "build_hcm_case_import_intent",
    "build_hcm_partial_case_import_intent",
    "parse_hcm_service_time",
]
