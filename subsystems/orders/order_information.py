"""Typed Query/Preview contract for the two staff order-information sheets.

The JSON files under ``db/templates/tpl_info_*.json`` are presentation
templates only.  This module owns the bounded projection contract used by the
API and UI; it deliberately has no access to survey JSON or template formulas.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
import hashlib
import json
from pathlib import Path
from typing import Protocol

from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.validation import require_canonical_text, require_positive_integer


TEMPLATE_DIRECTORY = Path(__file__).resolve().parents[2] / "db" / "templates"


class OrderInformationTemplate(StrEnum):
    INFO_01 = "tpl_info_01"
    INFO_02 = "tpl_info_02"


class OrderInformationError(ValueError):
    def __init__(self, code: str, message: str, *, not_found: bool = False) -> None:
        self.code = code
        self.not_found = not_found
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class OrderInformationOwnerSnapshot:
    case_no: str
    assignment_id: int
    facts: Mapping[str, object]
    owner_fingerprints: Mapping[str, str]
    field_issues: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        require_canonical_text(self.case_no, "case number", 50)
        require_positive_integer(self.assignment_id, "assignment id")
        if not isinstance(self.facts, Mapping):
            raise TypeError("order information facts must be a mapping")
        if not isinstance(self.owner_fingerprints, Mapping):
            raise TypeError("order information owner fingerprints must be a mapping")
        if not isinstance(self.field_issues, Mapping):
            raise TypeError("order information field issues must be a mapping")


class OrderInformationRepository(Protocol):
    def load_owner_snapshot(
        self, case_no: str, assignment_id: int | None = None
    ) -> OrderInformationOwnerSnapshot | None: ...


@dataclass(frozen=True, slots=True)
class OrderInformationFieldView:
    field_id: str
    label: str
    owner: str
    source: str | None
    requiredness: str
    status: str
    value: object


@dataclass(frozen=True, slots=True)
class OrderInformationResult:
    template_id: OrderInformationTemplate
    case_no: str
    assignment_id: int
    fields: tuple[OrderInformationFieldView, ...]
    owner_fingerprints: Mapping[str, str]
    blockers: tuple[str, ...]
    preview_fingerprint: PreviewFingerprint

    @property
    def can_render(self) -> bool:
        return not self.blockers


class OrderInformationQueryService:
    """Exact-target, zero-write query and preview for ``tpl_info_01/02``."""

    def __init__(self, repository: OrderInformationRepository) -> None:
        self._repository = repository

    def query(
        self,
        template_id: OrderInformationTemplate | str,
        case_no: str,
        assignment_id: int | None = None,
    ) -> OrderInformationResult:
        return self._build(template_id, case_no, assignment_id)

    def preview(
        self,
        template_id: OrderInformationTemplate | str,
        case_no: str,
        assignment_id: int | None = None,
    ) -> OrderInformationResult:
        return self._build(template_id, case_no, assignment_id)

    def _build(
        self,
        template_id: OrderInformationTemplate | str,
        case_no: str,
        assignment_id: int | None,
    ) -> OrderInformationResult:
        try:
            template = OrderInformationTemplate(template_id)
        except (TypeError, ValueError) as error:
            raise OrderInformationError(
                "order_information_template_not_found",
                "訂單資訊模板不存在。",
                not_found=True,
            ) from error
        canonical_case_no = require_canonical_text(case_no, "case number", 50)
        if assignment_id is not None:
            require_positive_integer(assignment_id, "assignment id")
        snapshot = self._repository.load_owner_snapshot(canonical_case_no, assignment_id)
        if snapshot is None:
            raise OrderInformationError(
                "order_information_target_not_found",
                "找不到指定案件或服務人員指派。",
                not_found=True,
            )
        if snapshot.case_no != canonical_case_no:
            raise OrderInformationError(
                "order_information_target_mismatch",
                "訂單資訊預覽對象身分不一致。",
            )
        if assignment_id is not None and snapshot.assignment_id != assignment_id:
            raise OrderInformationError(
                "order_information_target_mismatch",
                "訂單資訊預覽對象身分不一致。",
            )
        fields, blockers = _project_fields(template, snapshot.facts, snapshot.field_issues)
        fingerprint = fingerprint_payload(
            {
                "template_id": template.value,
                "case_no": snapshot.case_no,
                "assignment_id": snapshot.assignment_id,
                "owner_fingerprints": dict(sorted(snapshot.owner_fingerprints.items())),
                "fields": [
                    {"id": field.field_id, "status": field.status, "value": _fingerprint_value(field.value)}
                    for field in fields
                ],
                "blockers": list(blockers),
            }
        )
        return OrderInformationResult(
            template,
            snapshot.case_no,
            snapshot.assignment_id,
            fields,
            dict(sorted(snapshot.owner_fingerprints.items())),
            blockers,
            fingerprint,
        )


@dataclass(frozen=True, slots=True)
class CandidateInformationPreview:
    case_no: str
    candidate_id: int
    info_type: int
    staff_name: str
    text: str
    preview_fingerprint: str


def build_candidate_information(case_no, candidate_id, info_type, facts, field_issues, recipient_identity):
    """Reuse sheet projection without inventing an assignment or payroll fact."""
    require_canonical_text(case_no, "case number", 50)
    require_positive_integer(candidate_id, "candidate id")
    if info_type not in (1, 2):
        raise ValueError("info_type_invalid")
    template = OrderInformationTemplate.INFO_01 if info_type == 1 else OrderInformationTemplate.INFO_02
    fields, blockers = _project_fields(template, facts, field_issues)
    if "order_information_template_invalid" in blockers:
        raise ValueError("order_information_template_invalid")
    lines = [f"訂單資訊－{info_type}", "初步接案意願詢問；日期為預計期間，未確認需求請再與工會確認。"]
    labels = {"f_104_c4": "預計服務開始日期", "f_105_c5": "預計服務結束日期", "f_106_c6": "每日服務時數"}
    for item in fields:
        value = "待確認" if item.status in {"missing", "unresolved", "absent"} or _is_missing(item.value) else str(_fingerprint_value(item.value))
        lines.append(f"{labels.get(item.field_id, item.label)}：{value}")
    if info_type == 2:
        lines.extend(("食材準備參考（請另確認需求，非全部必購）：",
                      "中藥／食材：四物、四君、四神、枸杞、紅棗、黃耆、杜仲、大豐草、黑豆、紅豆、白木耳、紫米、桂圓肉、米酒、麻油",
                      "肉品：雞腿、雞胸、排骨、豬／牛肉絲、絞肉、雞蛋、魚排",
                      "蔬菜：青菜、紅蘿蔔、薑、香菇、其他菇類、豆製品"))
    text = "\n".join(lines)
    if len(text.encode("utf-16-le")) // 2 > 5000:
        raise ValueError("candidate_information_message_too_long")
    fingerprint = projection_fingerprint({"case_no": case_no, "candidate_id": candidate_id,
                                          "info_type": info_type, "text": text, "recipient": recipient_identity})
    return CandidateInformationPreview(case_no, candidate_id, info_type, str(facts["staff_name"]), text, fingerprint)


def _project_fields(
    template: OrderInformationTemplate,
    facts: Mapping[str, object],
    field_issues: Mapping[str, str],
) -> tuple[tuple[OrderInformationFieldView, ...], tuple[str, ...]]:
    path = TEMPLATE_DIRECTORY / f"{template.value}.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise OrderInformationError(
            "order_information_template_invalid", "訂單資訊模板無法讀取。"
        ) from error
    raw_fields = payload.get("fields") if isinstance(payload, dict) else None
    if not isinstance(raw_fields, list):
        raise OrderInformationError(
            "order_information_template_invalid", "訂單資訊模板欄位不正確。"
        )
    projected: list[OrderInformationFieldView] = []
    blockers: set[str] = set()
    for raw in raw_fields:
        if not isinstance(raw, Mapping):
            blockers.add("order_information_template_invalid")
            continue
        field_id = raw.get("id")
        label = raw.get("label")
        owner = raw.get("owner")
        source = raw.get("source")
        requiredness = raw.get("requiredness")
        status = raw.get("status", "resolved")
        key = raw.get("db_key")
        if (
            not isinstance(field_id, str)
            or not isinstance(label, str)
            or not isinstance(owner, str)
            or (source is not None and not isinstance(source, str))
            or requiredness not in {"required", "conditional", "optional"}
            or status not in {"resolved", "unresolved"}
            or not isinstance(key, str)
        ):
            blockers.add("order_information_template_invalid")
            continue
        value = facts.get(key)
        field_status = status
        issue = field_issues.get(key)
        if issue:
            blockers.add(f"order_information_source_{issue}:{field_id}")
            field_status = "missing"
        elif status == "unresolved":
            blockers.add(f"order_information_source_unresolved:{field_id}")
        elif requiredness == "required" and _is_missing(value):
            blockers.add(f"order_information_required_field_missing:{field_id}")
            field_status = "missing"
        elif requiredness == "conditional" and _is_missing(value):
            field_status = "absent"
        elif requiredness == "optional" and _is_missing(value):
            field_status = "absent"
        projected.append(
            OrderInformationFieldView(
                field_id, label, owner, source, requiredness, field_status, value
            )
        )
    return tuple(projected), tuple(sorted(blockers))


def _is_missing(value: object) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _fingerprint_value(value: object) -> object:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _fingerprint_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_fingerprint_value(item) for item in value]
    return value


def projection_fingerprint(values: Mapping[str, object]) -> str:
    payload = json.dumps(
        values, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":")
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


__all__ = [
    "OrderInformationError",
    "OrderInformationFieldView",
    "OrderInformationOwnerSnapshot",
    "OrderInformationQueryService",
    "OrderInformationRepository",
    "OrderInformationResult",
    "OrderInformationTemplate",
    "projection_fingerprint",
]
