from __future__ import annotations

import pandas as pd
import pytest

from scripts.imports import import_client_hcm


class _ApplicationMustNotRun:
    def case_exists(self, case_no):
        return False

    def preview(self, intent, correlation):
        raise AssertionError("invalid HCM row must not reach Preview")

    def apply(self, command):
        raise AssertionError("invalid HCM row must not reach Apply")


def test_invalid_hcm_row_is_review_required_without_fabricated_root(monkeypatch):
    emitted = []
    monkeypatch.setattr(
        import_client_hcm,
        "_normalized_record",
        lambda row: {"case_no": "HCM-001", "created_at": object()},
    )
    monkeypatch.setattr(
        import_client_hcm,
        "validate_hcm_row",
        lambda row: {"服務時間": "invalid service time"},
    )
    monkeypatch.setattr(
        import_client_hcm,
        "_emit_hcm_validation_anomaly",
        lambda case_no, ordinal, errors: emitted.append((case_no, ordinal, errors)),
    )

    outcome = import_client_hcm._import_row(
        pd.Series({"查詢序號(案件編號)": "HCM-001"}),
        7,
        object(),
        _ApplicationMustNotRun(),
        "hcm.xlsx",
    )

    assert outcome == "review_required"
    assert emitted[0][0:2] == ("HCM-001", 7)
    assert emitted[0][2]["服務時間"] == "invalid service time"
    assert "報名時間(建檔)" in emitted[0][2]


def test_hcm_database_config_has_no_default_credentials(monkeypatch):
    for setting in (
        "DB_HOST",
        "DB_USER",
        "DB_PASSWORD",
        "DB_DATABASE",
        "IMPORT_ALLOWED_DATABASES",
    ):
        monkeypatch.delenv(setting, raising=False)

    with pytest.raises(RuntimeError, match="hcm_import_database_config_missing"):
        import_client_hcm._database_config()


def test_hcm_database_target_requires_explicit_allowlist(monkeypatch):
    monkeypatch.setenv("DB_HOST", "127.0.0.1")
    monkeypatch.setenv("DB_USER", "operator")
    monkeypatch.setenv("DB_PASSWORD", "secret")
    monkeypatch.setenv("DB_DATABASE", "candidate_import")
    monkeypatch.setenv("IMPORT_ALLOWED_DATABASES", "another_candidate")

    with pytest.raises(RuntimeError, match="hcm_import_database_target_not_allowed"):
        import_client_hcm._database_config()


def test_invalid_hcm_row_persists_review_before_returning(monkeypatch):
    recorded = []
    connection = type("Connection", (), {"commit": lambda self: recorded.append("commit")})()
    monkeypatch.setattr(
        import_client_hcm,
        "record_invalid_beclass_row",
        lambda connection, **kwargs: recorded.append(kwargs) or "beclass-review:hcm",
    )

    identity = import_client_hcm._persist_hcm_review(
        connection,
        "a" * 64,
        "HCM資料",
        3,
        {"姓名": "測試"},
        "HCM-003",
        {"服務時間": "invalid"},
    )

    assert identity == "beclass-review:hcm"
    assert recorded[0]["source_kind"] is import_client_hcm.BeClassImportSourceKind.HCM
    assert recorded[0]["masked_identifier"] == "hcm-***--003"
    assert recorded[0]["issue_codes"] == ("hcm_field_invalid:服務時間",)
    assert recorded[1] == "commit"
