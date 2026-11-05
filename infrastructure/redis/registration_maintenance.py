"""Coalesced AOF cleanup with a generation watermark, never manual AOF deletion."""
from __future__ import annotations

import json
from uuid import uuid4

from subsystems.case_import.provisional_registration_types import ProvisionalRegistrationStorageError
from infrastructure.redis.registration_staging_repository import PREFIX


class RegistrationAofMaintenance:
    def __init__(self, repository):
        self._repository = repository

    def run_once(self):
        repository = self._repository
        lease = uuid4().hex
        key = PREFIX + "maintenance:lease"
        if not repository._call("set", key, lease, nx=True, ex=60):
            return "busy"
        try:
            info = repository._call("info", "persistence")
            generation = int(repository._call("get", PREFIX + "deletion-generation") or 0)
            completed = int(repository._call("get", PREFIX + "maintenance:completed-generation") or 0)
            pending_key = PREFIX + "maintenance:rewrite"
            pending = json.loads(repository._call("get", pending_key) or "null")
            if info.get("aof_rewrite_in_progress") or info.get("aof_rewrite_scheduled"):
                return "running"
            if pending:
                if info.get("aof_last_bgrewrite_status") == "ok" and int(info.get("aof_rewrites", 0)) > pending["rewrites"]:
                    completed = pending["generation"]
                    repository._call("set", PREFIX + "maintenance:completed-generation", completed)
                repository._call("delete", pending_key)
            if generation <= completed:
                return "clean"
            if not info.get("aof_enabled"):
                raise ProvisionalRegistrationStorageError("registration_aof_not_enabled")
            pending = {"generation": generation, "rewrites": int(info.get("aof_rewrites", 0))}
            repository._call("set", pending_key, json.dumps(pending, sort_keys=True))
            # Leave the watermark pending after an unknown outcome; next run checks Redis facts.
            repository._call("bgrewriteaof")
            return "started"
        finally:
            repository._eval("if redis.call('GET',KEYS[1])==ARGV[1] then redis.call('DEL',KEYS[1]) end; return {'ok'}", [key], [lease])
