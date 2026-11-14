"""Client Finance format rule for an explicitly assigned collection account."""

import re


def allows_historical_non_citizen_account(case_no: str) -> bool:
    parts = re.fullmatch(r"A([0-9]{3})[0-9]{3}", case_no)
    return parts is not None and parts[1] < "116"


def allows_case_account_edit(case_no: str) -> bool:
    parts = re.fullmatch(r"([0-9]{3})[0-9]{6}", case_no)
    return (parts is not None and parts[1] < "116") or allows_historical_non_citizen_account(case_no)


def canonical_virtual_account(value: str) -> str:
    account = value.strip()
    if re.fullmatch(r"99781699[0-9]{6}", account) is None:
        raise ValueError("虛擬帳號須為 99781699 開頭的 14 位數字。")
    return account
