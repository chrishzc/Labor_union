"""Fail-closed compatibility surface for the retired legacy LINE user lifecycle.

Canonical friend state, identity binding, and follow scheduling are owned by the
LINE platform identity repository and webhook applications.  The historical
module remains importable only because the current Task 97 governance matrix
still audits this path; none of its direct ``line_users``/``line_tasks`` writes
are retained.
"""

from __future__ import annotations


class LegacyLineUserLifecycleRetiredError(RuntimeError):
    code = "legacy_line_user_lifecycle_retired"


def _retired() -> None:
    raise LegacyLineUserLifecycleRetiredError(
        "use the canonical LINE platform identity and follow schedule applications"
    )


def activate_follow(*_args, **_kwargs) -> None:
    _retired()


def block_unfollow(*_args, **_kwargs) -> None:
    _retired()


def cancel_pending_onboarding(*_args, **_kwargs) -> None:
    _retired()


def assign_role(*_args, **_kwargs) -> None:
    _retired()


def apply_role(*_args, **_kwargs) -> None:
    _retired()


__all__ = [
    "LegacyLineUserLifecycleRetiredError",
    "activate_follow",
    "apply_role",
    "assign_role",
    "block_unfollow",
    "cancel_pending_onboarding",
]
