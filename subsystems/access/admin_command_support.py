from __future__ import annotations

import hashlib
import json


def fingerprint(payload) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def replay_result(receipt, request_fingerprint):
    if receipt is None:
        return None
    if receipt["request_fingerprint"] != request_fingerprint:
        raise ValueError("idempotency_key_conflict")
    result = receipt["result_snapshot"]
    return json.loads(result) if isinstance(result, str) else result
