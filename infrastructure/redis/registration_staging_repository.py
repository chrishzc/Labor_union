"""Dedicated durable registration Redis. No cache fallback and no SQL dependency."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import time
from uuid import UUID, uuid4

from redis.exceptions import RedisError

from domains.case_import.provisional_registration import ProvisionalRegistrationCandidate
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from subsystems.case_import.provisional_registration_types import (
    ProvisionalRegistrationConflictError, ProvisionalRegistrationStorageError,
)
from subsystems.case_import.registration_staging import StagedRegistration


RETENTION_MS = 14 * 24 * 60 * 60 * 1000
MAX_PAYLOAD_BYTES = 256 * 1024
PREFIX = "registration:"

# Keys are deliberately explicit so the public Redis ACL can write intake keys,
# read published results, and never write the private decision namespace.
_SUBMIT = """
local ready=tonumber(redis.call('GET',KEYS[1]))
local counter=tonumber(redis.call('GET',KEYS[2]))
if not ready or not counter or counter<ready then return {'uninitialized'} end
local old=redis.call('GET',KEYS[3])
if old then return {'existing',old} end
local active=redis.call('GET',KEYS[4])
if active then return {'active',active} end
local id=redis.call('INCR',KEYS[2])
if id>9007199254740991 then return {'uninitialized'} end
local suffix=tostring(id)
local meta=cjson.decode(ARGV[2]);meta.registration_id=id
redis.call('SET',ARGV[1]..'content:'..suffix,ARGV[3],'PXAT',ARGV[4],'NX')
redis.call('SET',ARGV[1]..'meta:'..suffix,cjson.encode(meta),'NX')
redis.call('ZADD',KEYS[5],id,suffix)
redis.call('ZADD',KEYS[6],ARGV[4],suffix)
redis.call('SET',KEYS[4],suffix,'PXAT',ARGV[4])
redis.call('SET',KEYS[3],suffix)
return {'created',suffix}
"""

_DECIDE = """
local raw=redis.call('GET',KEYS[1])
if not raw then return {'missing'} end
local meta=cjson.decode(raw)
local published=redis.call('GET',KEYS[3])
if published then
 local result=cjson.decode(published)
 if result.status=='approving' and ARGV[1]=='approve' then return {'approving'} end
 if (result.status=='approved' and ARGV[1]=='approve') or (result.status=='rejected' and ARGV[1]=='reject') or (result.status=='expired' and ARGV[1]=='expire') then return {result.status} end
 return {'conflict'}
end
if tonumber(ARGV[2])~=1 then return {'conflict'} end
local status=nil
if tonumber(meta.expires_ms)<=tonumber(ARGV[3]) then status='expired'
elseif ARGV[1]=='reject' then status='rejected'
elseif ARGV[1]=='expire' then return {'pending'}
else
 if redis.call('EXISTS',KEYS[2])==0 then return {'missing_content'} end
 local decision={status='approving',operation_id=ARGV[4],actor=ARGV[5],decided_ms=tonumber(ARGV[3])}
 redis.call('SET',KEYS[4],cjson.encode(decision))
 redis.call('SET',KEYS[3],cjson.encode({status='approving',operation_id=ARGV[4]}))
 redis.call('PERSIST',KEYS[2])
 redis.call('PERSIST',KEYS[5])
 redis.call('ZADD',KEYS[8],meta.registration_id,tostring(meta.registration_id))
 redis.call('ZREM',KEYS[6],tostring(meta.registration_id))
 redis.call('ZREM',KEYS[7],tostring(meta.registration_id))
 return {'approving'}
end
local decision={status=status,actor=ARGV[5],decided_ms=tonumber(ARGV[3])}
redis.call('SET',KEYS[4],cjson.encode(decision))
redis.call('SET',KEYS[3],cjson.encode({status=status}))
redis.call('DEL',KEYS[2])
if redis.call('GET',KEYS[5])==tostring(meta.registration_id) then redis.call('DEL',KEYS[5]) end
redis.call('ZREM',KEYS[6],tostring(meta.registration_id))
redis.call('ZREM',KEYS[7],tostring(meta.registration_id))
redis.call('INCR',KEYS[9])
return {status}
"""

_COMPLETE = """
local raw=redis.call('GET',KEYS[1]);if not raw then return {'missing'} end
local decision=cjson.decode(raw)
if decision.operation_id~=ARGV[1] then return {'conflict'} end
if decision.status~='approving' and decision.status~='approved' then return {'conflict'} end
local result=cjson.decode(ARGV[2]);result.status='approved';result.operation_id=ARGV[1]
decision.status='approved';decision.receipt=result
redis.call('SET',KEYS[1],cjson.encode(decision))
redis.call('SET',KEYS[2],cjson.encode(result))
redis.call('DEL',KEYS[3])
if redis.call('GET',KEYS[4])==ARGV[3] then redis.call('DEL',KEYS[4]) end
redis.call('ZREM',KEYS[5],ARGV[3]);redis.call('ZREM',KEYS[6],ARGV[3]);redis.call('ZREM',KEYS[7],ARGV[3])
redis.call('INCR',KEYS[8])
return {'approved'}
"""

_INITIALIZE = """
if redis.call('EXISTS',KEYS[1])==1 then
 local value=tonumber(redis.call('GET',KEYS[2]));if not value then return {'incomplete_restore'} end
 if value<tonumber(ARGV[1]) then redis.call('SET',KEYS[2],ARGV[1]) end
 return {'ready'}
end
if ARGV[2]~='new-empty-instance' then return {'uninitialized'} end
if redis.call('DBSIZE')~=0 then return {'incomplete_restore'} end
redis.call('SET',KEYS[2],ARGV[1]);redis.call('SET',KEYS[1],ARGV[1]);return {'ready'}
"""


class RedisRegistrationStagingRepository:
    def __init__(self, client, *, now_ms=None) -> None:
        self.client = client
        self._now_ms = now_ms or (lambda: int(time.time() * 1000))

    def _call(self, method, *args, **kwargs):
        try:
            return getattr(self.client, method)(*args, **kwargs)
        except RedisError:
            # Redis errors can contain command fragments. Never surface raw payloads/URLs.
            raise ProvisionalRegistrationStorageError("registration_redis_unavailable") from None

    def _eval(self, script, keys, args):
        result = self._call("eval", script, len(keys), *keys, *args)
        return [_text(item) for item in result]

    def initialize(self, sql_high_water: int, *, new_empty_instance=False):
        if isinstance(sql_high_water, bool) or not 0 <= sql_high_water < 9007199254740991:
            raise ValueError("registration_high_water_invalid")
        result = self._eval(_INITIALIZE, [PREFIX + "ready", PREFIX + "counter"],
                            [sql_high_water, "new-empty-instance" if new_empty_instance else "verify"])
        if result != ["ready"]:
            raise ProvisionalRegistrationStorageError("registration_redis_initialization_required")

    def submit(self, candidate: ProvisionalRegistrationCandidate, submission_id: str) -> StagedRegistration:
        try:
            submission_id = str(UUID(submission_id))
        except (ValueError, TypeError, AttributeError):
            raise ProvisionalRegistrationConflictError("registration_submission_id_invalid") from None
        subject = _subject(candidate.line_user_id)
        now = self._now_ms()
        meta = {"schema_version": 1, "content_version": 1, "subject": subject,
                "fingerprint": candidate.payload_fingerprint.value, "submitted_ms": now,
                "expires_ms": now + RETENTION_MS, "registration_kind": candidate.registration_kind}
        payload = _json({"client": dict(candidate.client_payload), "beclass": dict(candidate.beclass_payload)})
        if len(payload.encode("utf-8")) > MAX_PAYLOAD_BYTES:
            raise ProvisionalRegistrationConflictError("registration_payload_too_large")
        result = self._eval(_SUBMIT,
            [PREFIX + "ready", PREFIX + "counter", PREFIX + f"submission:{subject}:{submission_id}",
             PREFIX + "active:" + subject, PREFIX + "pending", PREFIX + "deadlines"],
            [PREFIX, _json(meta), payload, meta["expires_ms"]])
        if result[0] == "uninitialized":
            raise ProvisionalRegistrationStorageError("registration_redis_initialization_required")
        registration_id = int(result[1])
        saved = self._metadata(registration_id)
        if saved["subject"] != subject or saved["fingerprint"] != candidate.payload_fingerprint.value:
            raise ProvisionalRegistrationConflictError("registration_active_application_conflict")
        return self.get(registration_id, public=True)

    def _metadata(self, registration_id):
        self.ensure_initialized()
        _valid_id(registration_id)
        raw = self._call("get", PREFIX + f"meta:{registration_id}")
        if raw is None:
            raise ProvisionalRegistrationConflictError("registration_application_not_found")
        return json.loads(raw)

    def ensure_initialized(self):
        ready = self._call("get", PREFIX + "ready")
        counter = self._call("get", PREFIX + "counter")
        try:
            valid = ready is not None and counter is not None and int(counter) >= int(ready)
        except (ValueError, TypeError):
            valid = False
        if not valid:
            raise ProvisionalRegistrationStorageError("registration_redis_initialization_required")

    def status_for_submission(self, line_user_id: str, submission_id: str):
        try:
            submission_id = str(UUID(submission_id))
        except (ValueError, TypeError, AttributeError):
            raise ProvisionalRegistrationConflictError("registration_submission_id_invalid") from None
        registration_id = self._call("get", PREFIX + f"submission:{_subject(line_user_id)}:{submission_id}")
        if registration_id is None:
            return None
        snapshot = self.get(int(registration_id), public=True)
        if self._metadata(snapshot.registration_id)["subject"] != _subject(line_user_id):
            raise ProvisionalRegistrationConflictError("registration_subject_mismatch")
        return snapshot

    def get(self, registration_id: int, *, public=False) -> StagedRegistration:
        meta = self._metadata(registration_id)
        result = json.loads(self._call("get", PREFIX + f"result:{registration_id}") or "{}")
        decision = {} if public else json.loads(self._call("get", PREFIX + f"decision:{registration_id}") or "{}")
        status = result.get("status", "pending" if meta["expires_ms"] > self._now_ms() else "expired")
        candidate = None
        if status in {"pending", "approving"} and not public:
            raw = self._call("get", PREFIX + f"content:{registration_id}")
            if raw is None:
                # Recheck deadline to close an expiry between metadata and content reads.
                if status == "pending" and meta["expires_ms"] <= self._now_ms():
                    status = "expired"
                else:
                    raise ProvisionalRegistrationStorageError("registration_content_missing")
            else:
                payload = json.loads(raw)
                if fingerprint_payload(payload).value != meta["fingerprint"]:
                    raise ProvisionalRegistrationStorageError("registration_content_mismatch")
                subject = str(payload["client"]["line_user_id"])
                if _subject(subject) != meta["subject"]:
                    raise ProvisionalRegistrationStorageError("registration_subject_mismatch")
                candidate = ProvisionalRegistrationCandidate(subject, payload["client"], payload["beclass"], PreviewFingerprint(meta["fingerprint"]))
        return StagedRegistration(registration_id, 1 if status == "pending" else 2, status,
            _dt(meta["submitted_ms"]), _dt(meta["expires_ms"]), meta["registration_kind"],
            candidate, result.get("operation_id"), decision.get("actor"),
            result.get("client_id"), result.get("beclass_record_id"), result.get("case_no"),
            datetime.fromisoformat(result["approved_at_utc"]) if result.get("approved_at_utc") else None)

    def pending(self, *, after_id=0, limit=50):
        self.ensure_initialized()
        if isinstance(after_id, bool) or not isinstance(after_id, int) or after_id < 0 or not 1 <= limit <= 200:
            raise ValueError("registration_pagination_invalid")
        items = []
        # Bounded batches avoid expired rows hiding a live next page.
        for _ in range(20):
            ids = self._call("zrangebyscore", PREFIX + "pending", f"({after_id}", "+inf", start=0, num=limit)
            if not ids:
                break
            for value in ids:
                after_id = int(value)
                item = self.get(after_id)
                if item.status == "pending":
                    items.append(item)
                if len(items) == limit:
                    return tuple(items)
        return tuple(items)

    def _decide(self, registration_id, expected_version, action, actor):
        meta = self._metadata(registration_id)
        result = self._eval(_DECIDE,
            [PREFIX + f"meta:{registration_id}", PREFIX + f"content:{registration_id}",
             PREFIX + f"result:{registration_id}", PREFIX + f"decision:{registration_id}",
             PREFIX + "active:" + meta["subject"], PREFIX + "pending", PREFIX + "deadlines",
             PREFIX + "processing", PREFIX + "deletion-generation"],
            [action, expected_version, self._now_ms(), uuid4().hex, actor])
        if result[0] in {"conflict", "missing", "missing_content"}:
            raise ProvisionalRegistrationConflictError("registration_application_stale")
        return self.get(registration_id)

    def claim_approval(self, registration_id, expected_version, actor):
        result = self._decide(registration_id, expected_version, "approve", actor)
        if result.status not in {"approving", "approved"}:
            raise ProvisionalRegistrationConflictError("registration_application_expired")
        return result

    def reject(self, registration_id, expected_version, actor):
        return self._decide(registration_id, expected_version, "reject", actor)

    def complete(self, registration_id, operation_id, receipt):
        # Only allow minimal committed formal identifiers, never questionnaire data.
        allowed = {"client_id", "beclass_record_id", "case_no", "approved_at_utc"}
        if set(receipt) != allowed or not receipt["client_id"] or not receipt["beclass_record_id"]:
            raise ProvisionalRegistrationStorageError("registration_approval_receipt_invalid")
        meta = self._metadata(registration_id)
        result = self._eval(_COMPLETE,
            [PREFIX + f"decision:{registration_id}", PREFIX + f"result:{registration_id}",
             PREFIX + f"content:{registration_id}", PREFIX + "active:" + meta["subject"],
             PREFIX + "pending", PREFIX + "deadlines", PREFIX + "processing", PREFIX + "deletion-generation"],
            [operation_id, _json(receipt), registration_id])
        if result != ["approved"]:
            raise ProvisionalRegistrationConflictError("registration_approval_operation_mismatch")
        return self.get(registration_id)

    def processing_ids(self, *, limit=100):
        return tuple(int(value) for value in self._call("zrange", PREFIX + "processing", 0, limit - 1))

    def expire_due(self, *, limit=200):
        ids = self._call("zrangebyscore", PREFIX + "deadlines", "-inf", self._now_ms(), start=0, num=limit)
        for value in ids:
            self._decide(int(value), 1, "expire", "system:expiry")
        return len(ids)


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _subject(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _text(value):
    return value.decode("utf-8") if isinstance(value, bytes) else str(value)


def _dt(value):
    return datetime.fromtimestamp(value / 1000, timezone.utc)


def _valid_id(value):
    if isinstance(value, bool) or not isinstance(value, int) or not 0 < value <= 9007199254740991:
        raise ProvisionalRegistrationConflictError("registration_id_invalid")
