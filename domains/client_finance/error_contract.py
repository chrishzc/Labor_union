"""Stable Client Finance error codes and legacy compatibility aliases."""

from __future__ import annotations

from dataclasses import replace

from shared_kernel.errors import TypedError

CLIENT_FINANCE_CANDIDATE_STALE = "client_finance_candidate_stale"
CLIENT_FINANCE_IDEMPOTENCY_CONFLICT = "idempotency_conflict"

_LEGACY_CODE_ALIASES = {
    "client_finance_version_conflict": CLIENT_FINANCE_CANDIDATE_STALE,
    "financial_adjustment_candidate_stale": CLIENT_FINANCE_CANDIDATE_STALE,
    "stale_preview": CLIENT_FINANCE_CANDIDATE_STALE,
    "idempotency_mismatch": CLIENT_FINANCE_IDEMPOTENCY_CONFLICT,
}


def canonical_client_finance_error_code(code: str) -> str:
    return _LEGACY_CODE_ALIASES.get(code, code)


def canonicalize_client_finance_error(error: TypedError) -> TypedError:
    code = canonical_client_finance_error_code(error.code)
    blockers = tuple(
        sorted(
            {
                canonical_client_finance_error_code(blocker)
                for blocker in error.domain_blockers
            }
        )
    )
    if code == error.code and blockers == error.domain_blockers:
        return error
    return replace(error, code=code, domain_blockers=blockers)


__all__ = [
    "CLIENT_FINANCE_CANDIDATE_STALE",
    "CLIENT_FINANCE_IDEMPOTENCY_CONFLICT",
    "canonical_client_finance_error_code",
    "canonicalize_client_finance_error",
]
