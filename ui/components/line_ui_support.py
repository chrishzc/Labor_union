"""Shared capability and stable-operation helpers for thin LINE Streamlit panels."""

from __future__ import annotations

import hashlib
import json
from typing import Any
from uuid import uuid4

import streamlit as st


def has_capability(profile: dict[str, Any], capability: str) -> bool:
    return capability in set(profile.get("effective_capabilities") or ())


def operation_headers(operation: str, payload: dict[str, Any]) -> dict[str, str]:
    fingerprint = _payload_fingerprint(payload)
    state_key = f"operation_identity:{operation}"
    saved = st.session_state.get(state_key)
    if not saved or saved["fingerprint"] != fingerprint:
        identity = uuid4().hex
        saved = {"fingerprint": fingerprint, "identity": identity}
        st.session_state[state_key] = saved
    return {
        "Idempotency-Key": f"ui:{operation}:{saved['identity']}",
        "X-Correlation-ID": f"ui:{operation}:{saved['identity']}",
    }


def complete_operation(operation: str) -> None:
    st.session_state.pop(f"operation_identity:{operation}", None)


def _payload_fingerprint(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True, default=str
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


__all__ = ["complete_operation", "has_capability", "operation_headers"]
