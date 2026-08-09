"""Prevent removed compatibility modules from silently returning."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_unmounted_legacy_payment_route_and_schema_are_removed() -> None:
    retired_paths = (
        "api/routes/payments.py",
        "api/schemas/payments.py",
    )

    for relative_path in retired_paths:
        assert not (ROOT / relative_path).exists()


def test_finance_tab_has_no_unused_mixed_payment_compatibility_shim() -> None:
    source = (ROOT / "ui/pages/order/tab3_finance.py").read_text(encoding="utf-8")

    assert "_render_legacy_mixed_payment_overview" not in source


def test_zero_caller_legacy_modules_are_removed_after_replacement_migration() -> None:
    retired_paths = (
        "infrastructure/migration/fingerprints.py",
        "infrastructure/migration/journal.py",
        "infrastructure/migration/verification.py",
        "subsystems/access/security_audit_repository.py",
        "subsystems/scheduling/leave_resolution_preview.py",
        "ui/api_clients/order_lifecycle_api_client.py",
    )

    for relative_path in retired_paths:
        assert not (ROOT / relative_path).exists()
