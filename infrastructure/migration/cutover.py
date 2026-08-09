"""Configuration switch crash-state reconciliation."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping
from typing import Literal


SwitchCrashState = Literal[
    "prepared_not_switched",
    "switched_requires_restart",
    "completed",
    "ambiguous",
]


@dataclass(frozen=True, slots=True)
class SwitchReconciliation:
    state: SwitchCrashState
    next_action: str


@dataclass(frozen=True, slots=True)
class CutoverJournalEvent:
    sequence: int
    event_type: str
    receipt_sha256: str
    prior_event_sha256: str | None
    event_sha256: str


class AppendOnlyCutoverJournal:
    def __init__(self, path: Path) -> None:
        self._path = path.expanduser().resolve()

    def events(self) -> tuple[CutoverJournalEvent, ...]:
        if not self._path.exists():
            return ()
        events = tuple(
            CutoverJournalEvent(**json.loads(line))
            for line in self._path.read_text(encoding="utf-8").splitlines()
            if line
        )
        _validate_events(events)
        return events

    def append(
        self,
        event_type: str,
        receipt: Mapping[str, Any],
    ) -> CutoverJournalEvent:
        events = self.events()
        payload = _cutover_event_payload(events, event_type, receipt)
        event = CutoverJournalEvent(
            **payload,
            event_sha256=_digest(payload),
        )
        self._append_bytes(_canonical_json(asdict(event)) + b"\n")
        return event

    def _append_bytes(self, payload: bytes) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("ab") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())


def reconcile_switch_state(
    *,
    current_config_sha256: str,
    before_sha256: str,
    after_sha256: str,
    restart_receipt_present: bool,
    smoke_receipt_present: bool,
) -> SwitchReconciliation:
    if current_config_sha256 == before_sha256:
        return SwitchReconciliation("prepared_not_switched", "publish_candidate")
    if current_config_sha256 != after_sha256:
        return SwitchReconciliation("ambiguous", "manual_review")
    if not restart_receipt_present or not smoke_receipt_present:
        return SwitchReconciliation(
            "switched_requires_restart",
            "restart_and_run_read_smoke",
        )
    return SwitchReconciliation("completed", "none")


def _cutover_event_payload(
    events: tuple[CutoverJournalEvent, ...],
    event_type: str,
    receipt: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "sequence": len(events) + 1,
        "event_type": event_type,
        "receipt_sha256": hashlib.sha256(_canonical_json(receipt)).hexdigest(),
        "prior_event_sha256": events[-1].event_sha256 if events else None,
    }


def _validate_events(events: tuple[CutoverJournalEvent, ...]) -> None:
    prior_digest: str | None = None
    for sequence, event in enumerate(events, start=1):
        payload = asdict(event)
        payload.pop("event_sha256")
        if event.sequence != sequence or event.prior_event_sha256 != prior_digest:
            raise ValueError("cutover journal chain is broken")
        if event.event_sha256 != _digest(payload):
            raise ValueError("cutover journal digest mismatch")
        prior_digest = event.event_sha256


def _digest(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(payload)).hexdigest()


def _canonical_json(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
