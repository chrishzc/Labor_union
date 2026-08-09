"""Canonical preview and queue application service for LINE Rich Menu publication."""

from __future__ import annotations

import json
from typing import Callable

from domains.line.configuration import LineConfigurationKind
from domains.line.identities import LineRichMenuPublicationId
from shared_kernel.fingerprints import fingerprint_payload
from shared_kernel.identities import IdempotencyReceipt
from subsystems.line.capabilities import LineCapability, require_line_capability
from subsystems.line.message_configuration import configuration_definition
from subsystems.line.ports import LineAuditIntent, LineUnitOfWorkPort
from subsystems.line.rich_menu_contracts import (
    LineRichMenuPublicationQuery,
    PreviewLineRichMenuCommand,
    QueueLineRichMenuPublicationCommand,
    RetryLineRichMenuPublicationCommand,
)
from subsystems.line.rich_menu_definition import rich_menu_provider_definition


class LineRichMenuNotFoundError(LookupError):
    """Raised when a configured Rich Menu definition cannot be found."""


class LineRichMenuApplication:
    def __init__(self, unit_of_work_factory: Callable[[], LineUnitOfWorkPort]) -> None:
        self._unit_of_work_factory = unit_of_work_factory

    def preview(self, command: PreviewLineRichMenuCommand, actor):
        require_line_capability(actor, LineCapability.CONFIG_READ)
        with self._unit_of_work_factory() as unit_of_work:
            menu = self._menu(unit_of_work, command)
        return {
            "menu_definition": menu,
            "provider_definition": json.loads(rich_menu_provider_definition(menu)),
        }

    def list(self, query: LineRichMenuPublicationQuery, actor):
        require_line_capability(actor, LineCapability.CONFIG_READ)
        with self._unit_of_work_factory() as unit_of_work:
            return unit_of_work.rich_menu_publications.list(query)

    def get(self, publication_id, actor):
        require_line_capability(actor, LineCapability.CONFIG_READ)
        with self._unit_of_work_factory() as unit_of_work:
            result = unit_of_work.rich_menu_publications.get(publication_id)
        if result is None:
            raise LineRichMenuNotFoundError("找不到 Rich Menu 發布工作")
        return result

    def queue(self, command: QueueLineRichMenuPublicationCommand):
        require_line_capability(command.actor, LineCapability.MENU_PUBLISH)
        with self._unit_of_work_factory() as unit_of_work:
            menu = self._menu(unit_of_work, command)
            fingerprint = fingerprint_payload(
                {
                    "menu_definition_id": command.menu_definition_id,
                    "configuration_revision": command.configuration_revision.value,
                    "menu": menu,
                }
            )
            existing = unit_of_work.receipts.get(command.idempotency_key)
            if existing is not None:
                if existing.payload_fingerprint != fingerprint:
                    raise RuntimeError("line_rich_menu_command_idempotency_conflict")
                publication_id = int(existing.result_reference.rsplit(":", 1)[-1])
                result = unit_of_work.rich_menu_publications.get(
                    LineRichMenuPublicationId(publication_id)
                )
                if result is None:
                    raise RuntimeError("line_rich_menu_receipt_result_missing")
                return result
            result = unit_of_work.rich_menu_publications.queue(command)
            unit_of_work.receipts.append(
                IdempotencyReceipt(
                    command.idempotency_key,
                    fingerprint,
                    f"line-rich-menu-publication:{result.publication.publication_id.value}",
                )
            )
            unit_of_work.audit.append(
                LineAuditIntent(
                    "line.rich_menu.queue",
                    command.actor.actor_id,
                    "line_rich_menu_publication",
                    str(result.publication.publication_id.value),
                )
            )
            unit_of_work.commit()
        return result.publication

    def retry(self, command: RetryLineRichMenuPublicationCommand):
        require_line_capability(command.actor, LineCapability.MENU_PUBLISH)
        fingerprint = fingerprint_payload(
            {
                "action": "retry",
                "publication_id": command.publication_id.value,
                "reason": command.reason,
            }
        )
        reference = f"line-rich-menu-retry:{command.publication_id.value}"
        with self._unit_of_work_factory() as unit_of_work:
            existing = unit_of_work.receipts.get(command.idempotency_key)
            if existing is not None:
                if existing.payload_fingerprint != fingerprint or existing.result_reference != reference:
                    raise RuntimeError("line_rich_menu_command_idempotency_conflict")
                result = unit_of_work.rich_menu_publications.get(command.publication_id)
                if result is None:
                    raise LineRichMenuNotFoundError("找不到 Rich Menu 發布工作")
                return result
            try:
                result = unit_of_work.rich_menu_publications.retry(command)
            except LookupError as error:
                raise LineRichMenuNotFoundError("找不到 Rich Menu 發布工作") from error
            unit_of_work.receipts.append(
                IdempotencyReceipt(command.idempotency_key, fingerprint, reference)
            )
            unit_of_work.audit.append(
                LineAuditIntent(
                    "line.rich_menu.retry",
                    command.actor.actor_id,
                    "line_rich_menu_publication",
                    str(command.publication_id.value),
                )
            )
            unit_of_work.commit()
        return result

    def _menu(self, unit_of_work, command):
        snapshot = unit_of_work.configurations.get(LineConfigurationKind.RICH_MENUS)
        if snapshot.revision != command.configuration_revision:
            raise RuntimeError("line_rich_menu_configuration_revision_conflict")
        definition = configuration_definition(snapshot)
        menu = next(
            (
                item
                for item in definition.get("menus", [])
                if isinstance(item, dict) and item.get("id") == command.menu_definition_id
            ),
            None,
        )
        if menu is None or menu.get("enabled", True) is not True:
            raise LineRichMenuNotFoundError("找不到可發布的 Rich Menu")
        rich_menu_provider_definition(menu)
        return menu


__all__ = ["LineRichMenuApplication", "LineRichMenuNotFoundError"]
