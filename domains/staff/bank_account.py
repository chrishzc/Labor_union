"""Staff Bank Account command validation and safe projections."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping


_DIGITS = re.compile(r"^[0-9]+$")
_OPERATIONS = frozenset({"add", "replace", "deactivate", "set_primary"})


class StaffBankAccountValidationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class StaffBankAccountCommand:
    operation: str
    account_id: int | None = None
    bank_code: str | None = None
    branch_code: str | None = None
    account_no: str | None = None
    is_primary: bool | None = None
    successor_account_id: int | None = None


def normalize_bank_command(value: Mapping[str, object]) -> StaffBankAccountCommand:
    if not isinstance(value, Mapping):
        raise StaffBankAccountValidationError("staff_bank_command_invalid")
    unknown = set(value) - {
        "operation", "account_id", "bank_code", "branch_code", "account_no",
        "is_primary", "successor_account_id",
    }
    if unknown:
        raise StaffBankAccountValidationError("staff_bank_command_field_not_allowed")
    operation = str(value.get("operation") or "").strip()
    if operation not in _OPERATIONS:
        raise StaffBankAccountValidationError("staff_bank_operation_invalid")
    account_id = _optional_id(value.get("account_id"), "staff_bank_account_id_invalid")
    successor = _optional_id(
        value.get("successor_account_id"), "staff_bank_successor_account_id_invalid"
    )
    bank_code = _optional_digits(value.get("bank_code"), 3, "staff_bank_code_invalid")
    branch_code = _optional_digits(value.get("branch_code"), 4, "staff_bank_branch_code_invalid")
    account_no = _optional_digits_range(
        value.get("account_no"), 6, 20, "staff_bank_account_no_invalid"
    )
    is_primary = value.get("is_primary")
    if is_primary is not None and not isinstance(is_primary, bool):
        raise StaffBankAccountValidationError("staff_bank_primary_invalid")
    if operation in {"add", "replace"}:
        if bank_code is None or branch_code is None or account_no is None:
            raise StaffBankAccountValidationError("staff_bank_account_fields_required")
    if operation == "add" and account_id is not None:
        raise StaffBankAccountValidationError("staff_bank_add_account_id_forbidden")
    if operation != "add" and account_id is None:
        raise StaffBankAccountValidationError("staff_bank_account_id_required")
    if operation not in {"add", "replace"} and any(
        item is not None for item in (bank_code, branch_code, account_no, is_primary)
    ):
        raise StaffBankAccountValidationError("staff_bank_account_fields_not_allowed")
    if operation != "deactivate" and successor is not None:
        raise StaffBankAccountValidationError("staff_bank_successor_not_allowed")
    if account_id is not None and successor == account_id:
        raise StaffBankAccountValidationError("staff_bank_successor_must_differ")
    return StaffBankAccountCommand(
        operation,
        account_id,
        bank_code,
        branch_code,
        account_no,
        is_primary,
        successor,
    )


def account_last4(account_no: str | None) -> str | None:
    return account_no[-4:] if account_no else None


def _optional_id(value: object, code: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise StaffBankAccountValidationError(code)
    return value


def _optional_digits(value: object, length: int, code: str) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if len(text) != length or not _DIGITS.fullmatch(text):
        raise StaffBankAccountValidationError(code)
    return text


def _optional_digits_range(value: object, minimum: int, maximum: int, code: str) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not minimum <= len(text) <= maximum or not _DIGITS.fullmatch(text):
        raise StaffBankAccountValidationError(code)
    return text


__all__ = [
    "StaffBankAccountCommand",
    "StaffBankAccountValidationError",
    "account_last4",
    "normalize_bank_command",
]
