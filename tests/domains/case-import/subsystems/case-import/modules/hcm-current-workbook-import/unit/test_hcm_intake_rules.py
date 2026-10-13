from datetime import date, datetime
from types import SimpleNamespace

import pandas as pd
import pytest

from domains.case_import.client_import_validation import SERVICE_TYPE_VALUES
from domains.case_import.client_import_validation import validate_hcm_row
from domains.case_import.hcm_import_review import unresolved_hcm_review_fields
from scripts.imports import import_client_hcm
from subsystems.case_import.hcm_adapter import (
    build_approved_case_architecture_bootstrap_intent,
    calculate_hcm_service_end_date,
)


def test_urgent_case_caps_deposit_due_date_at_planned_start() -> None:
    urgent = build_approved_case_architecture_bootstrap_intent(
        "HCM-URGENT", "一般市民", datetime(2026, 9, 10, 9), date(2026, 9, 11)
    )
    ordinary = build_approved_case_architecture_bootstrap_intent(
        "HCM-NORMAL", "一般市民", datetime(2026, 9, 1, 9), date(2026, 9, 10)
    )

    assert urgent.client_payment_terms.deposit_due_date == date(2026, 9, 11)
    assert ordinary.client_payment_terms.deposit_due_date == date(2026, 9, 4)


def test_hcm_service_type_normalization_preserves_the_rest_weekday() -> None:
    assert import_client_hcm.normalize_hcm_row({"服務方式": "休周六"})["service_type"] == "休周六"
    assert import_client_hcm.normalize_hcm_row({"服務方式": "休周日"})["service_type"] == "休周日"
    assert import_client_hcm.normalize_hcm_row({"服務方式": "週休1日"})["service_type"] == "週休1日"
    assert {"休周六", "休周日"} <= SERVICE_TYPE_VALUES


@pytest.mark.parametrize('source', ['無休', '休五、日'])
def test_service_type_requires_explicit_correction_without_automatic_conversion(source):
    assert import_client_hcm.normalize_hcm_row({'服務方式': source})['service_type'] == source
    assert '服務方式' in validate_hcm_row({'服務方式': source})
    assert unresolved_hcm_review_fields(('服務方式',), {'clients.service_type': source}) == ('服務方式',)
    assert import_client_hcm._partial_hcm_record({'service_type': source}, {'服務方式': '需人工核對'})['service_type'] == source


@pytest.mark.parametrize('source', ['周休二日', '週休1日', '週休一日'])
def test_hcm_service_type_text_is_preserved_without_alias_rewriting(source):
    assert import_client_hcm.normalize_hcm_row({'服務方式': source})['service_type'] == source


@pytest.mark.parametrize('source', ['周休二日', '週休1日', '週休一日'])
def test_direct_repair_does_not_change_existing_hcm_service_type_validation(source):
    assert '服務方式' not in validate_hcm_row({'服務方式': source})
    assert unresolved_hcm_review_fields(('服務方式',), {'clients.service_type': source}) == ()


def test_hcm_end_date_uses_the_selected_single_rest_weekday() -> None:
    start = date(2026, 3, 2)  # Monday

    assert calculate_hcm_service_end_date(start, 6, "休周日", set()) == date(2026, 3, 7)
    assert calculate_hcm_service_end_date(start, 6, "休周六", set()) == date(2026, 3, 8)


def test_ambiguous_name_or_ip_is_a_nonblocking_warning(monkeypatch) -> None:
    applied = []
    recorded = []

    class Application:
        def resolve_hcm_identity(self, *_args):
            return import_client_hcm.HcmIdentityResolution.AMBIGUOUS

        def preview(self, *_args):
            return type("Preview", (), {"import_version": 0, "fingerprint": object()})()

        def apply(self, command):
            applied.append(command)

    monkeypatch.setattr(
        import_client_hcm,
        "_normalized_record",
        lambda _row: {
            "case_no": "HCM-NEW",
            "created_at": datetime(2026, 9, 1, 9),
            "name": "同名申請人",
            "ip_address": "192.0.2.1",
        },
    )
    monkeypatch.setattr(import_client_hcm, "validate_hcm_row", lambda _row: {})
    monkeypatch.setattr(
        import_client_hcm,
        "_hcm_import_intent",
        lambda *_args: SimpleNamespace(case_no="HCM-NEW", is_complete=True),
    )
    monkeypatch.setattr(import_client_hcm, "_apply_command", lambda *_args: object())
    monkeypatch.setattr(import_client_hcm, "_reconcile_without_rolling_back_hcm", lambda *_args: None)
    monkeypatch.setattr(
        import_client_hcm,
        "record_hcm_import_review",
        lambda _connection, **kwargs: recorded.append(kwargs) or "hcm-review:ambiguous",
    )

    outcome = import_client_hcm._import_row(
        pd.Series({"查詢序號(案件編號)": "HCM-NEW"}),
        2,
        object(),
        Application(),
        "hcm.xlsx",
        connection=object(),
        source_digest="a" * 64,
    )

    assert outcome == "inserted_with_warning"
    assert len(applied) == 1
    assert recorded[0]["issue_codes"] == ("hcm_identity:hcm_identity_ambiguous",)
