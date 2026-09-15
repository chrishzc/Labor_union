import pandas as pd
import pytest

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
