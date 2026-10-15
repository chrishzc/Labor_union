"""Human Preview/Apply for the existing government-funded advance recovery."""

from dataclasses import asdict, dataclass
from typing import Callable, Protocol, Any

from domains.client_finance.subsidy_advance_settlement import (
    AdvanceSettlementFacts, AdvanceSettlementRow, project_advance_settlement,
)
from shared_kernel.fingerprints import fingerprint_payload
from shared_kernel.money import MoneyNTD
from subsystems.client_finance.subsidy_advance_recovery import (
    GovernmentReceiptAllocationEvent, SubsidyAdvanceRecoveryWorkflow,
)


class AdvanceSettlementConflict(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class AdvanceSettlementPreview:
    row: AdvanceSettlementRow
    account_version: int
    batch_version: int
    preview_fingerprint: str


@dataclass(frozen=True, slots=True)
class AdvanceSettlementCommand:
    advance_id: int
    expected_account_version: int
    expected_batch_version: int
    preview_fingerprint: str
    idempotency_key: str
    actor: str
    reason: str


class AdvanceSettlementRepository(Protocol):
    def list_facts(self, after_id: int, search: str | None, limit: int) -> tuple[AdvanceSettlementFacts, ...]: ...
    def load(self, advance_id: int, *, lock: bool = False) -> AdvanceSettlementFacts | None: ...
    def load_receipt(self, key: str) -> dict | None: ...
    def save_receipt(self, command: AdvanceSettlementCommand, command_hash: str,
                     facts: AdvanceSettlementFacts, result: dict) -> None: ...
    def recovery_repository(self) -> Any: ...


class AdvanceSettlementApplication:
    def __init__(self, repository: AdvanceSettlementRepository, unit_of_work: Callable):
        self.repository = repository
        self.unit_of_work = unit_of_work

    def query(self, after_id: int = 0, search: str | None = None, limit: int = 100):
        facts = self.repository.list_facts(after_id, search, limit + 1)
        return {
            'rows': [asdict(project_advance_settlement(f)) for f in facts[:limit]],
            'next_cursor': facts[limit - 1].advance_id if len(facts) > limit else None,
        }

    def preview(self, advance_id: int) -> AdvanceSettlementPreview:
        return _preview(self._load(advance_id))

    def _load(self, advance_id: int, *, lock: bool = False):
        facts = self.repository.load(advance_id, lock=lock)
        if facts is None:
            raise AdvanceSettlementConflict('subsidy_advance_not_found')
        return facts

    def apply(self, command: AdvanceSettlementCommand) -> dict:
        command_hash = fingerprint_payload({'operation': 'subsidy_advance_settlement.v1', **asdict(command)}).value
        with self.unit_of_work() as uow:
            facts = self._load(command.advance_id, lock=True)
            previous = self.repository.load_receipt(command.idempotency_key)
            if previous is not None:
                if previous['command_fingerprint'] != command_hash:
                    raise AdvanceSettlementConflict('idempotency_mismatch')
                return previous['result_snapshot']
            preview = _preview(facts)
            if (preview.account_version != command.expected_account_version
                    or preview.batch_version != command.expected_batch_version
                    or preview.preview_fingerprint != command.preview_fingerprint):
                raise AdvanceSettlementConflict('stale_preview')
            allocation = facts.receipts[0]
            event = GovernmentReceiptAllocationEvent(
                allocation.source_outbox_id,
                f'government-allocation:{allocation.transaction_id}:{allocation.claim_item_id}',
                allocation.transaction_id, facts.case_no, allocation.claim_item_id,
                MoneyNTD(allocation.amount_ntd),
            )
            outcome = SubsidyAdvanceRecoveryWorkflow(self.repository.recovery_repository()).consume(event)
            if outcome != 'recovered':
                raise AdvanceSettlementConflict('subsidy_advance_settlement_ambiguous')
            result = {
                'advance_id': facts.advance_id, 'case_no': facts.case_no,
                'recovered_amount_ntd': facts.advance_amount_ntd,
                'account_version': preview.account_version + 1,
            }
            self.repository.save_receipt(command, command_hash, facts, result)
            uow.commit()
            return result


def _preview(facts: AdvanceSettlementFacts) -> AdvanceSettlementPreview:
    row = project_advance_settlement(facts)
    if row.status != 'ready':
        raise AdvanceSettlementConflict('subsidy_advance_not_ready')
    # The account version alone cannot detect a government reversal/allocation
    # or a background consumer recovery during human confirmation.
    payload = asdict(facts)
    payload.pop('client_name')
    for key in ('advanced_on', 'completed_on'):
        payload[key] = payload[key].isoformat() if payload[key] else None
    for receipt in payload['receipts']:
        receipt['received_on'] = receipt['received_on'].isoformat()
    return AdvanceSettlementPreview(row, facts.account_version,
                                    facts.entitlements[0].batch_version,
                                    fingerprint_payload(payload).value)
