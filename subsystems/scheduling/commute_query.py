"""Manual, single-person commute queries and shared monthly usage estimates."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal, Protocol
from zoneinfo import ZoneInfo

from shared_kernel.durable_job_queue import DurableJobCommand, DurableJobLease

COMMAND_TYPE = "scheduling_commute_query"
RECONCILIATION_TYPE = "scheduling_commute_billing_reconciliation"
BILLING_ZONE = ZoneInfo("America/Los_Angeles")
FREE_LIMIT = 1000


class CommuteError(ValueError):
    def __init__(self, code: str, message: str, status: int = 409):
        self.code, self.message, self.status = code, message, status
        super().__init__(message)


@dataclass(frozen=True)
class RouteResult:
    status: Literal["ready", "no_route", "failed", "unknown"]
    billing: Literal["billable", "not_billable", "unknown"]
    distance_meters: int | None = None
    duration_seconds: float | None = None
    message: str = ""


@dataclass(frozen=True)
class PreparedQuery:
    lease: DurableJobLease | None
    origin: str = ""
    destination: str = ""


@dataclass(frozen=True)
class CommuteHistoryRecord:
    record_id: str
    queried_at: datetime
    staff_id: int
    staff_name: str | None
    status: Literal["succeeded", "failed", "unknown"]
    message: str


class CommuteRepository(Protocol):
    def prepare(self, command: DurableJobCommand, now: datetime) -> PreparedQuery: ...
    def finish(self, lease: DurableJobLease, result: RouteResult) -> None: ...
    def usage(self, start: datetime, end: datetime) -> tuple[list[dict], dict | None]: ...
    def reconcile(self, command: DurableJobCommand) -> None: ...
    def history(self, case_no: str) -> list[CommuteHistoryRecord]: ...


class Transaction(Protocol):
    def begin(self) -> None: ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...


class RouteProvider(Protocol):
    @property
    def configured(self) -> bool: ...
    def compute(self, origin: str, destination: str) -> RouteResult: ...


def billing_period(now: datetime) -> tuple[str, datetime, datetime]:
    local = now.astimezone(BILLING_ZONE)
    start = local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    end = start.replace(year=start.year + 1, month=1) if start.month == 12 else start.replace(month=start.month + 1)
    return start.strftime("%Y-%m"), start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def estimated_cost(count: int) -> str:
    cost, lower = Decimal(0), FREE_LIMIT
    for upper, rate in ((100000, "0.015"), (500000, "0.012"), (1000000, "0.009"), (5000000, "0.0045"), (max(count, 5000000), "0.00114")):
        cost += Decimal(max(0, min(count, upper) - lower)) * Decimal(rate)
        lower = upper
    return format(cost.quantize(Decimal("0.01")), "f")


class CommuteApplication:
    def __init__(self, repository: CommuteRepository, transaction: Transaction, provider: RouteProvider):
        self.repository, self.transaction, self.provider = repository, transaction, provider

    def query(self, command: DurableJobCommand, now: datetime) -> dict:
        if not self.provider.configured:
            raise CommuteError("commute_not_configured", "尚未設定 Google Routes API，請聯絡管理員完成設定。", 503)
        self.transaction.begin()
        try:
            prepared = self.repository.prepare(command, now)
            self.transaction.commit()
        except Exception:
            self.transaction.rollback()
            raise
        if prepared.lease is None:
            return self._response(command, now, "already_requested", None, None,
                "此操作已受理，不會重複查詢或計費；距離未永久保存，需要新結果時請另按重新查詢。")
        # The durable claim is committed before any billable external request.
        # No automatic retry: a timeout may already have consumed usage.
        result = self.provider.compute(prepared.origin, prepared.destination)
        self.transaction.begin()
        try:
            self.repository.finish(prepared.lease, result)
            self.transaction.commit()
        except Exception:
            self.transaction.rollback()
            raise CommuteError("commute_outcome_unknown", "查詢已送出，但用量紀錄結果待確認；請先重新讀取用量，勿立即重查。", 503) from None
        return self._response(command, now, result.status, result.distance_meters, result.duration_seconds, result.message)

    def _response(self, command, now, status, distance, duration, message):
        return dict(case_no=command.payload["case_no"], staff_id=command.payload["staff_id"],
            event_key=command.payload["event_key"], status=status, distance_meters=distance,
            duration_seconds=duration, queried_at=now.isoformat(), message=message)

    def monthly_usage(self, now: datetime) -> dict:
        month, start, end = billing_period(now)
        rows, reconciliation = self.repository.usage(start, end)
        cutoff = reconciliation["through"] if reconciliation else start
        later = [row for row in rows if row["at"] >= cutoff]
        confirmed = (reconciliation["count"] if reconciliation else 0) + sum(row["billing"] == "billable" for row in later)
        uncertain = sum(row["billing"] == "unknown" for row in later)
        return dict(billing_month=month, billing_timezone="America/Los_Angeles", configured=self.provider.configured,
            free_limit=FREE_LIMIT, local_requests=len(rows), estimated_billable=confirmed,
            uncertain_requests=uncertain, free_used=min(FREE_LIMIT, confirmed),
            free_remaining=max(0, FREE_LIMIT - confirmed - uncertain), paid_requests=max(0, confirmed - FREE_LIMIT),
            estimated_cost_usd=estimated_cost(confirmed),
            verified_count=reconciliation["count"] if reconciliation else None,
            verified_through=cutoff.isoformat() if reconciliation else None,
            verified_at=reconciliation["at"].isoformat() if reconciliation else None)

    def history(self, case_no: str) -> dict:
        return dict(case_no=case_no, records=[dict(record_id=row.record_id,
            queried_at=row.queried_at.isoformat(), staff_id=row.staff_id, staff_name=row.staff_name,
            status=row.status, message=row.message) for row in self.repository.history(case_no)])

    def reconcile(self, command: DurableJobCommand, now: datetime) -> None:
        month, start, _ = billing_period(now)
        through = datetime.fromisoformat(command.payload["through"])
        if command.payload["month"] != month or through.tzinfo is None or not start <= through <= now:
            raise CommuteError("commute_reconciliation_invalid", "請填本月 Google 報表的實際統計截止時間，且不得超過現在。", 422)
        self.transaction.begin()
        try:
            self.repository.reconcile(command)
            self.transaction.commit()
        except Exception:
            self.transaction.rollback()
            raise
