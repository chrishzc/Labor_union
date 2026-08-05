import json
from typing import Any
from uuid import uuid4

import streamlit as st

from api.schemas.beclass_import_review import (
    BeClassImportReviewPreviewView,
    BeClassImportReviewQueryView,
)
from ui.api_clients.beclass_import_review_api_client import (
    BeClassImportReviewApiClient,
    BeClassImportReviewApiError,
)


_PREVIEW_STATE_KEY = "beclass_review_preview"


def render_beclass_import_review_panel(client: BeClassImportReviewApiClient) -> None:
    st.subheader("BeClass 匯入待修正資料")
    st.caption("依 review_identity 查詢，先做 Preview，再正式套用修正。")
    identity = st.text_input(
        "review_identity",
        value=str(st.session_state.get("beclass_import_review_identity") or ""),
        key="beclass_review_identity",
    )
    if st.button("讀取資料", key="beclass_review_load"):
        _load_review(client, identity)
    query = st.session_state.get("beclass_review_query")
    if query is None and identity:
        _load_review(client, identity)
        query = st.session_state.get("beclass_review_query")
    if query is None:
        return
    _render_review(query)
    _render_edit_and_preview(client, query)


def _load_review(client: BeClassImportReviewApiClient, identity: str) -> None:
    try:
        st.session_state["beclass_review_query"] = client.query_review(_text(identity))
    except (BeClassImportReviewApiError, ValueError) as error:
        st.error(f"讀取失敗：{error}")
        st.session_state.pop("beclass_review_query", None)


def _render_review(review: BeClassImportReviewQueryView) -> None:
    with st.expander("異常內容", expanded=True):
        st.json(
            {
                "review_identity": review.review_identity,
                "source_kind": review.source_kind,
                "status": review.status,
                "review_version": review.review_version,
                "issue_codes": review.issue_codes,
            }
        )
        st.write("來源資料（可參考）")
        st.json(review.source_payload)
        st.write("現行有效欄位")
        st.json(review.effective_payload)


def _render_edit_and_preview(
    client: BeClassImportReviewApiClient,
    review: BeClassImportReviewQueryView,
) -> None:
    with st.expander("產生修正 Preview", expanded=True):
        corrected_json = st.text_area(
            "corrected_fields（JSON）",
            value=_to_json(review.effective_payload),
            height=220,
            key="beclass_corrected_fields",
        )
        resolved_issue_codes = st.text_area(
            "resolved_issue_codes（每行一個）",
            value="\n".join(review.issue_codes),
            key="beclass_resolved_issue_codes",
        )
        if st.button("產生 Preview", key="beclass_preview_button"):
            corrected = _as_json(corrected_json, "corrected_fields")
            issues = _lines_to_list(resolved_issue_codes)
            if corrected is None:
                st.error("corrected_fields 需要合法 JSON 字典。")
                return
            _preview_review(client, review, corrected, issues)
        _render_preview(client, review)


def _render_preview(
    client: BeClassImportReviewApiClient,
    review: BeClassImportReviewQueryView,
) -> None:
    preview = st.session_state.get(_PREVIEW_STATE_KEY)
    if not isinstance(preview, BeClassImportReviewPreviewView):
        return
    if preview.candidate.review_identity != review.review_identity:
        return
    st.success("Preview 已建立")
    st.json(preview.model_dump())
    reason = st.text_input("修正原因", key="beclass_review_reason")
    if st.button("提交正式修正（Apply）", key="beclass_apply_button"):
        corrected = _as_json(
            st.session_state.get("beclass_corrected_fields", "{}"),
            "corrected_fields",
        )
        issues = _lines_to_list(
            str(st.session_state.get("beclass_resolved_issue_codes", ""))
        )
        if corrected is None:
            st.error("corrected_fields 需要合法 JSON 字典。")
            return
        if not reason.strip():
            st.error("請先輸入修正原因。")
            return
        try:
            st.session_state.pop(_PREVIEW_STATE_KEY)
            receipt = client.apply_review(
                review.review_identity,
                preview,
                corrected_fields=corrected,
                resolved_issue_codes=issues,
                reason=reason,
                idempotency_key=_new_key("beclass-review-apply"),
                correlation_id=_new_key("beclass-review-apply-correlation"),
            )
            st.success("Apply 成功")
            st.json(receipt.model_dump())
        except (BeClassImportReviewApiError, ValueError) as error:
            st.error(f"Apply 失敗：{error}")


def _preview_review(
    client: BeClassImportReviewApiClient,
    review: BeClassImportReviewQueryView,
    corrected: dict[str, Any],
    issues: list[str],
) -> None:
    try:
        st.session_state[_PREVIEW_STATE_KEY] = client.preview_review(
            review.review_identity,
            corrected_fields=corrected,
            resolved_issue_codes=issues,
            correlation_id=_new_key("beclass-review-preview"),
        )
    except (BeClassImportReviewApiError, ValueError) as error:
        st.error(f"Preview 失敗：{error}")


def _as_json(value: object, field_name: str) -> dict[str, Any] | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = json.loads(value)
    except ValueError:
        return None
    if not isinstance(parsed, dict):
        return None
    if not parsed and "" == parsed:
        return None
    return parsed


def _to_json(value: Mapping[str, object] | dict[str, Any]) -> str:
    return json.dumps(dict(value), ensure_ascii=False, indent=2, sort_keys=True)


def _lines_to_list(value: object) -> list[str]:
    if not isinstance(value, str):
        return []
    return [line.strip() for line in value.splitlines() if line.strip()]


def _text(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("review_identity is required")
    if not value.strip():
        raise ValueError("review_identity is required")
    return value.strip()


def _new_key(prefix: str) -> str:
    return f"{prefix}:{uuid4()}"
