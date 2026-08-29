"""
File: test_line_rich_menu_draft.py
Description: 驗證 Rich Menu typed action 正規化與 Preview 鎖定的 append-only 草稿流程。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import UTC, datetime

import pytest

from domains.line.configuration import LineConfigurationKind, LineConfigurationSnapshot
from domains.line.canonical_payload import canonical_line_payload_json
from domains.line.identities import LineConfigurationRevision, LineRichMenuPublicationId
from domains.line.media_asset import RichMenuMediaAsset
from domains.line.rich_menu import (
    LineRichMenuPublicationSnapshot,
    LineRichMenuPublicationStatus,
)
from domains.line.rich_menu_draft import (
    RichMenuDraftValidationError,
    normalize_rich_menu_action,
    normalize_rich_menu_draft,
)
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from subsystems.line.configuration_application import LineConfigurationApplication
from subsystems.line.configuration_contracts import (
    ApplyLineConfigurationResult,
    LineConfigurationCommandOutcome,
    LineRichMenuDraftPublicationState,
)


def _definition(action: dict[str, object]) -> dict[str, object]:
    return {
        "version": 2,
        "menus": [
            {
                "id": "customer_menu",
                "name": "客戶選單",
                "audience_role": "customer",
                "enabled": True,
                "selected": True,
                "set_as_default": True,
                "chat_bar_text": "服務選單",
                "size": {"width": 2500, "height": 843},
                "appearance": {"background_color": "#F5F5F5", "image_mode": "generated"},
                "buttons": [
                    {
                        "id": "primary_action",
                        "label": "主要功能",
                        "bounds": {"x": 0, "y": 0, "width": 2500, "height": 843},
                        "action": action,
                    }
                ],
            }
        ],
    }


class _ConfigurationRepository:
    def __init__(self, snapshot: LineConfigurationSnapshot) -> None:
        self.snapshot = snapshot
        self.apply_count = 0
        self._results_by_key = {}

    def get(self, kind: LineConfigurationKind) -> LineConfigurationSnapshot:
        assert kind is LineConfigurationKind.RICH_MENUS
        return self.snapshot

    def apply(self, command):
        key = command.idempotency_key.value
        existing = self._results_by_key.get(key)
        if existing is not None:
            fingerprint, snapshot = existing
            if fingerprint != command.candidate.fingerprint:
                raise RuntimeError("line_configuration_idempotency_conflict")
            return ApplyLineConfigurationResult(
                LineConfigurationCommandOutcome.EXISTING,
                snapshot,
            )
        self.apply_count += 1
        self.snapshot = LineConfigurationSnapshot(
            command.candidate.kind,
            command.candidate.resulting_revision,
            command.candidate.definition_json,
        )
        self._results_by_key[key] = (command.candidate.fingerprint, self.snapshot)
        return ApplyLineConfigurationResult(
            LineConfigurationCommandOutcome.CREATED,
            self.snapshot,
        )


class _Audit:
    def __init__(self) -> None:
        self.items = []

    def append(self, item) -> None:
        self.items.append(item)


class _PublicationRepository:
    def __init__(self, items=()) -> None:
        self.items = tuple(items)
        self.queried_revision = None

    def list_for_configuration_revision(self, revision):
        self.queried_revision = revision
        return self.items


class _MediaAssetRepository:
    def __init__(self, asset: RichMenuMediaAsset | None) -> None:
        self.asset = asset
        self.reads = []
        self.locks = []

    def get(self, query):
        self.reads.append(query)
        return self.asset

    def get_for_update(self, query):
        self.locks.append(query)
        return self.asset


def _media_asset(*, deleted: bool = False) -> RichMenuMediaAsset:
    created_at = datetime(2026, 8, 26, tzinfo=UTC)
    return RichMenuMediaAsset(
        asset_id=41,
        menu_definition_id="customer_menu",
        original_filename="customer-menu.png",
        mime_type="image/png",
        file_size=1024,
        sha256="a" * 64,
        width=2500,
        height=843,
        created_at=created_at,
        deleted_at=datetime(2026, 8, 27, tzinfo=UTC) if deleted else None,
    )


def _uploaded_definition(asset: RichMenuMediaAsset) -> dict[str, object]:
    definition = _definition({"type": "message", "text": "服務說明"})
    definition["menus"][0]["appearance"] = {
        "background_color": "#F5F5F5",
        "image_mode": "uploaded",
        "image_asset_id": asset.asset_id,
        "image_asset_sha256": asset.sha256,
        "image_asset_version": asset.asset_version.value,
    }
    return definition


@dataclass
class _UnitOfWork:
    configurations: _ConfigurationRepository
    audit: _Audit
    rich_menu_publications: _PublicationRepository | None = None
    commit_count: int = 0

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def commit(self) -> None:
        self.commit_count += 1


def _actor() -> ActorContext:
    return ActorContext("admin:rich-menu", ("line.config.manage",))


@pytest.mark.parametrize(
    ("action", "expected"),
    [
        ({"type": "message", "text": "聯絡工會", "uri_source": "literal"}, {"type": "message", "text": "聯絡工會"}),
        ({"type": "postback", "data": "case:open"}, {"type": "postback", "data": "case:open"}),
        (
            {"type": "uri", "uri_source": "liff", "uri": "?target=staff_schedule"},
            {"type": "uri", "uri_source": "liff", "uri": "?target=staff_schedule"},
        ),
        (
            {"type": "richmenuswitch", "rich_menu_alias_id": "staff-menu", "data": "switch:staff"},
            {"type": "richmenuswitch", "rich_menu_alias_id": "staff-menu", "data": "switch:staff"},
        ),
    ],
)
def test_closed_action_union_normalizes_each_supported_kind(action, expected) -> None:
    assert normalize_rich_menu_action(action) == expected


@pytest.mark.parametrize(
    "action",
    [
        {"type": "message", "text": "聯絡工會", "uri": "https://example.test"},
        {"type": "uri", "uri_source": "literal", "uri": "javascript:alert(1)"},
        {"type": "uri", "uri_source": "liff", "uri": "?target=unknown"},
        {"type": "postback", "data": "x" * 301},
        {"type": "richmenuswitch", "rich_menu_alias_id": "not allowed"},
        {"type": "provider_payload", "data": "raw"},
    ],
)
def test_action_validation_rejects_incompatible_or_unknown_values(action) -> None:
    with pytest.raises((RichMenuDraftValidationError, ValueError)):
        normalize_rich_menu_action(action)


@pytest.mark.parametrize(
    "appearance_patch",
    [
        {"image_asset_id": None},
        {"image_asset_sha256": None},
        {"image_asset_version": None},
        {"image_path": "C:/raw/menu.png"},
        {"image_asset_sha256": "not-a-digest"},
        {"image_asset_version": "not-a-version"},
    ],
)
def test_uploaded_background_requires_exact_controlled_asset_reference(
    appearance_patch,
) -> None:
    definition = _uploaded_definition(_media_asset())
    definition["menus"][0]["appearance"].update(appearance_patch)

    with pytest.raises((RichMenuDraftValidationError, ValueError)):
        normalize_rich_menu_draft(definition)


def test_generated_background_drops_legacy_path_and_asset_references() -> None:
    definition = _definition({"type": "message", "text": "服務說明"})
    definition["menus"][0]["appearance"].update(
        {
            "image_path": "legacy/generated.png",
            "image_asset_id": 41,
            "image_asset_sha256": "a" * 64,
            "image_asset_version": "b" * 64,
        }
    )

    normalized = normalize_rich_menu_draft(definition)

    assert normalized["menus"][0]["appearance"] == {
        "background_color": "#F5F5F5",
        "image_mode": "generated",
    }


def test_preview_is_zero_write_and_apply_requires_same_fingerprint() -> None:
    initial = LineConfigurationSnapshot(
        LineConfigurationKind.RICH_MENUS,
        LineConfigurationRevision(7),
        canonical_line_payload_json(_definition({"type": "message", "text": "原訊息"})),
    )
    repository = _ConfigurationRepository(initial)
    unit_of_work = _UnitOfWork(repository, _Audit())
    application = LineConfigurationApplication(lambda: unit_of_work)
    definition = _definition({"type": "message", "text": "新的實際訊息"})

    preview = application.preview_rich_menu_draft(
        LineConfigurationRevision(7),
        definition,
        _actor(),
    )

    assert preview.resulting_revision == LineConfigurationRevision(8)
    assert repository.apply_count == 0
    assert unit_of_work.commit_count == 0
    with pytest.raises(RuntimeError, match="preview_fingerprint_mismatch"):
        application.apply_rich_menu_draft(
            expected_revision=LineConfigurationRevision(7),
            definition=definition,
            preview_fingerprint=PreviewFingerprint("0" * 64),
            actor=_actor(),
            reason="更新 Rich Menu 訊息",
            idempotency_key=IdempotencyKey("rich-menu-draft-7"),
            correlation_id=CorrelationId("rich-menu-draft-correlation-7"),
        )
    assert repository.apply_count == 0
    assert unit_of_work.commit_count == 0

    result = application.apply_rich_menu_draft(
        expected_revision=LineConfigurationRevision(7),
        definition=definition,
        preview_fingerprint=preview.fingerprint,
        actor=_actor(),
        reason="更新 Rich Menu 訊息",
        idempotency_key=IdempotencyKey("rich-menu-draft-7"),
        correlation_id=CorrelationId("rich-menu-draft-correlation-7"),
    )

    assert result.snapshot.revision == LineConfigurationRevision(8)
    assert repository.apply_count == 1
    assert unit_of_work.commit_count == 1
    assert unit_of_work.audit.items[0].action == "line.rich_menu.draft.apply"


def test_uploaded_background_preview_reads_and_apply_fresh_locks_exact_asset() -> None:
    asset = _media_asset()
    initial = LineConfigurationSnapshot(
        LineConfigurationKind.RICH_MENUS,
        LineConfigurationRevision(7),
        canonical_line_payload_json(_definition({"type": "message", "text": "原訊息"})),
    )
    unit_of_work = _UnitOfWork(_ConfigurationRepository(initial), _Audit())
    media_assets = _MediaAssetRepository(asset)
    unit_of_work.rich_menu_media_assets = media_assets
    application = LineConfigurationApplication(lambda: unit_of_work)
    definition = _uploaded_definition(asset)

    preview = application.preview_rich_menu_draft(
        LineConfigurationRevision(7),
        definition,
        _actor(),
    )
    result = application.apply_rich_menu_draft(
        expected_revision=LineConfigurationRevision(7),
        definition=definition,
        preview_fingerprint=preview.fingerprint,
        actor=_actor(),
        reason="選擇受控背景圖",
        idempotency_key=IdempotencyKey("rich-menu-media-draft-7"),
        correlation_id=CorrelationId("rich-menu-media-correlation-7"),
    )

    assert result.outcome is LineConfigurationCommandOutcome.CREATED
    assert [query.asset_id for query in media_assets.reads] == [41]
    assert [query.asset_id for query in media_assets.locks] == [41]
    assert unit_of_work.commit_count == 1


def test_uploaded_background_apply_rejects_post_preview_drift_before_commit() -> None:
    asset = _media_asset()
    initial = LineConfigurationSnapshot(
        LineConfigurationKind.RICH_MENUS,
        LineConfigurationRevision(7),
        canonical_line_payload_json(_definition({"type": "message", "text": "原訊息"})),
    )
    repository = _ConfigurationRepository(initial)
    unit_of_work = _UnitOfWork(repository, _Audit())
    media_assets = _MediaAssetRepository(asset)
    unit_of_work.rich_menu_media_assets = media_assets
    application = LineConfigurationApplication(lambda: unit_of_work)
    definition = _uploaded_definition(asset)
    preview = application.preview_rich_menu_draft(
        LineConfigurationRevision(7), definition, _actor()
    )
    media_assets.asset = replace(asset, original_filename="renamed.png")

    with pytest.raises(RuntimeError, match="media_asset_version_conflict"):
        application.apply_rich_menu_draft(
            expected_revision=LineConfigurationRevision(7),
            definition=definition,
            preview_fingerprint=preview.fingerprint,
            actor=_actor(),
            reason="選擇受控背景圖",
            idempotency_key=IdempotencyKey("rich-menu-media-stale-7"),
            correlation_id=CorrelationId("rich-menu-media-stale-correlation-7"),
        )

    assert repository.apply_count == 1
    assert len(media_assets.locks) == 1
    assert unit_of_work.audit.items == []
    assert unit_of_work.commit_count == 0


def test_uploaded_background_terminal_replay_skips_later_asset_drift() -> None:
    asset = _media_asset()
    initial = LineConfigurationSnapshot(
        LineConfigurationKind.RICH_MENUS,
        LineConfigurationRevision(7),
        canonical_line_payload_json(_definition({"type": "message", "text": "原訊息"})),
    )
    repository = _ConfigurationRepository(initial)
    unit_of_work = _UnitOfWork(repository, _Audit())
    media_assets = _MediaAssetRepository(asset)
    unit_of_work.rich_menu_media_assets = media_assets
    application = LineConfigurationApplication(lambda: unit_of_work)
    definition = _uploaded_definition(asset)
    preview = application.preview_rich_menu_draft(
        LineConfigurationRevision(7), definition, _actor()
    )
    command = {
        "expected_revision": LineConfigurationRevision(7),
        "definition": definition,
        "preview_fingerprint": preview.fingerprint,
        "actor": _actor(),
        "reason": "選擇受控背景圖",
        "idempotency_key": IdempotencyKey("rich-menu-media-replay-7"),
        "correlation_id": CorrelationId("rich-menu-media-replay-correlation-7"),
    }
    created = application.apply_rich_menu_draft(**command)
    media_assets.asset = _media_asset(deleted=True)

    replay = application.apply_rich_menu_draft(**command)

    assert created.outcome is LineConfigurationCommandOutcome.CREATED
    assert replay.outcome is LineConfigurationCommandOutcome.EXISTING
    assert repository.apply_count == 1
    assert len(media_assets.locks) == 1


@pytest.mark.parametrize(
    ("drift", "error_code"),
    [
        ("missing", "media_asset_missing"),
        ("owner", "media_asset_owner_conflict"),
        ("deleted", "media_asset_deleted"),
        ("digest", "media_asset_digest_conflict"),
        ("version", "media_asset_version_conflict"),
        ("size", "media_asset_size_conflict"),
    ],
)
def test_uploaded_background_preview_rejects_asset_drift_without_write(
    drift,
    error_code,
) -> None:
    reference_asset = _media_asset()
    persisted_asset = {
        "missing": None,
        "owner": replace(reference_asset, menu_definition_id="staff_menu"),
        "deleted": replace(
            reference_asset,
            deleted_at=datetime(2026, 8, 27, tzinfo=UTC),
        ),
        "digest": replace(reference_asset, sha256="b" * 64),
        "version": replace(reference_asset, original_filename="renamed.png"),
        "size": replace(reference_asset, height=1686),
    }[drift]
    initial = LineConfigurationSnapshot(
        LineConfigurationKind.RICH_MENUS,
        LineConfigurationRevision(7),
        canonical_line_payload_json(_definition({"type": "message", "text": "原訊息"})),
    )
    repository = _ConfigurationRepository(initial)
    unit_of_work = _UnitOfWork(repository, _Audit())
    unit_of_work.rich_menu_media_assets = _MediaAssetRepository(persisted_asset)
    definition = _uploaded_definition(reference_asset)
    if drift == "size":
        definition["menus"][0]["appearance"]["image_asset_version"] = (
            persisted_asset.asset_version.value
        )

    with pytest.raises(RuntimeError, match=error_code):
        LineConfigurationApplication(lambda: unit_of_work).preview_rich_menu_draft(
            LineConfigurationRevision(7),
            definition,
            _actor(),
        )

    assert repository.apply_count == 0
    assert unit_of_work.commit_count == 0


def test_dedicated_query_normalizes_legacy_null_fields_without_writing() -> None:
    definition = _definition(
        {
            "type": "message",
            "text": "服務說明",
            "uri": None,
            "uri_source": "literal",
            "data": None,
        }
    )
    snapshot = LineConfigurationSnapshot(
        LineConfigurationKind.RICH_MENUS,
        LineConfigurationRevision(3),
        canonical_line_payload_json(definition),
    )
    repository = _ConfigurationRepository(snapshot)
    unit_of_work = _UnitOfWork(repository, _Audit())

    result = LineConfigurationApplication(lambda: unit_of_work).get_rich_menu_draft(_actor())

    action = json.loads(result.definition_json)["menus"][0]["buttons"][0]["action"]
    assert action == {"type": "message", "text": "服務說明"}
    assert repository.apply_count == 0
    assert unit_of_work.commit_count == 0


def test_draft_query_uses_exact_revision_publication_locks_with_published_precedence() -> None:
    definition = _definition({"type": "message", "text": "服務說明"})
    staff_menu = json.loads(json.dumps(definition["menus"][0]))
    staff_menu.update(
        {
            "id": "staff_menu",
            "name": "月嫂選單",
            "audience_role": "staff",
            "set_as_default": False,
        }
    )
    definition["menus"].append(staff_menu)
    snapshot = LineConfigurationSnapshot(
        LineConfigurationKind.RICH_MENUS,
        LineConfigurationRevision(8),
        canonical_line_payload_json(definition),
    )
    publications = _PublicationRepository(
        (
            LineRichMenuPublicationSnapshot(
                LineRichMenuPublicationId(1),
                "customer_menu",
                LineConfigurationRevision(8),
                LineRichMenuPublicationStatus.PUBLISHING,
            ),
            LineRichMenuPublicationSnapshot(
                LineRichMenuPublicationId(2),
                "customer_menu",
                LineConfigurationRevision(8),
                LineRichMenuPublicationStatus.PUBLISHED,
            ),
            LineRichMenuPublicationSnapshot(
                LineRichMenuPublicationId(3),
                "staff_menu",
                LineConfigurationRevision(8),
                LineRichMenuPublicationStatus.QUEUED,
            ),
        )
    )
    unit_of_work = _UnitOfWork(_ConfigurationRepository(snapshot), _Audit(), publications)

    result = LineConfigurationApplication(lambda: unit_of_work).get_rich_menu_draft_query(
        _actor()
    )

    assert publications.queried_revision == LineConfigurationRevision(8)
    assert tuple((item.menu_definition_id, item.state) for item in result.publication_locks) == (
        ("customer_menu", LineRichMenuDraftPublicationState.PUBLISHED),
        ("staff_menu", LineRichMenuDraftPublicationState.EDITABLE),
    )
    assert unit_of_work.commit_count == 0


def test_draft_query_fails_closed_on_non_exact_publication_revision() -> None:
    snapshot = LineConfigurationSnapshot(
        LineConfigurationKind.RICH_MENUS,
        LineConfigurationRevision(8),
        canonical_line_payload_json(_definition({"type": "message", "text": "服務說明"})),
    )
    publications = _PublicationRepository(
        (
            LineRichMenuPublicationSnapshot(
                LineRichMenuPublicationId(4),
                "customer_menu",
                LineConfigurationRevision(7),
                LineRichMenuPublicationStatus.PUBLISHED,
            ),
        )
    )
    unit_of_work = _UnitOfWork(_ConfigurationRepository(snapshot), _Audit(), publications)

    with pytest.raises(RuntimeError, match="revision_mismatch"):
        LineConfigurationApplication(lambda: unit_of_work).get_rich_menu_draft_query(_actor())
