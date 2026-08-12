from contextlib import contextmanager

from subsystems.contract_signing.command_receipts import append_command_receipt, append_outbox_intent


class _Connection:
    def __init__(self): self.calls = []
    @contextmanager
    def cursor(self): yield self
    def execute(self, statement, parameters): self.calls.append((statement, parameters))


def test_contract_signing_receipt_and_outbox_are_append_only_and_case_bound():
    connection = _Connection()
    append_command_receipt(connection, idempotency_key="key", command_kind="send_client_contract", case_no="CASE-1", document_version_id=3, signing_event_id=4, correlation_id="correlation", result_snapshot={"document_version_id": 3})
    append_outbox_intent(connection, case_no="CASE-1", signing_event_id=4, intent_key="key", intent_type="contract_document_sent", payload_snapshot={"document_version_id": 3})

    assert "contract_signing_command_receipts" in connection.calls[0][0]
    assert len(connection.calls[0][1][1]) == 64
    assert "contract_signing_outbox" in connection.calls[1][0]
