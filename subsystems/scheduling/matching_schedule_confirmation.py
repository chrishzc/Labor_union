"""Application workflow for matching schedule delivery and confirmation."""

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

    def confirm(self, recipient_id, value, actor, reason, key):
        if value == "rejected" and not reason.strip():
            raise ValueError("schedule_rejection_reason_required")
        try:
            result = self._repository.confirm(recipient_id, value, actor, reason.strip(), key)
            self._repository.commit()
            return result
        except Exception:
            self._repository.rollback()
            raise
