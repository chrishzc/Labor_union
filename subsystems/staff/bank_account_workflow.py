"""Staff Bank Account Query/Preview/Apply owner workflow."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Callable, Protocol

from domains.staff.bank_account import (
    StaffBankAccountCommand,
    account_last4,
    normalize_bank_command,
)
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey


_COMMAND_FAMILY = "staff_bank_account_change/v1"
_MAX_ACCOUNTS = 20


class StaffBankAccountNotFound(LookupError):
    pass


class StaffBankAccountConflict(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class StaffBankAccountFact:
    account_id: int
    bank_code: str
    branch_code: str
    account_no: str
    is_primary: bool
    is_active: bool


@dataclass(frozen=True, slots=True)
class StaffBankAccountSnapshot:
    staff_id: int
    version: int
    accounts: tuple[StaffBankAccountFact, ...]


@dataclass(frozen=True, slots=True)
class StaffBankAccountPreview:
    staff_id: int
    current_version: int
    operation: str
    before: Mapping[str, object] | None
    after: Mapping[str, object] | None
    preview_fingerprint: PreviewFingerprint


@dataclass(frozen=True, slots=True)
class StaffBankAccountReceipt:
    staff_id: int
    account_id: int
    operation: str
    resulting_version: int
    preview_fingerprint: PreviewFingerprint
    idempotency_key: IdempotencyKey
    replayed: bool
    readback: StaffBankAccountSnapshot


class StaffBankAccountRepository(Protocol):
    def load(self, staff_id: int, *, for_update: bool) -> Mapping[str, Any] | None: ...
    def account_owner(self, account_no: str, *, for_update: bool) -> int | None: ...
    def claim(self, *, staff_id: int, key: IdempotencyKey, command_fingerprint: PreviewFingerprint, correlation_id: CorrelationId) -> None: ...
    def load_receipt(self, key: IdempotencyKey, *, for_update: bool) -> Mapping[str, Any] | None: ...
    def persist(self, *, snapshot: StaffBankAccountSnapshot, command: StaffBankAccountCommand, candidate: StaffBankAccountSnapshot, actor: ActorContext, reason: str, key: IdempotencyKey, correlation_id: CorrelationId) -> tuple[int, int]: ...
    def save_receipt(self, *, key: IdempotencyKey, command_fingerprint: PreviewFingerprint, preview_fingerprint: PreviewFingerprint, actor: ActorContext, reason: str, result: Mapping[str, Any]) -> None: ...


class StaffBankAccountWorkflow:
    def __init__(self, repository: StaffBankAccountRepository, unit_of_work_factory: Callable[[], Any]) -> None:
        self._repository = repository
        self._unit_of_work_factory = unit_of_work_factory

    def query(self, staff_id: int) -> StaffBankAccountSnapshot:
        return _snapshot(self._require(self._repository.load(_staff_id(staff_id), for_update=False)))

    def preview(self, staff_id: int, raw_command: Mapping[str, object], expected_version: ExpectedVersion) -> StaffBankAccountPreview:
        snapshot = self.query(staff_id)
        command = normalize_bank_command(raw_command)
        candidate, target_before, target_after = self._candidate(snapshot, command, lock_collision=False)
        if snapshot.version != expected_version.value:
            raise StaffBankAccountConflict("staff_bank_stale_version")
        return _preview(snapshot, command, candidate, target_before, target_after)

    def apply(
        self,
        staff_id: int,
        raw_command: Mapping[str, object],
        expected_version: ExpectedVersion,
        preview_fingerprint: PreviewFingerprint,
        idempotency_key: IdempotencyKey,
        actor: ActorContext,
        reason: str,
        correlation_id: CorrelationId,
    ) -> StaffBankAccountReceipt:
        identity = _staff_id(staff_id)
        command = normalize_bank_command(raw_command)
        clean_reason = reason.strip()
        if not clean_reason:
            raise ValueError("staff_bank_reason_required")
        command_fingerprint = fingerprint_payload({
            "family": _COMMAND_FAMILY,
            "staff_id": identity,
            "command": _command_payload(command),
            "expected_version": expected_version.value,
            "preview_fingerprint": preview_fingerprint.value,
            "actor": actor.actor_id,
            "reason": clean_reason,
        })
        with self._unit_of_work_factory() as unit_of_work:
            self._repository.claim(
                staff_id=identity,
                key=idempotency_key,
                command_fingerprint=command_fingerprint,
                correlation_id=correlation_id,
            )
            replay = self._repository.load_receipt(idempotency_key, for_update=True)
            if replay is not None:
                if str(replay["request_fingerprint"]) != command_fingerprint.value:
                    raise StaffBankAccountConflict("idempotency_mismatch")
                fresh = _snapshot(self._require(self._repository.load(identity, for_update=False)))
                unit_of_work.commit()
                return _receipt(replay["result"], preview_fingerprint, idempotency_key, True, fresh)
            snapshot = _snapshot(self._require(self._repository.load(identity, for_update=True)))
            if snapshot.version != expected_version.value:
                raise StaffBankAccountConflict("staff_bank_stale_version")
            candidate, target_before, target_after = self._candidate(snapshot, command, lock_collision=True)
            expected_preview = _preview(snapshot, command, candidate, target_before, target_after)
            if expected_preview.preview_fingerprint != preview_fingerprint:
                raise StaffBankAccountConflict("staff_bank_stale_preview")
            account_id, resulting_version = self._repository.persist(
                snapshot=snapshot,
                command=command,
                candidate=candidate,
                actor=actor,
                reason=clean_reason,
                key=idempotency_key,
                correlation_id=correlation_id,
            )
            result = {
                "staff_id": identity,
                "account_id": account_id,
                "operation": command.operation,
                "resulting_version": resulting_version,
            }
            self._repository.save_receipt(
                key=idempotency_key,
                command_fingerprint=command_fingerprint,
                preview_fingerprint=preview_fingerprint,
                actor=actor,
                reason=clean_reason,
                result=result,
            )
            unit_of_work.commit()
            fresh = _snapshot(self._require(self._repository.load(identity, for_update=False)))
            return _receipt(result, preview_fingerprint, idempotency_key, False, fresh)

    def _candidate(self, snapshot: StaffBankAccountSnapshot, command: StaffBankAccountCommand, *, lock_collision: bool) -> tuple[StaffBankAccountSnapshot, StaffBankAccountFact | None, StaffBankAccountFact | None]:
        accounts = list(snapshot.accounts)
        target = next((item for item in accounts if item.account_id == command.account_id), None)
        if command.operation != "add" and target is None:
            raise StaffBankAccountNotFound("staff_bank_account_not_found")
        if command.account_no is not None:
            owner = self._repository.account_owner(command.account_no, for_update=lock_collision)
            if owner is not None and (target is None or owner != target.account_id):
                raise StaffBankAccountConflict("staff_bank_account_collision")
        before = target
        after: StaffBankAccountFact | None
        if command.operation == "add":
            if len(accounts) >= _MAX_ACCOUNTS:
                raise StaffBankAccountConflict("staff_bank_account_limit")
            primary = bool(command.is_primary) or not any(item.is_active for item in accounts)
            if primary:
                accounts = [_replace_flags(item, primary=False) for item in accounts]
            after = StaffBankAccountFact(
                0,
                str(command.bank_code),
                str(command.branch_code),
                str(command.account_no),
                primary,
                True,
            )
            accounts.append(after)
        elif command.operation == "replace":
            assert target is not None
            primary = target.is_primary if command.is_primary is None else command.is_primary
            if primary:
                accounts = [_replace_flags(item, primary=False) for item in accounts]
            after = StaffBankAccountFact(
                target.account_id,
                str(command.bank_code),
                str(command.branch_code),
                str(command.account_no),
                bool(primary),
                True,
            )
            accounts = [after if item.account_id == target.account_id else item for item in accounts]
        elif command.operation == "set_primary":
            assert target is not None
            if not target.is_active:
                raise StaffBankAccountConflict("staff_bank_inactive_cannot_be_primary")
            accounts = [_replace_flags(item, primary=item.account_id == target.account_id) for item in accounts]
            after = next(item for item in accounts if item.account_id == target.account_id)
        else:
            assert target is not None
            if not target.is_active:
                raise StaffBankAccountConflict("staff_bank_account_already_inactive")
            successor = None
            if command.successor_account_id is not None:
                successor = next(
                    (item for item in accounts if item.account_id == command.successor_account_id),
                    None,
                )
                if successor is None or not successor.is_active:
                    raise StaffBankAccountConflict("staff_bank_successor_invalid")
            if target.is_primary and successor is None:
                raise StaffBankAccountConflict("staff_bank_primary_successor_required")
            accounts = [
                _replace_flags(
                    item,
                    primary=(successor is not None and item.account_id == successor.account_id),
                    active=False if item.account_id == target.account_id else None,
                )
                for item in accounts
            ]
            after = next(item for item in accounts if item.account_id == target.account_id)
        _require_single_active_primary(accounts)
        return StaffBankAccountSnapshot(snapshot.staff_id, snapshot.version + 1, tuple(accounts)), before, after

    @staticmethod
    def _require(row: Mapping[str, Any] | None) -> Mapping[str, Any]:
        if row is None:
            raise StaffBankAccountNotFound("staff_not_found")
        return row


def _snapshot(row: Mapping[str, Any]) -> StaffBankAccountSnapshot:
    accounts = tuple(
        StaffBankAccountFact(
            int(item["id"]),
            str(item.get("bank_code") or ""),
            str(item.get("branch_code") or ""),
            str(item.get("account_no") or ""),
            bool(item.get("is_primary")),
            bool(item.get("is_active", True)),
        )
        for item in row.get("accounts", ())
    )
    return StaffBankAccountSnapshot(
        int(row["staff_id"]), int(row.get("aggregate_version") or 0), accounts
    )


def _preview(snapshot: StaffBankAccountSnapshot, command: StaffBankAccountCommand, candidate: StaffBankAccountSnapshot, before: StaffBankAccountFact | None, after: StaffBankAccountFact | None) -> StaffBankAccountPreview:
    safe_before = _safe_account(before)
    safe_after = _safe_account(after)
    fingerprint = fingerprint_payload({
        "family": _COMMAND_FAMILY,
        "staff_id": snapshot.staff_id,
        "version": snapshot.version,
        "command": _command_payload(command),
        "candidate": [_internal_account_payload(item) for item in candidate.accounts],
    })
    return StaffBankAccountPreview(
        snapshot.staff_id,
        snapshot.version,
        command.operation,
        safe_before,
        safe_after,
        fingerprint,
    )


def _safe_account(account: StaffBankAccountFact | None) -> Mapping[str, object] | None:
    if account is None:
        return None
    return {
        "account_id": account.account_id or None,
        "bank_code": account.bank_code,
        "branch_code": account.branch_code,
        "account_last4": account_last4(account.account_no),
        "is_primary": account.is_primary,
        "is_active": account.is_active,
    }


def _internal_account_payload(account: StaffBankAccountFact) -> Mapping[str, object]:
    return {
        "account_id": account.account_id,
        "bank_code": account.bank_code,
        "branch_code": account.branch_code,
        "account_no": account.account_no,
        "is_primary": account.is_primary,
        "is_active": account.is_active,
    }


def _command_payload(command: StaffBankAccountCommand) -> Mapping[str, object]:
    return {
        "operation": command.operation,
        "account_id": command.account_id,
        "bank_code": command.bank_code,
        "branch_code": command.branch_code,
        "account_no": command.account_no,
        "is_primary": command.is_primary,
        "successor_account_id": command.successor_account_id,
    }


def _replace_flags(account: StaffBankAccountFact, *, primary: bool | None = None, active: bool | None = None) -> StaffBankAccountFact:
    return StaffBankAccountFact(
        account.account_id,
        account.bank_code,
        account.branch_code,
        account.account_no,
        account.is_primary if primary is None else primary,
        account.is_active if active is None else active,
    )


def _require_single_active_primary(accounts: list[StaffBankAccountFact]) -> None:
    active = [item for item in accounts if item.is_active]
    if not active:
        raise StaffBankAccountConflict("staff_bank_active_account_required")
    if sum(1 for item in active if item.is_primary) != 1:
        raise StaffBankAccountConflict("staff_bank_single_primary_required")
    if any(item.is_primary and not item.is_active for item in accounts):
        raise StaffBankAccountConflict("staff_bank_inactive_primary_invalid")


def _receipt(result: Mapping[str, Any], preview: PreviewFingerprint, key: IdempotencyKey, replayed: bool, readback: StaffBankAccountSnapshot) -> StaffBankAccountReceipt:
    return StaffBankAccountReceipt(
        int(result["staff_id"]),
        int(result["account_id"]),
        str(result["operation"]),
        int(result["resulting_version"]),
        preview,
        key,
        replayed,
        readback,
    )


def _staff_id(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("staff_id_invalid")
    return value


__all__ = [
    "StaffBankAccountConflict",
    "StaffBankAccountFact",
    "StaffBankAccountNotFound",
    "StaffBankAccountPreview",
    "StaffBankAccountReceipt",
    "StaffBankAccountSnapshot",
    "StaffBankAccountWorkflow",
]
