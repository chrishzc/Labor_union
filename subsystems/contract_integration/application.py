"""Durable webhook intake and evidence consumer orchestration."""

from __future__ import annotations

import hashlib
import json

from domains.contract_integration.contract_event import ContractStatusRegression

from subsystems.contract_integration.contracts import (
    ContractIntakeOutcome,
    ContractWebhookIntakeResult,
    ReceiveContractWebhookCommand,
)


class ContractSignatureInvalid(ValueError):
    def __init__(self, receipt_id: int) -> None:
        self.receipt_id = receipt_id
        super().__init__("external_signature_invalid")


class ContractWebhookApplication:
    def __init__(self, unit_of_work, verifier, normalizer) -> None:
        self._unit_of_work = unit_of_work
        self._verifier = verifier
        self._normalizer = normalizer

    # Two commits are explicit so untrusted-payload failure cannot erase the security receipt.
    def receive(self, command: ReceiveContractWebhookCommand) -> ContractWebhookIntakeResult:
        payload_hash = hashlib.sha256(command.raw_body).hexdigest()
        verified = self._verifier.verify(command.raw_body, command.signature)
        with self._unit_of_work() as unit_of_work:
            receipt_id = unit_of_work.contracts.record_security_receipt(
                command.provider,
                payload_hash,
                verified,
                command.received_at,
                command.correlation_id.value,
            )
            unit_of_work.commit()
        if not verified:
            raise ContractSignatureInvalid(receipt_id)
        event = self._normalizer.normalize(command.raw_body)
        with self._unit_of_work() as unit_of_work:
            inbox_id, created = unit_of_work.contracts.add_inbox(
                event,
                _minimal_payload(command.raw_body),
                command.received_at,
            )
            unit_of_work.commit()
        outcome = ContractIntakeOutcome.ACCEPTED if created else ContractIntakeOutcome.DUPLICATE
        return ContractWebhookIntakeResult(outcome, receipt_id, inbox_id)


class ContractEvidenceWorker:
    def __init__(self, unit_of_work, worker_id: str) -> None:
        self._unit_of_work = unit_of_work
        self._worker_id = worker_id

    def run_once(self) -> int:
        with self._unit_of_work() as unit_of_work:
            evidence = unit_of_work.contracts.claim_next(self._worker_id)
            unit_of_work.commit()
        if evidence is None:
            return 0
        self._apply(evidence)
        return 1

    def _apply(self, evidence) -> None:
        try:
            with self._unit_of_work() as unit_of_work:
                unit_of_work.contracts.apply_verified_evidence(evidence)
                unit_of_work.commit()
        except ContractStatusRegression as error:
            with self._unit_of_work() as unit_of_work:
                unit_of_work.contracts.reject(evidence.inbox_id, str(error))
                unit_of_work.commit()


def _minimal_payload(raw_body: bytes) -> str:
    payload = json.loads(raw_body.decode("utf-8"))
    allowed = {name: payload.get(name) for name in (
        "event_id", "event", "contract_id", "status", "occurred_at"
    )}
    return json.dumps(allowed, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


__all__ = [
    "ContractEvidenceWorker",
    "ContractSignatureInvalid",
    "ContractWebhookApplication",
]
