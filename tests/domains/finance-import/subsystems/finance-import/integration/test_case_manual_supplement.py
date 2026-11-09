"""Manual command replay compares complete content before invoking the financial writer."""
import pytest

from subsystems.finance_import.case_manual_supplement import (
    CaseManualSupplementService, ManualSupplementConflict, ManualSupplementResult,
)


class Repository:
    def __init__(self):
        self.receipts = {}
        self.writes = 0
    def lock_case(self, case_no):
        pass
    def reserve_or_replay(self, key, digest):
        if key not in self.receipts:
            return None
        original, result = self.receipts[key]
        if original != digest:
            raise ManualSupplementConflict()
        return result
    def reconcile(self, command, key, digest):
        self.writes += 1
        result = ManualSupplementResult(command.case_no, 42, 17, command.direction,
                                       command.target_item, command.amount_ntd, True)
        self.receipts[key] = (digest, result)
        return result


@pytest.mark.parametrize("field,value", [
    ("case_no", "115000002"), ("bank", "taishin"), ("direction", "client_refund"),
    ("target_item", "second"), ("amount_ntd", 999), ("transaction_date", "2026-10-21"),
    ("reason", "different"), ("actor", "another"), ("settlement_mode", "partial"),
])
def test_same_key_returns_original_receipt_and_any_content_change_conflicts(field, value):
    repository = Repository()
    service = CaseManualSupplementService(repository)
    command = dict(case_no="115000001", bank="sinopac", direction="client_receipt",
                   target_item="first", amount_ntd=1000, transaction_date="2026-10-20",
                   reason=None, idempotency_key="operation", actor="synthetic")
    receipt = service.execute(**command)
    assert service.execute(**command) == receipt
    with pytest.raises(ManualSupplementConflict):
        service.execute(**{**command, field: value})
    assert repository.writes == 1
