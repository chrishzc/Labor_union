"""Stable LINE Integration error codes and compatibility aliases."""

from __future__ import annotations

from dataclasses import replace

from shared_kernel.errors import TypedError

LINE_SIGNATURE_INVALID = "line_signature_invalid"
LINE_WEBHOOK_PAYLOAD_INVALID = "line_webhook_payload_invalid"
LINE_WEBHOOK_EVENT_UNSUPPORTED = "line_webhook_event_unsupported"
LINE_WEBHOOK_IDENTITY_UNAVAILABLE = "line_webhook_identity_unavailable"
LINE_WEBHOOK_IDEMPOTENCY_CONFLICT = "line_webhook_idempotency_conflict"
LINE_IDENTITY_NOT_FOUND = "line_identity_not_found"
LINE_IDENTITY_ALREADY_BOUND = "line_identity_already_bound"
LINE_IDENTITY_BINDING_CONFLICT = "line_identity_binding_conflict"
LINE_REVIEW_NOT_FOUND = "line_review_not_found"
LINE_REVIEW_ALREADY_DECIDED = "line_review_already_decided"
LINE_REVIEW_CANDIDATE_STALE = "line_review_candidate_stale"
LINE_REVIEW_TRANSITION_INVALID = "line_review_transition_invalid"
LINE_DELIVERY_TASK_NOT_FOUND = "line_delivery_task_not_found"
LINE_DELIVERY_TASK_NOT_DUE = "line_delivery_task_not_due"
LINE_DELIVERY_TASK_ALREADY_CLAIMED = "line_delivery_task_already_claimed"
LINE_DELIVERY_LEASE_LOST = "line_delivery_lease_lost"
LINE_DELIVERY_TERMINAL_FAILURE = "line_delivery_terminal_failure"
LINE_PROVIDER_RATE_LIMITED = "line_provider_rate_limited"
LINE_PROVIDER_REJECTED = "line_provider_rejected"
LINE_PROVIDER_UNAVAILABLE = "line_provider_unavailable"
LINE_CONFIGURATION_INVALID = "line_configuration_invalid"
LINE_CONFIGURATION_REVISION_CONFLICT = "line_configuration_revision_conflict"
LINE_RICH_MENU_PUBLICATION_STALE = "line_rich_menu_publication_stale"
LINE_RICH_MENU_TRANSITION_INVALID = "line_rich_menu_transition_invalid"
LINE_ADMIN_PRINCIPAL_REQUIRED = "line_admin_principal_required"
LINE_CAPABILITY_DENIED = "line_capability_denied"

_LEGACY_LINE_ERROR_ALIASES = {
    "invalid_reply_token": LINE_PROVIDER_REJECTED,
    "line_review_state_conflict": LINE_REVIEW_ALREADY_DECIDED,
    "line_task_already_processing": LINE_DELIVERY_TASK_ALREADY_CLAIMED,
    "stale_line_configuration": LINE_CONFIGURATION_REVISION_CONFLICT,
}


def canonical_line_error_code(code: str) -> str:
    return _LEGACY_LINE_ERROR_ALIASES.get(code, code)


def canonicalize_line_error(error: TypedError) -> TypedError:
    code = canonical_line_error_code(error.code)
    blockers = tuple(
        sorted({canonical_line_error_code(item) for item in error.domain_blockers})
    )
    if code == error.code and blockers == error.domain_blockers:
        return error
    return replace(error, code=code, domain_blockers=blockers)


__all__ = [
    name
    for name in globals()
    if name.startswith("LINE_")
] + ["canonical_line_error_code", "canonicalize_line_error"]
