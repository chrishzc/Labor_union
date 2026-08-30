import json

import pytest

from subsystems.government_subsidy.subsidy_advance_outbox_consumer import (
    _allocation_event,
    _payload,
)


def test_allocation_event_preserves_canonical_government_identity():
    event = {"id": 12}
    payload = {"transaction_id": 42}
    allocation = {"claim_item_id": 7, "case_no": "CASE-7", "amount_ntd": 6000}

    result = _allocation_event(event, payload, allocation)

    assert result.source_outbox_id == 12
    assert result.government_allocation_identity == "government-allocation:42:7"
    assert result.government_transaction_id == 42
    assert result.case_no == "CASE-7"
    assert result.claim_item_id == 7
    assert result.amount.amount == 6000


def test_payload_requires_an_allocation_list():
    assert _payload(json.dumps({"allocations": []})) == {"allocations": []}

    with pytest.raises(ValueError, match="payload is invalid"):
        _payload({"transaction_id": 42})
