"""Fail-closed assembly of anomaly recovery action bindings."""

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
    if set(facts.source_bindings) != set(descriptor.source_binding_keys):
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
        source_bindings=dict(facts.source_bindings),
        required_operator_inputs=descriptor.required_operator_inputs,
        required_capability=descriptor.required_capability,
        completion_predicate=descriptor.completion_predicate,
        action_contract_version=descriptor.action_contract_version,
    )
