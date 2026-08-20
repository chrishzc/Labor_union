"""
File: import_warning_tracking.py
Description: 定義匯入警示 occurrence、追蹤狀態與未登錄 issue 的去敏錯誤。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import hashlib
import json
import re


_LOGICAL_CODE = re.compile(r"^[A-Z][A-Z0-9-]{2,80}$")
_LANE_NAME = re.compile(r"^[a-z][a-z0-9_-]{1,63}$")


class ImportWarningTrackingStatus(StrEnum):
    OPEN = "open"
    AWAITING_EXTERNAL_CONFIRMATION = "awaiting_external_confirmation"
    RESPONSE_RECORDED = "response_recorded"
    REIMPORT_REQUESTED = "reimport_requested"
    CLOSED = "closed"
    AUTO_RESOLVED = "auto_resolved"


class WarningTransitionError(ValueError):
    pass


class UnknownImportWarningIssueError(ValueError):
    """Signal a projection contract gap without copying source issue text."""

    def __init__(self, *, owning_lane: str, issue_code: str) -> None:
        lane = _require_lane(owning_lane)
        issue = _require_text(issue_code, "issue code")
        digest = hashlib.sha256(issue.encode("utf-8")).hexdigest()[:16]
        super().__init__(f"import_warning_projection_unknown_issue:{lane}:{digest}")


@dataclass(frozen=True, slots=True)
class ImportWarningOccurrence:
    occurrence_identity: str
    owning_lane: str
    source_event_identity: str
    logical_code: str
    field_path: str
    masked_subject: str
    issue_codes: tuple[str, ...]
    tracking_status: ImportWarningTrackingStatus


@dataclass(frozen=True, slots=True)
class WarningTransitionPreview:
    allowed: bool
    resulting_status: ImportWarningTrackingStatus
    expected_version: int
    resulting_version: int


def build_import_warning_occurrence(
    *,
    owning_lane: str,
    source_event_identity: str,
    logical_code: str,
    field_path: str,
    masked_subject: str,
    issue_codes: tuple[str, ...],
) -> ImportWarningOccurrence:
    lane = _require_lane(owning_lane)
    source = _require_text(source_event_identity, "source event identity")
    code = _require_logical_code(logical_code)
    path = _require_text(field_path, "field path")
    subject = _require_text(masked_subject, "masked subject")
    canonical_issues = _canonical_issue_codes(issue_codes)
    identity = _occurrence_identity(lane, source, code, path)
    return ImportWarningOccurrence(
        identity, lane, source, code, path, subject, canonical_issues,
        ImportWarningTrackingStatus.OPEN,
    )


def preview_warning_transition(
    *,
    current_status: ImportWarningTrackingStatus,
    current_version: int,
    target_status: ImportWarningTrackingStatus,
    actor_kind: str,
) -> WarningTransitionPreview:
    _require_version(current_version)
    actor = _require_text(actor_kind, "actor kind")
    if target_status is ImportWarningTrackingStatus.AUTO_RESOLVED and actor != "system":
        raise WarningTransitionError("auto_resolved requires a system actor")
    if target_status is ImportWarningTrackingStatus.CLOSED and actor not in {"system", "union_operator"}:
        raise WarningTransitionError("closed requires a union operator or system actor")
    if target_status not in _allowed_targets(current_status, actor):
        raise WarningTransitionError("warning transition is not allowed")
    return WarningTransitionPreview(True, target_status, current_version, current_version + 1)


def _allowed_targets(status: ImportWarningTrackingStatus, actor: str) -> frozenset[ImportWarningTrackingStatus]:
    if status in {ImportWarningTrackingStatus.CLOSED, ImportWarningTrackingStatus.AUTO_RESOLVED}:
        return frozenset()
    if actor == "system":
        return frozenset({ImportWarningTrackingStatus.CLOSED, ImportWarningTrackingStatus.AUTO_RESOLVED})
    targets = {
        ImportWarningTrackingStatus.OPEN: {ImportWarningTrackingStatus.AWAITING_EXTERNAL_CONFIRMATION},
        ImportWarningTrackingStatus.AWAITING_EXTERNAL_CONFIRMATION: {ImportWarningTrackingStatus.RESPONSE_RECORDED},
        ImportWarningTrackingStatus.RESPONSE_RECORDED: {ImportWarningTrackingStatus.REIMPORT_REQUESTED},
        ImportWarningTrackingStatus.REIMPORT_REQUESTED: set(),
    }
    return frozenset({*targets.get(status, set()), ImportWarningTrackingStatus.CLOSED})


def _occurrence_identity(lane: str, source: str, code: str, path: str) -> str:
    payload = json.dumps([lane, source, code, path], ensure_ascii=False, separators=(",", ":"))
    return f"import-warning:{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"


def _canonical_issue_codes(issue_codes: tuple[str, ...]) -> tuple[str, ...]:
    values = tuple(sorted({_require_text(code, "issue code") for code in issue_codes}))
    if not values:
        raise ValueError("issue codes must not be empty")
    return values


def _require_logical_code(value: str) -> str:
    code = _require_text(value, "logical code")
    if not _LOGICAL_CODE.fullmatch(code):
        raise ValueError("logical code is invalid")
    return code


def _require_lane(value: str) -> str:
    lane = _require_text(value, "owning lane")
    if not _LANE_NAME.fullmatch(lane):
        raise ValueError("owning lane is invalid")
    return lane


def _require_text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    return value.strip()


def _require_version(value: int) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise WarningTransitionError("current version must be positive")


__all__ = [
    "ImportWarningOccurrence",
    "ImportWarningTrackingStatus",
    "UnknownImportWarningIssueError",
    "WarningTransitionError",
    "WarningTransitionPreview",
    "build_import_warning_occurrence",
    "preview_warning_transition",
]
