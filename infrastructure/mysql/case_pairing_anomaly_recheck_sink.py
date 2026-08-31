"""Legacy compatibility adapter for restricted Case Import scripts.

Case pairing follow-up is owner work, not a current Anomalies product.  The
historical import entry points still construct this dependency, so the adapter
remains importable while deliberately discarding the retired recheck intent.
The canonical Web composition no longer injects it.
"""


class MySqlCasePairingAnomalyRecheckSink:
    def __init__(self, connection) -> None:
        del connection

    def append_case_pairing_recheck(self, request) -> None:
        del request


__all__ = ["MySqlCasePairingAnomalyRecheckSink"]
