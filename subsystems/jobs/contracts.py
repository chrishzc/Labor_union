"""
File: contracts.py
Description: 定義 Durable Job canonical equality、提交者、衝突與封閉 terminal outcome 契約。
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from typing import Any, Mapping

from shared_kernel.errors import TypedError


COMMAND_KEY_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._:-]{0,190}$")
SYSTEM_ACTOR_PATTERN = re.compile(r"^system:[a-z0-9][a-z0-9._:-]{0,190}$")
ADMIN_ACTOR_PATTERN = re.compile(r"^admin_user_id:[1-9][0-9]*$")
TERMINAL_OUTCOME_SCHEMA_VERSION = 1


class DurableJobContractViolation(ValueError):
    """Canonical durable command input or stored state is invalid."""


class DurableJobCommandConflict(RuntimeError):
    """The same canonical key already represents a different command equality."""

    code = "durable_job_command_conflict"

    def __init__(self, job_id: str, mismatched_fields: tuple[str, ...]):
        self.job_id = job_id
        self.mismatched_fields = mismatched_fields
        super().__init__(self.code)


@dataclass(frozen=True, slots=True)
class CanonicalCommandEquality:
    command_type: str
    command_version: int
    canonical_payload: str
    submitted_by: str


@dataclass(frozen=True, slots=True)
class DurableJobSuccessOutcome:
    result_reference: str
    schema_version: int = TERMINAL_OUTCOME_SCHEMA_VERSION
    kind: str = "success"

    def __post_init__(self) -> None:
        if self.schema_version != TERMINAL_OUTCOME_SCHEMA_VERSION:
            raise DurableJobContractViolation("unsupported terminal outcome schema version")
        if self.kind != "success" or not _is_bounded_text(self.result_reference, 191):
            raise DurableJobContractViolation("invalid durable job result reference")

    def to_payload(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "result_reference": self.result_reference,
            "schema_version": self.schema_version,
        }


@dataclass(frozen=True, slots=True)
class DurableJobFailureOutcome:
    category: str
    code: str
    message: str
    retryable: bool = False
    correlation_id: str | None = None
    domain_blockers: tuple[str, ...] = ()
    schema_version: int = TERMINAL_OUTCOME_SCHEMA_VERSION
    kind: str = "failure"

    def __post_init__(self) -> None:
        if self.schema_version != TERMINAL_OUTCOME_SCHEMA_VERSION:
            raise DurableJobContractViolation("unsupported terminal outcome schema version")
        if self.kind != "failure":
            raise DurableJobContractViolation("invalid durable job failure kind")
        if not all(
            (
                _is_bounded_text(self.category, 64),
                _is_bounded_text(self.code, 128),
                _is_bounded_text(self.message, 512),
            )
        ):
            raise DurableJobContractViolation("invalid durable job failure payload")
        if self.correlation_id is not None and not _is_bounded_text(self.correlation_id, 255):
            raise DurableJobContractViolation("invalid durable job correlation identity")
        if any(not _is_bounded_text(blocker, 255) for blocker in self.domain_blockers):
            raise DurableJobContractViolation("invalid durable job domain blocker")

    @classmethod
    def from_typed_error(cls, error: TypedError) -> DurableJobFailureOutcome:
        return cls(
            category=error.category.value,
            code=error.code,
            message=error.message,
            retryable=error.retryable,
            correlation_id=error.correlation_id.value,
            domain_blockers=tuple(error.domain_blockers),
        )

    def to_payload(self) -> dict[str, Any]:
        error: dict[str, Any] = {
            "category": self.category,
            "code": self.code,
            "domain_blockers": list(self.domain_blockers),
            "message": self.message,
            "retryable": self.retryable,
        }
        if self.correlation_id is not None:
            error["correlation_id"] = self.correlation_id
        return {
            "error": error,
            "kind": self.kind,
            "schema_version": self.schema_version,
        }


def validate_command_key(value: str) -> str:
    if not isinstance(value, str) or COMMAND_KEY_PATTERN.fullmatch(value) is None:
        raise DurableJobContractViolation("invalid canonical durable command key")
    return value


def validate_submitted_by(value: str) -> str:
    if not isinstance(value, str) or len(value) > 191 or not (
        ADMIN_ACTOR_PATTERN.fullmatch(value) or SYSTEM_ACTOR_PATTERN.fullmatch(value)
    ):
        raise DurableJobContractViolation("invalid immutable durable command actor")
    return value


def canonicalize_payload(payload: Mapping[str, Any]) -> str:
    if not isinstance(payload, dict):
        raise DurableJobContractViolation("durable command payload must be a JSON object")
    _validate_json_value(payload)
    try:
        return json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as error:
        raise DurableJobContractViolation("durable command payload is not canonical JSON") from error


def parse_canonical_payload(value: Any) -> dict[str, Any]:
    if isinstance(value, bytes):
        value = value.decode("utf-8")
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise DurableJobContractViolation("stored durable command payload is invalid JSON") from error
    else:
        parsed = value
    if not isinstance(parsed, dict):
        raise DurableJobContractViolation("stored durable command payload must be an object")
    canonicalize_payload(parsed)
    return parsed


def equality_for(
    command_type: str,
    command_version: int,
    payload: Mapping[str, Any],
    submitted_by: str,
) -> CanonicalCommandEquality:
    if not _is_bounded_text(command_type, 191):
        raise DurableJobContractViolation("invalid durable command type")
    if isinstance(command_version, bool) or not isinstance(command_version, int) or command_version < 1:
        raise DurableJobContractViolation("invalid durable command version")
    return CanonicalCommandEquality(
        command_type,
        command_version,
        canonicalize_payload(payload),
        validate_submitted_by(submitted_by),
    )


def equality_mismatches(
    requested: CanonicalCommandEquality,
    stored: CanonicalCommandEquality,
) -> tuple[str, ...]:
    return tuple(
        field
        for field in ("command_type", "command_version", "canonical_payload", "submitted_by")
        if getattr(requested, field) != getattr(stored, field)
    )


def _validate_json_value(value: Any) -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise DurableJobContractViolation("durable command payload contains a non-finite number")
        return
    if isinstance(value, list):
        for item in value:
            _validate_json_value(item)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise DurableJobContractViolation("durable command payload keys must be strings")
            _validate_json_value(item)
        return
    raise DurableJobContractViolation("durable command payload contains a non-JSON value")


def _is_bounded_text(value: Any, maximum: int) -> bool:
    return isinstance(value, str) and bool(value) and len(value) <= maximum
