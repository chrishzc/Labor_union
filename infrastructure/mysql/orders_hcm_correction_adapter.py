"""Orders owner bridge for HCM corrections; it borrows Case Import's UoW."""

from __future__ import annotations

from dataclasses import replace

from infrastructure.mysql.order_terms_repository import MySqlOrderTermsRepository
from shared_kernel.clock import SystemBusinessClock
from shared_kernel.identities import (
    ActorContext,
    CorrelationId,
    ExpectedVersion,
    IdempotencyKey,
)
from subsystems.orders.terms_workflow import OrderTermsApplyRequest, OrderTermsWorkflow


class MySqlOrdersHcmCorrectionAdapter:
    """Translate only current HCM-owned Order fields to typed Terms Apply."""

    def __init__(self, connection) -> None:
        self._connection = connection

    def apply_in_current_uow(
        self,
        case_no: str,
        values: dict[str, object],
        *,
        source_event_identity: str,
        actor: str,
        reason: str,
        correlation_id: str,
        idempotency_key: str,
    ):
        if any(key == "orders.service_type" for key in values):
            raise ValueError("orders_service_type_not_owned")
        repository = MySqlOrderTermsRepository(self._connection)
        workflow = OrderTermsWorkflow(repository, _nested_uow_forbidden, SystemBusinessClock())
        facts = repository.load_for_preview(case_no)
        terms = facts.order.terms
        updates = {}
        for target, value in values.items():
            if target == "orders.service_hours_per_day":
                updates["service_hours_per_day"] = value
            elif target == "orders.service_start_time":
                updates.setdefault("service_time", {})["start_time"] = value
            elif target == "orders.service_end_time":
                updates.setdefault("service_time", {})["end_time"] = value
            elif target == "orders.service_end_day_offset":
                updates.setdefault("service_time", {})["end_day_offset"] = value
            elif target == "orders.service_days":
                updates["service_days"] = value
            elif target == "orders.start_date":
                updates["planned_start_date"] = value
            elif target == "orders.end_date":
                # End date is derived by Orders and is never directly written.
                continue
            else:
                raise ValueError("orders_hcm_correction_target_invalid")
        if "service_time" in updates:
            from domains.orders.terms import ServiceTimeTerms
            current = terms.service_time
            updates["service_time"] = ServiceTimeTerms(
                updates["service_time"].get("start_time", current.start_time),
                updates["service_time"].get("end_time", current.end_time),
                updates["service_time"].get("end_day_offset", current.end_day_offset),
            )
        proposed = replace(terms, **updates)
        preview = workflow.preview(case_no, proposed)
        return workflow.apply_in_current_uow(
            OrderTermsApplyRequest(
                case_no,
                proposed,
                ExpectedVersion(preview.order_version),
                ExpectedVersion(preview.scheduling_version),
                ExpectedVersion(preview.client_finance_version),
                ExpectedVersion(preview.payroll_version),
                preview.fingerprint,
                IdempotencyKey(idempotency_key),
                ActorContext(actor),
                reason,
                CorrelationId(correlation_id),
            )
        )


def _nested_uow_forbidden():
    raise RuntimeError("hcm_correction_requires_case_import_uow")


__all__ = ["MySqlOrdersHcmCorrectionAdapter"]
