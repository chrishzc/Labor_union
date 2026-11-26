"""Queries, previews and revision commands for the LINE FAQ chat layout."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Any

from domains.line.configuration import (
    LineConfigurationKind,
    LineConfigurationSnapshot,
    build_configuration_candidate,
)
from domains.line.faq_chat_layout import (
    FaqIssue,
    FaqLayout,
    FaqLayoutInvalid,
    FaqPreview,
    PublishedFaqAnswer,
    add_category,
    decode_layout,
    project_category,
    validate_card_edits,
    validate_publication,
)
from domains.line.identities import LineConfigurationRevision
from shared_kernel.fingerprints import fingerprint_payload
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from subsystems.knowledge_retrieval.faq_catalog import KnowledgeCatalogUnavailable
from subsystems.line.capabilities import LineCapability, require_line_capability
from subsystems.line.configuration_contracts import (
    ApplyLineConfigurationCommand,
    LineConfigurationCommandOutcome,
    LineConfigurationCurrentConflict,
    LineConfigurationKeyConflict,
    LineConfigurationWriteRace,
)
from subsystems.line.ports import LineAuditIntent, LineUnitOfWorkPort


FAQ_CHAT_LAYOUT_KIND = LineConfigurationKind.FAQ_CHAT_LAYOUT


class FaqLayoutUnavailable(RuntimeError):
    pass


class FaqCategoryNotPublished(LookupError):
    pass


class FaqLayoutRevisionConflict(RuntimeError):
    def __init__(self, current_revision: int):
        self.current_revision = current_revision
        super().__init__("faq_layout_revision_conflict")


class FaqLayoutIdempotencyConflict(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class FaqLayoutState:
    draft_revision: int
    published_revision: int | None
    draft_layout: FaqLayout
    published_layout: FaqLayout | None


@dataclass(frozen=True, slots=True)
class FaqOperationReceipt:
    operation_id: str
    draft_revision: int
    published_revision: int | None = None
    category_id: str | None = None


class FaqChatLayoutApplication:
    def __init__(
        self,
        open_unit_of_work: Callable[[], LineUnitOfWorkPort],
        get_published_faq: Callable[[str], PublishedFaqAnswer | None],
    ) -> None:
        self._open_unit_of_work = open_unit_of_work
        self._get_published_faq = get_published_faq

    def query(self, actor: ActorContext) -> FaqLayoutState:
        require_line_capability(actor, LineCapability.CONFIG_MANAGE)
        return self._current()

    def _current(self) -> FaqLayoutState:
        try:
            with self._open_unit_of_work() as unit:
                return _state(unit.configurations.get(FAQ_CHAT_LAYOUT_KIND))
        except Exception as error:
            raise FaqLayoutUnavailable from error

    def published_layout(self) -> FaqLayout | None:
        return self._current().published_layout

    def category_names(self) -> dict[str, str]:
        return {card.category_id: card.name for card in self._current().draft_layout.categories}

    def preview_published(self, category_id: str) -> FaqPreview:
        layout = self.published_layout()
        preview = project_category(layout, category_id, self._get_published_faq) if layout else None
        if preview is None:
            raise FaqCategoryNotPublished
        return preview

    def preview(
        self, actor: ActorContext, category_id: str, *, draft: dict[str, Any] | None = None,
    ) -> FaqPreview:
        require_line_capability(actor, LineCapability.CONFIG_MANAGE)
        if draft is None:
            return self.preview_published(category_id)
        preview = project_category(decode_layout(draft), category_id, self._get_published_faq)
        if preview is None:
            raise FaqLayoutInvalid(FaqIssue("faq_category_unknown", "category_id"))
        return preview

    def operation(self, actor: ActorContext, key: IdempotencyKey) -> FaqOperationReceipt | None:
        require_line_capability(actor, LineCapability.CONFIG_MANAGE)
        try:
            with self._open_unit_of_work() as unit:
                snapshot = unit.configurations.get_by_idempotency_key(FAQ_CHAT_LAYOUT_KIND, key)
                if snapshot is not None:
                    receipt, _ = _receipt(snapshot)
                    if receipt.operation_id == key.value:
                        return receipt
        except Exception as error:
            raise FaqLayoutUnavailable from error
        return None

    def create_category(
        self, name: str, expected_revision: int, actor: ActorContext,
        key: IdempotencyKey, correlation_id: CorrelationId,
    ) -> FaqOperationReceipt:
        return self._mutate("create_category", {"name": name}, expected_revision, actor, key, correlation_id)

    def save_draft(
        self, layout: dict[str, Any], expected_revision: int, actor: ActorContext,
        key: IdempotencyKey, correlation_id: CorrelationId,
    ) -> FaqOperationReceipt:
        return self._mutate("save_draft", {"layout": layout}, expected_revision, actor, key, correlation_id)

    def publish(
        self, expected_revision: int, actor: ActorContext, key: IdempotencyKey,
        correlation_id: CorrelationId,
    ) -> FaqOperationReceipt:
        return self._mutate("publish", {}, expected_revision, actor, key, correlation_id)

    def _mutate(
        self, operation: str, payload: dict[str, Any], expected_revision: int, actor: ActorContext,
        key: IdempotencyKey, correlation_id: CorrelationId,
    ) -> FaqOperationReceipt:
        require_line_capability(actor, LineCapability.CONFIG_MANAGE)
        try:
            fingerprint = fingerprint_payload({
                "operation": operation, "expected_revision": expected_revision, "payload": payload,
            }).value
        except (TypeError, ValueError) as error:
            raise FaqLayoutInvalid(FaqIssue("invalid_payload", "layout")) from error

        try:
            with self._open_unit_of_work() as unit:
                previous = unit.configurations.get_by_idempotency_key(FAQ_CHAT_LAYOUT_KIND, key)
                if previous is not None:
                    return _replay(previous, key, fingerprint)
                current = _state(unit.configurations.get(FAQ_CHAT_LAYOUT_KIND))
                if current.draft_revision != expected_revision:
                    raise FaqLayoutRevisionConflict(current.draft_revision)
                draft = current.draft_layout
                published = current.published_layout
                published_revision = current.published_revision
                next_revision = expected_revision + 1
                if operation == "create_category":
                    added = add_category(draft, payload["name"])
                    draft = FaqLayout((*draft.categories, added))
                    receipt = FaqOperationReceipt(key.value, next_revision, category_id=added.category_id)
                elif operation == "save_draft":
                    edited = decode_layout(payload["layout"])
                    validate_card_edits(draft, edited)
                    draft = edited
                    receipt = FaqOperationReceipt(key.value, next_revision)
                else:
                    validate_publication(draft, self._get_published_faq)
                    published, published_revision = draft, next_revision
                    receipt = FaqOperationReceipt(key.value, next_revision, published_revision)
                command = _command(
                    draft, published, published_revision, expected_revision, fingerprint,
                    receipt, operation, actor, key, correlation_id,
                )
                result = unit.configurations.apply(command)
                if result.outcome is LineConfigurationCommandOutcome.EXISTING:
                    return _replay(result.snapshot, key, fingerprint)
                append_faq_layout_audit(unit, command)
                unit.commit()
                return receipt
        except (
            FaqLayoutInvalid, FaqLayoutIdempotencyConflict, KnowledgeCatalogUnavailable,
        ):
            raise
        except (
            FaqLayoutRevisionConflict, LineConfigurationCurrentConflict,
            LineConfigurationKeyConflict, LineConfigurationWriteRace,
        ) as error:
            return self._resolve_write_race(expected_revision, key, fingerprint, error)
        except Exception as error:
            raise FaqLayoutUnavailable from error

    def _resolve_write_race(
        self, expected_revision: int, key: IdempotencyKey, fingerprint: str, error: RuntimeError,
    ) -> FaqOperationReceipt:
        try:
            with self._open_unit_of_work() as unit:
                previous = unit.configurations.get_by_idempotency_key(FAQ_CHAT_LAYOUT_KIND, key)
                if previous is not None:
                    return _replay(previous, key, fingerprint)
                current = unit.configurations.get(FAQ_CHAT_LAYOUT_KIND).revision.value
        except FaqLayoutIdempotencyConflict:
            raise
        except Exception as read_error:
            raise FaqLayoutUnavailable from read_error
        if isinstance(error, LineConfigurationKeyConflict):
            raise FaqLayoutIdempotencyConflict from error
        if current != expected_revision:
            raise FaqLayoutRevisionConflict(current) from error
        raise FaqLayoutUnavailable from error


def append_faq_layout_audit(unit: LineUnitOfWorkPort, command: ApplyLineConfigurationCommand) -> None:
    unit.audit.append(LineAuditIntent(
        f"line.faq_layout.{command.reason}",
        command.actor.actor_id,
        "line_configuration",
        f"{FAQ_CHAT_LAYOUT_KIND.value}:{command.candidate.resulting_revision.value}",
    ))


def build_initial_faq_layout_command(
    layout: FaqLayout, actor: ActorContext, correlation_id: CorrelationId,
) -> ApplyLineConfigurationCommand:
    """Build the reviewed, first published snapshot for the migration transaction."""
    require_line_capability(actor, LineCapability.CONFIG_MANAGE)
    normalized = decode_layout(asdict(layout))
    key = IdempotencyKey("line-config-bootstrap:faq_chat_layout:v1")
    receipt = FaqOperationReceipt(key.value, 1, 1)
    fingerprint = fingerprint_payload({"operation": "bootstrap", "layout": asdict(normalized)}).value
    return _command(normalized, normalized, 1, 0, fingerprint, receipt, "bootstrap", actor, key, correlation_id)


def _command(
    draft: FaqLayout, published: FaqLayout | None, published_revision: int | None,
    before_revision: int, fingerprint: str, receipt: FaqOperationReceipt, operation: str,
    actor: ActorContext, key: IdempotencyKey, correlation_id: CorrelationId,
) -> ApplyLineConfigurationCommand:
    candidate = build_configuration_candidate(
        kind=FAQ_CHAT_LAYOUT_KIND,
        current_revision=LineConfigurationRevision(before_revision),
        expected_revision=LineConfigurationRevision(before_revision),
        definition={
            "schema_version": 1,
            "draft_layout": asdict(draft),
            "published_layout": asdict(published) if published is not None else None,
            "published_revision": published_revision,
            "command_fingerprint": fingerprint,
            "receipt": asdict(receipt),
        },
    )
    return ApplyLineConfigurationCommand(candidate, actor, operation, key, correlation_id)


def _state(snapshot: LineConfigurationSnapshot) -> FaqLayoutState:
    revision = snapshot.revision.value
    if revision == 0:
        return FaqLayoutState(0, None, FaqLayout(), None)
    definition = _definition(snapshot)
    published_revision = definition["published_revision"]
    published = definition["published_layout"]
    if (
        (published_revision is None) != (published is None)
        or (published_revision is not None and (
            type(published_revision) is not int or not 0 < published_revision <= revision
        ))
    ):
        raise ValueError("invalid FAQ published revision")
    return FaqLayoutState(
        revision, published_revision, decode_layout(definition["draft_layout"]),
        decode_layout(published) if published is not None else None,
    )


def _definition(snapshot: LineConfigurationSnapshot) -> dict[str, Any]:
    definition = json.loads(snapshot.definition_json)
    if definition["schema_version"] != 1:
        raise ValueError("unknown FAQ snapshot schema")
    return definition


def _receipt(snapshot: LineConfigurationSnapshot) -> tuple[FaqOperationReceipt, str]:
    definition = _definition(snapshot)
    return FaqOperationReceipt(**definition["receipt"]), definition["command_fingerprint"]


def _replay(
    snapshot: LineConfigurationSnapshot, key: IdempotencyKey, fingerprint: str,
) -> FaqOperationReceipt:
    receipt, saved = _receipt(snapshot)
    if receipt.operation_id != key.value or saved != fingerprint:
        raise FaqLayoutIdempotencyConflict
    return receipt
