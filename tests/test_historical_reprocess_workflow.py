from domains.finance_import.planning import (
    CanonicalFinanceImportRow,
    FinanceClassificationType,
    FinanceImportDisposition,
)
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from shared_kernel.money import MoneyNTD
from subsystems.finance_import.historical_reprocess_workflow import (
    HistoricalReprocessApplyRequest,
    HistoricalReprocessFacts,
    HistoricalReprocessRow,
    HistoricalReprocessWorkflow,
)
from subsystems.finance_import.import_workflow import (
    FinanceDispatchOutcome,
    FinanceImportDispatchResult,
)


def _row():
    after = CanonicalFinanceImportRow(
        "row:1", 2, MoneyNTD(300), FinanceClassificationType.CLIENT_REFUND,
        FinanceImportDisposition.CREATE, PreviewFingerprint("a" * 64), ("client:1",), (), (),
    )
    return HistoricalReprocessRow("row:1", FinanceClassificationType.NON_BUSINESS_REVIEW, after)


def _facts(version=4):
    return HistoricalReprocessFacts("batch:1", version, True, "classifier:v2", (_row(),))


class _UnitOfWork:
    def __init__(self, repository=None):
        self.repository = repository
        self.committed = False
        self.calls_snapshot = None

    def __enter__(self):
        if self.repository is not None:
            self.calls_snapshot = list(self.repository.calls)
        return self

    def __exit__(self, exception_type, *_):
        if exception_type is not None and self.calls_snapshot is not None:
            self.repository.calls = self.calls_snapshot
        return False

    def commit(self): self.committed = True


class _Repository:
    def __init__(self): self.facts = _facts(); self.receipts = {}; self.calls = []
    def load_historical_reprocess(self, _, *, for_update): return self.facts
    def find_historical_reprocess_receipt(self, key): return self.receipts.get(key.value)
    def append_reprocess_classification_events(self, plan, actor): self.calls.append(("classification", plan, actor))
    def append_reprocess_run(self, plan, count): self.calls.append(("run", plan, count)); return 99
    def append_reprocess_outbox(self, plan): self.calls.append(("outbox", plan))
    def advance_batch_version(self, *args): self.calls.append(("version", *args))
    def save_historical_reprocess_receipt(self, key, stored): self.receipts[key.value] = stored


class _PostingPort:
    def __init__(self): self.rows = []
    def resolve(self, row): return row
    def post(self, row):
        self.rows.append(row)
        return FinanceImportDispatchResult(
            row.row_identity,
            FinanceDispatchOutcome.RECONCILED,
            "client-finance:test",
        )


def _request(preview, version=4, key="reprocess-1"):
    return HistoricalReprocessApplyRequest("batch:1", ExpectedVersion(version), preview.fingerprint, IdempotencyKey(key), ActorContext("admin"), "reclassify historical row", CorrelationId("reprocess-test"))


def test_apply_appends_events_dispatch_receipt_and_outbox_in_one_unit_of_work():
    repository = _Repository(); posting = _PostingPort(); unit = _UnitOfWork()
    workflow = HistoricalReprocessWorkflow(repository, posting, lambda: unit)
    preview = workflow.preview("batch:1", CorrelationId("preview"))

    receipt = workflow.apply(_request(preview))

    assert receipt.reclassified_count == receipt.dispatched_count == 1
    assert receipt.reprocess_run_id == 99
    assert [call[0] for call in repository.calls] == ["classification", "run", "outbox", "version"]
    assert posting.rows == [_row().after]
    assert unit.committed is True


def test_apply_replays_same_idempotency_key_without_second_dispatch():
    repository = _Repository(); posting = _PostingPort(); workflow = HistoricalReprocessWorkflow(repository, posting, _UnitOfWork)
    preview = workflow.preview("batch:1", CorrelationId("preview")); request = _request(preview)

    first = workflow.apply(request); second = workflow.apply(request)

    assert second == first
    assert len(posting.rows) == 1


def test_apply_appends_classification_before_owning_domain_dispatch():
    steps = []

    class OrderedRepository(_Repository):
        def append_reprocess_classification_events(self, plan, actor):
            steps.append("classification")
            super().append_reprocess_classification_events(plan, actor)

    class OrderedPostingPort(_PostingPort):
        def post(self, row):
            steps.append("dispatch")
            return super().post(row)

    repository = OrderedRepository()
    workflow = HistoricalReprocessWorkflow(
        repository,
        OrderedPostingPort(),
        _UnitOfWork,
    )
    preview = workflow.preview("batch:1", CorrelationId("preview"))

    workflow.apply(_request(preview))

    assert steps == ["classification", "dispatch"]


def test_apply_rejects_stale_batch_version_before_dispatch():
    repository = _Repository(); posting = _PostingPort(); workflow = HistoricalReprocessWorkflow(repository, posting, _UnitOfWork)
    preview = workflow.preview("batch:1", CorrelationId("preview"))

    try: workflow.apply(_request(preview, version=3))
    except Exception as error: assert error.error.code == "stale_preview"
    else: raise AssertionError("stale reprocess must not dispatch")

    assert posting.rows == []


def test_apply_rejects_nonfinal_owning_domain_result_without_persisting_reprocess():
    class PendingPostingPort(_PostingPort):
        def post(self, row):
            self.rows.append(row)
            return FinanceImportDispatchResult(
                row.row_identity,
                FinanceDispatchOutcome.PENDING,
            )

    repository = _Repository()
    unit_of_work = _UnitOfWork(repository)
    workflow = HistoricalReprocessWorkflow(
        repository,
        PendingPostingPort(),
        lambda: unit_of_work,
    )
    preview = workflow.preview("batch:1", CorrelationId("preview"))

    try:
        workflow.apply(_request(preview))
    except Exception as error:
        assert error.error.code == "historical_reprocess_dispatch_not_final"
    else:
        raise AssertionError("non-final dispatch must block Historical Reprocess")

    assert repository.calls == []
    assert unit_of_work.committed is False
