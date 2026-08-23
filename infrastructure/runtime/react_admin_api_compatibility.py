"""
File: react_admin_api_compatibility.py
Description: 載入並驗證 React 管理端 API compatibility registry、rollover 與 closed slug。
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Mapping


REGISTRY_CONTRACT = "react-admin-api-compatibility/v1"
REGISTRY_FAMILY = "react-admin-api"
REGISTRY_PATH = (
    Path(__file__).resolve().parents[2]
    / "config"
    / "react_admin_api_compatibility.registry.json"
)
SLUG_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{0,95}$")
_DIGEST_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_SENSITIVE_FRAGMENTS = (
    "password",
    "secret",
    "token",
    "api-key",
    "access-token",
    "authorization",
    "bearer",
    "credential",
    "private-key",
)
_TOP_LEVEL_KEYS = {
    "contract",
    "registry_revision",
    "family",
    "active_revision",
    "accepted_revisions",
    "revisions",
    "registry_digest",
}
_REVISION_STATUSES = frozenset({"active", "accepted", "closed"})


class ReactAdminApiCompatibilityError(RuntimeError):
    """拒絕不完整、漂移或不安全的 API compatibility identity。"""


@dataclass(frozen=True, slots=True)
class ApiCompatibilityRevision:
    identity: str
    status: str


@dataclass(frozen=True, slots=True)
class ReactAdminApiCompatibilityRegistry:
    contract: str
    registry_revision: str
    family: str
    active_revision: str
    accepted_revisions: tuple[str, ...]
    revisions: Mapping[str, ApiCompatibilityRevision]
    registry_digest: str

    def require_accepted(self, revision: object) -> str:
        identity = validate_closed_identity(revision, "api compatibility revision")
        if identity not in self.accepted_revisions:
            raise ReactAdminApiCompatibilityError(
                "react admin api compatibility revision is not accepted"
            )
        return identity


def load_react_admin_api_compatibility_registry(
    path: Path = REGISTRY_PATH,
) -> ReactAdminApiCompatibilityRegistry:
    try:
        raw_bytes = path.read_bytes()
        payload = json.loads(raw_bytes.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ReactAdminApiCompatibilityError(
            "react admin api compatibility registry is unreadable"
        ) from error
    return parse_react_admin_api_compatibility_registry(payload)


def parse_react_admin_api_compatibility_registry(
    payload: object,
) -> ReactAdminApiCompatibilityRegistry:
    if not isinstance(payload, dict) or set(payload) != _TOP_LEVEL_KEYS:
        raise ReactAdminApiCompatibilityError(
            "react admin api compatibility registry shape is invalid"
        )
    if payload["contract"] != REGISTRY_CONTRACT or payload["family"] != REGISTRY_FAMILY:
        raise ReactAdminApiCompatibilityError(
            "react admin api compatibility registry contract is invalid"
        )
    registry_revision = validate_closed_identity(
        payload["registry_revision"], "registry revision"
    )
    active_revision = validate_closed_identity(
        payload["active_revision"], "active revision"
    )
    accepted_payload = payload["accepted_revisions"]
    if not isinstance(accepted_payload, list) or not accepted_payload:
        raise ReactAdminApiCompatibilityError(
            "react admin api compatibility accepted revisions are invalid"
        )
    accepted = tuple(
        validate_closed_identity(item, "accepted revision")
        for item in accepted_payload
    )
    if len(set(accepted)) != len(accepted):
        raise ReactAdminApiCompatibilityError(
            "react admin api compatibility accepted revisions are duplicated"
        )
    revisions_payload = payload["revisions"]
    if not isinstance(revisions_payload, dict) or not revisions_payload:
        raise ReactAdminApiCompatibilityError(
            "react admin api compatibility revisions are invalid"
        )
    revisions: dict[str, ApiCompatibilityRevision] = {}
    for raw_identity, raw_metadata in revisions_payload.items():
        identity = validate_closed_identity(raw_identity, "revision identity")
        if (
            not isinstance(raw_metadata, dict)
            or set(raw_metadata) != {"status"}
            or raw_metadata["status"] not in _REVISION_STATUSES
        ):
            raise ReactAdminApiCompatibilityError(
                "react admin api compatibility revision metadata is invalid"
            )
        revisions[identity] = ApiCompatibilityRevision(
            identity=identity,
            status=str(raw_metadata["status"]),
        )
    if not set(accepted).issubset(revisions):
        raise ReactAdminApiCompatibilityError(
            "react admin api compatibility accepted revision is unknown"
        )
    active_rows = {
        identity for identity, metadata in revisions.items() if metadata.status == "active"
    }
    expected_accepted = {
        identity
        for identity, metadata in revisions.items()
        if metadata.status in {"active", "accepted"}
    }
    if active_rows != {active_revision} or set(accepted) != expected_accepted:
        raise ReactAdminApiCompatibilityError(
            "react admin api compatibility rollover state is invalid"
        )
    digest = payload["registry_digest"]
    if not isinstance(digest, str) or _DIGEST_PATTERN.fullmatch(digest) is None:
        raise ReactAdminApiCompatibilityError(
            "react admin api compatibility registry digest is invalid"
        )
    unsigned = dict(payload)
    unsigned.pop("registry_digest")
    if _digest_bytes(_canonical_json(unsigned)) != digest:
        raise ReactAdminApiCompatibilityError(
            "react admin api compatibility registry digest does not match"
        )
    return ReactAdminApiCompatibilityRegistry(
        contract=REGISTRY_CONTRACT,
        registry_revision=registry_revision,
        family=REGISTRY_FAMILY,
        active_revision=active_revision,
        accepted_revisions=accepted,
        revisions=MappingProxyType(revisions),
        registry_digest=digest,
    )


def validate_closed_identity(value: object, field_name: str) -> str:
    if not isinstance(value, str) or SLUG_PATTERN.fullmatch(value) is None:
        raise ReactAdminApiCompatibilityError(
            f"react admin {field_name} is not a closed slug"
        )
    if any(fragment in value for fragment in _SENSITIVE_FRAGMENTS):
        raise ReactAdminApiCompatibilityError(
            f"react admin {field_name} contains a forbidden identity fragment"
        )
    return value


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


__all__ = [
    "ApiCompatibilityRevision",
    "ReactAdminApiCompatibilityError",
    "ReactAdminApiCompatibilityRegistry",
    "REGISTRY_PATH",
    "load_react_admin_api_compatibility_registry",
    "parse_react_admin_api_compatibility_registry",
    "validate_closed_identity",
]
