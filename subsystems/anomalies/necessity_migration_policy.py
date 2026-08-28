"""
File: necessity_migration_policy.py
Description: 將異常必要性移轉的 disposition 與證據固定為 server-owned policy。
"""

from __future__ import annotations

from dataclasses import dataclass

from domains.anomalies.maintenance import (
    AnomalyReclassificationAlertIdentity,
    AnomalyReclassificationCandidate,
    AnomalyReclassificationDisposition,
    AnomalyReclassificationTargetBinding,
    preview_anomaly_reclassification,
)
from shared_kernel.fingerprints import fingerprint_payload
from shared_kernel.identities import ActorContext


@dataclass(frozen=True, slots=True)
class AnomalyNecessityMigrationDecision:
    """One approved, immutable policy decision; callers cannot replace fields."""

    disposition: AnomalyReclassificationDisposition
    target: AnomalyReclassificationTargetBinding | None
    rulebook_reference: str
    release_evidence_reference: str


class ApprovedAnomalyNecessityMigrationPolicy:
    """Resolve only definitions admitted by the current approved migration slice."""

    identity = "anomaly-necessity-migration:2026-08-27:schedule-005:v1"
    _SCHEDULE_005_RULEBOOK = (
        "document/架構重整/01_規格基線/06_Anomalies_Domain.md#"
        "異常必要性與一般工作項分界"
    )
    _SCHEDULE_005_RELEASE_EVIDENCE = (
        "document/架構重整/03_追蹤清單與證據/evidence/"
        "2026-08-27_anomaly_rulebook_oracle_matrix.md#SCHEDULE-005"
    )

    def __init__(self) -> None:
        self._decisions = {
            "SCHEDULE-005": AnomalyNecessityMigrationDecision(
                AnomalyReclassificationDisposition.RETIRED_FALSE_POSITIVE,
                None,
                self._SCHEDULE_005_RULEBOOK,
                self._SCHEDULE_005_RELEASE_EVIDENCE,
            )
        }
        self.fingerprint = fingerprint_payload(
            {
                "policy_identity": self.identity,
                "decisions": {
                    code: {
                        "disposition": decision.disposition.value,
                        "target_domain": (
                            decision.target.target_domain if decision.target else None
                        ),
                        "target_reference": (
                            decision.target.target_reference if decision.target else None
                        ),
                        "target_version": (
                            decision.target.target_version if decision.target else None
                        ),
                        "rulebook_reference": decision.rulebook_reference,
                        "release_evidence_reference": (
                            decision.release_evidence_reference
                        ),
                    }
                    for code, decision in sorted(self._decisions.items())
                },
            }
        )

    @property
    def eligible_codes(self) -> tuple[str, ...]:
        return tuple(sorted(self._decisions))

    def build_candidate(
        self,
        alert: AnomalyReclassificationAlertIdentity,
        *,
        actor: ActorContext,
        reason: str,
        evidence_reference: str,
    ) -> AnomalyReclassificationCandidate:
        """Build a candidate exclusively from the approved server policy."""
        if not isinstance(alert, AnomalyReclassificationAlertIdentity):
            raise TypeError("anomaly_necessity_migration_alert_invalid")
        try:
            decision = self._decisions[alert.definition_code]
        except KeyError as error:
            raise ValueError(
                "anomaly_necessity_migration_definition_not_admitted"
            ) from error
        return preview_anomaly_reclassification(
            disposition=decision.disposition,
            alert=alert,
            target=decision.target,
            actor=actor,
            reason=reason,
            evidence_reference=evidence_reference,
            rulebook_reference=decision.rulebook_reference,
            release_evidence_reference=decision.release_evidence_reference,
        )


def approved_anomaly_necessity_migration_policy(
) -> ApprovedAnomalyNecessityMigrationPolicy:
    return ApprovedAnomalyNecessityMigrationPolicy()


__all__ = [
    "AnomalyNecessityMigrationDecision",
    "ApprovedAnomalyNecessityMigrationPolicy",
    "approved_anomaly_necessity_migration_policy",
]
