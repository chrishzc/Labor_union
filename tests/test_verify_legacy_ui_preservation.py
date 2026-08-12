from scripts.verify_legacy_ui_preservation import _field, compare_preserved_rows


def test_immutability_comparison_ignores_target_only_append_rows():
    source_rows = [{"id": 1, "case_no": "CASE-1", "status": "new"}]
    target_rows = source_rows + [{"id": 2, "case_no": "CASE-2", "status": "new"}]

    result = compare_preserved_rows(source_rows, target_rows, ("id",), ("id", "case_no", "status"))

    assert result["passed"] is True
    assert result["source_row_count"] == 1
    assert result["target_matched_row_count"] == 1


def test_immutability_comparison_rejects_a_changed_preserved_row():
    source_rows = [{"id": 1, "case_no": "CASE-1", "status": "new"}]
    target_rows = [{"id": 1, "case_no": "CASE-1", "status": "changed"}]

    result = compare_preserved_rows(source_rows, target_rows, ("id",), ("id", "case_no", "status"))

    assert result["passed"] is False


def test_information_schema_field_lookup_is_case_insensitive():
    assert _field({"COLUMN_NAME": "case_no"}, "column_name") == "case_no"
