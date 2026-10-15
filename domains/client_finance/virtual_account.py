"""Client Finance format rule for an explicitly assigned collection account."""

import re


def canonical_virtual_account(value: str) -> str:
    account = value.strip()
    if re.fullmatch(r"99781699[0-9]{6}", account) is None:
        raise ValueError("虛擬帳號須為 99781699 開頭的 14 位數字。")
    return account
