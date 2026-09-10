"""
File: test_import_warning_auto_resolution_guard.py
Description: 驗證 legacy 匯入警示只能依明列規則書終態契約自動解除。
"""

import pytest

from infrastructure.mysql import import_warning_auto_resolution as subject


def test_unknown_terminal_predicate_fails_before_any_tracking_write(monkeypatch) -> None:
    monkeypatch.setattr(
        subject,
        "_append_auto_resolved_event",
        lambda *_args, **_kwargs: pytest.fail("must not write"),
    )

    with pytest.raises(
        ValueError,
        match="import_warning_auto_resolution_rulebook_contract_missing",
    ):
        subject._resolve_rows(
            object(),
            (_row("HCM-FIELD-001"),),
            owner_event_identity="event-1",
            projector_identity="projector-1",
            terminal_predicate="event_received",
        )


def test_terminal_predicate_cannot_resolve_another_logical_code(monkeypatch) -> None:
    monkeypatch.setattr(
        subject,
        "_append_auto_resolved_event",
        lambda *_args, **_kwargs: pytest.fail("must not write"),
    )

    with pytest.raises(
        ValueError,
        match="import_warning_auto_resolution_predicate_mismatch",
    ):
        subject._resolve_rows(
            object(),
            (_row("FINANCE-ROW-001"),),
            owner_event_identity="event-1",
            projector_identity="projector-1",
            terminal_predicate=subject.HCM_FIELD_CORRECTION_TERMINAL_PREDICATE,
        )


def test_hcm_field_terminal_contract_allows_exact_owner_projection(monkeypatch) -> None:
    captured = []
    monkeypatch.setattr(
        subject,
        "_append_auto_resolved_event",
        lambda _connection, row, **_kwargs: captured.append(row["logical_code"]),
    )

    count = subject._resolve_rows(
        object(),
        (_row("HCM-FIELD-002"),),
        owner_event_identity="event-1",
        projector_identity="projector-1",
        terminal_predicate=subject.HCM_FIELD_CORRECTION_TERMINAL_PREDICATE,
    )

    assert count == 1
    assert captured == ["HCM-FIELD-002"]


def _row(logical_code: str):
    return {
        "id": 1,
        "occurrence_identity": "warning-1",
        "logical_code": logical_code,
        "tracking_status": "open",
        "tracking_version": 1,
    }
