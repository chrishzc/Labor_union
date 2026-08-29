from domains.client_finance.deposit_lifecycle import (
    DepositLifecycleEvent,
    DepositLifecycleFacts,
    decide_deposit_lifecycle_impact,
)
from shared_kernel.fingerprints import PreviewFingerprint


def _identity(char: str) -> PreviewFingerprint:
    return PreviewFingerprint(char * 64)


def _facts(**changes) -> DepositLifecycleFacts:
    values = {
        "case_no": "G14-CASE",
        "event": DepositLifecycleEvent.REVERSAL,
        "deposit_settled": False,
        "settlement_identity": None,
        "actual_start_exists": False,
        "service_started": False,
        "service_completed": False,
        "confirmed_settlement_identity": None,
    }
    values.update(changes)
    return DepositLifecycleFacts(**values)


def test_pre_service_deposit_reversal_blocks_entry_without_service_rollback():
    impact = decide_deposit_lifecycle_impact(_facts())

    assert impact.lifecycle_intent is DepositLifecycleEvent.REVERSAL
    assert impact.block_enter_service is True
    assert impact.preserve_service_state is False
    assert impact.require_actual_start_reconfirmation is False
    assert impact.anomaly_code is None


def test_post_service_deposit_reversal_preserves_service_and_routes_anomaly():
    impact = decide_deposit_lifecycle_impact(
        _facts(actual_start_exists=True, service_started=True)
    )

    assert impact.block_enter_service is False
    assert impact.preserve_service_state is True
    assert impact.require_actual_start_reconfirmation is False
    assert impact.anomaly_code == "finance.deposit_reversal_after_service_started"


def test_new_settlement_identity_invalidates_prior_actual_start_reconfirmation():
    impact = decide_deposit_lifecycle_impact(
        _facts(
            event=DepositLifecycleEvent.RECEIPT,
            deposit_settled=True,
            settlement_identity=_identity("b"),
            actual_start_exists=True,
            confirmed_settlement_identity=_identity("a"),
        )
    )

    assert impact.block_enter_service is False
    assert impact.require_actual_start_reconfirmation is True
