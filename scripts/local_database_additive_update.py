"""
File: local_database_additive_update.py
Description: 提供 canonical 本機 additive migration runner 的相容匯出介面。
"""

from __future__ import annotations

from scripts import migrate_preserved_database_additive_schema as _canonical

# This module deliberately contains no qualification, descriptor, SQL, lock, or
# journal logic. The migration runner is the sole owner of those contracts.
LocalAdditiveBlocked = _canonical.LocalAdditiveBlocked
MAX_DURATION_MS = _canonical.LOCAL_ADDITIVE_MAX_DURATION_MS
LOCK_TIMEOUT_SECONDS = _canonical.LOCAL_ADDITIVE_LOCK_TIMEOUT_SECONDS
ALLOWED_PREFIX = _canonical.LOCAL_ADDITIVE_TARGET_PREFIX

plan = _canonical.local_additive_plan
prepare_backup = _canonical.local_additive_prepare_backup
apply = _canonical.local_additive_apply
_classify_statement = _canonical._local_classify_statement
_payload_digest = _canonical._local_payload_digest
_discover_qualification = _canonical._local_discover_qualification
_append_event = _canonical._local_append_event
_read_events = _canonical._local_read_events
