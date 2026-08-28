"""
File: source_version.py
Description: 組合業務日與 owner root version，提供可跨 legacy 日期版號的單調異常來源版本。
"""

from __future__ import annotations

from datetime import date, datetime

from shared_kernel.validation import require_nonnegative_integer


_ROOT_VERSION_RADIX = 1_000_000_000


def daily_root_source_version(*, as_of: date, root_version: int) -> int:
    """Return a version monotonic in both business date and owner root version.

    Older reminder projectors stored only ``date.toordinal()``. Multiplying the
    ordinal by the reserved radix makes the first migrated projection newer
    than every legacy date-only value while preserving same-day root changes.
    """
    if isinstance(as_of, datetime) or not isinstance(as_of, date):
        raise TypeError("as of date must be a date")
    current_root_version = require_nonnegative_integer(root_version, "root version")
    if current_root_version >= _ROOT_VERSION_RADIX:
        raise ValueError("root version exceeds daily source-version radix")
    return as_of.toordinal() * _ROOT_VERSION_RADIX + current_root_version


__all__ = ["daily_root_source_version"]
