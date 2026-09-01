from contextlib import AbstractContextManager

import pytest

from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from subsystems.client_finance.payment_destination_configuration import (
    PaymentDestinationApplyRequest,
    PaymentDestinationConfigurationApplication,
    PaymentDestinationConfigurationError,
)


class _Unit(AbstractContextManager):
    def __init__(self): self.committed = False
    def __exit__(self, *_args): return False
    def commit(self): self.committed = True


class _Repo:
    current = None
    receipt = None
    def load_current(self, *, lock=False): return self.current
    def find_receipt(self, key): return self.receipt
    def persist(self, request, receipt, command): self.current = type("Current", (), {"account_display": receipt.account_display, "revision": receipt.resulting_revision})(); self.saved = (request, receipt, command)


def test_payment_destination_query_preview_apply_and_readback():
    repo = _Repo(); units = []
    app = PaymentDestinationConfigurationApplication(repo, lambda: units.append(_Unit()) or units[-1])
    assert app.query() is None
    preview = app.preview("822-123456789", 0)
    receipt = app.apply(PaymentDestinationApplyRequest(
        "822-123456789", 0, preview.preview_fingerprint, IdempotencyKey("destination-1"),
        CorrelationId("correlation-1"), ActorContext("admin"), "建立正式代收付帳戶",
    ))
    assert receipt.resulting_revision == 1
    assert receipt.account_display == "822-123456789"
    assert units[0].committed is True
    assert app.query().account_display == "822-123456789"


def test_payment_destination_rejects_stale_expected_revision():
    repo = _Repo(); repo.current = type("Current", (), {"account_display": "old", "revision": 2})()
    app = PaymentDestinationConfigurationApplication(repo, _Unit)
    with pytest.raises(PaymentDestinationConfigurationError) as captured:
        app.preview("new", 1)
    assert captured.value.code == "client_payment_destination_stale"
