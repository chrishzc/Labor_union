"""
File: import_warning_tracking_workflow.py
Description: 編排匯入警示唯讀查詢、業務顯示、業面導向與版本轉態。
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Protocol

from domains.anomalies.import_warning_tracking import (
    ImportWarningTrackingStatus,
    WarningTransitionError,
    preview_warning_transition,
)
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey


@dataclass(frozen=True, slots=True)
class ImportWarningTask:
    occurrence_identity: str
    owning_lane: str
    logical_code: str
    field_path: str
    masked_subject: str
    issue_codes: tuple[str, ...]
    tracking_status: ImportWarningTrackingStatus
    tracking_version: int
    evidence_reference: str | None
    navigation_action: str | None = None
    display_message: str | None = None


@dataclass(frozen=True, slots=True)
class WarningTransitionRequest:
    occurrence_identity: str
    expected_version: int
    target_status: ImportWarningTrackingStatus
    actor: ActorContext
    reason_code: str
    note: str | None
    evidence_reference: str | None
    idempotency_key: IdempotencyKey
    correlation_id: CorrelationId


@dataclass(frozen=True, slots=True)
class WarningTransitionPreview:
    occurrence_identity: str
    expected_version: int
    resulting_status: ImportWarningTrackingStatus
    resulting_version: int


@dataclass(frozen=True, slots=True)
class WarningTransitionReceipt:
    occurrence_identity: str
    before_status: ImportWarningTrackingStatus
    after_status: ImportWarningTrackingStatus
    resulting_version: int
    receipt_identity: str
    correlation_id: str
    replayed: bool


@dataclass(frozen=True, slots=True)
class WarningReferralDescriptor:
    """UI-neutral, privacy-safe context for entering an owning workflow."""

    occurrence_identity: str
    expected_version: int
    owning_lane: str
    logical_code: str
    field_path: str
    masked_subject: str
    display_message: str
    navigation_action: str
    action_kind: str
    target_command: str | None


class ImportWarningTrackingRepository(Protocol):
    def query_tasks(self, *, active_only: bool, limit: int, offset: int) -> tuple[ImportWarningTask, ...]: ...

    def load_task(self, occurrence_identity: str, *, for_update: bool) -> ImportWarningTask | None: ...

    def replay(
        self,
        request: WarningTransitionRequest,
    ) -> WarningTransitionReceipt | None: ...

    def apply_transition(
        self,
        task: ImportWarningTask,
        request: WarningTransitionRequest,
        preview: WarningTransitionPreview,
    ) -> WarningTransitionReceipt: ...

    def lookup_receipt(self, receipt_identity: str) -> WarningTransitionReceipt | None: ...


class ImportWarningTrackingApplication:
    def __init__(self, repository: ImportWarningTrackingRepository, unit_of_work_factory) -> None:
        self._repository = repository
        self._unit_of_work_factory = unit_of_work_factory

    def query_tasks(self, *, active_only: bool = True, limit: int = 100, offset: int = 0) -> tuple[ImportWarningTask, ...]:
        return tuple(
            replace(
                task,
                navigation_action=_navigation_action(task),
                display_message=_display_message(task),
            )
            for task in self._repository.query_tasks(
                active_only=active_only, limit=limit, offset=offset
            )
        )

    def preview(self, request: WarningTransitionRequest) -> WarningTransitionPreview:
        task = self._require_task(request.occurrence_identity, for_update=False)
        return self._preview(task, request)

    def query_referral(
        self,
        occurrence_identity: str,
        *,
        expected_version: int,
    ) -> WarningReferralDescriptor:
        """Return owner navigation context without writing or exposing source data."""
        task = self._require_task(occurrence_identity, for_update=False)
        if expected_version != task.tracking_version:
            raise ValueError("import_warning_version_conflict")
        action = _hcm_referral_action(task)
        if action is None:
            raise ValueError("import_warning_referral_unavailable")
        navigation_action = _navigation_action(task)
        if navigation_action is None:
            raise ValueError("import_warning_referral_unavailable")
        action_kind, target_command = action
        return WarningReferralDescriptor(
            occurrence_identity=task.occurrence_identity,
            expected_version=task.tracking_version,
            owning_lane=task.owning_lane,
            logical_code=task.logical_code,
            field_path=task.field_path,
            masked_subject=task.masked_subject,
            display_message=_display_message(task),
            navigation_action=navigation_action,
            action_kind=action_kind,
            target_command=target_command,
        )

    def apply(self, request: WarningTransitionRequest) -> WarningTransitionReceipt:
        with self._unit_of_work_factory() as unit_of_work:
            replay = self._repository.replay(request)
            if replay is not None:
                return replay
            task = self._require_task(request.occurrence_identity, for_update=True)
            replay = self._repository.replay(request)
            if replay is not None:
                return replay
            preview = self._preview(task, request)
            receipt = self._repository.apply_transition(task, request, preview)
            unit_of_work.commit()
        return receipt

    def query_receipt(self, receipt_identity: str) -> WarningTransitionReceipt:
        receipt = self._repository.lookup_receipt(receipt_identity)
        if receipt is None:
            raise ValueError("import_warning_receipt_not_found")
        return receipt

    def _require_task(self, occurrence_identity: str, *, for_update: bool) -> ImportWarningTask:
        task = self._repository.load_task(occurrence_identity, for_update=for_update)
        if task is None:
            raise ValueError("import_warning_not_found")
        return task

    @staticmethod
    def _preview(task: ImportWarningTask, request: WarningTransitionRequest) -> WarningTransitionPreview:
        try:
            transition = preview_warning_transition(
                current_status=task.tracking_status,
                current_version=task.tracking_version,
                target_status=request.target_status,
                actor_kind="system" if request.actor.actor_id == "system" else "union_operator",
            )
        except WarningTransitionError as error:
            raise ValueError("import_warning_transition_not_allowed") from error
        if request.expected_version != task.tracking_version:
            raise ValueError("import_warning_version_conflict")
        return WarningTransitionPreview(
            occurrence_identity=task.occurrence_identity,
            expected_version=task.tracking_version,
            resulting_status=transition.resulting_status,
            resulting_version=task.tracking_version + 1,
        )


def _navigation_action(task: ImportWarningTask) -> str | None:
    """Return a UI-neutral owner-screen action, never a correction command or URL."""
    if task.tracking_status in {
        ImportWarningTrackingStatus.CLOSED,
        ImportWarningTrackingStatus.AUTO_RESOLVED,
    }:
        return None
    if task.owning_lane == "hcm" and task.logical_code in {
        "HCM-CASE-002",
        "HCM-FIELD-001",
        "HCM-FIELD-002",
        "HCM-LINK-001",
        "HCM-LINK-002",
        "HCM-BECLASS-001",
    }:
        return "hcm_import_center"
    if task.owning_lane == "historical_order" and task.logical_code in {
        "ORDER-HIST-FIELD-001",
        "ORDER-HIST-STAFF-001",
        "ORDER-HIST-STAFF-002",
        "ORDER-HIST-ASSIGNMENT-001",
    }:
        return "historical_order_import_center"
    if task.owning_lane == "beclass_client" and task.logical_code in {
        "CLIENT-BECLASS-BIND-001",
        "CLIENT-BECLASS-BIND-002",
        "CLIENT-BECLASS-BIND-003",
        "CLIENT-BECLASS-SOURCE-001",
    }:
        return "client_beclass_import_center"
    if task.owning_lane == "beclass_staff" and task.logical_code in {
        "STAFF-BECLASS-IDENTITY-001",
        "STAFF-BECLASS-NAME-001",
        "STAFF-BECLASS-IDENTITY-002",
        "STAFF-BECLASS-NAME-002",
        "STAFF-BECLASS-FIELD-002",
    }:
        return "staff_beclass_import_center"
    if task.owning_lane == "finance_import" and task.logical_code in {
        "FINANCE-SOURCE-001",
        "FINANCE-ROW-001",
    }:
        return "finance_import_recovery_center"
    return None


def _hcm_referral_action(task: ImportWarningTask) -> tuple[str, str | None] | None:
    """Fail closed unless the HCM logical type has an approved owner outcome."""
    if task.owning_lane != "hcm":
        return None
    if task.logical_code in {
        "HCM-CASE-002",
        "HCM-FIELD-001",
        "HCM-FIELD-002",
        "HCM-LINK-001",
        "HCM-LINK-002",
    }:
        return ("owner_preview_apply", "preview_hcm_resubmission")
    if task.logical_code == "HCM-BECLASS-001":
        return ("wait_for_counterpart", None)
    return None


def _display_message(task: ImportWarningTask) -> str:
    """Render stable business wording while logical codes stay field-agnostic."""
    field = {"身分證字號": "身分證"}.get(task.field_path, task.field_path)
    if (
        task.logical_code == "CLIENT-BECLASS-SOURCE-001"
        and task.field_path == "$requires_cooking"
    ):
        return "料理需求答案無法判定"
    if (
        task.logical_code == "CLIENT-BECLASS-SOURCE-001"
        and "client_beclass_source_payload_conflict" in task.issue_codes
    ):
        return "來源資料與既有匯入內容不同"
    if task.logical_code == "CLIENT-BECLASS-SOURCE-001":
        if any(issue.startswith("client_field_missing:") for issue in task.issue_codes):
            return f"缺少{field}"
        if any(issue.startswith("client_field_invalid:") for issue in task.issue_codes):
            return f"{field}格式錯誤"
        return f"{field}缺漏或格式錯誤"
    if task.logical_code == "HCM-FIELD-001":
        return f"缺少{field}"
    if task.logical_code in {"HCM-FIELD-002", "STAFF-BECLASS-FIELD-002"}:
        if any(
            issue.startswith("historical_nonempty_conflict:")
            for issue in task.issue_codes
        ):
            return f"{field}與現有資料衝突"
        return f"{field}格式錯誤"
    if task.logical_code == "FINANCE-SOURCE-001":
        label = {
            "transaction_date": "交易日期",
            "posting_date": "帳務日期",
            "value_date": "計息日期",
            "transaction_amount": "交易金額",
            "source_bank_account": "來源銀行帳號",
        }.get(task.field_path, task.field_path)
        if any(
            issue.startswith("finance_source_field_missing:")
            for issue in task.issue_codes
        ):
            return f"缺少{label}"
        return f"{label}格式錯誤"
    messages = {
        "HCM-LINK-001": "疑似已有客戶，待確認連結",
        "HCM-LINK-002": "無法唯一確認客戶身分",
        "HCM-CASE-002": "HCM 案件內容與現有資料衝突",
        "HCM-BECLASS-001": "等待客戶完成 BeClass 資料",
        "STAFF-BECLASS-IDENTITY-001": "缺少身分證",
        "STAFF-BECLASS-NAME-001": "缺少姓名",
        "STAFF-BECLASS-IDENTITY-002": "身分證對應多筆服務人員",
        "STAFF-BECLASS-NAME-002": "歷史姓名已更新",
        "CLIENT-BECLASS-BIND-001": "找不到對應客戶",
        "CLIENT-BECLASS-BIND-002": "對應到多筆客戶",
        "CLIENT-BECLASS-BIND-003": "客戶案件關聯無法唯一確認",
        "ORDER-HIST-STAFF-001": "找不到對應服務人員",
        "ORDER-HIST-STAFF-002": "對應到多筆服務人員",
        "ORDER-HIST-ASSIGNMENT-001": "歷史訂單服務人員配對衝突",
        "ORDER-HIST-FIELD-001": "歷史訂單欄位衝突",
        "FINANCE-ROW-001": "銀行流水待確認歸屬",
    }
    return messages.get(task.logical_code, "匯入資料待人工確認")


__all__ = [
    "ImportWarningTask",
    "ImportWarningTrackingApplication",
    "ImportWarningTrackingRepository",
    "WarningTransitionPreview",
    "WarningTransitionReceipt",
    "WarningTransitionRequest",
    "WarningReferralDescriptor",
    "_display_message",
]
