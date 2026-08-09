"""Module tests for stable LINE typed error aliases."""

from domains.line.error_contract import (
    LINE_CONFIGURATION_REVISION_CONFLICT,
    LINE_PROVIDER_REJECTED,
    LINE_REVIEW_ALREADY_DECIDED,
    canonical_line_error_code,
    canonicalize_line_error,
)
from shared_kernel.errors import ErrorCategory, TypedError
from shared_kernel.identities import CorrelationId


def test_legacy_error_codes_map_to_stable_line_codes() -> None:
    assert canonical_line_error_code("invalid_reply_token") == LINE_PROVIDER_REJECTED
    assert (
        canonical_line_error_code("stale_line_configuration")
        == LINE_CONFIGURATION_REVISION_CONFLICT
    )


def test_typed_error_aliases_include_domain_blockers() -> None:
    error = TypedError(
        ErrorCategory.CONFLICT,
        "line_review_state_conflict",
        "申請已經完成",
        CorrelationId("correlation:1"),
        domain_blockers=("line_review_state_conflict",),
    )

    canonical = canonicalize_line_error(error)
    assert canonical.code == LINE_REVIEW_ALREADY_DECIDED
    assert canonical.domain_blockers == (LINE_REVIEW_ALREADY_DECIDED,)
