"""
File: matching_schedule_confirmation.py
Description: 協調媒合日期表的 LINE 發送、人工快照及逐一確認交易。
"""

class MatchingScheduleConfirmationWorkflow:
    def __init__(self, repository):
        self._repository = repository

    def query(self, case_no, plan_id):
        return self._repository.query(case_no, plan_id)

    def send(self, case_no, plan_id, actor, key):
        try:
            result = self._repository.send(case_no, plan_id, actor, key)
            self._repository.commit()
            return result
        except Exception:
            self._repository.rollback()
            raise

    def preview_manual(self, case_no, plan_id):
        return self._repository.preview_manual(case_no, plan_id)

    def prepare_manual(self, case_no, plan_id, actor, reason, expected_version, fingerprint, key):
        normalized_reason = reason.strip()
        if not normalized_reason:
            raise ValueError("manual_schedule_confirmation_reason_required")
        try:
            result = self._repository.prepare_manual(
                case_no, plan_id, actor, normalized_reason, expected_version, fingerprint, key
            )
            self._repository.commit()
            return result
        except Exception:
            self._repository.rollback()
            raise

    def confirm(self, recipient_id, value, actor, reason, key):
        normalized_reason = reason.strip()
        if value in {"rejected", "manually_confirmed", "manually_revoked"} and not normalized_reason:
            raise ValueError("schedule_confirmation_reason_required")
        try:
            result = self._repository.confirm(recipient_id, value, actor, normalized_reason, key)
            self._repository.commit()
            return result
        except Exception:
            self._repository.rollback()
            raise
