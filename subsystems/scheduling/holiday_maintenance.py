"""
File: holiday_maintenance.py
Description: 協調國定假日 horizon 的零寫入預覽、fresh-lock Apply 與冪等 receipt。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from typing import Literal, Protocol

from shared_kernel.fingerprints import fingerprint_payload
from subsystems.scheduling.holiday_calendar_query import (
    HolidayCalendarFacts,
    HolidayFact,
    SchedulingHolidayQuery,
)

_FAMILY = "scheduling_holiday_maintenance/v2"


@dataclass(frozen=True, slots=True)
class HolidayCommand:
    action: Literal["upsert", "delete"]
    holiday_date: date
    holiday_name: str | None
    is_double_pay_default: bool
    from_date: date
    to_date: date


@dataclass(frozen=True, slots=True)
class HolidayPreview:
    command: HolidayCommand
    before: HolidayFact | None
    calendar: HolidayCalendarFacts
    preview_fingerprint: str


@dataclass(frozen=True, slots=True)
class HolidayReceipt:
    receipt_key: str
    action: Literal["upsert", "delete"]
    holiday_date: date
    changed: bool
    from_date: date
    to_date: date
    source_identity: str
    previous_calendar_version: str
    resulting_calendar_version: str
    preview_fingerprint: str


class HolidayWorkflowError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class HolidayMaintenanceRepository(SchedulingHolidayQuery, Protocol):
    def load_receipt(self, family: str, key: str): ...

    def save_receipt(
        self,
        family: str,
        key: str,
        request_fingerprint: str,
        preview_fingerprint: str,
        actor: str,
        reason: str,
        result: dict[str, object],
    ) -> None: ...

    def upsert_holiday(
        self,
        holiday_date: date,
        holiday_name: str,
        is_double_pay_default: bool,
    ) -> None: ...

    def delete_holiday(self, holiday_date: date) -> None: ...


def preview(repository: SchedulingHolidayQuery, command: HolidayCommand) -> HolidayPreview:
    calendar = repository.query(command.from_date, command.to_date, lock=False)
    return _preview_from_calendar(command, calendar)


def apply(
    repository: HolidayMaintenanceRepository,
    command: HolidayCommand,
    expected_calendar_version: str,
    preview_fingerprint: str,
    idempotency_key: str,
    actor: str,
    reason: str,
) -> HolidayReceipt:
    request_fingerprint = fingerprint_payload(
        {
            "command": _command_payload(command),
            "expected_calendar_version": expected_calendar_version,
            "preview_fingerprint": preview_fingerprint,
            "actor": actor,
            "reason": reason,
        }
    ).value
    stored = repository.load_receipt(_FAMILY, idempotency_key)
    if stored is not None:
        if stored["request_fingerprint"] != request_fingerprint:
            raise HolidayWorkflowError("idempotency_key_conflict")
        return _receipt_from_snapshot(stored["result_snapshot"])

    calendar = repository.query(command.from_date, command.to_date, lock=True)
    if calendar.holiday_version != expected_calendar_version:
        raise HolidayWorkflowError("stale_preview")
    current_preview = _preview_from_calendar(command, calendar)
    if current_preview.preview_fingerprint != preview_fingerprint:
        raise HolidayWorkflowError("stale_preview")

    changed = _would_change(command, current_preview.before)
    if changed and command.action == "delete":
        repository.delete_holiday(command.holiday_date)
    elif changed:
        repository.upsert_holiday(
            command.holiday_date,
            command.holiday_name or "",
            command.is_double_pay_default,
        )
    resulting = repository.query(command.from_date, command.to_date, lock=True)
    receipt = HolidayReceipt(
        idempotency_key,
        command.action,
        command.holiday_date,
        changed,
        command.from_date,
        command.to_date,
        resulting.source_identity,
        calendar.holiday_version,
        resulting.holiday_version,
        preview_fingerprint,
    )
    repository.save_receipt(
        _FAMILY,
        idempotency_key,
        request_fingerprint,
        preview_fingerprint,
        actor,
        reason,
        _receipt_payload(receipt),
    )
    return receipt


def _preview_from_calendar(
    command: HolidayCommand,
    calendar: HolidayCalendarFacts,
) -> HolidayPreview:
    before = next(
        (item for item in calendar.holidays if item.holiday_date == command.holiday_date),
        None,
    )
    if command.action == "delete" and before is None:
        raise HolidayWorkflowError("holiday_not_found")
    payload = {
        "command": _command_payload(command),
        "before": _fact_payload(before),
        "planning_horizon": {
            "from_date": command.from_date.isoformat(),
            "to_date": command.to_date.isoformat(),
        },
        "source_identity": calendar.source_identity,
        "calendar_version": calendar.holiday_version,
        "schedule_impact": "none",
        "payroll_impact": "none",
    }
    return HolidayPreview(
        command,
        before,
        calendar,
        fingerprint_payload(payload).value,
    )


def _would_change(command: HolidayCommand, before: HolidayFact | None) -> bool:
    if command.action == "delete":
        return True
    return before != HolidayFact(
        command.holiday_date,
        command.holiday_name or "",
        command.is_double_pay_default,
    )


def _command_payload(command: HolidayCommand) -> dict[str, object]:
    return {
        "action": command.action,
        "holiday_date": command.holiday_date.isoformat(),
        "holiday_name": command.holiday_name,
        "is_double_pay_default": command.is_double_pay_default,
        "from_date": command.from_date.isoformat(),
        "to_date": command.to_date.isoformat(),
    }


def _fact_payload(fact: HolidayFact | None) -> dict[str, object] | None:
    if fact is None:
        return None
    return {
        "holiday_date": fact.holiday_date.isoformat(),
        "holiday_name": fact.holiday_name,
        "is_double_pay_default": fact.is_double_pay_default,
    }


def _receipt_payload(receipt: HolidayReceipt) -> dict[str, object]:
    return {
        "receipt_key": receipt.receipt_key,
        "action": receipt.action,
        "holiday_date": receipt.holiday_date.isoformat(),
        "changed": receipt.changed,
        "from_date": receipt.from_date.isoformat(),
        "to_date": receipt.to_date.isoformat(),
        "source_identity": receipt.source_identity,
        "previous_calendar_version": receipt.previous_calendar_version,
        "resulting_calendar_version": receipt.resulting_calendar_version,
        "preview_fingerprint": receipt.preview_fingerprint,
    }


def _receipt_from_snapshot(snapshot) -> HolidayReceipt:
    payload = json.loads(snapshot) if isinstance(snapshot, str) else snapshot
    return HolidayReceipt(
        payload["receipt_key"],
        payload["action"],
        date.fromisoformat(payload["holiday_date"]),
        payload["changed"],
        date.fromisoformat(payload["from_date"]),
        date.fromisoformat(payload["to_date"]),
        payload["source_identity"],
        payload["previous_calendar_version"],
        payload["resulting_calendar_version"],
        payload["preview_fingerprint"],
    )
