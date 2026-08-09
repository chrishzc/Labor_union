import pytest

from subsystems.access import source_data_correction


class _Repository:
    def __init__(self):
        self.rows = {"clients": {1: {"name": "王小美", "phone": "0912", "address": "舊址"}}}
        self.receipts = {}
        self.commits = 0

    def load_source_row(self, table, row_id, **_kwargs):
        return self.rows.get(table, {}).get(row_id)

    def update_source_row(self, table, row_id, updates):
        self.rows[table][row_id].update(updates)

    def load_receipt(self, family, key):
        return self.receipts.get((family, key))

    def save_receipt(self, family, key, request_fingerprint, preview_fingerprint, actor, reason, result):
        self.receipts[(family, key)] = {
            "request_fingerprint": request_fingerprint,
            "result_snapshot": result,
        }

    def commit(self):
        self.commits += 1


def test_source_correction_apply_replays_and_rejects_protected_fields():
    repository = _Repository()
    preview = source_data_correction.preview(
        repository, "clients", 1, {"phone": "0988", "address": "新址"}
    )
    result = source_data_correction.apply(
        repository, "clients", 1, {"phone": "0988", "address": "新址"},
        preview["preview_fingerprint"], "source-key-1", "admin", "更正聯絡資料"
    )

    assert result["changed_fields"] == ["address", "phone"]
    assert repository.rows["clients"][1]["phone"] == "0988"
    assert source_data_correction.apply(
        repository, "clients", 1, {"phone": "0988", "address": "新址"},
        preview["preview_fingerprint"], "source-key-1", "admin", "更正聯絡資料"
    ) == result
    with pytest.raises(ValueError, match="protected_source_field"):
        source_data_correction.preview(repository, "clients", 1, {"case_no": "C-1"})
