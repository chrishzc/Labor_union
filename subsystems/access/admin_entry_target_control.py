"""
File: admin_entry_target_control.py
Description: 管理已核准管理端入口的檔案式 target、單筆 CAS、重播與 artifact 健康門禁。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from hashlib import sha256
import json
import re
from typing import Literal, Protocol, TypeVar


Target = Literal["streamlit", "react"]
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
ENTRY_ID_PATTERN = re.compile(r"^ui-react:#[a-z0-9-]+$")
IDENTITY_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,190}$")
REASON_CODES = frozenset({"activate_react", "rollback", "rehearsal", "incident_recovery"})
REGISTRY_REVISION = "phase5a-mapped-entries-v2-system-status"

FROZEN_ENTRY_TARGETS: dict[str, tuple[str, str, str]] = {
    "ui-react:#account-management": ("access", "/?entry=access-management", "/admin/#account-management"),
    "ui-react:#anomalies": ("anomalies", "/?entry=anomalies", "/admin/#anomalies"),
    "ui-react:#data-browser": ("data-browser", "/?entry=data-browser", "/admin/#data-browser"),
    "ui-react:#data-import": ("data-import", "/?entry=data-import", "/admin/#data-import"),
    "ui-react:#finance": ("finance", "/?entry=finance", "/admin/#finance"),
    "ui-react:#line-management": ("line", "/?entry=line-management", "/admin/#line-management"),
    "ui-react:#order-tracker": (
        "order-workbench",
        "/?entry=form-management&view=order-tracker",
        "/admin/#order-tracker",
    ),
    "ui-react:#orders": ("orders", "/?entry=orders", "/admin/#orders"),
    "ui-react:#reports": ("reports-system", "/?entry=system-status&view=reports", "/admin/#reports"),
    "ui-react:#scheduling": (
        "staff-scheduling",
        "/?entry=scheduling&view=calendar",
        "/admin/#scheduling",
    ),
    "ui-react:#staff": (
        "staff-scheduling",
        "/?entry=scheduling&view=staff-directory",
        "/admin/#staff",
    ),
    "ui-react:#system-status": ("reports-system", "/?entry=system-status", "/admin/#system-status"),
}


def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def digest_value(value: object) -> str:
    return sha256(canonical_json_bytes(value)).hexdigest()


REGISTRY_DIGEST = digest_value(
    [
        {
            "entry_id": entry_id,
            "replacement_group": values[0],
            "streamlit_target": values[1],
            "react_target": values[2],
        }
        for entry_id, values in sorted(FROZEN_ENTRY_TARGETS.items())
    ]
)


@dataclass(frozen=True, slots=True)
class ArtifactBinding:
    version: str
    digest: str
    api_compatibility_revision: str


@dataclass(frozen=True, slots=True)
class ArtifactHealth:
    healthy: bool
    version: str
    digest: str
    api_compatibility_revision: str


@dataclass(frozen=True, slots=True)
class EntryTargetRecord:
    entry_id: str
    replacement_group: str
    current_target: Target
    streamlit_target: str
    react_target: str
    required_react_artifact: ArtifactBinding | None
    entry_revision: int


@dataclass(frozen=True, slots=True)
class SwitchReceipt:
    receipt_id: str
    command_fingerprint: str
    idempotency_key: str
    entry_id: str
    before_target: Target
    resulting_target: Target
    before_state_revision: int
    resulting_state_revision: int
    before_entry_revision: int
    resulting_entry_revision: int
    artifact_version: str | None
    artifact_digest: str | None
    api_compatibility_revision: str | None
    actor_id: str
    reason_code: str
    correlation_id: str
    occurred_at: str
    previous_receipt_digest: str | None
    receipt_digest: str
    replayed: bool = False


@dataclass(frozen=True, slots=True)
class EntryTargetState:
    schema_version: int
    registry_revision: str
    registry_digest: str
    revision: int
    entries: tuple[EntryTargetRecord, ...]
    receipts: tuple[SwitchReceipt, ...]
    state_digest: str

    def entry(self, entry_id: str) -> EntryTargetRecord:
        for item in self.entries:
            if item.entry_id == entry_id:
                return item
        raise EntryTargetError("not_found", "unknown_entry", "找不到管理端入口", self.revision)


@dataclass(frozen=True, slots=True)
class SwitchCommand:
    entry_id: str
    expected_state_revision: int
    expected_entry_revision: int
    expected_current_target: Target
    desired_target: Target
    required_react_artifact: ArtifactBinding | None
    reason_code: str
    idempotency_key: str
    actor_id: str
    correlation_id: str


@dataclass(frozen=True, slots=True)
class SwitchPreview:
    entry_id: str
    current_target: Target
    desired_target: Target
    state_revision: int
    entry_revision: int
    command_fingerprint: str
    would_replay: bool


class EntryTargetError(RuntimeError):
    def __init__(self, category: str, code: str, message: str, current_revision: int | None = None):
        super().__init__(code)
        self.category = category
        self.code = code
        self.message = message
        self.current_revision = current_revision


T = TypeVar("T")


class AdminEntryTargetStorePort(Protocol):
    def read(self) -> EntryTargetState: ...

    def mutate(self, operation: Callable[[EntryTargetState], tuple[EntryTargetState, T]]) -> T: ...


class ReactArtifactHealthPort(Protocol):
    def query(self) -> ArtifactHealth: ...


class UnavailableReactArtifactHealth:
    def query(self) -> ArtifactHealth:
        raise EntryTargetError("unavailable", "react_artifact_unavailable", "React artifact 尚未可用")


class AdminEntryTargetControl:
    def __init__(
        self,
        store: AdminEntryTargetStorePort,
        artifact_health: ReactArtifactHealthPort | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._store = store
        self._artifact_health = artifact_health or UnavailableReactArtifactHealth()
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def query(self) -> EntryTargetState:
        return self._store.read()

    def resolve(self, entry_id: str) -> EntryTargetRecord:
        return self._store.read().entry(entry_id)

    def preview(self, command: SwitchCommand) -> SwitchPreview:
        state = self._store.read()
        command = validate_command(command)
        fingerprint = command_fingerprint(command)
        replay = _find_replay(state, command.idempotency_key, fingerprint)
        if replay is not None:
            return SwitchPreview(
                command.entry_id,
                replay.resulting_target,
                replay.resulting_target,
                replay.resulting_state_revision,
                replay.resulting_entry_revision,
                fingerprint,
                True,
            )
        entry = _validate_fresh_command(state, command)
        self._verify_artifact(command, state.revision)
        return SwitchPreview(
            entry.entry_id,
            entry.current_target,
            command.desired_target,
            state.revision,
            entry.entry_revision,
            fingerprint,
            False,
        )

    def apply(self, command: SwitchCommand) -> SwitchReceipt:
        command = validate_command(command)
        fingerprint = command_fingerprint(command)

        def operation(state: EntryTargetState) -> tuple[EntryTargetState, SwitchReceipt]:
            replay = _find_replay(state, command.idempotency_key, fingerprint)
            if replay is not None:
                return state, replace(replay, replayed=True)
            entry = _validate_fresh_command(state, command)
            self._verify_artifact(command, state.revision)
            next_state_revision = state.revision + 1
            next_entry_revision = entry.entry_revision + 1
            previous_digest = state.receipts[-1].receipt_digest if state.receipts else None
            occurred_at = self._clock().astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
            binding = command.required_react_artifact
            receipt_base = {
                "receipt_id": f"admin-entry-target:{next_state_revision}:{command.entry_id}",
                "command_fingerprint": fingerprint,
                "idempotency_key": command.idempotency_key,
                "entry_id": command.entry_id,
                "before_target": entry.current_target,
                "resulting_target": command.desired_target,
                "before_state_revision": state.revision,
                "resulting_state_revision": next_state_revision,
                "before_entry_revision": entry.entry_revision,
                "resulting_entry_revision": next_entry_revision,
                "artifact_version": binding.version if binding else None,
                "artifact_digest": binding.digest if binding else None,
                "api_compatibility_revision": binding.api_compatibility_revision if binding else None,
                "actor_id": command.actor_id,
                "reason_code": command.reason_code,
                "correlation_id": command.correlation_id,
                "occurred_at": occurred_at,
                "previous_receipt_digest": previous_digest,
            }
            receipt = SwitchReceipt(**receipt_base, receipt_digest=digest_value(receipt_base))
            next_entry = replace(
                entry,
                current_target=command.desired_target,
                required_react_artifact=binding,
                entry_revision=next_entry_revision,
            )
            next_entries = tuple(next_entry if item.entry_id == entry.entry_id else item for item in state.entries)
            unsigned = replace(
                state,
                revision=next_state_revision,
                entries=next_entries,
                receipts=(*state.receipts, receipt),
                state_digest="",
            )
            next_state = replace(unsigned, state_digest=calculate_state_digest(unsigned))
            return next_state, receipt

        return self._store.mutate(operation)

    def _verify_artifact(self, command: SwitchCommand, current_revision: int) -> None:
        if command.desired_target == "streamlit":
            if command.required_react_artifact is not None:
                raise EntryTargetError("validation", "artifact_not_allowed", "Streamlit target 不接受 artifact binding")
            return
        binding = command.required_react_artifact
        if binding is None:
            raise EntryTargetError("validation", "artifact_required", "React target 必須指定 artifact binding")
        health = self._artifact_health.query()
        if not health.healthy:
            raise EntryTargetError(
                "unavailable", "react_artifact_unavailable", "React artifact 尚未健康", current_revision
            )
        if (
            health.version != binding.version
            or health.digest != binding.digest
            or health.api_compatibility_revision != binding.api_compatibility_revision
        ):
            raise EntryTargetError("conflict", "react_artifact_stale", "React artifact identity 已變更", current_revision)


def validate_command(command: SwitchCommand) -> SwitchCommand:
    if command.entry_id not in FROZEN_ENTRY_TARGETS or ENTRY_ID_PATTERN.fullmatch(command.entry_id) is None:
        raise EntryTargetError("not_found", "unknown_entry", "找不到管理端入口")
    if command.expected_state_revision < 1 or command.expected_entry_revision < 1:
        raise EntryTargetError("validation", "invalid_revision", "revision 必須大於零")
    if command.expected_current_target not in {"streamlit", "react"} or command.desired_target not in {
        "streamlit",
        "react",
    }:
        raise EntryTargetError("validation", "invalid_target", "target 不符合契約")
    if command.reason_code not in REASON_CODES:
        raise EntryTargetError("validation", "invalid_reason_code", "reason code 不符合契約")
    for label, value in (
        ("idempotency_key", command.idempotency_key),
        ("actor_id", command.actor_id),
        ("correlation_id", command.correlation_id),
    ):
        if IDENTITY_PATTERN.fullmatch(value) is None:
            raise EntryTargetError("validation", f"invalid_{label}", f"{label} 不符合契約")
    if command.required_react_artifact is not None:
        _validate_artifact(command.required_react_artifact)
    return command


def command_fingerprint(command: SwitchCommand) -> str:
    return digest_value(command_to_mapping(command))


def command_to_mapping(command: SwitchCommand) -> dict[str, object]:
    return {
        "entry_id": command.entry_id,
        "expected_state_revision": command.expected_state_revision,
        "expected_entry_revision": command.expected_entry_revision,
        "expected_current_target": command.expected_current_target,
        "desired_target": command.desired_target,
        "required_react_artifact": _artifact_to_mapping(command.required_react_artifact),
        "reason_code": command.reason_code,
        "idempotency_key": command.idempotency_key,
        "actor_id": command.actor_id,
        "correlation_id": command.correlation_id,
    }


def calculate_state_digest(state: EntryTargetState) -> str:
    return digest_value(state_to_mapping(state, include_state_digest=False))


def state_to_mapping(state: EntryTargetState, *, include_state_digest: bool = True) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": state.schema_version,
        "registry_revision": state.registry_revision,
        "registry_digest": state.registry_digest,
        "revision": state.revision,
        "entries": [_entry_to_mapping(item) for item in state.entries],
        "receipts": [_receipt_to_mapping(item) for item in state.receipts],
    }
    if include_state_digest:
        payload["state_digest"] = state.state_digest
    return payload


def state_from_mapping(payload: object) -> EntryTargetState:
    root = _strict_mapping(
        payload,
        {"schema_version", "registry_revision", "registry_digest", "revision", "entries", "receipts", "state_digest"},
        "state",
    )
    entries_payload = root["entries"]
    receipts_payload = root["receipts"]
    if not isinstance(entries_payload, list) or not isinstance(receipts_payload, list):
        raise EntryTargetError("unavailable", "entry_target_state_corrupt", "Entry target state 已毀損")
    state = EntryTargetState(
        schema_version=_strict_int(root["schema_version"]),
        registry_revision=_strict_str(root["registry_revision"]),
        registry_digest=_strict_str(root["registry_digest"]),
        revision=_strict_int(root["revision"]),
        entries=tuple(_entry_from_mapping(item) for item in entries_payload),
        receipts=tuple(_receipt_from_mapping(item) for item in receipts_payload),
        state_digest=_strict_str(root["state_digest"]),
    )
    validate_state(state)
    return state


def validate_state(state: EntryTargetState) -> None:
    if state.schema_version != 1 or state.registry_revision != REGISTRY_REVISION or state.registry_digest != REGISTRY_DIGEST:
        raise EntryTargetError("unavailable", "entry_target_registry_stale", "Entry target registry revision 不相符")
    if state.revision < 1 or not SHA256_PATTERN.fullmatch(state.state_digest):
        raise EntryTargetError("unavailable", "entry_target_state_corrupt", "Entry target state 已毀損")
    if tuple(item.entry_id for item in state.entries) != tuple(sorted(FROZEN_ENTRY_TARGETS)):
        raise EntryTargetError("unavailable", "entry_target_registry_stale", "Entry target identity set 不相符")
    for item in state.entries:
        group, streamlit_target, react_target = FROZEN_ENTRY_TARGETS[item.entry_id]
        if (
            item.replacement_group != group
            or item.streamlit_target != streamlit_target
            or item.react_target != react_target
            or item.current_target not in {"streamlit", "react"}
            or item.entry_revision < 1
        ):
            raise EntryTargetError("unavailable", "entry_target_state_corrupt", "Entry target record 已毀損")
        if item.current_target == "streamlit" and item.required_react_artifact is not None:
            raise EntryTargetError("unavailable", "entry_target_state_corrupt", "Streamlit target 含有無效 artifact")
        if item.current_target == "react" and item.required_react_artifact is None:
            raise EntryTargetError("unavailable", "entry_target_state_corrupt", "React target 缺少 artifact")
        if item.required_react_artifact is not None:
            _validate_artifact(item.required_react_artifact)
    if state.revision != len(state.receipts) + 1:
        raise EntryTargetError("unavailable", "entry_target_receipt_chain_corrupt", "State revision 與 receipt chain 不相符")
    previous: str | None = None
    seen_keys: set[str] = set()
    entry_revisions = {entry_id: 1 for entry_id in FROZEN_ENTRY_TARGETS}
    entry_targets: dict[str, Target] = {entry_id: "streamlit" for entry_id in FROZEN_ENTRY_TARGETS}
    entry_artifacts: dict[str, ArtifactBinding | None] = {entry_id: None for entry_id in FROZEN_ENTRY_TARGETS}
    for index, receipt in enumerate(state.receipts, start=1):
        if receipt.replayed or receipt.previous_receipt_digest != previous or receipt.idempotency_key in seen_keys:
            raise EntryTargetError("unavailable", "entry_target_receipt_chain_corrupt", "Entry target receipt chain 已毀損")
        expected_entry_revision = entry_revisions.get(receipt.entry_id)
        if (
            expected_entry_revision is None
            or receipt.receipt_id != f"admin-entry-target:{index + 1}:{receipt.entry_id}"
            or SHA256_PATTERN.fullmatch(receipt.command_fingerprint) is None
            or SHA256_PATTERN.fullmatch(receipt.receipt_digest) is None
            or IDENTITY_PATTERN.fullmatch(receipt.idempotency_key) is None
            or IDENTITY_PATTERN.fullmatch(receipt.actor_id) is None
            or IDENTITY_PATTERN.fullmatch(receipt.correlation_id) is None
            or receipt.reason_code not in REASON_CODES
            or not _valid_utc_instant(receipt.occurred_at)
            or receipt.before_state_revision != index
            or receipt.resulting_state_revision != index + 1
            or receipt.before_entry_revision != expected_entry_revision
            or receipt.resulting_entry_revision != expected_entry_revision + 1
            or receipt.before_target != entry_targets[receipt.entry_id]
            or receipt.before_target == receipt.resulting_target
        ):
            raise EntryTargetError("unavailable", "entry_target_receipt_chain_corrupt", "Receipt revision chain 已毀損")
        if receipt.resulting_target == "react":
            if (
                receipt.artifact_version is None
                or receipt.artifact_digest is None
                or receipt.api_compatibility_revision is None
            ):
                raise EntryTargetError("unavailable", "entry_target_receipt_chain_corrupt", "React receipt 缺少 artifact")
            try:
                _validate_artifact(
                    ArtifactBinding(
                        receipt.artifact_version,
                        receipt.artifact_digest,
                        receipt.api_compatibility_revision,
                    )
                )
            except EntryTargetError as error:
                raise EntryTargetError(
                    "unavailable", "entry_target_receipt_chain_corrupt", "React receipt artifact 已毀損"
                ) from error
            resulting_artifact = ArtifactBinding(
                receipt.artifact_version,
                receipt.artifact_digest,
                receipt.api_compatibility_revision,
            )
        elif any(
            value is not None
            for value in (
                receipt.artifact_version,
                receipt.artifact_digest,
                receipt.api_compatibility_revision,
            )
        ):
            raise EntryTargetError("unavailable", "entry_target_receipt_chain_corrupt", "Streamlit receipt 含有 artifact")
        else:
            resulting_artifact = None
        unsigned = _receipt_to_mapping(receipt, include_digest=False)
        if receipt.receipt_digest != digest_value(unsigned):
            raise EntryTargetError("unavailable", "entry_target_receipt_chain_corrupt", "Entry target receipt digest 不相符")
        previous = receipt.receipt_digest
        seen_keys.add(receipt.idempotency_key)
        entry_revisions[receipt.entry_id] = expected_entry_revision + 1
        entry_targets[receipt.entry_id] = receipt.resulting_target
        entry_artifacts[receipt.entry_id] = resulting_artifact
    if any(state.entry(entry_id).entry_revision != revision for entry_id, revision in entry_revisions.items()):
        raise EntryTargetError("unavailable", "entry_target_receipt_chain_corrupt", "Entry revision 與 receipt chain 不相符")
    if any(state.entry(entry_id).current_target != target for entry_id, target in entry_targets.items()):
        raise EntryTargetError("unavailable", "entry_target_receipt_chain_corrupt", "Entry target 與 receipt chain 不相符")
    if any(
        state.entry(entry_id).required_react_artifact != artifact
        for entry_id, artifact in entry_artifacts.items()
    ):
        raise EntryTargetError("unavailable", "entry_target_receipt_chain_corrupt", "Entry artifact 與 receipt chain 不相符")
    if state.state_digest != calculate_state_digest(state):
        raise EntryTargetError("unavailable", "entry_target_state_digest_mismatch", "Entry target state digest 不相符")


def make_initial_state() -> EntryTargetState:
    entries = tuple(
        EntryTargetRecord(entry_id, values[0], "streamlit", values[1], values[2], None, 1)
        for entry_id, values in sorted(FROZEN_ENTRY_TARGETS.items())
    )
    unsigned = EntryTargetState(1, REGISTRY_REVISION, REGISTRY_DIGEST, 1, entries, (), "")
    return replace(unsigned, state_digest=calculate_state_digest(unsigned))


def _validate_fresh_command(state: EntryTargetState, command: SwitchCommand) -> EntryTargetRecord:
    entry = state.entry(command.entry_id)
    if (
        state.revision != command.expected_state_revision
        or entry.entry_revision != command.expected_entry_revision
        or entry.current_target != command.expected_current_target
    ):
        raise EntryTargetError("conflict", "entry_target_stale", "Entry target state 已變更", state.revision)
    if entry.current_target == command.desired_target:
        raise EntryTargetError("conflict", "entry_target_noop", "Entry target 已是指定狀態", state.revision)
    return entry


def _find_replay(state: EntryTargetState, idempotency_key: str, fingerprint: str) -> SwitchReceipt | None:
    for receipt in state.receipts:
        if receipt.idempotency_key != idempotency_key:
            continue
        if receipt.command_fingerprint != fingerprint:
            raise EntryTargetError("conflict", "idempotency_key_conflict", "Idempotency key 已用於其他命令", state.revision)
        return receipt
    return None


def _validate_artifact(binding: ArtifactBinding) -> None:
    if IDENTITY_PATTERN.fullmatch(binding.version) is None or IDENTITY_PATTERN.fullmatch(binding.api_compatibility_revision) is None:
        raise EntryTargetError("validation", "invalid_artifact_identity", "Artifact identity 不符合契約")
    if SHA256_PATTERN.fullmatch(binding.digest) is None:
        raise EntryTargetError("validation", "invalid_artifact_digest", "Artifact digest 不符合契約")


def _artifact_to_mapping(binding: ArtifactBinding | None) -> dict[str, str] | None:
    if binding is None:
        return None
    return {
        "version": binding.version,
        "digest": binding.digest,
        "api_compatibility_revision": binding.api_compatibility_revision,
    }


def _artifact_from_mapping(payload: object) -> ArtifactBinding | None:
    if payload is None:
        return None
    item = _strict_mapping(payload, {"version", "digest", "api_compatibility_revision"}, "artifact")
    binding = ArtifactBinding(
        _strict_str(item["version"]),
        _strict_str(item["digest"]),
        _strict_str(item["api_compatibility_revision"]),
    )
    try:
        _validate_artifact(binding)
    except EntryTargetError as error:
        raise EntryTargetError(
            "unavailable", "entry_target_state_corrupt", "Entry target artifact 已毀損"
        ) from error
    return binding


def _entry_to_mapping(item: EntryTargetRecord) -> dict[str, object]:
    return {
        "entry_id": item.entry_id,
        "replacement_group": item.replacement_group,
        "current_target": item.current_target,
        "streamlit_target": item.streamlit_target,
        "react_target": item.react_target,
        "required_react_artifact": _artifact_to_mapping(item.required_react_artifact),
        "entry_revision": item.entry_revision,
    }


def _entry_from_mapping(payload: object) -> EntryTargetRecord:
    item = _strict_mapping(
        payload,
        {
            "entry_id",
            "replacement_group",
            "current_target",
            "streamlit_target",
            "react_target",
            "required_react_artifact",
            "entry_revision",
        },
        "entry",
    )
    target = _strict_str(item["current_target"])
    if target not in {"streamlit", "react"}:
        raise EntryTargetError("unavailable", "entry_target_state_corrupt", "Entry target enum 已毀損")
    return EntryTargetRecord(
        _strict_str(item["entry_id"]),
        _strict_str(item["replacement_group"]),
        target,
        _strict_str(item["streamlit_target"]),
        _strict_str(item["react_target"]),
        _artifact_from_mapping(item["required_react_artifact"]),
        _strict_int(item["entry_revision"]),
    )


def _receipt_to_mapping(item: SwitchReceipt, *, include_digest: bool = True) -> dict[str, object]:
    payload: dict[str, object] = {
        "receipt_id": item.receipt_id,
        "command_fingerprint": item.command_fingerprint,
        "idempotency_key": item.idempotency_key,
        "entry_id": item.entry_id,
        "before_target": item.before_target,
        "resulting_target": item.resulting_target,
        "before_state_revision": item.before_state_revision,
        "resulting_state_revision": item.resulting_state_revision,
        "before_entry_revision": item.before_entry_revision,
        "resulting_entry_revision": item.resulting_entry_revision,
        "artifact_version": item.artifact_version,
        "artifact_digest": item.artifact_digest,
        "api_compatibility_revision": item.api_compatibility_revision,
        "actor_id": item.actor_id,
        "reason_code": item.reason_code,
        "correlation_id": item.correlation_id,
        "occurred_at": item.occurred_at,
        "previous_receipt_digest": item.previous_receipt_digest,
    }
    if include_digest:
        payload["receipt_digest"] = item.receipt_digest
    return payload


def _receipt_from_mapping(payload: object) -> SwitchReceipt:
    keys = {
        "receipt_id",
        "command_fingerprint",
        "idempotency_key",
        "entry_id",
        "before_target",
        "resulting_target",
        "before_state_revision",
        "resulting_state_revision",
        "before_entry_revision",
        "resulting_entry_revision",
        "artifact_version",
        "artifact_digest",
        "api_compatibility_revision",
        "actor_id",
        "reason_code",
        "correlation_id",
        "occurred_at",
        "previous_receipt_digest",
        "receipt_digest",
    }
    item = _strict_mapping(payload, keys, "receipt")
    before = _strict_str(item["before_target"])
    result = _strict_str(item["resulting_target"])
    if before not in {"streamlit", "react"} or result not in {"streamlit", "react"}:
        raise EntryTargetError("unavailable", "entry_target_receipt_chain_corrupt", "Receipt target 已毀損")
    optional = lambda key: None if item[key] is None else _strict_str(item[key])
    return SwitchReceipt(
        receipt_id=_strict_str(item["receipt_id"]),
        command_fingerprint=_strict_str(item["command_fingerprint"]),
        idempotency_key=_strict_str(item["idempotency_key"]),
        entry_id=_strict_str(item["entry_id"]),
        before_target=before,
        resulting_target=result,
        before_state_revision=_strict_int(item["before_state_revision"]),
        resulting_state_revision=_strict_int(item["resulting_state_revision"]),
        before_entry_revision=_strict_int(item["before_entry_revision"]),
        resulting_entry_revision=_strict_int(item["resulting_entry_revision"]),
        artifact_version=optional("artifact_version"),
        artifact_digest=optional("artifact_digest"),
        api_compatibility_revision=optional("api_compatibility_revision"),
        actor_id=_strict_str(item["actor_id"]),
        reason_code=_strict_str(item["reason_code"]),
        correlation_id=_strict_str(item["correlation_id"]),
        occurred_at=_strict_str(item["occurred_at"]),
        previous_receipt_digest=optional("previous_receipt_digest"),
        receipt_digest=_strict_str(item["receipt_digest"]),
    )


def _strict_mapping(payload: object, expected: set[str], label: str) -> Mapping[str, object]:
    if not isinstance(payload, dict) or set(payload) != expected or not all(isinstance(key, str) for key in payload):
        raise EntryTargetError("unavailable", f"entry_target_{label}_corrupt", f"Entry target {label} 已毀損")
    return payload


def _strict_str(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise EntryTargetError("unavailable", "entry_target_state_corrupt", "Entry target state 已毀損")
    return value


def _strict_int(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise EntryTargetError("unavailable", "entry_target_state_corrupt", "Entry target state 已毀損")
    return value


def _valid_utc_instant(value: str) -> bool:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() == timezone.utc.utcoffset(parsed)
