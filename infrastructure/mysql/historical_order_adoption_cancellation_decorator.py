"""Add the canonical cancellation control when Historical Orders adopts status 0."""

from __future__ import annotations

from domains.orders.lifecycle import OrderLifecycleStatus
from infrastructure.mysql.historical_order_adoption_repository import (
    MySqlHistoricalOrderAdoptionRepository,
)
from subsystems.orders.order_lifecycle_command_envelope import (
    lock_order_lifecycle_command_envelope,
)
from subsystems.orders.order_lifecycle_control_commands import (
    CancellationControlCommand,
    apply_order_lifecycle_control_command,
)


_HISTORICAL_REASON_PREFIX = "historical_order_adoption:"


class MySqlHistoricalOrderAdoptionCancellationDecorator:
    """Keep status-0 terminal across later normal lifecycle recalculation."""

    def __init__(self, connection, inner=None) -> None:
        self._connection = connection
        self._inner = inner or MySqlHistoricalOrderAdoptionRepository(connection)

    def load_order(self, case_no, client_name, *, for_update):
        return self._inner.load_order(case_no, client_name, for_update=for_update)

    def resolve_staff(self, name, *, for_update):
        return self._inner.resolve_staff(name, for_update=for_update)

    def active_assignments(self, case_no, *, for_update):
        return self._inner.active_assignments(case_no, for_update=for_update)

    def find_receipt(self, key, source_identity):
        return self._inner.find_receipt(key, source_identity)

    def persist(self, request, preview, assignment_ids):
        _sync_historical_cancellation(self._connection, request, preview)
        return self._inner.persist(request, preview, assignment_ids)


def _sync_historical_cancellation(connection, request, preview) -> None:
    # The inner repository will append the matching lifecycle decision only when
    # the adoption mutates the Orders aggregate.  Keep the control/event pair
    # together and avoid creating control-only no-op history.
    if preview.resulting_version == preview.expected_version:
        return

    target_active = preview.after_status == OrderLifecycleStatus.CANCELLED.value
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT state,reason FROM order_lifecycle_control_state "
            "WHERE case_no=%s AND control_type='cancellation' "
            "AND control_key='order_cancelled' FOR UPDATE",
            (preview.case_no,),
        )
        current = cursor.fetchone()
        current_active = bool(current and current.get("state") == "active")
        if target_active == current_active:
            return
        if (
            not target_active
            and current_active
            and not str(current.get("reason") or "").startswith(_HISTORICAL_REASON_PREFIX)
        ):
            return

        envelope = lock_order_lifecycle_command_envelope(
            cursor,
            preview.case_no,
            preview.expected_version,
            request.idempotency_key,
        )
        apply_order_lifecycle_control_command(
            cursor,
            envelope,
            CancellationControlCommand(
                "activate" if target_active else "clear",
                request.actor,
                f"{_HISTORICAL_REASON_PREFIX}{request.reason}",
                preview.expected_version,
                request.idempotency_key,
            ),
        )


__all__ = ["MySqlHistoricalOrderAdoptionCancellationDecorator"]
