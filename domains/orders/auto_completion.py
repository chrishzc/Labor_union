"""Pure decision for the canonical Orders service-completion command."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload


@dataclass(frozen=True, slots=True)
class AutoCompletionCandidate:
    case_no: str
    expected_order_version: int
    resulting_order_version: int
    completion_instant: datetime
    evaluation_at: datetime
    fingerprint: PreviewFingerprint


def build_auto_completion_candidate(
    *,
    case_no: str,
    expected_order_version: int,
    completion_instant: datetime,
    evaluation_at: datetime,
) -> AutoCompletionCandidate:
    """Build only after the repository has locked and validated root facts."""
    if evaluation_at < completion_instant:
        raise ValueError("auto_completion_time_not_reached")
    fingerprint = fingerprint_payload(
        {
            "case_no": case_no,
            "completion_instant": completion_instant.isoformat(),
            "evaluation_at": evaluation_at.isoformat(),
            "expected_order_version": expected_order_version,
        }
    )
    return AutoCompletionCandidate(
        case_no,
        expected_order_version,
        expected_order_version + 1,
        completion_instant,
        evaluation_at,
        fingerprint,
    )
