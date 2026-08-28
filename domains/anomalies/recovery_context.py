"""
File: recovery_context.py
Description: 以 owner 根事實 fail-closed 組裝單一或多個 recovery action bindings。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from domains.anomalies.registry import RecoveryActionDescriptor
from shared_kernel.validation import require_canonical_text, require_nonnegative_integer


@dataclass(frozen=True, slots=True)
class RecoveryContextFacts:
    """Current owning-Domain facts required to expose one recovery action."""

    action_key: str
    source_bindings: Mapping[str, str | int]
    aggregate_versions: Mapping[str, int]

    def __post_init__(self) -> None:
        require_canonical_text(self.action_key, "recovery action key", 191)
        for key, value in self.source_bindings.items():
            require_canonical_text(key, "recovery source binding key", 191)
            if isinstance(value, bool) or not isinstance(value, (str, int)):
                raise ValueError("recovery_context_invalid")
        for key, value in self.aggregate_versions.items():
            require_canonical_text(key, "recovery aggregate version key", 191)
            require_nonnegative_integer(value, "recovery aggregate version")


def assemble_recovery_action(
    descriptor: RecoveryActionDescriptor,
    facts: RecoveryContextFacts | None,
) -> RecoveryActionDescriptor | None:
    """Returns no action until the owning domain supplies every immutable binding."""
    if facts is None or facts.action_key != descriptor.action_key:
        return None
    declared_keys = set(descriptor.source_binding_keys)
    if not declared_keys.issubset(facts.source_bindings):
        return None
    if not facts.aggregate_versions:
        return None
    return RecoveryActionDescriptor(
        action_key=descriptor.action_key,
        label=descriptor.label,
        owning_domain=descriptor.owning_domain,
        preview_operation=descriptor.preview_operation,
        apply_operation=descriptor.apply_operation,
        requires_preview=descriptor.requires_preview,
        form_schema_key=descriptor.form_schema_key,
        source_binding_keys=descriptor.source_binding_keys,
        source_bindings={
            key: facts.source_bindings[key] for key in descriptor.source_binding_keys
        },
        required_operator_inputs=descriptor.required_operator_inputs,
        required_capability=descriptor.required_capability,
        completion_predicate=descriptor.completion_predicate,
        action_contract_version=descriptor.action_contract_version,
    )


def bind_recovery_actions(
    descriptors: tuple[RecoveryActionDescriptor, ...],
    root_fact_snapshot: Mapping[str, object],
) -> tuple[RecoveryActionDescriptor, ...]:
    """只暴露具完整 owner identities 與 aggregate versions 的處理動作。"""
    raw_bindings = root_fact_snapshot.get("recovery_bindings")
    if not isinstance(raw_bindings, Mapping) or not all(
        isinstance(key, str) for key in raw_bindings
    ):
        return ()
    bindings = {str(key): value for key, value in raw_bindings.items()}
    aggregate_versions = {
        key: value
        for key, value in bindings.items()
        if key.endswith("_version")
        and not isinstance(value, bool)
        and isinstance(value, int)
        and value >= 0
    }
    source_version = root_fact_snapshot.get("source_version")
    if (
        not isinstance(source_version, bool)
        and isinstance(source_version, int)
        and source_version >= 0
    ):
        aggregate_versions.setdefault("source_version", source_version)
    if not aggregate_versions:
        return ()

    actions: list[RecoveryActionDescriptor] = []
    for descriptor in descriptors:
        try:
            facts = RecoveryContextFacts(
                descriptor.action_key,
                bindings,
                aggregate_versions,
            )
            action = assemble_recovery_action(descriptor, facts)
        except (TypeError, ValueError):
            continue
        if action is not None:
            actions.append(action)
    return tuple(actions)
