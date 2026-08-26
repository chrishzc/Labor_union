"""
File: configuration_application.py
Description: 協調版本化 LINE 設定的查詢、套用與受控初始化修復。
"""

from __future__ import annotations

import json
from typing import Callable, Mapping

from domains.line.configuration import (
    LineConfigurationKind,
    build_configuration_candidate,
)
from domains.line.canonical_payload import validate_canonical_line_payload_json
from domains.line.configuration import LineConfigurationSnapshot
from domains.line.identities import LineConfigurationRevision
from domains.line.rich_menu_draft import normalize_rich_menu_draft
from domains.line.rich_menu import LineRichMenuPublicationStatus
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from subsystems.line.capabilities import LineCapability, require_line_capability
from subsystems.line.configuration_contracts import (
    ApplyLineConfigurationCommand,
    GetLineConfigurationSafeQuery,
    LineConfigurationCommandOutcome,
    LineConfigurationQueryContractError,
    LineConfigurationQueryUnavailableError,
    LineConfigurationSafeResult,
    LineConfigurationSafeState,
    LineRichMenuDraftPublicationLock,
    LineRichMenuDraftPublicationState,
    LineRichMenuDraftQueryResult,
)
from subsystems.line.media_asset_contracts import RichMenuMediaAssetDetailQuery
from subsystems.line.message_configuration import (
    configuration_definition,
    validate_message_schedules,
    validate_message_templates,
)
from domains.line.notification_rules import (
    materialize_notification_rules_definition,
    validate_notification_rules,
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

    def get_safe(
        self,
        query: GetLineConfigurationSafeQuery,
        actor: ActorContext,
    ) -> LineConfigurationSafeResult:
        require_line_capability(actor, LineCapability.CONFIG_READ)
        try:
            with self._unit_of_work_factory() as unit_of_work:
                snapshot = unit_of_work.configurations.get(query.kind)
        except Exception as error:
            raise LineConfigurationQueryUnavailableError() from error
        try:
            return _safe_configuration_result(query, snapshot)
        except LineConfigurationQueryContractError:
            raise
        except Exception as error:
            raise LineConfigurationQueryContractError() from error

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
        if kind is LineConfigurationKind.NOTIFICATION_RULES:
            definition = materialize_notification_rules_definition(definition)
        return build_configuration_candidate(
            kind=kind,
            current_revision=current.revision,
            expected_revision=expected_revision,
            definition=definition,
        )

    def get_rich_menu_draft(self, actor: ActorContext) -> LineConfigurationSnapshot:
        """Return the normalized editable definition through the dedicated owner."""
        require_line_capability(actor, LineCapability.CONFIG_MANAGE)
        with self._unit_of_work_factory() as unit_of_work:
            snapshot = unit_of_work.configurations.get(LineConfigurationKind.RICH_MENUS)
        definition = normalize_rich_menu_draft(json.loads(snapshot.definition_json))
        return LineConfigurationSnapshot(
            snapshot.kind,
            snapshot.revision,
            json.dumps(
                definition,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
        )

    def get_rich_menu_draft_query(self, actor: ActorContext) -> LineRichMenuDraftQueryResult:
        """Return the normalized draft and exact-revision publication locks."""
        require_line_capability(actor, LineCapability.CONFIG_MANAGE)
        with self._unit_of_work_factory() as unit_of_work:
            snapshot = unit_of_work.configurations.get(LineConfigurationKind.RICH_MENUS)
            publications = unit_of_work.rich_menu_publications.list_for_configuration_revision(
                snapshot.revision
            )
        definition = normalize_rich_menu_draft(json.loads(snapshot.definition_json))
        normalized_snapshot = LineConfigurationSnapshot(
            snapshot.kind,
            snapshot.revision,
            json.dumps(
                definition,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
        )
        menu_ids = tuple(str(item["id"]) for item in definition.get("menus", ()))
        states = {
            menu_id: LineRichMenuDraftPublicationState.EDITABLE
            for menu_id in menu_ids
        }
        for publication in publications:
            if publication.configuration_revision != snapshot.revision:
                raise RuntimeError("line_rich_menu_publication_revision_mismatch")
            if publication.menu_definition_id not in states:
                raise RuntimeError("line_rich_menu_publication_menu_mismatch")
            if publication.status is LineRichMenuPublicationStatus.PUBLISHED:
                states[publication.menu_definition_id] = (
                    LineRichMenuDraftPublicationState.PUBLISHED
                )
            elif (
                publication.status is LineRichMenuPublicationStatus.PUBLISHING
                and states[publication.menu_definition_id]
                is not LineRichMenuDraftPublicationState.PUBLISHED
            ):
                states[publication.menu_definition_id] = (
                    LineRichMenuDraftPublicationState.PROCESSING
                )
        return LineRichMenuDraftQueryResult(
            normalized_snapshot,
            tuple(
                LineRichMenuDraftPublicationLock(menu_id, snapshot.revision, states[menu_id])
                for menu_id in menu_ids
            ),
        )

    def preview_rich_menu_draft(
        self,
        expected_revision: LineConfigurationRevision,
        definition: Mapping[str, object],
        actor: ActorContext,
    ):
        require_line_capability(actor, LineCapability.CONFIG_MANAGE)
        normalized = normalize_rich_menu_draft(definition)
        with self._unit_of_work_factory() as unit_of_work:
            current = unit_of_work.configurations.get(LineConfigurationKind.RICH_MENUS)
            _validate_rich_menu_media_assets(
                normalized,
                unit_of_work,
                for_update=False,
            )
        return build_configuration_candidate(
            kind=LineConfigurationKind.RICH_MENUS,
            current_revision=current.revision,
            expected_revision=expected_revision,
            definition=normalized,
        )

    def apply_rich_menu_draft(
        self,
        *,
        expected_revision: LineConfigurationRevision,
        definition: Mapping[str, object],
        preview_fingerprint: PreviewFingerprint,
        actor: ActorContext,
        reason: str,
        idempotency_key: IdempotencyKey,
        correlation_id: CorrelationId,
    ):
        """Append a preview-locked draft revision without publication side effects."""
        require_line_capability(actor, LineCapability.CONFIG_MANAGE)
        normalized = normalize_rich_menu_draft(definition)
        candidate = build_configuration_candidate(
            kind=LineConfigurationKind.RICH_MENUS,
            current_revision=expected_revision,
            expected_revision=expected_revision,
            definition=normalized,
        )
        if candidate.fingerprint != preview_fingerprint:
            raise RuntimeError("line_rich_menu_draft_preview_fingerprint_mismatch")
        with self._unit_of_work_factory() as unit_of_work:
            result = unit_of_work.configurations.apply(
                ApplyLineConfigurationCommand(
                    candidate,
                    actor,
                    reason,
                    idempotency_key,
                    correlation_id,
                )
            )
            if result.outcome is LineConfigurationCommandOutcome.CREATED:
                _validate_rich_menu_media_assets(
                    normalized,
                    unit_of_work,
                    for_update=True,
                )
            unit_of_work.audit.append(
                LineAuditIntent(
                    "line.rich_menu.draft.apply",
                    actor.actor_id,
                    "line_configuration",
                    f"rich_menus:{result.snapshot.revision.value}",
                )
            )
            unit_of_work.commit()
        return result

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
        if kind is LineConfigurationKind.NOTIFICATION_RULES:
            raise RuntimeError("notification rules require the dedicated mutation contract")
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


def _validate_rich_menu_media_assets(
    definition: Mapping[str, object],
    unit_of_work: LineUnitOfWorkPort,
    *,
    for_update: bool,
) -> None:
    references: list[tuple[int, str, str, str, int, int]] = []
    for menu in definition.get("menus", []):
        if not isinstance(menu, Mapping):
            raise RuntimeError("line_rich_menu_media_definition_invalid")
        appearance = menu.get("appearance", {})
        size = menu.get("size", {})
        if not isinstance(appearance, Mapping) or not isinstance(size, Mapping):
            raise RuntimeError("line_rich_menu_media_definition_invalid")
        if appearance.get("image_mode") != "uploaded":
            continue
        references.append(
            (
                int(appearance["image_asset_id"]),
                str(menu["id"]),
                str(appearance["image_asset_sha256"]),
                str(appearance["image_asset_version"]),
                int(size["width"]),
                int(size["height"]),
            )
        )
    if not references:
        return
    repository = unit_of_work.rich_menu_media_assets
    reader = repository.get_for_update if for_update else repository.get
    for asset_id, menu_id, sha256, version, width, height in sorted(references):
        asset = reader(
            RichMenuMediaAssetDetailQuery(
                menu_definition_id=menu_id,
                asset_id=asset_id,
            )
        )
        if asset is None:
            raise RuntimeError("line_rich_menu_media_asset_missing")
        if asset.menu_definition_id != menu_id:
            raise RuntimeError("line_rich_menu_media_asset_owner_conflict")
        if not asset.selectable:
            raise RuntimeError("line_rich_menu_media_asset_deleted")
        if asset.sha256 != sha256:
            raise RuntimeError("line_rich_menu_media_asset_digest_conflict")
        if asset.asset_version.value != version:
            raise RuntimeError("line_rich_menu_media_asset_version_conflict")
        if (asset.width, asset.height) != (width, height):
            raise RuntimeError("line_rich_menu_media_asset_size_conflict")


def _safe_configuration_result(
    query: GetLineConfigurationSafeQuery,
    snapshot: object,
) -> LineConfigurationSafeResult:
    if not isinstance(snapshot, LineConfigurationSnapshot):
        raise LineConfigurationQueryContractError()
    if snapshot.kind is not query.kind:
        raise LineConfigurationQueryContractError()
    if not isinstance(snapshot.revision, LineConfigurationRevision):
        raise LineConfigurationQueryContractError()
    validate_canonical_line_payload_json(snapshot.definition_json)
    state = (
        LineConfigurationSafeState.EMPTY
        if snapshot.definition_json == "{}"
        else LineConfigurationSafeState.CONFIGURED
    )
    return LineConfigurationSafeResult(
        kind=snapshot.kind,
        revision=snapshot.revision.value,
        state=state,
    )


__all__ = ["LineConfigurationApplication"]
