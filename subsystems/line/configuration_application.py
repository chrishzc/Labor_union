"""Canonical preview/apply service for versioned LINE configuration."""

from __future__ import annotations

from typing import Callable, Mapping

from domains.line.configuration import (
    LineConfigurationKind,
    build_configuration_candidate,
)
from domains.line.identities import LineConfigurationRevision
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from subsystems.line.capabilities import LineCapability, require_line_capability
from subsystems.line.configuration_contracts import ApplyLineConfigurationCommand
from subsystems.line.message_configuration import (
    configuration_definition,
    validate_message_schedules,
    validate_message_templates,
)
from subsystems.line.ports import LineAuditIntent, LineUnitOfWorkPort


class LineConfigurationApplication:
    def __init__(
        self,
        unit_of_work_factory: Callable[[], LineUnitOfWorkPort],
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory

    def get(self, kind: LineConfigurationKind, actor: ActorContext):
        require_line_capability(actor, LineCapability.CONFIG_READ)
        with self._unit_of_work_factory() as unit_of_work:
            return unit_of_work.configurations.get(kind)

    def preview(
        self,
        kind: LineConfigurationKind,
        expected_revision: LineConfigurationRevision,
        definition: Mapping[str, object],
        actor: ActorContext,
    ):
        require_line_capability(actor, LineCapability.CONFIG_MANAGE)
        with self._unit_of_work_factory() as unit_of_work:
            current = unit_of_work.configurations.get(kind)
            self._validate(unit_of_work, kind, definition)
        return build_configuration_candidate(
            kind=kind,
            current_revision=current.revision,
            expected_revision=expected_revision,
            definition=definition,
        )

    def apply(
        self,
        *,
        kind: LineConfigurationKind,
        expected_revision: LineConfigurationRevision,
        definition: Mapping[str, object],
        actor: ActorContext,
        reason: str,
        idempotency_key: IdempotencyKey,
        correlation_id: CorrelationId,
    ):
        require_line_capability(actor, LineCapability.CONFIG_MANAGE)
        with self._unit_of_work_factory() as unit_of_work:
            current = unit_of_work.configurations.get(kind)
            self._validate(unit_of_work, kind, definition)
            candidate = build_configuration_candidate(
                kind=kind,
                current_revision=current.revision,
                expected_revision=expected_revision,
                definition=definition,
            )
            result = unit_of_work.configurations.apply(
                ApplyLineConfigurationCommand(
                    candidate,
                    actor,
                    reason,
                    idempotency_key,
                    correlation_id,
                )
            )
            unit_of_work.audit.append(
                LineAuditIntent(
                    "line.configuration.apply",
                    actor.actor_id,
                    "line_configuration",
                    f"{kind.value}:{result.snapshot.revision.value}",
                )
            )
            unit_of_work.commit()
        return result

    def bootstrap_missing(
        self,
        definitions: Mapping[LineConfigurationKind, Mapping[str, object]],
        actor: ActorContext,
        *,
        reason: str,
        correlation_id: CorrelationId,
    ):
        """Seed JSON bootstrap defaults once; committed DB revisions remain authoritative."""
        require_line_capability(actor, LineCapability.CONFIG_MANAGE)
        ordered_kinds = (
            LineConfigurationKind.MESSAGE_TEMPLATES,
            LineConfigurationKind.MESSAGE_SCHEDULES,
            LineConfigurationKind.RICH_MENUS,
            LineConfigurationKind.LIFF,
            LineConfigurationKind.CUSTOMER_SERVICE,
        )
        results = []
        with self._unit_of_work_factory() as unit_of_work:
            for kind in ordered_kinds:
                definition = definitions.get(kind)
                if definition is None:
                    continue
                current = unit_of_work.configurations.get(kind)
                if current.revision.value != 0:
                    continue
                self._validate(unit_of_work, kind, definition)
                candidate = build_configuration_candidate(
                    kind=kind,
                    current_revision=current.revision,
                    expected_revision=current.revision,
                    definition=definition,
                )
                result = unit_of_work.configurations.apply(
                    ApplyLineConfigurationCommand(
                        candidate,
                        actor,
                        reason,
                        IdempotencyKey(f"line-config-bootstrap:{kind.value}:v1"),
                        correlation_id,
                    )
                )
                unit_of_work.audit.append(
                    LineAuditIntent(
                        "line.configuration.bootstrap",
                        actor.actor_id,
                        "line_configuration",
                        f"{kind.value}:{result.snapshot.revision.value}",
                    )
                )
                results.append(result)
            unit_of_work.commit()
        return tuple(results)

    def _validate(self, unit_of_work, kind, definition):
        if kind is LineConfigurationKind.MESSAGE_TEMPLATES:
            validate_message_templates(definition)
        elif kind is LineConfigurationKind.MESSAGE_SCHEDULES:
            templates = configuration_definition(
                unit_of_work.configurations.get(
                    LineConfigurationKind.MESSAGE_TEMPLATES
                )
            )
            validate_message_schedules(definition, templates)


__all__ = ["LineConfigurationApplication"]
