"""BeClass-owned refund account normalization and safe presentation."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import re


REFUND_FIELDS = ("refund_bank_code", "refund_account_no")
REFUND_SURVEY_FIELDS = ("補助款退款:銀行代號+分行代號", "銀行帳號")


@dataclass(frozen=True, slots=True, repr=False)
class RefundAccount:
    bank_code: str
    account_no: str


def normalize_refund_field(value: object, *, bank: bool) -> str | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise ValueError("refund_account_must_be_text")
    # Match workbook input: spaces, separators and full-width digits normalize once.
    value = value.translate(str.maketrans("０１２３４５６７８９", "0123456789"))
    value = re.sub(r"[\s-]", "", value)
    if not value:
        return None
    if not re.fullmatch(r"[0-9]+", value) or (len(value) != 7 if bank else len(value) > 50):
        raise ValueError("refund_bank_code_invalid" if bank else "refund_account_no_invalid")
    return value


def refund_fields_from_survey(survey: Mapping[str, object]) -> dict[str, str | None]:
    return {key: normalize_refund_field(survey.get(label), bank=index == 0)
            for index, (key, label) in enumerate(zip(REFUND_FIELDS, REFUND_SURVEY_FIELDS))}


def effective_refund_account(original: Mapping[str, object], corrections: Mapping[str, object]) -> RefundAccount | None:
    values = {key: corrections[key] if key in corrections else original.get(key) for key in REFUND_FIELDS}
    try:
        bank = normalize_refund_field(values["refund_bank_code"], bank=True)
        account = normalize_refund_field(values["refund_account_no"], bank=False)
    except ValueError:
        return None
    return RefundAccount(bank, account) if bank and account else None


def mask_refund_values(values: Mapping[str, object]) -> dict[str, object]:
    result = dict(values)
    account = result.get("refund_account_no")
    if account:
        # Never expose a short account in full either.
        result["refund_account_no"] = "****" + (str(account)[-4:] if len(str(account)) > 4 else "")
    return result
