"""Load only the approved contract templates and their immutable digests."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_DIRECTORY = PROJECT_ROOT / "db" / "templates" / "contracts"
_APPROVED_TEMPLATE_KEYS = frozenset({"contract_staff_service", "contract_client_copy"})


@dataclass(frozen=True, slots=True)
class ContractTemplateVersion:
    template_key: str
    display_name: str
    template_filename: str
    template_sha256: str
    mapping_sha256: str


def load_approved_template(template_key: str) -> ContractTemplateVersion:
    normalized_key = _require_approved_template_key(template_key)
    mapping_path = TEMPLATE_DIRECTORY / f"{normalized_key}.json"
    mapping_bytes = mapping_path.read_bytes()
    mapping = json.loads(mapping_bytes.decode("utf-8"))
    _validate_mapping(normalized_key, mapping)
    template_path = TEMPLATE_DIRECTORY / str(mapping["template_filename"])
    return ContractTemplateVersion(
        template_key=normalized_key,
        display_name=str(mapping["name"]),
        template_filename=template_path.name,
        template_sha256=_sha256(template_path.read_bytes()),
        mapping_sha256=_sha256(mapping_bytes),
    )


def approved_template_mapping_path(template_key: str) -> Path:
    normalized_key = _require_approved_template_key(template_key)
    return TEMPLATE_DIRECTORY / f"{normalized_key}.json"


def _require_approved_template_key(template_key: str) -> str:
    normalized_key = template_key.strip() if isinstance(template_key, str) else ""
    if normalized_key not in _APPROVED_TEMPLATE_KEYS:
        raise ValueError("contract template is not approved")
    return normalized_key


def _validate_mapping(template_key: str, mapping: object) -> None:
    if not isinstance(mapping, dict) or mapping.get("id") != template_key:
        raise ValueError("contract template mapping identity is invalid")
    if not isinstance(mapping.get("name"), str) or not mapping["name"].strip():
        raise ValueError("contract template name is invalid")
    filename = mapping.get("template_filename")
    if not isinstance(filename, str) or not filename.strip():
        raise ValueError("contract template filename is invalid")
    path = TEMPLATE_DIRECTORY / filename
    if not path.is_file():
        raise ValueError("contract template artifact is missing")
    if template_key == "contract_client_copy":
        _validate_client_precontract_mappings(mapping)


def _validate_client_precontract_mappings(mapping: dict[object, object]) -> None:
    expected = {
        "B7": "contract_signed_date",
        "B24": "committed_service_start_date",
        "D24": "committed_service_end_date",
        "B185": "contract_signed_date",
    }
    fields = mapping.get("param_mappings")
    if not isinstance(fields, dict):
        raise ValueError("contract template parameter mappings are invalid")
    actual = {cell: _mapping_key(fields.get(cell)) for cell in expected}
    if actual != expected:
        raise ValueError("client contract must use precontract service facts")


def _mapping_key(field: object) -> object:
    return field.get("db_key") if isinstance(field, dict) else None


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()
