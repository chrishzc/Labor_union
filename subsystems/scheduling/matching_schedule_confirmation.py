"""
File: matching_schedule_confirmation.py
Description: 協調媒合日期表的 LINE 發送、人工快照及逐一確認交易。
"""

from typing import Callable

class MatchingScheduleConfirmationWorkflow:
    def __init__(self, repository, unit_of_work_factory: Callable[[], object]):
        self._repository = repository
        self._unit_of_work_factory = unit_of_work_factory

    def query(self, case_no, plan_id):
        return self._repository.query(case_no, plan_id)

    def send(self, case_no, plan_id, actor, key):
        with self._unit_of_work_factory() as unit_of_work:
            result = self._repository.send(case_no, plan_id, actor, key)
            unit_of_work.commit()
            return result

    def preview_manual(self, case_no, plan_id):
        return self._repository.preview_manual(case_no, plan_id)

    def prepare_manual(self, case_no, plan_id, actor, reason, expected_version, fingerprint, key):
        normalized_reason = reason.strip()
        if not normalized_reason:
            raise ValueError("manual_schedule_confirmation_reason_required")
        with self._unit_of_work_factory() as unit_of_work:
            result = self._repository.prepare_manual(
                case_no, plan_id, actor, normalized_reason, expected_version, fingerprint, key
            )
            unit_of_work.commit()
            return result

    def confirm(self, recipient_id, value, actor, reason, key):
        normalized_reason = reason.strip()
        if value in {"rejected", "manually_confirmed", "manually_revoked"} and not normalized_reason:
            raise ValueError("schedule_confirmation_reason_required")
        with self._unit_of_work_factory() as unit_of_work:
            result = self._repository.confirm(recipient_id, value, actor, normalized_reason, key)
            unit_of_work.commit()
            return result
