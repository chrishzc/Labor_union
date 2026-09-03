"""Staff-owned Preview -> Apply command for the six roster case-preference topics."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Literal, Protocol

from shared_kernel.validation import require_positive_integer


TopicKey = Literal[
    "service_regions",
    "service_periods",
    "rest_schedule",
    "baby_counts",
    "holiday_availability",
    "transportation",
]

_TOPIC_KEYS: tuple[TopicKey, ...] = (
    "service_regions",
    "service_periods",
    "rest_schedule",
    "baby_counts",
    "holiday_availability",
    "transportation",
)


class StaffCasePreferenceCommandError(ValueError):
    """Base error for the bounded six-topic mutation."""


class StaffCasePreferenceNotFoundError(StaffCasePreferenceCommandError):
    pass


class StaffCasePreferenceValidationError(StaffCasePreferenceCommandError):
    pass


class StaffCasePreferenceStaleError(StaffCasePreferenceCommandError):
    pass


class StaffCasePreferencePersistenceError(StaffCasePreferenceCommandError):
    pass


@dataclass(frozen=True, slots=True)
class PreferenceTopicDraft:
    values: tuple[str, ...] = ()
    other_detail: str | None = None


@dataclass(frozen=True, slots=True)
class StaffCasePreferenceSnapshot:
    service_regions: PreferenceTopicDraft
    service_periods: PreferenceTopicDraft
    rest_schedule: PreferenceTopicDraft
    baby_counts: PreferenceTopicDraft
    holiday_availability: PreferenceTopicDraft
    transportation: PreferenceTopicDraft


@dataclass(frozen=True, slots=True)
class StaffCasePreferencePreview:
    staff_id: int
    expected_fingerprint: str
    preview_fingerprint: str
    changed_topics: tuple[TopicKey, ...]
    snapshot: StaffCasePreferenceSnapshot


@dataclass(frozen=True, slots=True)
class StaffCasePreferenceApplyRequest:
    staff_id: int
    snapshot: StaffCasePreferenceSnapshot
    expected_fingerprint: str
    preview_fingerprint: str


@dataclass(frozen=True, slots=True)
class StaffCasePreferenceReceipt:
    staff_id: int
    outcome: Literal["applied", "already_observed"]
    snapshot_fingerprint: str
    changed_topics: tuple[TopicKey, ...]


class StaffCasePreferenceCommandRepository(Protocol):
    def begin(self) -> None: ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...
    def load(self, staff_id: int, *, lock: bool) -> StaffCasePreferenceSnapshot | None: ...
    def replace(self, staff_id: int, snapshot: StaffCasePreferenceSnapshot) -> None: ...


class StaffCasePreferenceCommandApplication:
    """Mutate only the six canonical Staff relation topics consumed by the roster."""

    def __init__(self, repository: StaffCasePreferenceCommandRepository) -> None:
        self._repository = repository

    def preview(
        self,
        staff_id: int,
        snapshot: StaffCasePreferenceSnapshot,
    ) -> StaffCasePreferencePreview:
        require_positive_integer(staff_id, "staff case preference staff_id")
        proposed = normalize_snapshot(snapshot)
        current = self._repository.load(staff_id, lock=False)
        if current is None:
            raise StaffCasePreferenceNotFoundError("staff_not_found")
        current = normalize_snapshot(current)
        expected_fingerprint = snapshot_fingerprint(current)
        return StaffCasePreferencePreview(
            staff_id=staff_id,
            expected_fingerprint=expected_fingerprint,
            preview_fingerprint=preview_fingerprint(
                staff_id,
                expected_fingerprint,
                proposed,
            ),
            changed_topics=changed_topics(current, proposed),
            snapshot=proposed,
        )

    def apply(
        self,
        request: StaffCasePreferenceApplyRequest,
    ) -> StaffCasePreferenceReceipt:
        require_positive_integer(request.staff_id, "staff case preference staff_id")
        proposed = normalize_snapshot(request.snapshot)
        expected_preview = preview_fingerprint(
            request.staff_id,
            request.expected_fingerprint,
            proposed,
        )
        if request.preview_fingerprint != expected_preview:
            raise StaffCasePreferenceStaleError("stale_preview")

        self._repository.begin()
        try:
            current = self._repository.load(request.staff_id, lock=True)
            if current is None:
                raise StaffCasePreferenceNotFoundError("staff_not_found")
            current = normalize_snapshot(current)
            current_fingerprint = snapshot_fingerprint(current)
            target_fingerprint = snapshot_fingerprint(proposed)

            if current_fingerprint == target_fingerprint:
                self._repository.commit()
                return StaffCasePreferenceReceipt(
                    staff_id=request.staff_id,
                    outcome="already_observed",
                    snapshot_fingerprint=target_fingerprint,
                    changed_topics=(),
                )

            if current_fingerprint != request.expected_fingerprint:
                raise StaffCasePreferenceStaleError("stale_snapshot")

            changed = changed_topics(current, proposed)
            self._repository.replace(request.staff_id, proposed)
            observed = self._repository.load(request.staff_id, lock=True)
            if observed is None or snapshot_fingerprint(normalize_snapshot(observed)) != target_fingerprint:
                raise StaffCasePreferencePersistenceError("staff_case_preference_readback_mismatch")
            self._repository.commit()
            return StaffCasePreferenceReceipt(
                staff_id=request.staff_id,
                outcome="applied",
                snapshot_fingerprint=target_fingerprint,
                changed_topics=changed,
            )
        except Exception:
            self._repository.rollback()
            raise


def normalize_snapshot(snapshot: StaffCasePreferenceSnapshot) -> StaffCasePreferenceSnapshot:
    return StaffCasePreferenceSnapshot(
        service_regions=_normalize_topic(snapshot.service_regions, allow_other=True),
        service_periods=_normalize_topic(snapshot.service_periods, allow_other=True),
        rest_schedule=_normalize_topic(snapshot.rest_schedule, allow_other=True),
        baby_counts=_normalize_topic(snapshot.baby_counts, allow_other=True),
        holiday_availability=_normalize_topic(snapshot.holiday_availability, allow_other=True),
        transportation=_normalize_topic(snapshot.transportation, allow_other=False),
    )


def snapshot_fingerprint(snapshot: StaffCasePreferenceSnapshot) -> str:
    payload = {
        key: {
            "values": list(getattr(snapshot, key).values),
            "other_detail": getattr(snapshot, key).other_detail,
        }
        for key in _TOPIC_KEYS
    }
    return _fingerprint(payload)


def preview_fingerprint(
    staff_id: int,
    expected_fingerprint: str,
    snapshot: StaffCasePreferenceSnapshot,
) -> str:
    return _fingerprint(
        {
            "staff_id": staff_id,
            "expected_fingerprint": expected_fingerprint,
            "snapshot_fingerprint": snapshot_fingerprint(snapshot),
        }
    )


def changed_topics(
    before: StaffCasePreferenceSnapshot,
    after: StaffCasePreferenceSnapshot,
) -> tuple[TopicKey, ...]:
    return tuple(key for key in _TOPIC_KEYS if getattr(before, key) != getattr(after, key))


def _normalize_topic(
    topic: PreferenceTopicDraft,
    *,
    allow_other: bool,
) -> PreferenceTopicDraft:
    values: set[str] = set()
    for raw_value in topic.values:
        value = _required_text(raw_value, "case preference value")
        if value == "其他":
            raise StaffCasePreferenceValidationError(
                "'其他' 必須透過同母題 other_detail 傳入。"
            )
        values.add(value)
    other_detail = _optional_text(topic.other_detail)
    if not allow_other and other_detail is not None:
        raise StaffCasePreferenceValidationError(
            "transportation_other_source_not_ready"
        )
    return PreferenceTopicDraft(tuple(sorted(values)), other_detail)


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise StaffCasePreferenceValidationError(f"{field} 必須是字串。")
    text = value.strip()
    if not text:
        raise StaffCasePreferenceValidationError(f"{field} 不得為空。")
    if len(text) > 191:
        raise StaffCasePreferenceValidationError(f"{field} 不得超過 191 字元。")
    return text


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    return _required_text(value, "case preference other_detail")


def _fingerprint(payload: object) -> str:
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(serialized).hexdigest()


__all__ = [
    "PreferenceTopicDraft",
    "StaffCasePreferenceApplyRequest",
    "StaffCasePreferenceCommandApplication",
    "StaffCasePreferenceCommandError",
    "StaffCasePreferenceCommandRepository",
    "StaffCasePreferenceNotFoundError",
    "StaffCasePreferencePersistenceError",
    "StaffCasePreferencePreview",
    "StaffCasePreferenceReceipt",
    "StaffCasePreferenceSnapshot",
    "StaffCasePreferenceStaleError",
    "StaffCasePreferenceValidationError",
    "TopicKey",
    "changed_topics",
    "normalize_snapshot",
    "preview_fingerprint",
    "snapshot_fingerprint",
]
