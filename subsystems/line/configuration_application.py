"""
File: configuration_application.py
Description: 協調版本化 LINE 設定的查詢、套用與受控初始化修復。
"""

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
from domains.line.notification_rules import validate_notification_rules
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

    def repair_empty_rich_menu_configuration(
        self,
        definition: Mapping[str, object],
        actor: ActorContext,
        *,
        correlation_id: CorrelationId,
    ):
        """Append a repair revision only when the current canonical value is `{}`."""
        require_line_capability(actor, LineCapability.CONFIG_MANAGE)
        with self._unit_of_work_factory() as unit_of_work:
            current = unit_of_work.configurations.get(LineConfigurationKind.RICH_MENUS)
            if current.revision.value == 0 or current.definition_json != "{}":
                return None
            candidate = build_configuration_candidate(
                kind=LineConfigurationKind.RICH_MENUS,
                current_revision=current.revision,
                expected_revision=current.revision,
                definition=definition,
            )
            result = unit_of_work.configurations.apply(
                ApplyLineConfigurationCommand(
                    candidate, actor, "repair exact empty Rich Menu configuration",
                    IdempotencyKey("line-config-repair:rich-menus-empty:v1"),
                    correlation_id,
                )
            )
            unit_of_work.audit.append(LineAuditIntent(
                "line.configuration.repair_empty_rich_menus", actor.actor_id,
                "line_configuration", f"rich_menus:{result.snapshot.revision.value}",
            ))
            unit_of_work.commit()
        return result

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
        elif kind is LineConfigurationKind.NOTIFICATION_RULES:
            validate_notification_rules(definition)


__all__ = ["LineConfigurationApplication"]
