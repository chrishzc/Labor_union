"""
File: historical_completion_projector.py
Description: 將 fresh owner completion readback 投影為 Step 11 與可操作缺根事實警示。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from subsystems.orders.historical_completion_oracle import (
    CompletionOwner,
    CompletionReferral,
    HistoricalCompletionOracleResult,
    HistoricalCompletionState,
    HistoricalSettlementSourceVersion,
)


@dataclass(frozen=True, slots=True)
class HistoricalCompletionAlertProjection:
    """One active alert derived from an exact missing owner root."""

    code: str
    owner: CompletionOwner
    field_path: str
    referral: CompletionReferral
    message: str


@dataclass(frozen=True, slots=True)
class HistoricalCompletionTerminalProjection:
    """A non-persisted terminal view rebuilt from the current owner readbacks."""

    case_no: str
    state: HistoricalCompletionState
    step_11_status: Literal["completed", "blocked", "unavailable"]
    step_11_completed: bool
    historical_alerts_completed: bool
    active_alerts: tuple[HistoricalCompletionAlertProjection, ...]
    owner_versions: tuple[tuple[str, int], ...]
    owner_source_versions: tuple[HistoricalSettlementSourceVersion, ...]
    source_fingerprint: PreviewFingerprint
    projection_fingerprint: PreviewFingerprint

    def __post_init__(self) -> None:
        if self.step_11_completed is not (
            self.state is HistoricalCompletionState.COMPLETED
        ):
            raise ValueError("Step 11 status does not match completion state")
        if self.historical_alerts_completed is not (not self.active_alerts):
            raise ValueError("historical alert state does not match active alerts")
        if self.step_11_completed is not self.historical_alerts_completed:
            raise ValueError("Step 11 and historical alert terminal states diverge")
        if self.projection_fingerprint != fingerprint_payload(self.canonical_payload):
            raise ValueError("historical completion projection fingerprint mismatch")

    @property
    def canonical_payload(self) -> dict[str, object]:
        return {
            "case_no": self.case_no,
            "state": self.state.value,
            "step_11_status": self.step_11_status,
            "step_11_completed": self.step_11_completed,
            "historical_alerts_completed": self.historical_alerts_completed,
            "active_alerts": tuple(
                {
                    "code": alert.code,
                    "owner": alert.owner.value,
                    "field_path": alert.field_path,
                    "referral": alert.referral.value,
                    "message": alert.message,
                }
                for alert in self.active_alerts
            ),
            "owner_versions": self.owner_versions,
            "owner_source_versions": tuple(
                {
                    "kind": source.kind.value,
                    "identity": source.identity,
                    "version": source.version,
                }
                for source in self.owner_source_versions
            ),
            "source_fingerprint": self.source_fingerprint.value,
        }


def project_historical_completion(
    result: HistoricalCompletionOracleResult,
) -> HistoricalCompletionTerminalProjection:
    """Build a fresh query projection; never persist or mutate owner facts."""

    if not isinstance(result, HistoricalCompletionOracleResult):
        raise TypeError("historical completion oracle result is invalid")
    alerts = tuple(
        HistoricalCompletionAlertProjection(
            item.code,
            item.owner,
            item.field_path,
            item.referral,
            item.message,
        )
        for item in result.missing_roots
    )
    status: Literal["completed", "blocked", "unavailable"] = result.state.value
    payload = {
        "case_no": result.case_no,
        "state": result.state.value,
        "step_11_status": status,
        "step_11_completed": result.step_11_completed,
        "historical_alerts_completed": not alerts,
        "active_alerts": tuple(
            {
                "code": alert.code,
                "owner": alert.owner.value,
                "field_path": alert.field_path,
                "referral": alert.referral.value,
                "message": alert.message,
            }
            for alert in alerts
        ),
        "owner_versions": result.owner_versions,
        "owner_source_versions": tuple(
            {
                "kind": source.kind.value,
                "identity": source.identity,
                "version": source.version,
            }
            for source in result.owner_source_versions
        ),
        "source_fingerprint": result.fingerprint.value,
    }
    return HistoricalCompletionTerminalProjection(
        result.case_no,
        result.state,
        status,
        result.step_11_completed,
        not alerts,
        alerts,
        result.owner_versions,
        result.owner_source_versions,
        result.fingerprint,
        fingerprint_payload(payload),
    )


__all__ = [
    "HistoricalCompletionAlertProjection",
    "HistoricalCompletionTerminalProjection",
    "project_historical_completion",
]
