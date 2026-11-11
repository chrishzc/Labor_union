"""Transactional application service for one active LINE provisional registration."""

from __future__ import annotations

from domains.case_import.provisional_registration import (
    ProvisionalRegistrationDomainError,
    ProvisionalRegistrationIntent,
    build_provisional_registration_candidate,
)
from subsystems.case_import.provisional_registration_types import (
    ProvisionalRegistrationConflict,
    ProvisionalRegistrationConflictError,
    ProvisionalRegistrationReceipt,
    ProvisionalRegistrationStorageError,
)


def registration_confirmation_text(name: str, *, approved: bool, case_no: str | None = None) -> str:
    if not approved:
        return f"【系統通知】\n{name}您好，需求申請已送出，待工會人員核准後才建立正式客戶資料。送出申請不代表已完成媒合。"
    if case_no:
        return f"【系統通知】\n{name}您好，非市民服務申請已核准。\n案件編號：{case_no}\n工會將與您確認後續服務安排。"
    return (
        f"【系統通知】\n服務登記與綁定成功！您的 LINE 帳號已連結至客戶「{name}」的專屬資料庫。\n"
        "您的案件編號尚待行政核發；完成核對後將主動通知您。\n"
        "工會行政專員將於上班時間透過 LINE 與您聯繫確認服務細節，請您耐心等候！"
    )


class ProvisionalRegistrationApplication:
    def __init__(self, repository, unit_of_work_factory) -> None:
        self._repository = repository
        self._unit_of_work_factory = unit_of_work_factory

    def apply(self, intent: ProvisionalRegistrationIntent) -> ProvisionalRegistrationReceipt:
        candidate = build_provisional_registration_candidate(intent)
        with self._unit_of_work_factory() as unit_of_work:
            outcome = self._repository.apply(candidate)
            unit_of_work.commit()
        if isinstance(outcome, ProvisionalRegistrationConflict):
            raise ProvisionalRegistrationConflictError("registration_conflict")
        return outcome


__all__ = [
    "ProvisionalRegistrationApplication",
    "ProvisionalRegistrationConflictError",
    "ProvisionalRegistrationDomainError",
    "ProvisionalRegistrationReceipt",
    "ProvisionalRegistrationStorageError",
]
