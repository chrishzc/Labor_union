"""Manifest verification and post-cutover execution contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping, Protocol, Sequence


VerificationValidator = Callable[[], Mapping[str, Any]]


@dataclass(frozen=True, slots=True)
class VerificationReceipt:
    verification_id: str
    phase: str
    status: str
    evidence: Mapping[str, Any]


class RestartPort(Protocol):
    def restart(self, target: str) -> Mapping[str, Any]: ...


class ReadSmokePort(Protocol):
    def run(self, smoke_id: str) -> Mapping[str, Any]: ...


def run_manifest_verifications(
    contracts: Sequence[Any],
    *,
    phase: str,
    validators: Mapping[str, VerificationValidator],
) -> tuple[VerificationReceipt, ...]:
    selected = tuple(item for item in contracts if item.phase == phase)
    missing = sorted(
        item.verification_id
        for item in selected
        if item.verification_id not in validators
    )
    if missing:
        raise ValueError("verification validator missing: " + ",".join(missing))
    return tuple(_run_verification(item, validators) for item in selected)


def restart_and_run_read_smoke(
    restart_targets: Sequence[str],
    smoke_ids: Sequence[str],
    restart_port: RestartPort,
    smoke_port: ReadSmokePort,
) -> dict[str, tuple[Mapping[str, Any], ...]]:
    restart_receipts = tuple(
        _require_passed(restart_port.restart(target), "restart", target)
        for target in restart_targets
    )
    smoke_receipts = tuple(
        _require_passed(smoke_port.run(smoke_id), "smoke", smoke_id)
        for smoke_id in smoke_ids
    )
    return {"restart_receipts": restart_receipts, "smoke_receipts": smoke_receipts}


def _run_verification(
    contract: Any,
    validators: Mapping[str, VerificationValidator],
) -> VerificationReceipt:
    evidence = validators[contract.verification_id]()
    _require_passed(evidence, "verification", contract.verification_id)
    return VerificationReceipt(
        verification_id=contract.verification_id,
        phase=contract.phase,
        status="passed",
        evidence=dict(evidence),
    )


def _require_passed(
    receipt: Mapping[str, Any],
    receipt_kind: str,
    receipt_id: str,
) -> Mapping[str, Any]:
    if receipt.get("status") != "passed":
        raise ValueError(f"{receipt_kind} failed: {receipt_id}")
    return dict(receipt)

