"""
================================================================================
檔案名稱: api/schemas/matches.py
功能說明: 訂單媒合意願回覆與月嫂定案指派 API 的輸入資料格式
================================================================================
"""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, PositiveInt


class _ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

class MatchReplyRequest(BaseModel):
    accepted: Optional[bool] = Field(None, description="月嫂接案意願: True=願意(1), False=拒絕(0), None=待回覆(NULL)")

class MatchAssignRequest(BaseModel):
    staff_id: int = Field(..., description="擬定案指派之月嫂 staff_id")

class MatchCreateRequest(BaseModel):
    staff_id: int = Field(..., description="月嫂 staff_id")


class MatchLineTestBindingRequest(BaseModel):
    client_line_user_id: str = Field(..., min_length=1, description="測試客戶 LINE userId")
    staff_id: int = Field(..., description="要測試的月嫂 staff_id")
    staff_line_user_id: str = Field(..., min_length=1, description="測試月嫂 LINE userId")


class StaffRecommendationView(_ClosedModel):
    staff_id: int = Field(gt=0)
    name: str
    phone: str | None
    line_user_id: str | None
    score: int = Field(ge=-50, le=100)
    display_label: str
    is_perfect: bool
    reasons: list[Literal["符合區域", "檔期無衝突", "胎數符合", "時段符合"]]
    reject_reasons: list[
        Literal["區域不符", "檔期衝突", "不承接雙胞胎", "時段不符"]
    ]


class OrderMatchRecordView(_ClosedModel):
    match_id: int = Field(gt=0)
    case_no: str = Field(min_length=1, max_length=50)
    staff_id: int = Field(gt=0)
    caregiver_accepted: Literal[0, 1] | None
    sent_info_1_at: datetime | None
    sent_info_2_at: datetime | None
    sent_resume_at: datetime | None
    staff_name: str
    staff_phone: str | None


DeliveryStatus = Literal[
    "pending", "processing", "sent", "retryable_failed", "failed", "cancelled"
]


class ActiveMatchingPlanView(_ClosedModel):
    id: int = Field(gt=0)
    case_no: str = Field(min_length=1, max_length=50)
    version: int = Field(ge=1)
    status: Literal["proposed", "accepted"]
    is_active: Literal[1] | None
    order_status: str
    client_line_user_id: str | None


class ActiveMatchingSegmentView(_ClosedModel):
    segment_id: int = Field(gt=0)
    segment_order: int = Field(ge=1, le=4)
    staff_id: int = Field(gt=0)
    assigned_start_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    assigned_end_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    staff_name: str
    staff_line_user_id: str | None
    willingness: Literal["pending", "willing", "unwilling"]
    info_1_sent: bool
    info_2_sent: bool
    resume_sent: bool


class ActiveAvailabilityLockView(_ClosedModel):
    lock_id: int = Field(gt=0)
    plan_id: int = Field(gt=0)
    status: Literal["active"]
    created_by: str
    created_at: datetime


class ActiveDepositProjectionView(_ClosedModel):
    deposit_receivable: int
    deposit_received: int
    deposit_received_at: datetime | None


class ActiveMatchingPlanStateView(_ClosedModel):
    plan: ActiveMatchingPlanView
    segments: list[ActiveMatchingSegmentView] = Field(min_length=1, max_length=4)
    all_willing: bool
    availability_lock: ActiveAvailabilityLockView | None
    deposit: ActiveDepositProjectionView | None


class ContactMatchingPlanView(_ClosedModel):
    id: int = Field(gt=0)
    case_no: str = Field(min_length=1, max_length=50)
    communication_version: int = Field(ge=0)
    status: Literal["draft", "proposed", "accepted", "rejected", "superseded", "cancelled"]
    is_active: Literal[1] | None


class ContactMatchingSegmentView(_ClosedModel):
    segment_id: int = Field(gt=0)
    segment_order: int = Field(ge=1, le=4)
    staff_id: int = Field(gt=0)
    staff_name: str
    assigned_start_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    assigned_end_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    willingness: Literal["pending", "willing", "unwilling"]
    info_1_status: DeliveryStatus | None
    info_2_status: DeliveryStatus | None


class ManualProfilesEvidenceView(_ClosedModel):
    event_ids: list[int] = Field(min_length=1, max_length=4)
    confirmation_method: Literal["phone", "in_person", "paper", "other"]
    reason: str = Field(min_length=1, max_length=500)
    actor_id: str = Field(min_length=1, max_length=191)
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class FormalPlanContactStateView(_ClosedModel):
    plan: ContactMatchingPlanView
    segments: list[ContactMatchingSegmentView] = Field(min_length=1, max_length=4)
    all_willing: bool
    customer_decision: Literal["pending", "accepted", "declined", "contact_requested"]
    customer_profiles_status: DeliveryStatus | None
    customer_profiles_manual_confirmation: ManualProfilesEvidenceView | None


class MatchingPlanSegmentReceiptView(_ClosedModel):
    segment_order: int = Field(ge=1, le=4)
    staff_id: PositiveInt
    assigned_start_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    assigned_end_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")


class MatchingPlanReceiptView(_ClosedModel):
    plan_id: PositiveInt
    case_no: str = Field(min_length=1, max_length=50)
    version: PositiveInt
    status: Literal["proposed"]
    result: Literal["created", "existing"]
    segments: list[MatchingPlanSegmentReceiptView] = Field(
        min_length=1,
        max_length=4,
    )


class MatchingNotificationReceiptView(_ClosedModel):
    intent_id: PositiveInt
    line_delivery_task_id: PositiveInt | None
    delivery_status: Literal["pending", "projected", "failed", "cancelled"]
    notification_kind: Literal[
        "caregiver_info_1",
        "caregiver_info_2",
        "customer_profiles",
    ]


class ManualMatchingProfilesPreviewView(_ClosedModel):
    case_no: str = Field(min_length=1, max_length=50)
    plan_id: PositiveInt
    expected_version: int = Field(ge=0)
    segment_ids: list[PositiveInt] = Field(min_length=1, max_length=4)
    confirmation_method: Literal["phone", "in_person", "paper", "other"]
    reason: str = Field(min_length=1, max_length=500)
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    apply_allowed: bool


class ManualMatchingProfilesReceiptView(_ClosedModel):
    case_no: str = Field(min_length=1, max_length=50)
    plan_id: PositiveInt
    communication_version: int = Field(ge=0)
    event_ids: list[PositiveInt] = Field(min_length=1, max_length=4)
    confirmation_method: Literal["phone", "in_person", "paper", "other"]
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    replayed: bool


class MatchingCustomerDecisionReceiptView(_ClosedModel):
    event_id: PositiveInt
    communication_version: int = Field(ge=0)
    source: Literal["admin"]
    willingness: None
    customer_decision: Literal["accepted", "declined", "contact_requested"]


class MatchingCaregiverWillingnessReceiptView(_ClosedModel):
    event_id: PositiveInt
    communication_version: int = Field(ge=0)
    source: Literal["admin"]
    willingness: Literal["willing", "unwilling"]
    customer_decision: None


class MatchingPlanCancellationReceiptView(_ClosedModel):
    status: Literal["cancelled", "idempotent_replay"]
    event_id: PositiveInt
