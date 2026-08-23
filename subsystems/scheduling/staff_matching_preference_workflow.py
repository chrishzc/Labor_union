"""
File: staff_matching_preference_workflow.py
Description: 編排 Staff matching preference 的 aggregate lock、Preview、Apply 與冪等交易。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping, Protocol

from domains.scheduling.staff_matching_preferences import (
    PreferenceValue,
    StaffPreferenceDefinition,
    parse_preference_value,
)
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey


class StaffMatchingPreferenceRepository(Protocol):
    def list_definitions(self, *, active_only: bool) -> tuple[tuple[StaffPreferenceDefinition, int], ...]: ...
    def load_definition(self, preference_key: str, *, for_update: bool) -> tuple[StaffPreferenceDefinition, int] | None: ...
    def staff_exists(self, staff_id: int) -> bool: ...
    def lock_profile_aggregate(self, staff_id: int) -> None: ...
    def load_profile(self, staff_id: int, *, for_update: bool) -> tuple[int, Mapping[str, Mapping[str, Any]]]: ...
    def find_receipt(self, key: IdempotencyKey, *, for_update: bool) -> Mapping[str, Any] | None: ...
    def save_definition(self, definition: StaffPreferenceDefinition, version: int, actor: str) -> None: ...
    def save_profile(self, staff_id: int, values: Mapping[str, PreferenceValue], version: int, actor: str) -> None: ...
    def append_event(self, event: "PreferenceEvent") -> int: ...
    def save_receipt(self, receipt: "PreferenceReceipt") -> None: ...


@dataclass(frozen=True, slots=True)
class DefinitionPreview:
    before: StaffPreferenceDefinition | None
    after: StaffPreferenceDefinition
    version: int
    fingerprint: PreviewFingerprint


@dataclass(frozen=True, slots=True)
class ProfilePreview:
    staff_id: int
    before: Mapping[str, Mapping[str, Any]]
    after: Mapping[str, Mapping[str, Any]]
    version: int
    fingerprint: PreviewFingerprint


@dataclass(frozen=True, slots=True)
class PreferenceApplyRequest:
    expected_version: ExpectedVersion
    preview_fingerprint: PreviewFingerprint
    idempotency_key: IdempotencyKey
    actor: ActorContext
    reason: str
    correlation_id: CorrelationId


@dataclass(frozen=True, slots=True)
class PreferenceEvent:
    event_type: str
    aggregate_identity: str
    resulting_version: int
    actor: str
    reason: str
    correlation_id: str
    idempotency_key: str
    before: Mapping[str, Any]
    after: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class PreferenceReceipt:
    key: IdempotencyKey
    command_family: str
    aggregate_identity: str
    command_fingerprint: PreviewFingerprint
    preview_fingerprint: PreviewFingerprint
    result: Mapping[str, Any]


class StaffMatchingPreferenceWorkflow:
    def __init__(self, repository: StaffMatchingPreferenceRepository, unit_of_work_factory: Callable[[], Any]) -> None:
        self._repository = repository
        self._unit_of_work_factory = unit_of_work_factory

    def query_definitions(self, *, active_only: bool = True):
        return self._repository.list_definitions(active_only=active_only)

    def preview_definition(self, definition: StaffPreferenceDefinition) -> DefinitionPreview:
        current = self._repository.load_definition(definition.preference_key, for_update=False)
        before, version = current if current is not None else (None, 0)
        payload = _definition_preview_payload(before, definition, version)
        return DefinitionPreview(before, definition, version, fingerprint_payload(payload))

    def apply_definition(self, definition: StaffPreferenceDefinition, request: PreferenceApplyRequest):
        family = "staff_preference_definition/v1"
        identity = definition.preference_key
        command_fingerprint = _command_fingerprint(family, identity, definition.canonical_payload(), request)
        with self._unit_of_work_factory() as unit_of_work:
            replay = _replay(self._repository, request, command_fingerprint)
            if replay is not None:
                unit_of_work.commit()
                return replay
            preview = self._fresh_definition_preview(definition, request)
            result = self._persist_definition(preview, request, command_fingerprint)
            unit_of_work.commit()
            return result

    def query_profile(self, staff_id: int) -> ProfilePreview:
        _require_staff(self._repository, staff_id)
        version, raw_values = self._repository.load_profile(staff_id, for_update=False)
        return _profile_preview(
            self._repository,
            staff_id,
            raw_values,
            raw_values,
            version,
            require_active=False,
        )

    def preview_profile(self, staff_id: int, proposed: Mapping[str, Mapping[str, Any]]) -> ProfilePreview:
        _require_staff(self._repository, staff_id)
        version, before = self._repository.load_profile(staff_id, for_update=False)
        return _profile_preview(
            self._repository,
            staff_id,
            before,
            proposed,
            version,
            require_active=True,
        )

    def apply_profile(self, staff_id: int, proposed: Mapping[str, Mapping[str, Any]], request: PreferenceApplyRequest):
        family, identity = "staff_matching_profile/v1", str(staff_id)
        command_fingerprint = _command_fingerprint(family, identity, proposed, request)
        with self._unit_of_work_factory() as unit_of_work:
            _lock_profile_aggregate(self._repository, staff_id)
            replay = _replay(self._repository, request, command_fingerprint)
            if replay is not None:
                unit_of_work.commit()
                return replay
            preview, values = self._fresh_profile_preview(staff_id, proposed, request)
            result = self._persist_profile(preview, values, request, command_fingerprint)
            unit_of_work.commit()
            return result

    def _fresh_definition_preview(self, definition, request):
        current = self._repository.load_definition(definition.preference_key, for_update=True)
        before, version = current if current is not None else (None, 0)
        _require_version(version, request.expected_version)
        _require_definition_semantics_unchanged(before, definition)
        preview = DefinitionPreview(before, definition, version, fingerprint_payload(_definition_preview_payload(before, definition, version)))
        _require_preview(preview.fingerprint, request.preview_fingerprint)
        return preview

    def _fresh_profile_preview(self, staff_id, proposed, request):
        _require_staff(self._repository, staff_id)
        version, before = self._repository.load_profile(staff_id, for_update=True)
        _require_version(version, request.expected_version)
        values = _parse_profile_values(
            self._repository,
            proposed,
            require_active=True,
            lock_definitions=True,
        )
        preview = _profile_preview_from_values(staff_id, before, values, version)
        _require_preview(preview.fingerprint, request.preview_fingerprint)
        return preview, values

    def _persist_definition(self, preview, request, command_fingerprint):
        version = preview.version + 1
        self._repository.save_definition(preview.after, version, request.actor.actor_id)
        result = {
            "preference_key": preview.after.preference_key,
            "version": version,
            "preview_fingerprint": request.preview_fingerprint.value,
            "idempotency_key": request.idempotency_key.value,
        }
        self._save_event_and_receipt("definition_changed", preview.after.preference_key, version, preview.before.canonical_payload() if preview.before else {}, preview.after.canonical_payload(), result, request, command_fingerprint)
        return result

    def _persist_profile(self, preview, values, request, command_fingerprint):
        version = preview.version + 1
        self._repository.save_profile(preview.staff_id, values, version, request.actor.actor_id)
        result = {
            "staff_id": preview.staff_id,
            "version": version,
            "values": preview.after,
            "preview_fingerprint": request.preview_fingerprint.value,
            "idempotency_key": request.idempotency_key.value,
        }
        self._save_event_and_receipt("profile_changed", str(preview.staff_id), version, preview.before, preview.after, result, request, command_fingerprint)
        return result

    def _save_event_and_receipt(self, event_type, identity, version, before, after, result, request, command_fingerprint):
        self._repository.append_event(PreferenceEvent(event_type, identity, version, request.actor.actor_id, request.reason, request.correlation_id.value, request.idempotency_key.value, before, after))
        family = "staff_preference_definition/v1" if event_type == "definition_changed" else "staff_matching_profile/v1"
        self._repository.save_receipt(PreferenceReceipt(request.idempotency_key, family, identity, command_fingerprint, request.preview_fingerprint, result))


def _profile_preview(
    repository,
    staff_id,
    before,
    proposed,
    version,
    *,
    require_active,
    lock_definitions=False,
):
    values = _parse_profile_values(
        repository,
        proposed,
        require_active=require_active,
        lock_definitions=lock_definitions,
    )
    return _profile_preview_from_values(staff_id, before, values, version)


def _profile_preview_from_values(staff_id, before, values, version):
    after = {key: value.canonical_payload() for key, value in sorted(values.items())}
    payload = {"after": after, "before": dict(before), "staff_id": staff_id, "version": version}
    return ProfilePreview(staff_id, dict(before), after, version, fingerprint_payload(payload))


def _parse_profile_values(
    repository,
    proposed,
    *,
    require_active,
    lock_definitions=False,
):
    parsed: dict[str, PreferenceValue] = {}
    for key, payload in proposed.items():
        loaded = repository.load_definition(key, for_update=lock_definitions)
        if loaded is None or (require_active and not loaded[0].active):
            raise ValueError("preference_definition_not_active")
        parsed[key] = parse_preference_value(loaded[0], payload)
    return parsed


def _definition_preview_payload(before, after, version):
    return {"after": after.canonical_payload(), "before": before.canonical_payload() if before else {}, "version": version}


def _command_fingerprint(family, identity, payload, request):
    return fingerprint_payload(
        {
            "actor": request.actor.actor_id,
            "aggregate_identity": identity,
            "command_family": family,
            "payload": dict(payload),
            "reason": request.reason,
            "expected_version": request.expected_version.value,
            "preview_fingerprint": request.preview_fingerprint.value,
        }
    )


def _lock_profile_aggregate(repository, staff_id: int) -> None:
    """Lock the stable staff identity before profile/receipt reads."""
    repository.lock_profile_aggregate(staff_id)


def _replay(repository, request, command_fingerprint):
    receipt = repository.find_receipt(request.idempotency_key, for_update=True)
    if receipt is None:
        return None
    if str(receipt["command_fingerprint"]) != command_fingerprint.value:
        raise ValueError("idempotency_conflict")
    return dict(receipt["result"])


def _require_staff(repository, staff_id):
    if isinstance(staff_id, bool) or not isinstance(staff_id, int) or staff_id <= 0:
        raise ValueError("staff_id_invalid")
    if not repository.staff_exists(staff_id):
        raise ValueError("staff_not_found")


def _require_version(current, expected):
    if current != expected.value:
        raise ValueError("stale_version")


def _require_preview(current, expected):
    if current != expected:
        raise ValueError("stale_preview")


def _require_definition_semantics_unchanged(before, after):
    if before is None:
        return
    immutable = (before.value_kind, before.order_fact_key, before.comparison_operator)
    proposed = (after.value_kind, after.order_fact_key, after.comparison_operator)
    if immutable != proposed:
        raise ValueError("preference_semantics_immutable")
