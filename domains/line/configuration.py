"""Pure LINE configuration revision and preview rules."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Mapping

from domains.line.canonical_payload import (
    canonical_line_payload_json,
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
