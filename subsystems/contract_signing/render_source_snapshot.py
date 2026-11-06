"""Contract-owned reproducible source versions; never persist draft file bytes."""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
import hashlib
from io import BytesIO
import json
import math
from pathlib import Path
from typing import Callable, Mapping, Protocol
from xml.dom.minidom import parseString
from xml.parsers.expat import ExpatError
from zipfile import BadZipFile, ZIP_DEFLATED, ZipFile, ZipInfo

from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from domains.contract_signing.template_management import TemplateManagementError
from shared_kernel.validation import require_canonical_text, require_positive_integer, require_sha256_hex
from subsystems.contract_signing.contract_renderer import ContractRendererError, render_contract_template
from subsystems.contract_signing.template_catalog import TEMPLATE_DIRECTORY, approved_template_mapping_path
from subsystems.contract_signing.unsigned_contract_pdf import UnsignedContractPdfError, _require_persisted_actor


SCHEMA = "contract-render-source.v1"
SERIALIZATION = "canonical-xlsx-zip.v1"
SOURCE_FIELDS = frozenset({"case_no", "document_scope", "matching_plan_id", "matching_segment_id",
    "document_target_key", "template_key", "template_sha256", "mapping_sha256", "facts_snapshot_sha256"})


def _error(code):
    return UnsignedContractPdfError(category="conflict", code=code,
        message="契約來源快照或核准模板不一致，請重新讀取目前契約資料。")


def canonical_json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _encode(value):
    if value is None: kind, stored = "null", None
    elif type(value) is bool: kind, stored = "bool", value
    elif type(value) is int: kind, stored = "int", str(value)
    elif type(value) is float and math.isfinite(value): kind, stored = "float", value.hex()
    elif type(value) is str: kind, stored = "str", value
    elif isinstance(value, Decimal) and value.is_finite(): kind, stored = "decimal", str(value)
    elif isinstance(value, datetime): kind, stored = "datetime", value.isoformat()
    elif isinstance(value, date): kind, stored = "date", value.isoformat()
    elif type(value) in {list, tuple}: kind, stored = type(value).__name__, [_encode(item) for item in value]
    elif type(value) is dict and all(type(key) is str for key in value):
        kind, stored = "dict", {key: _encode(item) for key, item in value.items()}
    else: raise _error("contract_render_snapshot_value_invalid")
    return {"type": kind, "value": stored}


def _decode(value):
    if not isinstance(value, dict) or set(value) != {"type", "value"}: raise ValueError("typed value")
    kind, raw = value["type"], value["value"]
    if kind == "null" and raw is None: result = None
    elif kind == "bool" and type(raw) is bool: result = raw
    elif kind == "str" and type(raw) is str: result = raw
    elif kind == "int" and type(raw) is str: result = int(raw)
    elif kind == "float" and type(raw) is str: result = float.fromhex(raw)
    elif kind == "decimal" and type(raw) is str: result = Decimal(raw)
    elif kind == "date" and type(raw) is str: result = date.fromisoformat(raw)
    elif kind == "datetime" and type(raw) is str: result = datetime.fromisoformat(raw)
    elif kind in {"list", "tuple"} and type(raw) is list:
        result = [_decode(item) for item in raw]
        if kind == "tuple": result = tuple(result)
    elif kind == "dict" and type(raw) is dict:
        result = {key: _decode(item) for key, item in raw.items()}
    else: raise ValueError("unknown typed value")
    if _encode(result) != value: raise ValueError("noncanonical typed value")
    return result


def canonical_xlsx(content: bytes) -> bytes:
    """New snapshot sources only: normalize ZIP metadata and OOXML clock metadata."""
    output = BytesIO()
    with ZipFile(BytesIO(content)) as original, ZipFile(output, "w", compression=ZIP_DEFLATED, compresslevel=9) as target:
        names = original.namelist()
        if len(names) != len(set(names)): raise _error("contract_render_snapshot_archive_invalid")
        for name in sorted(names):
            payload = original.read(name)
            if name == "docProps/core.xml":
                document = parseString(payload)
                for local in ("created", "modified"):
                    for element in document.getElementsByTagNameNS("http://purl.org/dc/terms/", local):
                        while element.firstChild is not None: element.removeChild(element.firstChild)
                        element.appendChild(document.createTextNode("1980-01-01T00:00:00Z"))
                # Preserve namespace declarations and QName-valued xsi:type.
                payload = document.toxml(encoding="utf-8")
                document.unlink()
            entry = ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            entry.compress_type = ZIP_DEFLATED
            entry.create_system = 0
            target.writestr(entry, payload, compresslevel=9)
    return output.getvalue()


def _render(source, facts, template):
    template_path = template.template_path or TEMPLATE_DIRECTORY / template.template_filename
    mapping_path = template.mapping_path or approved_template_mapping_path(template.template_key)
    try:
        if (template.template_key != source["template_key"]
            or hashlib.sha256(Path(template_path).read_bytes()).hexdigest() != source["template_sha256"]
            or hashlib.sha256(Path(mapping_path).read_bytes()).hexdigest() != source["mapping_sha256"]):
            raise _error("contract_render_snapshot_template_stale")
        return canonical_xlsx(render_contract_template(template_path=template_path, mapping_path=mapping_path, facts=facts))
    except ContractRendererError as error:
        raise UnsignedContractPdfError(category="unavailable" if error.retryable else "domain_blocked",
            code=error.code, message="契約來源目前無法重建。", retryable=error.retryable) from None
    except OSError:
        raise UnsignedContractPdfError(category="unavailable", code="contract_render_snapshot_template_unavailable",
            message="核准契約模板目前無法讀取。", retryable=True) from None
    except (ValueError, KeyError):
        raise _error("contract_render_snapshot_template_invalid") from None
    except (BadZipFile, ExpatError):
        raise UnsignedContractPdfError(category="domain_blocked", code="contract_render_snapshot_content_invalid",
            message="契約來源格式不正確，無法重建。") from None


def load_snapshot_template(row, catalog=None):
    from subsystems.contract_signing.template_catalog import load_approved_template
    try:
        return (catalog.load_exact(row["template_key"], row["template_sha256"], row["mapping_sha256"])
                if catalog is not None else load_approved_template(row["template_key"]))
    except TemplateManagementError as error:
        raise UnsignedContractPdfError(category=error.category, code=error.code,
            message="文件引用的核准模板目前無法使用。", retryable=error.category == "unavailable") from None
    except OSError:
        raise UnsignedContractPdfError(category="unavailable", code="contract_render_snapshot_template_unavailable",
            message="核准契約模板目前無法讀取。", retryable=True) from None
    except (ValueError, KeyError):
        raise _error("contract_render_snapshot_template_invalid") from None


@dataclass(frozen=True, slots=True)
class ContractRenderSnapshot:
    payload: str
    snapshot_sha256: str
    source_sha256: str
    source_size_bytes: int


def create_render_snapshot(source: Mapping[str, object], facts: Mapping[str, object], template) -> ContractRenderSnapshot:
    if set(source) != SOURCE_FIELDS: raise _error("contract_render_snapshot_source_invalid")
    value = {"schema": SCHEMA, "serialization": SERIALIZATION, "source": dict(source),
        "facts": {key: _encode(item) for key, item in facts.items()}}
    payload = canonical_json(value)
    content = _render(value["source"], {key: _decode(item) for key, item in value["facts"].items()}, template)
    return ContractRenderSnapshot(payload, hashlib.sha256(payload.encode()).hexdigest(),
        hashlib.sha256(content).hexdigest(), len(content))


def rebuild_render_snapshot(row: Mapping[str, object], template) -> bytes:
    try:
        value = row["render_source_snapshot"]
        value = json.loads(value) if isinstance(value, (str, bytes)) else value
        if set(value) != {"schema", "serialization", "source", "facts"} or value["schema"] != SCHEMA or value["serialization"] != SERIALIZATION:
            raise ValueError("snapshot schema")
        if (set(value["source"]) != SOURCE_FIELDS
            or canonical_json(value["source"]) != canonical_json({key: row[key] for key in SOURCE_FIELDS})):
            raise ValueError("snapshot lineage")
        if hashlib.sha256(canonical_json(value).encode()).hexdigest() != row["render_source_snapshot_sha256"]:
            raise ValueError("snapshot digest")
        facts = {key: _decode(item) for key, item in value["facts"].items()}
        content = _render(value["source"], facts, template)
        if (hashlib.sha256(content).hexdigest() != row["render_source_sha256"]
            or len(content) != row["render_source_size_bytes"]): raise ValueError("source digest/size")
        return content
    except UnsignedContractPdfError: raise
    except (TypeError, ValueError, KeyError, AttributeError, ArithmeticError):
        raise _error("contract_render_snapshot_invalid") from None


@dataclass(frozen=True, slots=True)
class RenderSourceRequest:
    case_no: str
    document_scope: str
    matching_segment_id: int | None
    actor: ActorContext
    idempotency_key: IdempotencyKey
    correlation_id: CorrelationId
    operation: str = "prepare"

    def __post_init__(self):
        require_canonical_text(self.case_no, "case number", 50)
        _require_persisted_actor(self.actor)
        if not isinstance(self.idempotency_key, IdempotencyKey) or not isinstance(self.correlation_id, CorrelationId):
            raise TypeError("source command identity is invalid")
        if self.document_scope not in {"client_contract", "staff_segment"}:
            raise ValueError("unknown render source scope")
        if self.document_scope == "staff_segment":
            require_positive_integer(self.matching_segment_id, "matching segment")
        elif self.matching_segment_id is not None:
            raise ValueError("client source must not specify staff segment")
        if self.operation not in {"prepare", "send"}: raise ValueError("unknown source operation")

    @property
    def identity(self):
        return {"case_no": self.case_no, "document_scope": self.document_scope,
            "matching_segment_id": self.matching_segment_id,
            "document_target_key": "client-contract" if self.document_scope == "client_contract" else f"staff-segment:{self.matching_segment_id}"}

    @property
    def receipt_identity(self):
        return {**self.identity, "actor_id": self.actor.actor_id, "operation": self.operation}


class RenderSourceRepository(Protocol):
    def find_preparation(self, request: RenderSourceRequest): ...
    def find_matching_source(self, source, snapshot: ContractRenderSnapshot) -> int | None: ...
    def append_source(self, request: RenderSourceRequest, source, snapshot: ContractRenderSnapshot) -> int: ...
    def save_preparation(self, request: RenderSourceRequest, document_id: int) -> None: ...


class RenderSourceWorkflow:
    """Borrow the original Contract Signing transaction; no commit or storage effects."""
    def __init__(self, repository: RenderSourceRepository): self._repository = repository

    def prepare(self, request: RenderSourceRequest, load_current: Callable):
        stored = self._repository.find_preparation(request)
        if stored is not None:
            if stored["request"] != request.receipt_identity: raise _error("contract_unsigned_source_idempotency_conflict")
            require_positive_integer(stored["document_version_id"], "source version")
            return stored["document_version_id"], True
        plan_id, template, facts, facts_sha256 = load_current()
        require_positive_integer(plan_id, "matching plan")
        require_sha256_hex(facts_sha256, "facts SHA-256")
        expected_template = "contract_client_copy" if request.document_scope == "client_contract" else "contract_staff_service"
        if template.template_key != expected_template: raise _error("contract_render_snapshot_template_scope_mismatch")
        source = {**request.identity, "matching_plan_id": plan_id, "template_key": template.template_key,
            "template_sha256": template.template_sha256, "mapping_sha256": template.mapping_sha256,
            "facts_snapshot_sha256": facts_sha256}
        snapshot = create_render_snapshot(source, facts, template)
        document_id = self._repository.find_matching_source(source, snapshot)
        replayed = document_id is not None
        if document_id is None: document_id = self._repository.append_source(request, source, snapshot)
        require_positive_integer(document_id, "source version")
        self._repository.save_preparation(request, document_id)
        return document_id, replayed
