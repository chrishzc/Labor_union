import pandas as pd
import pytest

from domains.client_finance.virtual_account import allows_historical_non_citizen_account
from subsystems.client_finance.legacy_virtual_account_workbook import (
    LegacyVirtualAccountWorkbookConflict,
    LegacyVirtualAccountWorkbookService,
)


class _Repository:
    def __init__(self, orders=(), mappings=()):
        self.orders = set(orders)
        self.mappings = set(mappings)
        self.receipts = {}

    def acquire_lock(self, key):
        return True

    def release_lock(self, key):
        pass

    def row_state(self, case_no, virtual_account, *, lock):
        del lock
        if case_no not in self.orders:
            return "missing_order"
        return "existing" if (case_no, virtual_account) in self.mappings else "create"

    def insert_mapping(self, case_no, virtual_account, source_digest, source_row, actor):
        del source_digest, source_row, actor
        pair = (case_no, virtual_account)
        if pair in self.mappings:
            return False
        self.mappings.add(pair)
        return True

    def effective_non_citizen_account_owner(self, account):
        owners = {case for case, number in self.mappings if number == account}
        if len(owners) != 1:
            return None
        owner = owners.pop()
        if allows_historical_non_citizen_account(owner) and sum(case == owner for case, _ in self.mappings) == 1:
            return owner
        return None

    def load_receipt(self, key):
        return self.receipts.get(key)

    def save_receipt(self, key, request_fingerprint, preview_fingerprint, actor, result):
        del actor
        self.receipts[key] = {
            "request_fingerprint": request_fingerprint,
            "preview_fingerprint": preview_fingerprint,
            "result_snapshot": __import__("json").dumps(result),
        }


class _UnitOfWork:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def commit(self):
        pass


def _workbook(tmp_path, rows, name="accounts.xlsx"):
    path = tmp_path / name
    pd.DataFrame(rows, columns=["虛擬帳號", "市府訂單號碼"]).to_excel(path, index=False)
    return path


def test_preview_imports_only_valid_rows_with_existing_orders(tmp_path):
    path = _workbook(tmp_path, [
        ["99781699114001", "114000001"],
        ["99781699114002", None],
        ["99781699114003", "114000003"],
        ["99781699004(社)", "114000004"],
    ])
    service = LegacyVirtualAccountWorkbookService(_Repository({"114000001"}), _UnitOfWork)

    preview = service.preview(str(path))

    assert preview.source_row_count == 4
    assert preview.candidate_count == 1
    assert preview.import_count == 1
    assert preview.existing_count == 0
    assert preview.skipped_count == 3


def test_apply_allows_multiple_accounts_per_case_and_replays_safely(tmp_path):
    path = _workbook(tmp_path, [
        ["99781699114001", "114000001"],
        ["99781699114002", "114000001"],
    ])
    repository = _Repository({"114000001"})
    service = LegacyVirtualAccountWorkbookService(repository, _UnitOfWork)
    preview = service.preview(str(path))

    receipt = service.apply(str(path), "key-1", preview.preview_fingerprint, "admin")
    replay = service.apply(str(path), "key-1", preview.preview_fingerprint, "admin")

    assert receipt.inserted_count == 2
    assert repository.mappings == {
        ("114000001", "99781699114001"),
        ("114000001", "99781699114002"),
    }
    assert replay.replayed_workbook is True
    assert replay.inserted_count == 2


def test_apply_rejects_a_stale_preview(tmp_path):
    path = _workbook(tmp_path, [["99781699114001", "114000001"]])
    service = LegacyVirtualAccountWorkbookService(_Repository({"114000001"}), _UnitOfWork)

    with pytest.raises(LegacyVirtualAccountWorkbookConflict, match="preview_stale"):
        service.apply(str(path), "key-1", "0" * 64, "admin")


def test_ordinary_workbook_skips_only_account_in_use_by_non_citizen(tmp_path):
    occupied, ordinary = "99781699115042", "99781699115043"
    path = _workbook(tmp_path, [[occupied, "115000001"], [ordinary, "115000001"]])
    repository = _Repository(
        {"A115001", "115000001", "115000002"},
        {("A115001", occupied), ("115000002", ordinary)},
    )
    service = LegacyVirtualAccountWorkbookService(repository, _UnitOfWork)

    first = service.preview(str(path))
    receipt = service.apply(str(path), "protected", first.preview_fingerprint, "admin")

    assert (first.import_count, first.skipped_count) == (1, 1)
    assert (receipt.inserted_count, receipt.skipped_count) == (1, 1)
    assert [(row.source_row, row.case_no, row.status, row.related_case_nos) for row in receipt.non_citizen_rows] == [
        (2, "115000001", "conflict", ("A115001",)),
    ]
    assert repository.mappings == {
        ("A115001", occupied), ("115000002", ordinary), ("115000001", ordinary),
    }


def test_ordinary_apply_rechecks_new_non_citizen_owner(tmp_path):
    account = "99781699115042"
    path = _workbook(tmp_path, [[account, "115000001"]])
    repository = _Repository({"115000001", "A115001"})
    service = LegacyVirtualAccountWorkbookService(repository, _UnitOfWork)
    preview = service.preview(str(path))
    repository.mappings.add(("A115001", account))

    with pytest.raises(LegacyVirtualAccountWorkbookConflict, match="preview_stale"):
        service.apply(str(path), "stale-owner", preview.preview_fingerprint, "admin")
    assert repository.mappings == {("A115001", account)}


def test_a_new_operation_can_import_a_row_skipped_before_the_order_existed(tmp_path):
    path = _workbook(tmp_path, [["99781699114001", "114000001"]])
    repository = _Repository()
    service = LegacyVirtualAccountWorkbookService(repository, _UnitOfWork)
    first_preview = service.preview(str(path))
    first_receipt = service.apply(
        str(path), "key-1", first_preview.preview_fingerprint, "admin"
    )
    repository.orders.add("114000001")
    second_preview = service.preview(str(path))
    second_receipt = service.apply(
        str(path), "key-2", second_preview.preview_fingerprint, "admin"
    )

    assert first_receipt.skipped_count == 1
    assert second_receipt.inserted_count == 1
