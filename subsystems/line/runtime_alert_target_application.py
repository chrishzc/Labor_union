"""
File: runtime_alert_target_application.py
Description: 協調 runtime alert target 的 typed query、CAS mutation、鎖、receipt 與 audit。
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Callable

from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.identities import CorrelationId, IdempotencyKey
from subsystems.line.runtime_alert_target_contracts import (
    AddLineAlertAdminTargetCommand,
    AlertAdminCandidateView,
    AlertTargetView,
    LineAlertTargetMutationReceipt,
    LineAlertTargetMutationPreview,
    ResetLineAlertGroupCommand,
    RuntimeAlertTargetError,
    SetLineAlertTargetEnabledCommand,
    command_fingerprint,
)


_LOCK_TIMEOUT_SECONDS = 5
_COMMAND_FAMILY = "line_alert_target"


class RuntimeAlertTargetApplication:
    def __init__(self, unit_of_work_factory: Callable[[], object], now: Callable[[], datetime]):
        self._unit_of_work_factory = unit_of_work_factory
        self._now = now

    def list_targets(self) -> tuple[AlertTargetView, ...]:
        with self._unit_of_work_factory() as unit_of_work:
            rows = unit_of_work.runtime_monitor.list_alert_targets()
            return tuple(_target_view(row) for row in rows)

    def list_admin_candidates(self) -> tuple[AlertAdminCandidateView, ...]:
        with self._unit_of_work_factory() as unit_of_work:
            rows = unit_of_work.runtime_monitor.list_admin_alert_candidates()
            return tuple(_candidate_view(row) for row in rows)

    def reset(self, command: ResetLineAlertGroupCommand) -> LineAlertTargetMutationReceipt:
        return self._apply(command, operation="group_reset")

    def set_enabled(self, command: SetLineAlertTargetEnabledCommand) -> LineAlertTargetMutationReceipt:
        return self._apply(command, operation="enable" if command.enabled else "disable")

    def add_admin_target(self, command: AddLineAlertAdminTargetCommand) -> LineAlertTargetMutationReceipt:
        return self._apply(command, operation="admin_target_add")

    def preview(self, command) -> LineAlertTargetMutationPreview:
        operation = _operation(command)
        with self._unit_of_work_factory() as unit_of_work:
            snapshot = _preview_snapshot(
                unit_of_work.runtime_monitor,
                command,
                operation,
                for_update=False,
            )
            fingerprint = _preview_fingerprint(command, snapshot)
            return LineAlertTargetMutationPreview(
                operation=operation,
                target_id=snapshot["target_id"],
                previous_state=snapshot["previous_state"],
                resulting_state=snapshot["resulting_state"],
                current_version=snapshot["current_version"],
                preview_fingerprint=fingerprint,
                apply_ready=True,
            )

    def register_group(
        self,
        unit_of_work: object,
        group_id: str,
        actor_id: str,
        event_id: str,
    ) -> bool:
        """在既有 worker UoW 內註冊，不自行 commit；禁止 disabled row 靜默復活。"""
        key = IdempotencyKey(f"line-alert-registration:{event_id}")
        correlation = CorrelationId(f"line-event:{event_id}")
        fingerprint = fingerprint_payload(
            {"operation": "group_registration", "event_id": event_id, "actor_id": actor_id,
             "group_identity_digest": hashlib.sha256(group_id.encode("utf-8")).hexdigest()}
        )
        repo = unit_of_work.runtime_monitor
        existing = repo.load_admin_command_receipt(_COMMAND_FAMILY, key.value, for_update=False)
        if existing is not None:
            _check_receipt(existing, fingerprint.value)
            return bool(_receipt_result(existing).get("created", False))
        _acquire(repo)
        unit_of_work.add_after_completion(lambda: _release(repo))
        existing = repo.load_admin_command_receipt(_COMMAND_FAMILY, key.value, for_update=True)
        if existing is not None:
            _check_receipt(existing, fingerprint.value)
            return bool(_receipt_result(existing).get("created", False))
        active = repo.find_active_group_targets(for_update=True)
        if active:
            if any(str(row.get("group_id")) == group_id for row in active):
                current = _target_view(next(row for row in active if str(row.get("group_id")) == group_id))
                result = _registration_result(current, False, key.value, correlation.value, self._now())
                repo.save_admin_command_receipt(
                    _COMMAND_FAMILY, key.value, fingerprint.value, actor_id,
                    "LINE 群組告警註冊重播", result,
                )
                _save_registration_audit(repo, actor_id, current, result, "LINE 群組告警註冊重播")
                return False
            raise RuntimeAlertTargetError(
                "conflict", "line_alert_group_already_active", "已有其他 LINE 告警群組啟用"
            )
        historical = repo.find_group_target(group_id, for_update=True)
        if historical is not None:
            raise RuntimeAlertTargetError(
                "conflict", "line_alert_target_registration_conflict", "既有停用群組不可由 webhook 靜默重新啟用"
            )
        target_id = repo.insert_group_target(group_id, "LINE 工會異常通知群組", actor_id)
        current = _target_view(repo.get_alert_target(target_id, for_update=True))
        result = _registration_result(current, True, key.value, correlation.value, self._now())
        repo.save_admin_command_receipt(
            _COMMAND_FAMILY, key.value, fingerprint.value, actor_id,
            "LINE 群組告警註冊", result,
        )
        _save_registration_audit(repo, actor_id, current, result, "LINE 群組告警註冊")
        return True

    def _apply(self, command, *, operation: str) -> LineAlertTargetMutationReceipt:
        fingerprint = command_fingerprint(command)
        with self._unit_of_work_factory() as reader:
            existing = reader.runtime_monitor.load_admin_command_receipt(
                _COMMAND_FAMILY, command.idempotency_key.value, for_update=False
            )
        if existing is not None:
            _check_receipt(existing, fingerprint.value)
            return _receipt_from_snapshot(_receipt_result(existing), replayed=True)
        unit_of_work = self._unit_of_work_factory()
        unit_of_work.__enter__()
        repo = unit_of_work.runtime_monitor
        committed = False
        failure = None
        result = None
        held = False
        try:
            _acquire(repo)
            held = True
            result = self._mutate_locked(unit_of_work, repo, command, operation, fingerprint.value)
            unit_of_work.commit()
            committed = True
        except Exception as error:
            failure = error
        release_failure = None
        if held:
            try:
                _release(repo)
            except Exception as error:
                release_failure = error
        try:
            if committed:
                unit_of_work.__exit__(None, None, None)
            else:
                error = failure or release_failure
                unit_of_work.__exit__(type(error), error, error.__traceback__)
        except Exception as error:
            if committed:
                release_failure = release_failure or error
            else:
                failure = failure or error
        if committed and release_failure:
            raise RuntimeAlertTargetError(
                "unavailable", "line_alert_target_commit_outcome_unknown",
                "runtime alert target commit outcome requires receipt query", retryable=True,
            ) from release_failure
        if failure:
            if isinstance(failure, RuntimeAlertTargetError):
                raise failure
            raise RuntimeAlertTargetError(
                "unavailable", "line_alert_target_persistence_unavailable",
                "runtime alert target persistence unavailable", retryable=True,
            ) from failure
        if release_failure:
            raise release_failure
        return result

    def _mutate_locked(self, unit_of_work, repo, command, operation, fingerprint):
        existing = repo.load_admin_command_receipt(
            _COMMAND_FAMILY, command.idempotency_key.value, for_update=True
        )
        if existing is not None:
            _check_receipt(existing, fingerprint)
            return _receipt_from_snapshot(_receipt_result(existing), replayed=True)
        try:
                if command.preview_fingerprint is not None:
                    preview_snapshot = _preview_snapshot(
                        repo,
                        command,
                        operation,
                        for_update=True,
                    )
                    current_preview = _preview_fingerprint(command, preview_snapshot)
                    if current_preview != command.preview_fingerprint:
                        raise RuntimeAlertTargetError(
                            "conflict",
                            "line_alert_target_preview_conflict",
                            "LINE 告警對象 Preview 已過期，請重新查詢並預覽",
                        )
                if isinstance(command, ResetLineAlertGroupCommand):
                    target = _reset_target(repo, command.expected_version)
                    enabled = False
                elif isinstance(command, SetLineAlertTargetEnabledCommand):
                    target = repo.get_alert_target(command.target_id, for_update=True)
                    if target is None:
                        _raise_not_found()
                    _check_version(target, command.expected_version)
                    enabled = command.enabled
                    _ensure_singleton(repo, target, enabled)
                else:
                    target = repo.get_admin_target(command.admin_user_id, for_update=True)
                    enabled = True
                    if target is None:
                        target_id = repo.insert_admin_target(
                            command.admin_user_id, command.minimum_status, command.actor.actor_id
                        )
                        target = repo.get_alert_target(target_id, for_update=True)
                    else:
                        target_id = int(target["id"])
                        repo.update_admin_target(target_id, command.minimum_status)
                        target = repo.get_alert_target(target_id, for_update=True)
                previous_state = _state(target)
                if not isinstance(command, AddLineAlertAdminTargetCommand):
                    repo.update_alert_target_enabled(int(target["id"]), enabled)
                target = repo.get_alert_target(int(target["id"]), for_update=True)
                result = _build_receipt(target, previous_state, operation, command.correlation_id.value, self._now())
                repo.save_admin_command_receipt(
                    _COMMAND_FAMILY, command.idempotency_key.value, fingerprint,
                    command.actor.actor_id, command.reason, _receipt_payload(result),
                )
                repo.save_alert_target_admin_audit(
                    command.actor.actor_id, _audit_action(operation), result.target_id,
                    {"receipt_id": result.receipt_id, "reason": command.reason,
                     "expected_version": getattr(command, "expected_version", "not_applicable"),
                     "resulting_version": result.current_version,
                     "previous_state": result.previous_state,
                     "resulting_state": result.resulting_state,
                     "correlation_id": result.correlation_id},
                )
                return result
        except RuntimeAlertTargetError:
            raise
        except LookupError as error:
            raise RuntimeAlertTargetError(
                "validation", "line_alert_admin_not_linked",
                "工會人員尚未綁定 LINE，不能設為通知對象",
            ) from error


def _operation(command) -> str:
    if isinstance(command, ResetLineAlertGroupCommand):
        return "group_reset"
    if isinstance(command, SetLineAlertTargetEnabledCommand):
        return "enable" if command.enabled else "disable"
    if isinstance(command, AddLineAlertAdminTargetCommand):
        return "admin_target_add"
    raise TypeError("unsupported runtime alert target command")


def _preview_snapshot(repo, command, operation: str, *, for_update: bool) -> dict:
    if isinstance(command, ResetLineAlertGroupCommand):
        targets = repo.find_active_group_targets(for_update=for_update)
        if not targets:
            _raise_not_found()
        if len(targets) != 1:
            raise RuntimeAlertTargetError(
                "conflict",
                "line_alert_group_singleton_violation",
                "active LINE 告警群組狀態需人工復原",
            )
        target = targets[0]
        _check_version(target, command.expected_version)
        view = _target_view(target)
        return _preview_values(view.target_id, view.state, "disabled", view.current_version, operation)
    if isinstance(command, SetLineAlertTargetEnabledCommand):
        target = repo.get_alert_target(command.target_id, for_update=for_update)
        if target is None:
            _raise_not_found()
        _check_version(target, command.expected_version)
        _ensure_singleton(repo, target, command.enabled)
        view = _target_view(target)
        return _preview_values(
            view.target_id,
            view.state,
            "active" if command.enabled else "disabled",
            view.current_version,
            operation,
        )
    candidates = tuple(repo.list_admin_alert_candidates())
    candidate = next(
        (
            row
            for row in candidates
            if int(row.get("id", row.get("candidate_id", 0))) == command.admin_user_id
        ),
        None,
    )
    if candidate is None or not bool(candidate.get("line_linked")):
        raise RuntimeAlertTargetError(
            "validation",
            "line_alert_admin_not_linked",
            "工會人員尚未綁定 LINE，不能設為通知對象",
        )
    target = repo.get_admin_target(command.admin_user_id, for_update=for_update)
    if target is None:
        return _preview_values(None, "absent", "active", "absent", operation)
    view = _target_view(target)
    return _preview_values(view.target_id, view.state, "active", view.current_version, operation)


def _preview_values(target_id, previous_state, resulting_state, current_version, operation):
    return {
        "operation": operation,
        "target_id": target_id,
        "previous_state": previous_state,
        "resulting_state": resulting_state,
        "current_version": current_version,
    }


def _preview_fingerprint(command, snapshot: dict) -> PreviewFingerprint:
    return fingerprint_payload(
        {
            "command_fingerprint": command_fingerprint(command).value,
            "candidate": snapshot,
        }
    )


def _acquire(repo) -> None:
    try:
        if repo.acquire_alert_target_lock(_LOCK_TIMEOUT_SECONDS) is not True:
            raise RuntimeAlertTargetError(
                "unavailable", "line_alert_target_serialization_unavailable",
                "runtime alert target serialization unavailable", retryable=True,
            )
    except RuntimeAlertTargetError:
        raise
    except Exception as error:
        raise RuntimeAlertTargetError(
            "unavailable", "line_alert_target_serialization_unavailable",
            "runtime alert target serialization unavailable", retryable=True,
        ) from error


def _release(repo) -> None:
    try:
        if repo.release_alert_target_lock() is not True:
            raise RuntimeAlertTargetError(
                "unavailable", "line_alert_target_commit_outcome_unknown",
                "runtime alert target commit outcome requires receipt query", retryable=True,
            )
    except RuntimeAlertTargetError:
        raise
    except Exception as error:
        raise RuntimeAlertTargetError(
            "unavailable", "line_alert_target_commit_outcome_unknown",
            "runtime alert target commit outcome requires receipt query", retryable=True,
        ) from error


def _reset_target(repo, expected_version):
    active = repo.find_active_group_targets(for_update=True)
    if not active:
        _raise_not_found()
    if len(active) != 1:
        raise RuntimeAlertTargetError(
            "conflict", "line_alert_group_singleton_violation", "active LINE 告警群組狀態需人工復原"
        )
    target = active[0]
    _check_version(target, expected_version)
    return target


def _ensure_singleton(repo, target, enabled):
    if not enabled or target["target_type"] != "group":
        return
    active = repo.find_active_group_targets(for_update=True)
    if any(int(row["id"]) != int(target["id"]) for row in active):
        raise RuntimeAlertTargetError(
            "conflict", "line_alert_group_already_active", "已有其他 LINE 告警群組啟用"
        )


def _target_view(row) -> AlertTargetView:
    try:
        return _target_view_unchecked(row)
    except RuntimeAlertTargetError:
        raise
    except (AttributeError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise _persistence_corrupt() from error


def _target_view_unchecked(row) -> AlertTargetView:
    updated = row.get("updated_at_utc")
    if not isinstance(updated, datetime):
        raise RuntimeAlertTargetError(
            "unavailable", "line_alert_target_version_unavailable",
            "runtime alert target version unavailable", retryable=False,
        )
    if updated.tzinfo is None or updated.utcoffset() is None:
        updated = updated.replace(tzinfo=timezone.utc)
    elif updated.utcoffset() != timezone.utc.utcoffset(updated):
        raise RuntimeAlertTargetError(
            "unavailable", "line_alert_target_persistence_corrupt",
            "runtime alert target persistence is corrupt", retryable=False,
        )
    target_id = int(row["id"])
    target_type = str(row["target_type"])
    state = "active" if bool(row["enabled"]) else "disabled"
    version = fingerprint_payload({
        "target_id": target_id,
        "target_kind": target_type,
        "state": state,
        "minimum_status": str(row["minimum_status"]),
        "updated_at": updated.astimezone(timezone.utc).isoformat(),
    }).value
    return AlertTargetView(
        target_id, target_type, f"LINE 告警對象 #{target_id}", state,
        str(row["minimum_status"]), version, updated.astimezone(timezone.utc),
    )


def _candidate_view(row) -> AlertAdminCandidateView:
    try:
        return AlertAdminCandidateView(
            int(row["id"]), f"LINE 管理員告警對象 #{int(row['id'])}", bool(row.get("line_linked", False))
        )
    except (AttributeError, KeyError, TypeError, ValueError) as error:
        raise _persistence_corrupt() from error


def _check_version(row, expected_version):
    current = _target_view(row).current_version
    if current != expected_version:
        raise RuntimeAlertTargetError(
            "conflict", "line_alert_target_version_conflict", "runtime alert target version is stale"
        )


def _state(row):
    try:
        return "active" if bool(row["enabled"]) else "disabled"
    except (KeyError, TypeError, ValueError) as error:
        raise _persistence_corrupt() from error


def _build_receipt(row, previous_state, operation, correlation_id, committed_at):
    view = _target_view(row)
    return LineAlertTargetMutationReceipt(
        _receipt_id(operation, correlation_id), _COMMAND_FAMILY, operation,
        view.target_id, previous_state, view.state, view.current_version,
        False, correlation_id, committed_at.astimezone(timezone.utc),
    )


def _registration_result(view, created, idempotency_key, correlation_id, committed_at):
    return {
        "receipt_id": _receipt_id("group_registration", idempotency_key),
        "command_family": _COMMAND_FAMILY,
        "operation": "group_registration",
        "created": created,
        "target_id": view.target_id,
        "previous_state": "disabled",
        "resulting_state": "active",
        "current_version": view.current_version,
        "correlation_id": correlation_id,
        "committed_at": committed_at.astimezone(timezone.utc).isoformat(),
    }


def _save_registration_audit(repo, actor_id, current, result, reason):
    repo.save_alert_target_admin_audit(actor_id, "line.alert_target.register", current.target_id, {
        "receipt_id": result["receipt_id"],
        "reason": reason,
        "expected_version": "absent",
        "resulting_version": current.current_version,
        "previous_state": "absent",
        "resulting_state": "active",
        "correlation_id": result["correlation_id"],
    })


def _receipt_id(operation, correlation_id):
    digest = hashlib.sha256(f"{_COMMAND_FAMILY}:{operation}:{correlation_id}".encode()).hexdigest()[:32]
    return f"receipt:{digest}"


def _receipt_payload(receipt):
    return {
        "receipt_id": receipt.receipt_id,
        "command_family": receipt.command_family,
        "operation": receipt.operation,
        "target_id": receipt.target_id,
        "previous_state": receipt.previous_state,
        "resulting_state": receipt.resulting_state,
        "current_version": receipt.current_version,
        "replayed": False,
        "correlation_id": receipt.correlation_id,
        "committed_at": receipt.committed_at.isoformat(),
    }


def _receipt_result(row):
    try:
        value = row.get("result_snapshot") if hasattr(row, "get") else None
        if isinstance(value, str):
            value = json.loads(value)
        if not isinstance(value, dict):
            raise ValueError("receipt snapshot must be an object")
        return value
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        raise _persistence_corrupt() from error


def _receipt_from_snapshot(value, *, replayed):
    try:
        if value["command_family"] != _COMMAND_FAMILY:
            raise ValueError("receipt command family is invalid")
        if value["operation"] not in {"group_reset", "enable", "disable", "admin_target_add"}:
            raise ValueError("receipt operation is invalid")
        return LineAlertTargetMutationReceipt(
            str(value["receipt_id"]), str(value["command_family"]), str(value["operation"]),
            int(value["target_id"]), str(value["previous_state"]), str(value["resulting_state"]),
            str(value["current_version"]), replayed, str(value["correlation_id"]),
            datetime.fromisoformat(str(value["committed_at"])),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise _persistence_corrupt() from error


def _persistence_corrupt():
    return RuntimeAlertTargetError(
        "unavailable", "line_alert_target_persistence_corrupt",
        "runtime alert target persistence is corrupt", retryable=False,
    )


def _check_receipt(row, fingerprint):
    try:
        stored_value = row["request_fingerprint"]
    except (KeyError, TypeError) as error:
        raise _persistence_corrupt() from error
    stored = str(stored_value)
    if stored != fingerprint:
        raise RuntimeAlertTargetError(
            "idempotency_mismatch", "line_alert_target_idempotency_mismatch",
            "idempotency key payload mismatch"
        )


def _raise_not_found():
    raise RuntimeAlertTargetError(
        "not_found", "line_alert_target_not_found", "找不到目前啟用的 LINE 告警對象"
    )


def _audit_action(operation):
    return {
        "group_reset": "line.alert_target.group_reset",
        "enable": "line.alert_target.enable",
        "disable": "line.alert_target.disable",
        "admin_target_add": "line.alert_target.enable",
    }[operation]


__all__ = ["RuntimeAlertTargetApplication"]
