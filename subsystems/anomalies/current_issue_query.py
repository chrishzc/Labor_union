"""Bounded, signed-cursor query for the canonical current anomaly projection."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import base64
import hashlib
import hmac
import json
from typing import Protocol

from domains.anomalies.current_issue import CurrentIssueProjection


@dataclass(frozen=True, slots=True)
class CurrentIssueListRequest:
    definition_code: str | None = None
    owner_domain: str | None = None
    blocking: bool | None = None
    limit: int = 50
    cursor: str | None = None

    def __post_init__(self) -> None:
        for value, name in (
            (self.definition_code, "definition_code"),
            (self.owner_domain, "owner_domain"),
        ):
            if value is not None and (
                not isinstance(value, str)
                or not value.strip()
                or value != value.strip()
                or len(value) > 191
            ):
                raise ValueError(f"anomaly {name} filter is invalid")
        if self.blocking is not None and not isinstance(self.blocking, bool):
            raise ValueError("anomaly blocking filter is invalid")
        if isinstance(self.limit, bool) or not isinstance(self.limit, int) or not 1 <= self.limit <= 100:
            raise ValueError("anomaly limit is invalid")
        if self.cursor is not None and (
            not isinstance(self.cursor, str) or not self.cursor or len(self.cursor) > 2048
        ):
            raise ValueError("anomaly_cursor_invalid")


@dataclass(frozen=True, slots=True)
class CurrentIssueSummary:
    issue_key: str
    definition_code: str
    owner_domain: str
    severity: str
    blocking: bool
    episode_started_at: datetime
    last_verified_at: datetime


@dataclass(frozen=True, slots=True)
class CurrentIssuePage:
    items: tuple[CurrentIssueSummary, ...]
    next_cursor: str | None


class CurrentIssueQueryRepository(Protocol):
    def query_current_page(
        self,
        request: CurrentIssueListRequest,
        after: tuple[int, int, datetime, str] | None,
        fetch_limit: int,
    ) -> tuple[CurrentIssueProjection, ...]: ...


class CurrentIssueCursorCodec:
    def __init__(self, secret: str | bytes) -> None:
        rendered = secret.encode("utf-8") if isinstance(secret, str) else secret
        if not isinstance(rendered, bytes) or len(rendered) < 32:
            raise ValueError("anomaly cursor signing key is unavailable")
        self._secret = rendered

    def encode(
        self,
        request: CurrentIssueListRequest,
        last: CurrentIssueProjection,
    ) -> str:
        candidate = last.candidate
        payload = {
            "v": 1,
            "filters": _filter_payload(request),
            "limit": request.limit,
            "last": [
                int(candidate.blocking),
                _severity_rank(candidate.severity),
                _canonical_datetime(last.episode_started_at),
                last.issue_key,
            ],
        }
        encoded = _b64(_canonical_json(payload))
        signature = _b64(hmac.new(self._secret, encoded.encode("ascii"), hashlib.sha256).digest())
        return encoded + "." + signature

    def decode(
        self,
        request: CurrentIssueListRequest,
    ) -> tuple[int, int, datetime, str] | None:
        if request.cursor is None:
            return None
        try:
            encoded, supplied_signature = request.cursor.split(".", 1)
            expected = _b64(
                hmac.new(self._secret, encoded.encode("ascii"), hashlib.sha256).digest()
            )
            if not hmac.compare_digest(supplied_signature, expected):
                raise ValueError
            payload = json.loads(_unb64(encoded).decode("utf-8"))
            if payload.get("v") != 1:
                raise ValueError
            if payload.get("filters") != _filter_payload(request):
                raise ValueError
            if payload.get("limit") != request.limit:
                raise ValueError
            last = payload.get("last")
            if not isinstance(last, list) or len(last) != 4:
                raise ValueError
            blocking, severity_rank, episode_started_at, issue_key = last
            if blocking not in (0, 1) or severity_rank not in (1, 2):
                raise ValueError
            if not isinstance(issue_key, str) or not issue_key.startswith("ci_"):
                raise ValueError
            parsed = datetime.fromisoformat(episode_started_at)
            if parsed.tzinfo is None:
                raise ValueError
            return blocking, severity_rank, parsed, issue_key
        except (AttributeError, UnicodeDecodeError, ValueError, json.JSONDecodeError) as error:
            raise ValueError("anomaly_cursor_invalid") from error


class CurrentIssueQueryApplication:
    def __init__(
        self,
        repository: CurrentIssueQueryRepository,
        cursor_codec: CurrentIssueCursorCodec,
    ) -> None:
        self._repository = repository
        self._cursor_codec = cursor_codec

    def query(self, request: CurrentIssueListRequest) -> CurrentIssuePage:
        after = self._cursor_codec.decode(request)
        rows = self._repository.query_current_page(request, after, request.limit + 1)
        visible = rows[: request.limit]
        next_cursor = None
        if len(rows) > request.limit and visible:
            next_cursor = self._cursor_codec.encode(request, visible[-1])
        return CurrentIssuePage(
            tuple(
                CurrentIssueSummary(
                    item.issue_key,
                    item.candidate.definition_code,
                    item.candidate.owner_domain,
                    item.candidate.severity,
                    item.candidate.blocking,
                    item.episode_started_at,
                    item.last_verified_at,
                )
                for item in visible
            ),
            next_cursor,
        )


def _filter_payload(request: CurrentIssueListRequest) -> dict[str, object]:
    return {
        "blocking": request.blocking,
        "definition_code": request.definition_code,
        "owner_domain": request.owner_domain,
    }


def _severity_rank(value: str) -> int:
    ranks = {"warning": 1, "blocking": 2}
    try:
        return ranks[value]
    except KeyError as error:
        raise ValueError("anomaly projection severity is invalid") from error


def _canonical_datetime(value: datetime) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError("anomaly projection timestamp is invalid")
    return value.isoformat()


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


__all__ = [
    "CurrentIssueCursorCodec",
    "CurrentIssueListRequest",
    "CurrentIssuePage",
    "CurrentIssueQueryApplication",
    "CurrentIssueQueryRepository",
    "CurrentIssueSummary",
]
