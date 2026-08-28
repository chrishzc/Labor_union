"""
File: historical_completion_query.py
Description: 只讀組合各 owner terminal roots，交由完成 oracle 判定歷史案件狀態。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, TypeVar

from shared_kernel.errors import ErrorCategory, TypedError
from shared_kernel.identities import CorrelationId
from shared_kernel.validation import require_canonical_text
from subsystems.orders.historical_completion_oracle import (
    CompletionOwner,
    HistoricalCompletionFacts,
    HistoricalCompletionOracleResult,
    HistoricalOrdersCompletionReadback,
    HistoricalSettlementReadback,
    evaluate_historical_completion,
)


_CASE_NUMBER_MAXIMUM_LENGTH = 50


@dataclass(frozen=True, slots=True)
class HistoricalCompletionQueryRequest:
    """The single case identity accepted by the cross-owner read composition."""

    case_no: str

    def __post_init__(self) -> None:
        require_canonical_text(self.case_no, "case number", _CASE_NUMBER_MAXIMUM_LENGTH)


class OrdersSchedulingCompletionReadPort(Protocol):
    """Read-only Orders/Scheduling owner port; implementations must not write."""

    def load_completion_readback(
        self, case_no: str, *, for_update: bool = False
    ) -> HistoricalOrdersCompletionReadback | None: ...


class ClientFinanceCompletionReadPort(Protocol):
    """Read-only Client Finance terminal settlement port."""

    def load_completion_readback(
        self, case_no: str, *, for_update: bool = False
    ) -> HistoricalSettlementReadback | None: ...


class StaffPayablesCompletionReadPort(Protocol):
    """Read-only Staff Payables terminal settlement port."""

    def load_completion_readback(
        self, case_no: str, *, for_update: bool = False
    ) -> HistoricalSettlementReadback | None: ...


class HistoricalCompletionQueryError(Exception):
    """A typed, fail-closed error at the cross-owner query boundary."""

    def __init__(self, error: TypedError) -> None:
        super().__init__(error.code)
        self.error = error


_Readback = TypeVar("_Readback")


class HistoricalCompletionQueryWorkflow:
    """Load three current owner roots and delegate all completion rules to the oracle."""

    def __init__(
        self,
        orders_scheduling: OrdersSchedulingCompletionReadPort,
        client_finance: ClientFinanceCompletionReadPort,
        staff_payables: StaffPayablesCompletionReadPort,
    ) -> None:
        self._orders_scheduling = orders_scheduling
        self._client_finance = client_finance
        self._staff_payables = staff_payables

    def query(
        self,
        request: HistoricalCompletionQueryRequest,
        correlation_id: CorrelationId,
    ) -> HistoricalCompletionOracleResult:
        if not isinstance(request, HistoricalCompletionQueryRequest):
            raise TypeError("historical completion query request is invalid")
        if not isinstance(correlation_id, CorrelationId):
            raise TypeError("historical completion correlation id is invalid")

        case_no = request.case_no
        orders = self._load(
            self._orders_scheduling,
            case_no,
            HistoricalOrdersCompletionReadback,
            "orders_scheduling",
            correlation_id,
        )
        client_finance = self._load(
            self._client_finance,
            case_no,
            HistoricalSettlementReadback,
            "client_finance",
            correlation_id,
            expected_owner=CompletionOwner.CLIENT_FINANCE,
        )
        staff_payables = self._load(
            self._staff_payables,
            case_no,
            HistoricalSettlementReadback,
            "staff_payables",
            correlation_id,
            expected_owner=CompletionOwner.STAFF_PAYABLES,
        )

        facts = HistoricalCompletionFacts(
            case_no,
            orders
            if orders is not None
            else _unavailable_orders_readback(case_no),
            client_finance
            if client_finance is not None
            else _unavailable_settlement_readback(
                case_no, CompletionOwner.CLIENT_FINANCE
            ),
            staff_payables
            if staff_payables is not None
            else _unavailable_settlement_readback(
                case_no, CompletionOwner.STAFF_PAYABLES
            ),
        )
        return evaluate_historical_completion(facts)

    def execute(
        self,
        request: HistoricalCompletionQueryRequest,
        correlation_id: CorrelationId,
    ) -> HistoricalCompletionOracleResult:
        """Alias for callers that use the subsystem query/execute convention."""

        return self.query(request, correlation_id)

    @staticmethod
    def _load(
        port: object,
        case_no: str,
        expected_type: type[_Readback],
        owner: str,
        correlation_id: CorrelationId,
        expected_owner: CompletionOwner | None = None,
    ) -> _Readback | None:
        loader = getattr(port, "load_completion_readback", None)
        if not callable(loader):
            raise _query_error(
                correlation_id,
                ErrorCategory.CONFLICT,
                f"historical_completion_{owner}_port_invalid",
            )
        try:
            result = loader(case_no, for_update=False)
        except (ConnectionError, LookupError, TimeoutError, OSError) as error:
            # An unavailable owner is represented through the oracle so callers can
            # display an actionable unavailable state without claiming completion.
            return None
        except HistoricalCompletionQueryError:
            raise
        except (TypeError, ValueError) as error:
            raise _query_error(
                correlation_id,
                ErrorCategory.CONFLICT,
                f"historical_completion_{owner}_readback_invalid",
            ) from error
        except Exception:
            # Storage drivers do not share one portable exception hierarchy.
            # At this read boundary an unknown owner failure is unavailable,
            # never evidence that Step 11 is complete.
            return None
        if result is None:
            return None
        if not isinstance(result, expected_type):
            raise _query_error(
                correlation_id,
                ErrorCategory.CONFLICT,
                f"historical_completion_{owner}_readback_invalid",
            )
        if result.case_no != case_no:
            raise _query_error(
                correlation_id,
                ErrorCategory.CONFLICT,
                f"historical_completion_{owner}_identity_mismatch",
            )
        if expected_owner is not None and result.owner is not expected_owner:
            raise _query_error(
                correlation_id,
                ErrorCategory.CONFLICT,
                f"historical_completion_{owner}_owner_mismatch",
            )
        return result


def _unavailable_orders_readback(case_no: str) -> HistoricalOrdersCompletionReadback:
    from domains.orders.lifecycle import OrderLifecycleStatus

    return HistoricalOrdersCompletionReadback(
        case_no=case_no,
        lifecycle_version=0,
        canonical_status=OrderLifecycleStatus.DISCUSSION,
        completion_lineage_identity=None,
        actual_start_date=None,
        official_service_fact_identity=None,
        official_service_dates=(),
        required_service_day_count=1,
        service_time_tuple_complete=False,
        readback_available=False,
    )


def _unavailable_settlement_readback(
    case_no: str, owner: CompletionOwner
) -> HistoricalSettlementReadback:
    return HistoricalSettlementReadback(
        case_no=case_no,
        owner=owner,
        aggregate_version=None,
        settlement_lineage_identity=None,
        obligation_count=0,
        open_obligation_count=0,
        allocation_lineage_identity=None,
        readback_available=False,
    )


def _query_error(
    correlation_id: CorrelationId,
    category: ErrorCategory,
    code: str,
) -> HistoricalCompletionQueryError:
    return HistoricalCompletionQueryError(
        TypedError(
            category,
            code,
            "歷史案件完成根事實查詢無法安全完成。",
            correlation_id,
            domain_blockers=(code,),
        )
    )


__all__ = [
    "ClientFinanceCompletionReadPort",
    "HistoricalCompletionQueryError",
    "HistoricalCompletionQueryRequest",
    "HistoricalCompletionQueryWorkflow",
    "OrdersSchedulingCompletionReadPort",
    "StaffPayablesCompletionReadPort",
]
