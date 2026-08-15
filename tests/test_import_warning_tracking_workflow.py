"""
File: test_import_warning_tracking_workflow.py
Description: 驗證匯入警示追蹤的 Preview 零寫入與 Apply 單一交易邊界。
"""

from domains.anomalies.import_warning_tracking import ImportWarningTrackingStatus
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from subsystems.anomalies.import_warning_tracking_workflow import (
    ImportWarningTask,
    ImportWarningTrackingApplication,
    WarningTransitionRequest,
)


class _UnitOfWork:
    def __init__(self) -> None:
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def commit(self) -> None:
        self.committed = True


class _Repository:
    def __init__(self, task: ImportWarningTask) -> None:
        self.task = task
        self.applied = False

    def query_tasks(self, **_):
        return (self.task,)

    def load_task(self, *_ , **__):
        return self.task

    def replay(self, _request):
        return None

    def apply_transition(self, _task, _request, preview):
        self.applied = True
        return preview


def _request() -> WarningTransitionRequest:
    return WarningTransitionRequest(
        occurrence_identity="warning-1",
        expected_version=1,
        target_status=ImportWarningTrackingStatus.AWAITING_EXTERNAL_CONFIRMATION,
        actor=ActorContext("operator-1"),
        reason_code="contact_started",
        note=None,
        evidence_reference=None,
        idempotency_key=IdempotencyKey("warning-1-contact"),
        correlation_id=CorrelationId("warning-1-contact"),
    )


def test_preview_does_not_write_tracking_state() -> None:
    task = ImportWarningTask("warning-1", "hcm", "IMPORT-004", "phone", "masked", (), ImportWarningTrackingStatus.OPEN, 1, None)
    repository = _Repository(task)
    application = ImportWarningTrackingApplication(repository, _UnitOfWork)

    preview = application.preview(_request())

    assert preview.resulting_status is ImportWarningTrackingStatus.AWAITING_EXTERNAL_CONFIRMATION
    assert repository.applied is False


def test_apply_appends_through_repository_and_commits_once() -> None:
    task = ImportWarningTask("warning-1", "hcm", "IMPORT-004", "phone", "masked", (), ImportWarningTrackingStatus.OPEN, 1, None)
    repository = _Repository(task)
    unit_of_work = _UnitOfWork()
    application = ImportWarningTrackingApplication(repository, lambda: unit_of_work)

    application.apply(_request())

    assert repository.applied is True
    assert unit_of_work.committed is True
