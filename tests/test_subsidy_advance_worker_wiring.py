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
    class _Runtime:
        def connection(self):
            return connection

        def subsidy_advance_recovery_repository(self, _connection):
            raise AssertionError("patched consumer must not construct a repository")

    monkeypatch.setattr(outbox_worker, "require_runtime", lambda _runtime: _Runtime())
    monkeypatch.setattr(outbox_worker, "consume_finance_import_anomaly_events", lambda *_args, **_kwargs: _Result(2, 1))
    monkeypatch.setattr(outbox_worker, "consume_beclass_import_review_events", lambda *_args, **_kwargs: _Result(3, 1))
    monkeypatch.setattr(outbox_worker, "consume_hcm_import_review_events", lambda *_args, **_kwargs: _Result(4, 2))
    monkeypatch.setattr(outbox_worker, "consume_hcm_resubmission_outbox", lambda *_args, **_kwargs: 8)
    monkeypatch.setattr(
        outbox_worker,
        "consume_historical_order_adoption_review_events",
        lambda *_args, **_kwargs: _Result(6, 4),
    )
    monkeypatch.setattr(
        outbox_worker,
        "consume_historical_order_review_remediation_events",
        lambda *_args, **_kwargs: _Result(0, 0),
    )
    monkeypatch.setattr(outbox_worker, "consume_government_subsidy_advance_events", lambda *_args, **_kwargs: (5, 2))
    monkeypatch.setattr(outbox_worker, "consume_client_finance_orders_events", lambda *_args, **_kwargs: (11, 13))
    monkeypatch.setattr(outbox_worker, "consume_security_alert_outbox", lambda *_args, **_kwargs: _Result(12, 5))
    monkeypatch.setattr(outbox_worker, "_consume_sources_if_due", lambda *_: (7, 3))

    result = outbox_worker._consume_once()

    assert (result.delivered_count, result.failed_count) == (58, 31)
    assert connection.closed is True
