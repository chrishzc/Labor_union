import pytest

from domains.anomalies.current_issue import RecheckScope, build_owner_lock_key
from domains.finance_import.anomaly_remediation import (
    FinanceImportIntegrityCounts,
    FinanceImportIntegrityOwnerFact,
    FinanceImportIntegrityRepairPath,
    FinanceImportSourceCorrectionApplyRequest,
    build_finance_import_integrity_owner_fact,
    build_source_correction_lineage,
    finance_import_integrity_predicate,
)
from infrastructure.mysql.finance_import_current_issue_adapter import (
    FinanceImportSourceCorrectionConflict,
    MySqlFinanceImportCurrentIssueAdapter,
)
from subsystems.finance_import.current_anomaly_facts import (
    FinanceImportAnomalyOwnerReadback,
    build_finance_import_recheck_request,
)


def _fact(
    *,
    batch_identity: str = "finance-import-batch:7",
    batch_version: int = 3,
    counts: FinanceImportIntegrityCounts | None = None,
    authoritative_complete: bool = True,
    canonical_roots_valid: bool = True,
    projection_consistent: bool = True,
    repair_path: FinanceImportIntegrityRepairPath = FinanceImportIntegrityRepairPath.DERIVED_REBUILD,
    source_correction=None,
) -> FinanceImportIntegrityOwnerFact:
    return build_finance_import_integrity_owner_fact(
        batch_identity,
        batch_version,
        "owner-snapshot-token",
        counts or FinanceImportIntegrityCounts(2, 2, 2),
        authoritative_complete=authoritative_complete,
        canonical_roots_valid=canonical_roots_valid,
        projection_consistent=projection_consistent,
        repair_path=repair_path,
        source_correction=source_correction,
    )


def _source_request() -> FinanceImportSourceCorrectionApplyRequest:
    return FinanceImportSourceCorrectionApplyRequest(
        "finance-import-batch:7",
        3,
        "finance-import-batch:8",
        1,
        "operator-7",
        "human confirmed source correction",
        "evidence-7",
    )


def test_pending_rows_are_not_current_integrity_inconsistency() -> None:
    fact = _fact(counts=FinanceImportIntegrityCounts(2, 2, 2, non_pending_inconsistent_count=0))
    assert fact.unresolved_reason_codes == ()
    assert finance_import_integrity_predicate(fact) is False


@pytest.mark.parametrize(
    "counts",
    [
        FinanceImportIntegrityCounts(2, 1, 1),
        FinanceImportIntegrityCounts(2, 3, 3),
        FinanceImportIntegrityCounts(2, 3, 2),
        FinanceImportIntegrityCounts(2, 2, 2, non_pending_inconsistent_count=1),
        FinanceImportIntegrityCounts(2, 2, 2, partial_batch_count=1),
    ],
)
def test_each_nonzero_integrity_component_keeps_issue_active(
    counts: FinanceImportIntegrityCounts,
) -> None:
    assert _fact(counts=counts).predicate_active is True


def test_derived_projection_rebuild_is_same_batch_and_stays_active_until_fresh_readback() -> None:
    stale = _fact(projection_consistent=False)
    assert stale.repair_is_deterministic_rebuild is True
    assert stale.predicate_active is True
    fresh = _fact(projection_consistent=True)
    assert fresh.batch_identity == stale.batch_identity
    assert fresh.batch_version == stale.batch_version
    assert fresh.predicate_active is False


def test_terminal_source_correction_clears_old_immutable_error() -> None:
    lineage = build_source_correction_lineage(
        _source_request(),
        successor_unique=True,
        successor_completed=True,
        successor_fresh_verified=True,
        successor_covers_all_current_problems=True,
        accepted_in_owner_uow=True,
    )
    fact = _fact(
        counts=FinanceImportIntegrityCounts(2, 1, 1),
        canonical_roots_valid=False,
        projection_consistent=False,
        repair_path=FinanceImportIntegrityRepairPath.SOURCE_CORRECTION,
        source_correction=lineage,
    )
    assert lineage.terminal is True
    assert fact.unresolved_reason_codes == ()
    assert fact.predicate_active is False


def test_partial_source_correction_keeps_original_issue_active() -> None:
    lineage = build_source_correction_lineage(
        _source_request(),
        successor_unique=True,
        successor_completed=True,
        successor_fresh_verified=False,
        successor_covers_all_current_problems=True,
        accepted_in_owner_uow=True,
    )
    fact = _fact(
        counts=FinanceImportIntegrityCounts(2, 1, 1),
        repair_path=FinanceImportIntegrityRepairPath.SOURCE_CORRECTION,
        source_correction=lineage,
    )
    assert fact.predicate_active is True
    assert "successor_not_fresh" in {reason.value for reason in fact.unresolved_reason_codes}


def test_ambiguous_source_correction_keeps_issue_active() -> None:
    lineage = build_source_correction_lineage(
        _source_request(),
        successor_unique=False,
        successor_completed=True,
        successor_fresh_verified=True,
        successor_covers_all_current_problems=True,
        accepted_in_owner_uow=True,
    )
    fact = _fact(
        counts=FinanceImportIntegrityCounts(2, 2, 2),
        repair_path=FinanceImportIntegrityRepairPath.SOURCE_CORRECTION,
        source_correction=lineage,
    )
    assert fact.predicate_active is True
    assert "successor_not_unique" in {reason.value for reason in fact.unresolved_reason_codes}


def test_source_correction_rejects_same_batch_successor() -> None:
    with pytest.raises(ValueError, match="new batch"):
        FinanceImportSourceCorrectionApplyRequest(
            "finance-import-batch:7", 3, "finance-import-batch:7", 4,
            "operator-7", "correction", "evidence-7",
        )


class _OwnerRepository:
    def __init__(self, fact):
        self.fact = fact
        self.calls = []

    def read_integrity(self, batch_identity, *, for_update=False):
        self.calls.append((batch_identity, for_update))
        return self.fact

    def append_source_correction_lineage(self, request, lineage):
        return "lineage-1"


def test_owner_readback_is_closed_and_recheck_binds_exact_version() -> None:
    repository = _OwnerRepository(_fact())
    readback = FinanceImportAnomalyOwnerReadback(repository)
    fact = readback.read("IMPORT-006", "finance-import-batch:7", for_update=True)
    request = build_finance_import_recheck_request(
        "finance-import-batch:7", fact, intent_identity="intent-7"
    )
    assert request.owner_version == 3
    assert repository.calls == [("finance-import-batch:7", True)]
    with pytest.raises(ValueError, match="not_supported"):
        readback.read("IMPORT-005", "finance-import-batch:7")


def test_mysql_readback_locks_batch_contract_before_aggregates() -> None:
    class Cursor:
        def __init__(self):
            self.executions = []
            self.responses = [
                {"batch_id": 7, "batch_identity": "finance-import-batch:7", "batch_version": 3,
                 "row_count": 2, "status": "completed"},
                {"occurrence_count": 2, "distinct_canonical_count": 2,
                 "non_pending_inconsistent_count": 0, "partial_batch_count": 0},
                None,
            ]

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, query, params):
            self.executions.append((query, params))

        def fetchone(self):
            return self.responses.pop(0)

    class Connection:
        def __init__(self):
            self.cursor_value = Cursor()

        def cursor(self):
            return self.cursor_value

    connection = Connection()
    fact = MySqlFinanceImportCurrentIssueAdapter(connection).read_integrity(
        "finance-import-batch:7", for_update=True
    )
    assert fact.predicate_active is False
    assert "FOR UPDATE" in connection.cursor_value.executions[0][0]
    assert connection.cursor_value.executions[0][1] == ("finance-import-batch:7",)
    assert connection.cursor_value.executions[1][1] == (7, 7)


def test_source_correction_write_rejects_lineage_for_another_successor() -> None:
    adapter = MySqlFinanceImportCurrentIssueAdapter(None)
    lineage = build_source_correction_lineage(
        _source_request(),
        successor_unique=True,
        successor_completed=True,
        successor_fresh_verified=True,
        successor_covers_all_current_problems=True,
        accepted_in_owner_uow=True,
    )
    mismatched_request = FinanceImportSourceCorrectionApplyRequest(
        "finance-import-batch:7", 3, "finance-import-batch:9", 1,
        "operator-7", "human confirmed source correction", "evidence-7",
    )
    with pytest.raises(ValueError, match="does not match Apply request"):
        adapter.append_source_correction_lineage(mismatched_request, lineage)


def test_source_correction_append_derives_successor_flags_from_fresh_owner_facts() -> None:
    class Cursor:
        lastrowid = 19

        def __init__(self):
            self.response = None
            self.executions = []

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, query, params):
            self.executions.append((query, params))

        def fetchone(self):
            return self.response

    class Connection:
        def __init__(self):
            self.cursor_value = Cursor()

        def cursor(self):
            return self.cursor_value

    adapter = MySqlFinanceImportCurrentIssueAdapter(Connection())
    original = _fact(counts=FinanceImportIntegrityCounts(2, 1, 1))
    successor = _fact(batch_identity="finance-import-batch:8", batch_version=1)
    adapter.read_integrity = lambda identity, *, for_update=False: (
        original if identity == "finance-import-batch:7" else successor
    )
    untrusted_flags = build_source_correction_lineage(
        _source_request(),
        successor_unique=False,
        successor_completed=False,
        successor_fresh_verified=False,
        successor_covers_all_current_problems=False,
        accepted_in_owner_uow=False,
    )
    result = adapter.append_source_correction_lineage(_source_request(), untrusted_flags)
    assert result == "finance-import-source-correction:19"
    assert adapter._connection.cursor_value.executions[-1][1] == (
        7, "finance-import-batch:7", 3, 8, "finance-import-batch:8", 1,
        "operator-7", "human confirmed source correction", "evidence-7",
    )


def test_source_correction_append_replays_exact_row_and_rejects_conflict() -> None:
    class Cursor:
        def __init__(self, row):
            self.row = row

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, *_args):
            return None

        def fetchone(self):
            return self.row

    class Connection:
        def __init__(self, row):
            self.cursor_value = Cursor(row)

        def cursor(self):
            return self.cursor_value

    request = _source_request()
    row = {
        "id": 19,
        "original_batch_id": 7,
        "original_batch_identity": request.original_batch_identity,
        "original_batch_version": request.expected_original_batch_version,
        "corrected_successor_batch_id": 8,
        "corrected_successor_batch_identity": request.corrected_successor_batch_identity,
        "corrected_successor_version": request.corrected_successor_batch_version,
        "actor": request.actor,
        "reason": request.reason,
        "evidence_reference": request.evidence_reference,
    }
    assert MySqlFinanceImportCurrentIssueAdapter(Connection(row)).append_source_correction_lineage(request) == "finance-import-source-correction:19"
    conflict = dict(row, corrected_successor_batch_identity="finance-import-batch:9")
    with pytest.raises(FinanceImportSourceCorrectionConflict):
        MySqlFinanceImportCurrentIssueAdapter(Connection(conflict)).append_source_correction_lineage(request)


def test_source_correction_reader_verifies_successor_facts_instead_of_stored_flags() -> None:
    class Cursor:
        def __init__(self):
            self.responses = [
                {
                    "id": 19,
                    "original_batch_id": 7,
                    "original_batch_identity": "finance-import-batch:7",
                    "original_batch_version": 3,
                    "corrected_successor_batch_id": 8,
                    "corrected_successor_batch_identity": "finance-import-batch:8",
                    "corrected_successor_version": 1,
                    "actor": "operator-7",
                    "reason": "human confirmed source correction",
                    "evidence_reference": "evidence-7",
                },
                {"batch_id": 8, "batch_identity": "finance-import-batch:8", "batch_version": 1,
                 "row_count": 2, "status": "completed"},
                {"occurrence_count": 2, "distinct_canonical_count": 2,
                 "non_pending_inconsistent_count": 0, "partial_batch_count": 0},
            ]

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, *_args):
            return None

        def fetchone(self):
            return self.responses.pop(0)

    class Connection:
        def __init__(self):
            self.cursor_value = Cursor()

        def cursor(self):
            return self.cursor_value

    lineage = MySqlFinanceImportCurrentIssueAdapter(Connection()).read_source_correction_lineage(
        "finance-import-batch:7", 3
    )
    assert lineage is not None
    assert lineage.terminal is True


def test_source_correction_append_rejects_successor_with_current_problems() -> None:
    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, *_args):
            return None

        def fetchone(self):
            return None

    class Connection:
        def cursor(self):
            return Cursor()

    adapter = MySqlFinanceImportCurrentIssueAdapter(Connection())
    adapter.read_integrity = lambda identity, *, for_update=False: (
        _fact(counts=FinanceImportIntegrityCounts(2, 1, 1))
        if identity == "finance-import-batch:7"
        else _fact(batch_identity="finance-import-batch:8", batch_version=1, counts=FinanceImportIntegrityCounts(2, 1, 1))
    )
    with pytest.raises(ValueError, match="successor_incomplete"):
        adapter.append_source_correction_lineage(_source_request())


def test_scope_readback_uses_finance_import_owner_lock() -> None:
    repository = _OwnerRepository(_fact())
    scope = RecheckScope(
        "finance_import", "finance_import_batch", "IMPORT-006",
        ("finance-import-batch:7",),
        (build_owner_lock_key("finance_import", "finance_import_batch", "finance-import-batch:7"),),
    )
    snapshot = FinanceImportAnomalyOwnerReadback(repository).read_owner_snapshot(scope)
    assert snapshot.authoritative_complete is True
    assert snapshot.facts[0].batch_identity == "finance-import-batch:7"
