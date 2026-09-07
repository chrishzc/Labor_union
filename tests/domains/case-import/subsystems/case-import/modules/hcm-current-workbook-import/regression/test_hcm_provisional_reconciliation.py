# -*- coding: utf-8 -*-
"""
File: test_hcm_provisional_reconciliation.py
Description: 驗證 HCM 匯入時自動比對並消費狀態 C 臨時登記之 Domain 規則與配對邏輯。
"""

from datetime import date, datetime
from types import SimpleNamespace
import pytest

from domains.case_import.case_import import (
    CaseImportDomainError,
    CaseImportIssue,
    CaseImportIntent,
    ClientImportAttribute,
    ProvisionalRegistrationFacts,
    _validate_provisional_registration,
)
from subsystems.case_import.hcm_adapter import (
    build_hcm_case_import_intent,
    build_hcm_partial_case_import_intent,
)
from scripts.imports.import_client_hcm import _find_matching_provisional_registration


class FakeCursor:
    def __init__(self, fetch_result):
        self.fetch_result = fetch_result
        self.executed = []

    def execute(self, query, params=None):
        self.executed.append((query, params))

    def fetchall(self):
        return self.fetch_result


def test_find_matching_provisional_registration_unique_match():
    cursor = FakeCursor([{"id": 42}])
    record = {"name": "王小明", "phone": "0988776655"}
    result = _find_matching_provisional_registration(cursor, record)
    assert result == 42
    assert len(cursor.executed) == 1
    assert cursor.executed[0][1] == ("王小明", "0988776655")


def test_find_matching_provisional_registration_tuple_row():
    cursor = FakeCursor([(42,)])
    record = {"name": "王小明", "phone": "0988-776-655"}
    result = _find_matching_provisional_registration(cursor, record)
    assert result == 42


def test_find_matching_provisional_registration_no_match():
    cursor = FakeCursor([])
    record = {"name": "李大同", "phone": "0911223344"}
    result = _find_matching_provisional_registration(cursor, record)
    assert result is None


def test_find_matching_provisional_registration_ambiguous_multiple_matches():
    cursor = FakeCursor([{"id": 10}, {"id": 11}])
    record = {"name": "陳小美", "phone": "0922334455"}
    result = _find_matching_provisional_registration(cursor, record)
    assert result is None


def test_find_matching_provisional_registration_empty_inputs():
    assert _find_matching_provisional_registration(None, {"name": "A", "phone": "0911"}) is None
    cursor = FakeCursor([{"id": 1}])
    assert _find_matching_provisional_registration(cursor, {"name": "", "phone": "0911"}) is None
    assert _find_matching_provisional_registration(cursor, {"name": "A", "phone": ""}) is None


def test_build_hcm_case_import_intent_passes_provisional_registration_id():
    record = {
        "case_no": "115000001",
        "name": "王小明",
        "identity_status": "一般市民",
        "service_start_date": date(2026, 9, 1),
        "created_at": datetime(2026, 8, 1, 9, 0),
        "service_time": "8 小時 09:00 17:00",
        "service_days": 10,
    }
    intent = build_hcm_case_import_intent(
        record,
        date(2026, 9, 12),
        provisional_registration_id=99,
    )
    assert intent.provisional_registration_id == 99


def test_build_hcm_partial_case_import_intent_passes_provisional_registration_id():
    record = {"case_no": "115000001"}
    intent = build_hcm_partial_case_import_intent(record, provisional_registration_id=88)
    assert intent.provisional_registration_id == 88


def test_validate_provisional_registration_allows_real_hcm_line_handle():
    registration = ProvisionalRegistrationFacts(
        registration_id=1,
        line_user_id="U99c2e4a3629eb284d19ab0491d356839",
        status="submitted",
        client_id=6,
        beclass_record_id=3,
        beclass_query_no=None,
        has_open_conflict=False,
    )
    # HCM row has citizen text handle or empty LINE ID
    attributes = (
        ClientImportAttribute("case_no", "115000001"),
        ClientImportAttribute("name", "王小明"),
        ClientImportAttribute("line_id", "@wang123"),
    )
    intent = SimpleNamespace(provisional_registration_id=1, client_attributes=attributes)
    # Should not raise exception
    _validate_provisional_registration(registration, intent)


def test_validate_provisional_registration_rejects_conflicting_line_uid():
    registration = ProvisionalRegistrationFacts(
        registration_id=1,
        line_user_id="U99c2e4a3629eb284d19ab0491d356839",
        status="submitted",
        client_id=6,
        beclass_record_id=3,
        beclass_query_no=None,
        has_open_conflict=False,
    )
    # Conflicting LINE platform UID
    attributes = (
        ClientImportAttribute("case_no", "115000001"),
        ClientImportAttribute("name", "王小明"),
        ClientImportAttribute("line_id", "U11111111111111111111111111111111"),
    )
    intent = SimpleNamespace(provisional_registration_id=1, client_attributes=attributes)
    with pytest.raises(CaseImportDomainError) as excinfo:
        _validate_provisional_registration(registration, intent)
    assert excinfo.value.issue == CaseImportIssue.PROVISIONAL_REGISTRATION_IDENTITY_MISMATCH


def test_validate_provisional_registration_rejects_unsubmitted_status():
    registration = ProvisionalRegistrationFacts(
        registration_id=1,
        line_user_id="U99c2e4a3629eb284d19ab0491d356839",
        status="case_issued",
        client_id=6,
        beclass_record_id=3,
        beclass_query_no=None,
        has_open_conflict=False,
    )
    attributes = (
        ClientImportAttribute("case_no", "115000001"),
        ClientImportAttribute("name", "王小明"),
    )
    intent = SimpleNamespace(provisional_registration_id=1, client_attributes=attributes)
    with pytest.raises(CaseImportDomainError) as excinfo:
        _validate_provisional_registration(registration, intent)
    assert excinfo.value.issue == CaseImportIssue.PROVISIONAL_REGISTRATION_NOT_SUBMITTED
