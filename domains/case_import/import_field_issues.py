"""Current import field warnings, independent of immutable import evidence."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal, Mapping

from domains.case_import.refund_account import normalize_refund_field
from domains.clients.profile import ClientProfileValidationError, validate_changes


def hcm_notification_can_skip(source_field: str | None) -> bool:
    # The HCM workbook explicitly accepts a blank email. Do not infer that
    # an unknown or conditionally required field is optional.
    return source_field == "email"


@dataclass(frozen=True, slots=True)
class ImportFieldIssue:
    source: Literal["hcm", "client_beclass"]
    owner: Literal["client_profile", "client_beclass", "order_terms"]
    field: str
    source_field: str
    code: str
    message: str

    optional_skip_review_identity: str | None = None

    def as_dict(self) -> dict[str, str | None]:
        return asdict(self)


BECLASS_FIELD_TARGETS = {
    "Email": ("client_profile", "email"),
    "縣市": ("client_profile", "city"),
    "補助款退款:銀行代號+分行代號": ("client_beclass", "refund_bank_code"),
    "銀行帳號": ("client_beclass", "refund_account_no"),
}
CLIENT_BECLASS_COOKING_LOCKED_ISSUE = "service_data_locked"

# These keys name the existing owner controls. Source labels remain available
# for fields which the owner presents as read-only or explicitly skips.
HCM_FIELD_TARGETS = {
    "報名時間(建檔)": ("client_profile", "created_at"),
    "IP位址": ("client_profile", "ip_address"),
    "姓名": ("client_profile", "name"),
    "性別": ("client_profile", "gender"),
    "身分資格": ("client_profile", "identity_status"),
    "行動電話": ("client_profile", "phone"),
    "email": ("client_profile", "email"),
    "縣市": ("client_profile", "city"),
    "預產期/預計服務開始月份": ("client_profile", "due_month"),
    "不符合原因": ("client_profile", "reject_reason"),
    "居住型態": ("client_profile", "residence_type"),
    "生產方式": ("client_profile", "delivery_type"),
    "寶寶資訊": ("client_profile", "baby_info"),
    "服務方式": ("client_profile", "service_type"),
    "服務時間": ("order_terms", "service_hours_per_day"),
    "預計服務日期": ("order_terms", "planned_start_date"),
    "希望服務天數": ("order_terms", "service_days"),
}


def current_beclass_field_issues(codes: tuple[str, ...], values: Mapping[str, object],
                                 profile: Mapping[str, object], *, cleared_fields: frozenset[str] = frozenset()) -> tuple[ImportFieldIssue, ...]:
    issues = []
    for code in codes:
        if code == CLIENT_BECLASS_COOKING_LOCKED_ISSUE:
            if values.get("requires_cooking") is None:
                issues.append(ImportFieldIssue(
                    "client_beclass", "order_terms", "requires_cooking", "煮食需求", code,
                    "案件服務資料已鎖定，無法補寫煮食需求。",
                ))
            continue
        kind, separator, label = code.partition(":")
        if not separator or kind not in {"client_field_invalid", "client_field_missing"} or label not in BECLASS_FIELD_TARGETS:
            continue
        owner, field = BECLASS_FIELD_TARGETS[label]
        value = (profile if owner == "client_profile" else values).get(field)
        valid = False
        try:
            if owner == "client_profile":
                validate_changes({field: value})
                valid = True
            else:
                normalized = normalize_refund_field(value, bank=field == "refund_bank_code")
                valid = normalized is not None or field in cleared_fields
        except (ValueError, ClientProfileValidationError):
            pass
        if not valid:
            issues.append(ImportFieldIssue("client_beclass", owner, field, label, code,
                                          f"{label}來源資料有誤，請補正此欄位。"))
    return tuple(issues)


def current_hcm_field_issue(label: str, code: str, *, review_identity: str | None = None) -> ImportFieldIssue:
    owner, field = HCM_FIELD_TARGETS.get(label, ("client_profile", label))
    return ImportFieldIssue("hcm", owner, field, label, code,
                            f"{label}尚未完成，請核對此欄位。",
                            review_identity if hcm_notification_can_skip(label) else None)
