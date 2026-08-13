"""Fail-closed operator gate for restricted historical import adapters."""

from __future__ import annotations

import os
from typing import Sequence


_APPLY_FLAG = "--historical-apply"


def authorize_historical_apply(arguments: Sequence[str], database: str) -> str:
    if _APPLY_FLAG not in arguments:
        raise RuntimeError("historical_import_apply_flag_required")
    allowed_targets = {
        item.strip()
        for item in os.getenv("HISTORICAL_IMPORT_ALLOWED_DATABASES", "").split(",")
        if item.strip()
    }
    if not database.strip() or database.strip() not in allowed_targets:
        raise RuntimeError("historical_import_database_target_not_allowed")
    paths = [argument for argument in arguments if argument != _APPLY_FLAG]
    if len(paths) != 1:
        raise RuntimeError("historical_import_source_path_required")
    return paths[0]


__all__ = ["authorize_historical_apply"]
