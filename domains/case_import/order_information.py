"""Case Import owner projection for the legacy BeClass care answers.

The source payload is intentionally accepted only at this owner boundary.  A
consumer receives scalar, named facts (or a field-local issue), never the raw
survey mapping and never a default answer.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass


ORDER_INFORMATION_KEYS = (
    "dietary_habits",
    "vegetarian_preference",
    "alcohol_ratio",
    "cooking_oil_type",
    "maternal_allergy",
    "special_care_notes",
    "meal_preferences",
    "cooking_tools",
    "bath_water_prep",
    "breastfeeding_method",
    "holiday_pricing_terms",
    "multi_birth_count",
    "stair_floor_fee_mode",
    "parking_space_provided",
    "other_babies_present",
)


@dataclass(frozen=True, slots=True)
class OrderInformationProjection:
    """Named Case Import facts and field-local source issues."""

    values: Mapping[str, object]
    issues: Mapping[str, str]


_ALIASES: dict[str, tuple[str, ...]] = {
    "dietary_habits": ("月子餐點調理喜好/飲食習慣",),
    "vegetarian_preference": (
        "呈上題，若遇無法媒合到葷食服務人員時，是否可以接受蛋奶素服務人員？",
    ),
    "alcohol_ratio": ("2.餐飲含酒比例", "2．餐飲含酒比例"),
    "cooking_oil_type": ("3.料理用油:(可接受種類)", "3．料理用油:(可接受種類)"),
    "maternal_allergy": (
        "5媽咪有無過敏體質",
        "5.媽咪有無過敏體質",
        "5．媽咪有無過敏體質",
    ),
    "special_care_notes": ("特殊照護時應注意事項",),
    "meal_preferences": ("餐點喜忌備註",),
    "cooking_tools": ("烹煮工具",),
    "bath_water_prep": ("洗澡水準備",),
    "breastfeeding_method": ("哺乳方式",),
    "holiday_pricing_terms": ("特殊計費:甲方同意需另支付當日薪資1倍予乙方。",),
    "multi_birth_count": ("特殊計費:胎數",),
    "stair_floor_fee_mode": ("透天服務樓層方式(會加收樓層費)",),
    "parking_space_provided": ("提供服務人員轎車停車位",),
    "other_babies_present": ("服務時間內是否有其他寶寶",),
}


def project_order_information(raw_payload: object) -> OrderInformationProjection:
    """Normalize one BeClass payload into the current named owner facts.

    Missing keys remain ``None``.  Conflicting aliases affect only the
    conflicting canonical field and are reported as ``ambiguous``.  The
    function has no fallback values because a guessed care instruction is a
    materially different business fact.
    """

    data = _decode_mapping(raw_payload)
    if data is None:
        return OrderInformationProjection(
            values={key: None for key in ORDER_INFORMATION_KEYS},
            issues={key: "invalid_payload" for key in ORDER_INFORMATION_KEYS},
        )

    normalized: dict[str, list[object]] = {}
    for raw_key, raw_value in data.items():
        if not isinstance(raw_key, str):
            continue
        key = _normalize_key(raw_key)
        if key:
            normalized.setdefault(key, []).append(raw_value)

    values: dict[str, object] = {key: None for key in ORDER_INFORMATION_KEYS}
    issues: dict[str, str] = {}
    for canonical_key, aliases in _ALIASES.items():
        matches = [
            value
            for alias in aliases
            for value in normalized.get(_normalize_key(alias), ())
        ]
        clean = [_scalar_value(value) for value in matches]
        clean = [value for value in clean if value is not None]
        if not clean:
            continue
        if len({_comparison_value(value) for value in clean}) != 1:
            issues[canonical_key] = "ambiguous"
            continue
        values[canonical_key] = clean[0]
    return OrderInformationProjection(values=values, issues=issues)


def _decode_mapping(raw_payload: object) -> Mapping[object, object] | None:
    if isinstance(raw_payload, Mapping):
        return raw_payload
    if not isinstance(raw_payload, str) or not raw_payload.strip():
        return None
    try:
        decoded = json.loads(raw_payload)
    except (TypeError, ValueError):
        return None
    return decoded if isinstance(decoded, Mapping) else None


def _normalize_key(value: str) -> str:
    return (
        re.sub(r"[\s\u00a0]+", "", value)
        .replace("：", ":")
        .replace("．", ".")
        .rstrip(":")
        .lower()
    )


def _scalar_value(value: object) -> object | None:
    if value is None or isinstance(value, (Mapping, list, tuple, set)):
        return None
    if isinstance(value, str):
        value = value.strip()
        return value or None
    if isinstance(value, (bool, int, float)):
        return value
    return None


def _comparison_value(value: object) -> str:
    return str(value).strip().casefold()


__all__ = [
    "ORDER_INFORMATION_KEYS",
    "OrderInformationProjection",
    "project_order_information",
]
