"""MySQL adapter for Client Finance payment-destination configuration."""

from __future__ import annotations

import json

from domains.client_finance.payment_destination import ClientPaymentDestination
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import IdempotencyKey
from subsystems.client_finance.payment_destination_configuration import (
    PaymentDestinationApplyRequest,
    PaymentDestinationReceipt,
    StoredPaymentDestinationReceipt,
)


class MySqlClientPaymentDestinationRepository:
    def __init__(self, connection) -> None:
        self._connection = connection

    def load_current(self, *, lock: bool = False) -> ClientPaymentDestination | None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT account_display,revision FROM client_payment_destination_configuration_current WHERE singleton_id=1" + (" FOR UPDATE" if lock else "")
            )
            row = cursor.fetchone()
        return None if row is None else ClientPaymentDestination(str(row["account_display"]), int(row["revision"]))

    def find_receipt(self, key: IdempotencyKey) -> StoredPaymentDestinationReceipt | None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT command_fingerprint,result_snapshot FROM client_payment_destination_configuration_receipts WHERE idempotency_key=%s FOR UPDATE",
                (key.value,),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        snapshot = row["result_snapshot"] if isinstance(row["result_snapshot"], dict) else json.loads(row["result_snapshot"])
        receipt = PaymentDestinationReceipt(
            str(snapshot["account_display"]),
            int(snapshot["resulting_revision"]),
            PreviewFingerprint(str(snapshot["preview_fingerprint"])),
        )
        return StoredPaymentDestinationReceipt(PreviewFingerprint(str(row["command_fingerprint"])), receipt)

    def persist(self, request, receipt, command_fingerprint) -> None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO client_payment_destination_configuration_events (expected_revision,resulting_revision,account_display,actor,reason,idempotency_key,correlation_id,preview_fingerprint) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                (request.expected_revision, receipt.resulting_revision, receipt.account_display, request.actor.actor_id, request.reason.strip(), request.idempotency_key.value, request.correlation_id.value, request.preview_fingerprint.value),
            )
            event_id = int(cursor.lastrowid)
            cursor.execute(
                "INSERT INTO client_payment_destination_configuration_current (singleton_id,current_event_id,account_display,revision) VALUES (1,%s,%s,%s) ON DUPLICATE KEY UPDATE current_event_id=VALUES(current_event_id),account_display=VALUES(account_display),revision=VALUES(revision)",
                (event_id, receipt.account_display, receipt.resulting_revision),
            )
            snapshot = json.dumps({"account_display": receipt.account_display, "resulting_revision": receipt.resulting_revision, "preview_fingerprint": receipt.preview_fingerprint.value}, ensure_ascii=False, sort_keys=True)
            cursor.execute(
                "INSERT INTO client_payment_destination_configuration_receipts (idempotency_key,event_id,command_fingerprint,result_snapshot) VALUES (%s,%s,%s,%s)",
                (request.idempotency_key.value, event_id, command_fingerprint.value, snapshot),
            )

