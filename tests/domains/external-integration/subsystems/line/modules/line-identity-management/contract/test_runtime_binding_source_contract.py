"""Protect canonical role-scoped LINE binding reads across runtime consumers."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[8]


RUNTIME_BINDING_CONSUMERS = (
    "api/dependencies/contract_external_signing.py",
    "infrastructure/db/contract_external_signing_repository.py",
    "infrastructure/mysql/service_before_replacement_loader.py",
    "subsystems/contract_signing/client_contract_application.py",
    "subsystems/contract_signing/staff_contract_application.py",
)

NOTIFICATION_RECIPIENT_CONSUMERS = (
    "infrastructure/mysql/candidate_contact_pool_line_reply_repository.py",
    "infrastructure/mysql/line_order_group_adapters.py",
    "infrastructure/mysql/matching_coordination_customer_service_source.py",
    "infrastructure/mysql/matching_notification_repository.py",
    "infrastructure/mysql/matching_recommendation_repository.py",
    "infrastructure/mysql/matching_schedule_confirmation_repository.py",
    "infrastructure/mysql/order_auto_completion_repository.py",
    "infrastructure/mysql/order_cancellation_repository.py",
    "infrastructure/mysql/order_information_repository.py",
    "subsystems/line/candidate_contact_coordination_worker.py",
    "subsystems/line/candidate_contact_response_application.py",
    "subsystems/scheduling/candidate_contact_pool_workflow.py",
    "subsystems/scheduling/matching_communication_workflow.py",
)


def _source(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_runtime_consumers_do_not_read_legacy_single_role_binding_table() -> None:
    for relative_path in RUNTIME_BINDING_CONSUMERS:
        source = _source(relative_path)
        assert "line_identity_bindings" not in source, relative_path
        assert "line_identity_role_bindings" in source, relative_path


def test_notification_recipients_require_canonical_bound_role() -> None:
    for relative_path in NOTIFICATION_RECIPIENT_CONSUMERS:
        source = _source(relative_path)
        assert "line_identity_role_bindings" in source, relative_path
        assert "binding_status='bound'" in source.replace(" ", ""), relative_path
