"""Append-only migration journal and crash reconciliation."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Literal, Mapping


JournalStatus = Literal["prepared", "applied", "exact", "failed"]
ReconciledAction = Literal["execute", "skip_exact", "resume", "blocked"]


@dataclass(frozen=True, slots=True)
class JournalEntry:
    sequence: int
    operation_id: str
    part: str
    statement_index: int
    statement_sha256: str
    status: JournalStatus
    metadata_sha256: str
    prior_entry_sha256: str | None
    entry_sha256: str


@dataclass(frozen=True, slots=True)
class StatementReconciliation:
    action: ReconciledAction
    reason: str


class AppendOnlyDdlJournal:
    def __init__(self, path: Path) -> None:
        self._path = path.expanduser().resolve()

    def entries(self) -> tuple[JournalEntry, ...]:
        if not self._path.exists():
            return ()
        parsed = tuple(
            _parse_entry(line)
            for line in self._path.read_text(encoding="utf-8").splitlines()
            if line
        )
        _validate_chain(parsed)
        return parsed

    # Explicit identity fields prevent ambiguous positional journal writes.
    def append(
        self,
        *,
        operation_id: str,
        part: str,
        statement_index: int,
        statement_sha256: str,
        status: JournalStatus,
        metadata_sha256: str,
    ) -> JournalEntry:
        prior_entries = self.entries()
        entry = _build_entry(
            prior_entries,
            operation_id,
            part,
            statement_index,
            statement_sha256,
            status,
            metadata_sha256,
        )
        self._append_bytes(_serialize_entry(entry))
        return entry

    def _append_bytes(self, payload: bytes) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("ab") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())


def reconcile_statement(
    entries: tuple[JournalEntry, ...],
    *,
    operation_id: str,
    part: str,
    statement_index: int,
    statement_sha256: str,
    current_part_state: str,
    current_metadata_sha256: str,
) -> StatementReconciliation:
    matching = _matching_entries(
        entries, operation_id, part, statement_index, statement_sha256
    )
    return _reconcile_matching(
        matching,
        current_part_state,
        current_metadata_sha256,
    )


def _reconcile_matching(
    matching: tuple[JournalEntry, ...],
    current_part_state: str,
    current_metadata_sha256: str,
) -> StatementReconciliation:
    if current_part_state == "exact":
        return StatementReconciliation("skip_exact", "metadata_is_exact")
    if current_part_state == "drift":
        return StatementReconciliation("blocked", "metadata_drift")
    if not matching:
        return StatementReconciliation("execute", "no_prior_statement")
    return _reconcile_prior(
        matching,
        current_part_state,
        current_metadata_sha256,
    )


def _build_entry(
    entries: tuple[JournalEntry, ...],
    operation_id: str,
    part: str,
    statement_index: int,
    statement_sha256: str,
    status: JournalStatus,
    metadata_sha256: str,
) -> JournalEntry:
    payload = _entry_payload(
        entries,
        operation_id,
        part,
        statement_index,
        statement_sha256,
        status,
        metadata_sha256,
    )
    return JournalEntry(**payload, entry_sha256=_entry_digest(payload))


def _reconcile_prior(
    entries: tuple[JournalEntry, ...],
    current_state: str,
    metadata_sha256: str,
) -> StatementReconciliation:
    prior = entries[-1]
    if prior.status == "prepared" and prior.metadata_sha256 == metadata_sha256:
        return StatementReconciliation("execute", "prepared_without_effect")
    if prior.status == "prepared" and current_state == "resumable_partial":
        return StatementReconciliation("resume", "prepared_effect_detected")
    prepared = _latest_prepared_entry(entries)
    if prior.status == "failed" and prepared is not None:
        if prepared.metadata_sha256 == metadata_sha256:
            return StatementReconciliation("execute", "failed_without_effect")
    if prior.status in {"applied", "failed"} and current_state == "resumable_partial":
        return StatementReconciliation("resume", "durable_partial_boundary")
    return StatementReconciliation("blocked", "statement_receipt_conflict")


def _latest_prepared_entry(
    entries: tuple[JournalEntry, ...],
) -> JournalEntry | None:
    return next(
        (entry for entry in reversed(entries) if entry.status == "prepared"),
        None,
    )


def _matching_entries(
    entries: tuple[JournalEntry, ...],
    operation_id: str,
    part: str,
    statement_index: int,
    statement_sha256: str,
) -> tuple[JournalEntry, ...]:
    return tuple(
        entry
        for entry in entries
        if (
            entry.operation_id,
            entry.part,
            entry.statement_index,
            entry.statement_sha256,
        )
        == (operation_id, part, statement_index, statement_sha256)
    )


def _entry_payload(
    entries: tuple[JournalEntry, ...],
    operation_id: str,
    part: str,
    statement_index: int,
    statement_sha256: str,
    status: JournalStatus,
    metadata_sha256: str,
) -> dict[str, Any]:
    return {
        "sequence": len(entries) + 1,
        "operation_id": operation_id,
        "part": part,
        "statement_index": statement_index,
        "statement_sha256": statement_sha256,
        "status": status,
        "metadata_sha256": metadata_sha256,
        "prior_entry_sha256": entries[-1].entry_sha256 if entries else None,
    }


def _serialize_entry(entry: JournalEntry) -> bytes:
    return _canonical_json(asdict(entry)) + b"\n"


def _parse_entry(line: str) -> JournalEntry:
    payload = json.loads(line)
    if not isinstance(payload, dict):
        raise ValueError("journal entry must be an object")
    return JournalEntry(**payload)


def _validate_chain(entries: tuple[JournalEntry, ...]) -> None:
    prior_digest: str | None = None
    for expected_sequence, entry in enumerate(entries, start=1):
        payload = asdict(entry)
        payload.pop("entry_sha256")
        if entry.sequence != expected_sequence:
            raise ValueError("journal sequence is not contiguous")
        if entry.prior_entry_sha256 != prior_digest:
            raise ValueError("journal hash chain is broken")
        if _entry_digest(payload) != entry.entry_sha256:
            raise ValueError("journal entry digest mismatch")
        prior_digest = entry.entry_sha256


def _entry_digest(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(payload)).hexdigest()


def _canonical_json(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
