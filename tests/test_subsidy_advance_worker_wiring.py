"""
File: test_subsidy_advance_worker_wiring.py
Description: 驗證 architecture outbox worker彙總各來源的成功與失敗筆數。
"""

from subsystems.anomalies import outbox_worker


class _Connection:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class _Result:
    def __init__(self, delivered_count, failed_count):
        self.delivered_count = delivered_count
        self.failed_count = failed_count


def test_architecture_worker_delivers_subsidy_advance_recovery_events(monkeypatch):
    connection = _Connection()
    monkeypatch.setattr(outbox_worker, "get_connection", lambda: connection)
    monkeypatch.setattr(outbox_worker, "consume_finance_import_anomaly_events", lambda _: _Result(2, 1))
    monkeypatch.setattr(outbox_worker, "consume_beclass_import_review_events", lambda _: _Result(3, 1))
    monkeypatch.setattr(outbox_worker, "consume_hcm_import_review_events", lambda _: _Result(4, 2))
    monkeypatch.setattr(outbox_worker, "consume_hcm_resubmission_outbox", lambda _: 8)
    monkeypatch.setattr(
        outbox_worker,
        "consume_historical_order_adoption_review_events",
        lambda _: _Result(6, 4),
    )
    monkeypatch.setattr(outbox_worker, "consume_government_subsidy_advance_events", lambda _: (5, 2))
    monkeypatch.setattr(outbox_worker, "consume_government_overpayment_anomaly_events", lambda _: (0, 0))
    monkeypatch.setattr(outbox_worker, "consume_client_over_refund_recovery_anomaly_events", lambda _: (0, 0))
    monkeypatch.setattr(outbox_worker, "consume_client_refund_underpayment_anomaly_events", lambda _: (0, 0))
    monkeypatch.setattr(outbox_worker, "consume_staff_overpayment_recovery_anomaly_events", lambda _: (0, 0))
    monkeypatch.setattr(outbox_worker, "consume_staff_payout_difference_anomaly_events", lambda _: (0, 0))
    monkeypatch.setattr(outbox_worker, "consume_client_finance_orders_events", lambda _: (11, 13))
    monkeypatch.setattr(outbox_worker, "consume_security_alert_outbox", lambda _: _Result(12, 5))
    monkeypatch.setattr(outbox_worker, "_consume_sources_if_due", lambda *_: (7, 3))

    result = outbox_worker._consume_once()

    assert (result.delivered_count, result.failed_count) == (58, 31)
    assert connection.closed is True
