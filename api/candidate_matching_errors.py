"""Typed HTTP errors for candidate matching API routes."""

from __future__ import annotations

from fastapi import HTTPException

from api.error_contracts import typed_http_error


_CANDIDATE_MATCHING_MESSAGES = {
    "candidate_contact_order_not_negotiating": "本案目前無法繼續媒合。請重新讀取案件進度。",
    "candidate_matching_assignment_present": "本案已有正式指派。請重新讀取案件進度。",
    "candidate_matching_data_needs_review": "目前排班資料待核對。請先確認排班紀錄，再重新查詢。",
    "candidate_matching_service_started": "本案已有正式服務紀錄。請重新讀取案件進度。",
    "candidate_inquiry_dates_missing": "請先補存預計服務日期，再重新查詢。",
    "candidate_inquiry_dates_invalid": "預計服務日期不合法。請確認並保存正確日期後再查詢。",
    "candidate_inquiry_dates_too_long": "預計服務期間超過 60 天。請確認並保存日期後再查詢。",
    "candidate_staff_not_active": "這位月嫂目前無法加入候選。請確認月嫂名冊並重新查詢。",
}


def candidate_matching_http_error(error: ValueError, correlation_id: str) -> HTTPException:
    code = str(error)
    message = _CANDIDATE_MATCHING_MESSAGES.get(code)
    if message is None:
        return typed_http_error(409, "conflict", "conflict", "本案媒合資料已變更。請重新查詢。", correlation_id)
    return typed_http_error(409, "conflict", code, message, correlation_id)
