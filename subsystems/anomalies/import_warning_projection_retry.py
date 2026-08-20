"""
File: import_warning_projection_retry.py
Description: 集中警示投影的去敏錯誤、三次上限與一秒重試契約。
"""

from __future__ import annotations

import hashlib
import re

from domains.anomalies.import_warning_tracking import UnknownImportWarningIssueError


MAX_WARNING_PROJECTION_ATTEMPTS = 3
WARNING_PROJECTION_RETRY_DELAY_SECONDS = 1
WARNING_PROJECTION_RETRY_READY_SQL = (
    "(last_error IS NULL OR JSON_VALID(last_error)=0 OR "
    "COALESCE(CAST(JSON_UNQUOTE(JSON_EXTRACT(last_error,'$.retry_after_epoch')) "
    "AS DECIMAL(20,6)),0)<=UNIX_TIMESTAMP(UTC_TIMESTAMP(6)))"
)


def warning_projection_error_code(error: Exception, *, owning_lane: str) -> str:
    lane = owning_lane.strip()
    if not re.fullmatch(r"[a-z][a-z0-9_-]{1,63}", lane):
        raise ValueError("warning projection owning lane is invalid")
    message = str(error).strip()
    if isinstance(error, UnknownImportWarningIssueError):
        return message
    digest = hashlib.sha256(
        f"{type(error).__name__}:{message}".encode("utf-8")
    ).hexdigest()[:16]
    return f"warning_projection_failed:{lane}:{digest}"


__all__ = [
    "MAX_WARNING_PROJECTION_ATTEMPTS",
    "WARNING_PROJECTION_RETRY_DELAY_SECONDS",
    "WARNING_PROJECTION_RETRY_READY_SQL",
    "warning_projection_error_code",
]
