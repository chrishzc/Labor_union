"""Redis-only pending LIFF requests, isolated from registration records."""
import json
from time import time
from uuid import uuid4

from redis.exceptions import RedisError

from shared_kernel.fingerprints import fingerprint_payload

PREFIX = "registration:staff-profile:"
RETENTION_SECONDS = 14 * 24 * 60 * 60

_SUBMIT = """
local prior = redis.call('GET', KEYS[1])
if prior then return tonumber(prior) end
local expired = redis.call('ZRANGEBYSCORE', KEYS[4], '-inf', ARGV[4], 'LIMIT', 0, 100)
if #expired > 0 then
  redis.call('ZREM', KEYS[3], unpack(expired))
  redis.call('ZREM', KEYS[4], unpack(expired))
end
local id = redis.call('INCR', KEYS[2])
redis.call('SET', ARGV[1] .. id, ARGV[2], 'EX', ARGV[3])
redis.call('SET', KEYS[1], id, 'EX', ARGV[3])
redis.call('ZADD', KEYS[3], id, id)
redis.call('ZADD', KEYS[4], tonumber(ARGV[4]) + tonumber(ARGV[3]), id)
return id
"""

_DECIDE = """
local raw = redis.call('GET', KEYS[1])
if not raw then return 0 end
local item = cjson.decode(raw)
local action = ARGV[1]
if action == 'claim' then
  if item.status == 'approved' or item.status == 'approving' then return 1 end
  if item.status ~= 'pending' or item.version ~= tonumber(ARGV[2]) then return -1 end
  item.status = 'approving'
  item.actor = ARGV[3]
  item.operation_id = ARGV[4]
  item.version = item.version + 1
  redis.call('SET', KEYS[1], cjson.encode(item))
  redis.call('ZREM', KEYS[3], ARGV[5])
  return 1
end
if action == 'complete' then
  if item.operation_id ~= ARGV[4] then return -1 end
  if item.status == 'approved' then return 1 end
  if item.status ~= 'approving' then return -1 end
  item.status = 'approved'
elseif action == 'conflict' then
  if item.status ~= 'approving' or item.operation_id ~= ARGV[4] then return -1 end
  item.status = 'conflict'
else
  if item.status ~= 'pending' or item.version ~= tonumber(ARGV[2]) then return -1 end
  item.status = 'rejected'
  item.actor = ARGV[3]
end
item.content = nil
item.review = nil
item.version = item.version + 1
redis.call('SET', KEYS[1], cjson.encode(item), 'EX', ARGV[6])
redis.call('ZREM', KEYS[2], ARGV[5])
redis.call('ZREM', KEYS[3], ARGV[5])
return 1
"""


class StaffProfileStagingUnavailable(RuntimeError):
    pass


class StaffProfileStagingConflict(ValueError):
    pass


class StaffProfileChangeStaging:
    def __init__(self, client):
        self._client = client

    def _call(self, method, *args, **kwargs):
        try:
            return getattr(self._client, method)(*args, **kwargs)
        except RedisError:
            raise StaffProfileStagingUnavailable from None

    def submit(self, staff_id, submission_id, submitted, content, review):
        digest = fingerprint_payload(submitted).value
        item = {
            "staff_id": staff_id, "status": "pending", "version": 1,
            "digest": digest,
            "content": json.dumps(content, ensure_ascii=False),
            "review": json.dumps(review, ensure_ascii=False),
        }
        application_id = self._call(
            "eval", _SUBMIT, 4, f"{PREFIX}submission:{staff_id}:{submission_id}",
            f"{PREFIX}counter", f"{PREFIX}pending", f"{PREFIX}deadlines",
            f"{PREFIX}item:", json.dumps(item, ensure_ascii=False), RETENTION_SECONDS, time(),
        )
        saved = self.get(application_id, include_content=False)
        if saved["staff_id"] != staff_id or saved["digest"] != digest:
            raise StaffProfileStagingConflict
        return saved

    def find_submission(self, staff_id, submission_id, submitted):
        previous = self._call("get", f"{PREFIX}submission:{staff_id}:{submission_id}")
        if previous is None:
            return None
        saved = self.get(int(previous), include_content=False)
        if saved["staff_id"] != staff_id or saved["digest"] != fingerprint_payload(submitted).value:
            raise StaffProfileStagingConflict
        return saved

    def get(self, application_id, *, include_content=True):
        raw = self._call("get", f"{PREFIX}item:{application_id}")
        if raw is None:
            raise LookupError("staff_profile_request_not_found")
        item = json.loads(raw)
        for field in ("content", "review"):
            if not include_content:
                item.pop(field, None)
            elif field in item:
                item[field] = json.loads(item[field])
        return {**item, "id": application_id}

    def pending(self, after_id, limit):
        ids = self._call("zrangebyscore", f"{PREFIX}pending", f"({after_id}", "+inf", start=0, num=limit)
        items = []
        for raw_id in ids:
            application_id = int(raw_id)
            try:
                item = self.get(application_id, include_content=False)
            except LookupError:
                continue
            if item["status"] in {"pending", "approving"}:
                items.append({"id": application_id, "staff_id": item["staff_id"], "version": item["version"]})
        return items, int(ids[-1]) if len(ids) == limit else None

    def decide(self, application_id, action, *, version=0, actor="", operation_id=""):
        result = self._call(
            "eval", _DECIDE, 3, f"{PREFIX}item:{application_id}", f"{PREFIX}pending", f"{PREFIX}deadlines",
            action, version, actor, operation_id or uuid4().hex, application_id, RETENTION_SECONDS,
        )
        if not result:
            raise LookupError("staff_profile_request_not_found")
        if result < 0:
            raise StaffProfileStagingConflict
        return self.get(application_id)
