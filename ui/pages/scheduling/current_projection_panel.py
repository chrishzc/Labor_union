"""Thin read-only rendering for the current Scheduling projection."""

from __future__ import annotations

from datetime import date

import streamlit as st

from ui.api_clients.scheduling_current_api_client import (
    SchedulingCurrentApiClient,
    SchedulingCurrentApiError,
)


def render_scheduling_current_projection_panel(
    client: SchedulingCurrentApiClient,
    *,
    staff_id: int,
    range_start: date,
    range_end: date,
) -> None:
    try:
        projection = client.query(staff_id, range_start, range_end)
    except SchedulingCurrentApiError as error:
        st.error(f"目前檔期投影載入失敗 [{error.error.code}]：{error}")
        return
    except ValueError as error:
        st.error(f"目前檔期投影查詢條件無效：{error}")
        return
    _render_projection(projection)


def _render_projection(projection) -> None:
    st.caption(
        f"投影時間：{projection.evaluated_at.isoformat()}｜"
        f"版本案件數：{len(projection.case_versions)}"
    )
    st.subheader("日期可用性")
    st.dataframe(_day_rows(projection), hide_index=True, width="stretch")
    st.subheader("正式指派")
    assignments = [_assignment_row(item) for item in projection.assignments]
    if assignments:
        st.dataframe(assignments, hide_index=True, width="stretch")
        return
    st.info("此區間沒有正式指派。")


def _day_rows(projection) -> list[dict[str, object]]:
    return [
        {
            "日期": item.calendar_date.isoformat(),
            "可接案": item.available,
            "占用來源": "、".join(entry.occupancy_kind.value for entry in item.entries)
            or "無",
            "案件": "、".join(sorted({entry.case_no for entry in item.entries}))
            or "-",
        }
        for item in projection.days
    ]


def _assignment_row(item) -> dict[str, object]:
    return {
        "案件": item.case_no,
        "指派": item.assignment_id,
        "狀態": item.status.value,
        "期間": f"{item.assigned_start_date} ～ {item.assigned_end_date}",
        "正式服務日": item.official_service_day_count,
        "實際時數": item.actual_hours,
    }
