"""
File: configuration.py
Description: 定義版本化 LINE 設定候選與 revision 規則，包含受控通知規則種類。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Mapping

from domains.line.canonical_payload import (
    canonical_line_payload_json,
    canonical_line_payload_json_without_validation,
    validate_canonical_line_payload_json,
)
from domains.line.identities import LineConfigurationRevision
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload


class LineConfigurationKind(StrEnum):
    MESSAGE_TEMPLATES = "message_templates"
    MESSAGE_SCHEDULES = "message_schedules"
    RICH_MENUS = "rich_menus"
    LIFF = "liff"
    CUSTOMER_SERVICE = "customer_service"
    NOTIFICATION_RULES = "notification_rules"
    FAQ_CHAT_LAYOUT = "faq_chat_layout"


class LineConfigurationRevisionConflict(ValueError):
    """Raised when a configuration preview uses an outdated revision."""


@dataclass(frozen=True, slots=True)
class LineConfigurationCandidate:
    kind: LineConfigurationKind
    before_revision: LineConfigurationRevision
    resulting_revision: LineConfigurationRevision
    definition_json: str
    fingerprint: PreviewFingerprint


@dataclass(frozen=True, slots=True)
class LineConfigurationSnapshot:
    kind: LineConfigurationKind
    revision: LineConfigurationRevision
    definition_json: str

    def __post_init__(self) -> None:
        if not isinstance(self.kind, LineConfigurationKind):
            raise TypeError("LINE configuration kind is invalid")
        if self.kind is LineConfigurationKind.FAQ_CHAT_LAYOUT:
            definition = json.loads(self.definition_json)
            if not isinstance(definition, dict) or self.definition_json != (
                canonical_line_payload_json_without_validation(definition)
            ):
                raise ValueError("FAQ layout definition JSON must be a canonical object")
        else:
            validate_canonical_line_payload_json(self.definition_json)


# Kept cohesive so the revision, canonical definition, and fingerprint cannot drift.
def build_configuration_candidate(
    *,
    kind: LineConfigurationKind,
    current_revision: LineConfigurationRevision,
    expected_revision: LineConfigurationRevision,
    definition: Mapping[str, object],
) -> LineConfigurationCandidate:
    if not isinstance(kind, LineConfigurationKind):
        raise TypeError("LINE configuration kind is invalid")
    if current_revision != expected_revision:
        raise LineConfigurationRevisionConflict(
            "LINE configuration revision is stale"
        )
    if kind is LineConfigurationKind.FAQ_CHAT_LAYOUT:
        # The stored FAQ layout contains two snapshots. LINE messages render one card or menu page.
        definition_json = canonical_line_payload_json_without_validation(definition)
    else:
        definition_json = canonical_line_payload_json(definition)
    resulting_revision = LineConfigurationRevision(current_revision.value + 1)
    return LineConfigurationCandidate(
        kind,
        current_revision,
        resulting_revision,
        definition_json,
        _configuration_fingerprint(
            kind,
            current_revision,
            resulting_revision,
            definition_json,
        ),
    )


def _configuration_fingerprint(
    kind: LineConfigurationKind,
    before: LineConfigurationRevision,
    after: LineConfigurationRevision,
    definition_json: str,
) -> PreviewFingerprint:
    return fingerprint_payload(
        {
            "kind": kind.value,
            "before_revision": before.value,
            "resulting_revision": after.value,
            "definition": json.loads(definition_json),
        }
    )


__all__ = [
    "LineConfigurationCandidate",
    "LineConfigurationKind",
    "LineConfigurationSnapshot",
    "LineConfigurationRevisionConflict",
    "build_configuration_candidate",
]
