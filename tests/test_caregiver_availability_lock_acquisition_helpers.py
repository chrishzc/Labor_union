from __future__ import annotations

import ast
from copy import deepcopy
from datetime import date, datetime
from pathlib import Path

import pytest

from services import caregiver_availability_lock_acquisition_helpers as service


def _plan_row(
    case_no: str = "CASE-001",
    status: str = "proposed",
    is_active: int | None = 1,
    start: date = date(2026, 7, 1),
    end: date = date(2026, 7, 4),
) -> dict:
    return {
        "id": 100,
        "case_no": case_no,
        "status": status,
        "is_active": is_active,
        "start_date": start,
        "end_date": end,
    }


def _segment_rows() -> list[dict]:
    return [
        {
            "id": 10,
            "plan_id": 100,
            "segment_order": 1,
            "staff_id": 2,
            "assigned_start_date": date(2026, 7, 1),
            "assigned_end_date": date(2026, 7, 2),
        },
        {
            "id": 11,
            "plan_id": 100,
            "segment_order": 2,
            "staff_id": 1,
            "assigned_start_date": date(2026, 7, 3),
            "assigned_end_date": date(2026, 7, 4),
        },
    ]


def _conflict_rows() -> list[dict]:
    return [
        {
            "staff_id": 1,
            "lock_date": date(2026, 7, 3),
            "source_type": "schedule",
            "source_id": 31,
        },
        {
            "staff_id": 1,
            "lock_date": date(2026, 7, 3),
            "source_type": "schedule",
            "source_id": 31,
        },
        {
            "staff_id": 2,
            "lock_date": date(2026, 7, 2),
            "source_type": "assignment",
            "source_id": 21,
        },
        {
            "staff_id": 2,
            "lock_date": date(2026, 7, 2),
            "source_type": "active_lock",
            "source_id": 21,
        },
    ]


def test_normalize_lock_acquisition_inputs_success_and_stable_result():
    case_no = "CASE-001"
    request = {
        "case_no": case_no,
        "plan_id": 100,
        "event_key": "evt-001",
        "actor": "admin-01",
        "lock_id": 777,
    }
    plan_row = _plan_row()
    segments = _segment_rows()
    conflicts = _conflict_rows()

    snapshot_a = service.normalize_lock_acquisition_inputs(
        request["case_no"],
        request["plan_id"],
        request["event_key"],
        request["actor"],
        request["lock_id"],
        plan_row,
        segments,
        conflicts,
    )
    snapshot_b = service.normalize_lock_acquisition_inputs(
        request["case_no"],
        request["plan_id"],
        request["event_key"],
        request["actor"],
        request["lock_id"],
        plan_row,
        segments,
        conflicts,
    )

    assert snapshot_a == snapshot_b
    assert snapshot_a["canonical_request"] == {
        "case_no": "CASE-001",
        "plan_id": 100,
        "event_key": "evt-001",
        "actor": "admin-01",
        "lock_id": 777,
    }

    plan_snapshot = snapshot_a["canonical_plan_snapshot"]
    assert plan_snapshot["case_no"] == case_no
    assert plan_snapshot["segments"][0]["segment_order"] == 1
    assert plan_snapshot["segments"][1]["segment_order"] == 2
    assert plan_snapshot["staff_ids"] == [1, 2]
    assert [row["lock_date"] for row in plan_snapshot["lock_rows"]] == [
        "2026-07-01",
        "2026-07-02",
        "2026-07-03",
        "2026-07-04",
    ]

    assert snapshot_a["canonical_conflicts"] == [
        {"staff_id": 1, "lock_date": "2026-07-03", "source_type": "schedule", "source_id": 31},
        {"staff_id": 2, "lock_date": "2026-07-02", "source_type": "active_lock", "source_id": 21},
        {"staff_id": 2, "lock_date": "2026-07-02", "source_type": "assignment", "source_id": 21},
    ]

    payload = snapshot_a["acquired_event_payload"]
    assert set(payload.keys()) == {
        "case_no",
        "plan_id",
        "lock_id",
        "actor",
        "segments",
        "staff_ids",
        "lock_rows",
        "case_start_date",
        "case_end_date",
    }
    assert "event_key" not in payload
    assert payload["case_no"] == case_no
    assert payload == {
        "case_no": "CASE-001",
        "plan_id": 100,
        "lock_id": 777,
        "actor": "admin-01",
        "segments": [
            {
                "segment_id": 10,
                "segment_order": 1,
                "staff_id": 2,
                "assigned_start_date": "2026-07-01",
                "assigned_end_date": "2026-07-02",
            },
            {
                "segment_id": 11,
                "segment_order": 2,
                "staff_id": 1,
                "assigned_start_date": "2026-07-03",
                "assigned_end_date": "2026-07-04",
            },
        ],
        "staff_ids": [1, 2],
        "lock_rows": [
            {"segment_id": 10, "staff_id": 2, "lock_date": "2026-07-01"},
            {"segment_id": 10, "staff_id": 2, "lock_date": "2026-07-02"},
            {"segment_id": 11, "staff_id": 1, "lock_date": "2026-07-03"},
            {"segment_id": 11, "staff_id": 1, "lock_date": "2026-07-04"},
        ],
        "case_start_date": "2026-07-01",
        "case_end_date": "2026-07-04",
    }


def test_input_strings_rejects_whitespace_and_non_strict_values():
    for case_no in [None, 1, "", " CASE-1", "CASE-1 ", " CASE-1 "]:
        with pytest.raises(ValueError):
            service.normalize_lock_acquisition_request(case_no, 1, "evt", "actor", 11)

    for event_key in [None, 2, "", " evt", "evt ", " evt "]:
        with pytest.raises(ValueError):
            service.normalize_lock_acquisition_request("CASE-1", 1, event_key, "actor", 11)

    for actor in [None, 3, "", " admin", "admin "]:
        with pytest.raises(ValueError):
            service.normalize_lock_acquisition_request("CASE-1", 1, "evt", actor, 11)


def test_input_ints_reject_bool_zero_negative_non_int():
    for plan_id in [True, False, 0, -1, 1.5, "100"]:
        with pytest.raises(ValueError):
            service.normalize_lock_acquisition_request("CASE-1", plan_id, "evt", "actor", 11)


def test_lock_id_reject_bool_zero_negative_non_int():
    for lock_id in [True, False, 0, -1, 1.5, "100"]:
        with pytest.raises(ValueError):
            service.normalize_lock_acquisition_request("CASE-1", 1, "evt", "actor", lock_id)


def test_plan_row_invalid_shape_rejects():
    plan = _plan_row()
    plan.pop("status")
    with pytest.raises(ValueError, match="unexpected keys"):
        service.normalize_plan_snapshot("CASE-001", 100, plan, _segment_rows())

    too_many = {**_plan_row(), "extra": "x"}
    with pytest.raises(ValueError, match="unexpected keys"):
        service.normalize_plan_snapshot("CASE-001", 100, too_many, _segment_rows())


def test_plan_row_mismatch_case_or_id_rejects():
    with pytest.raises(ValueError, match="must match case_no"):
        service.normalize_plan_snapshot("CASE-OTHER", 100, _plan_row(), _segment_rows())
    with pytest.raises(ValueError, match="must match plan_id"):
        service.normalize_plan_snapshot("CASE-001", 999, _plan_row(), _segment_rows())


def test_plan_period_and_segments_contiguous_coverage_validation():
    with pytest.raises(ValueError, match="cannot be after"):
        service.normalize_plan_snapshot(
            "CASE-001",
            100,
            _plan_row(start=date(2026, 7, 5), end=date(2026, 7, 1)),
            _segment_rows(),
        )

    segments = [
        {
            "id": 10,
            "plan_id": 100,
            "segment_order": 1,
            "staff_id": 2,
            "assigned_start_date": date(2026, 7, 1),
            "assigned_end_date": date(2026, 7, 2),
        },
        {
            "id": 11,
            "plan_id": 100,
            "segment_order": 2,
            "staff_id": 1,
            "assigned_start_date": date(2026, 7, 4),
            "assigned_end_date": date(2026, 7, 5),
        },
    ]
    with pytest.raises(ValueError, match="without gaps"):
        service.normalize_plan_snapshot("CASE-001", 100, _plan_row(end=date(2026, 7, 5)), segments)


def test_segment_order_unique_and_contiguous_one_to_four():
    segments = _segment_rows()
    segments[1]["segment_order"] = 3
    with pytest.raises(ValueError, match="contiguous"):
        service.normalize_plan_snapshot("CASE-001", 100, _plan_row(), segments)

    segments = _segment_rows() + [
        {
            "id": 12,
            "plan_id": 100,
            "segment_order": 3,
            "staff_id": 3,
            "assigned_start_date": date(2026, 7, 5),
            "assigned_end_date": date(2026, 7, 6),
        },
        {
            "id": 13,
            "plan_id": 100,
            "segment_order": 4,
            "staff_id": 4,
            "assigned_start_date": date(2026, 7, 7),
            "assigned_end_date": date(2026, 7, 8),
        },
    ]
    valid_four = service.normalize_plan_snapshot("CASE-001", 100, _plan_row(end=date(2026, 7, 8)), segments)
    assert len(valid_four["segments"]) == 4
    assert valid_four["case_start_date"] == "2026-07-01"
    assert valid_four["case_end_date"] == "2026-07-08"

    too_many = _segment_rows() + [
        {
            "id": 12,
            "plan_id": 100,
            "segment_order": 3,
            "staff_id": 3,
            "assigned_start_date": date(2026, 7, 5),
            "assigned_end_date": date(2026, 7, 6),
        },
        {
            "id": 13,
            "plan_id": 100,
            "segment_order": 4,
            "staff_id": 4,
            "assigned_start_date": date(2026, 7, 7),
            "assigned_end_date": date(2026, 7, 8),
        },
        {
            "id": 14,
            "plan_id": 100,
            "segment_order": 5,
            "staff_id": 5,
            "assigned_start_date": date(2026, 7, 9),
            "assigned_end_date": date(2026, 7, 10),
        },
    ]
    with pytest.raises(ValueError, match="one to four"):
        service.normalize_plan_snapshot("CASE-001", 100, _plan_row(end=date(2026, 7, 8)), too_many)

    with pytest.raises(ValueError):
        service.normalize_plan_snapshot("CASE-001", 100, _plan_row(end=date(2026, 6, 30)), [])


def test_segment_staff_must_be_unique_and_dates_must_be_date_instances():
    duplicate_staff_segments = _segment_rows()
    duplicate_staff_segments[1]["staff_id"] = duplicate_staff_segments[0]["staff_id"]
    with pytest.raises(ValueError, match="unique"):
        service.normalize_plan_snapshot("CASE-001", 100, _plan_row(), duplicate_staff_segments)

    rows = _segment_rows()
    rows[0]["assigned_start_date"] = "2026-07-01"
    with pytest.raises(ValueError, match="must be date"):
        service.normalize_plan_snapshot("CASE-001", 100, _plan_row(), rows)

    rows = _segment_rows()
    rows[0]["assigned_start_date"] = datetime(2026, 7, 1)
    with pytest.raises(ValueError, match="must be date"):
        service.normalize_plan_snapshot("CASE-001", 100, _plan_row(), rows)


def test_plan_date_fields_must_be_date_not_string_or_datetime():
    bad = _plan_row()
    bad["start_date"] = "2026-07-01"
    with pytest.raises(ValueError, match="must be date"):
        service.normalize_plan_snapshot("CASE-001", 100, bad, _segment_rows())

    bad = _plan_row()
    bad["end_date"] = datetime(2026, 7, 4)
    with pytest.raises(ValueError, match="must be date"):
        service.normalize_plan_snapshot("CASE-001", 100, bad, _segment_rows())


def test_segment_rows_shape_enforced():
    with pytest.raises(ValueError, match="must be a dict"):
        service.normalize_plan_snapshot("CASE-001", 100, _plan_row(), [1, 2])

    wrong = _segment_rows()
    del wrong[0]["staff_id"]
    with pytest.raises(ValueError, match="unexpected keys"):
        service.normalize_plan_snapshot("CASE-001", 100, _plan_row(), wrong)


def test_normalize_conflicts_validates_shape_keys_and_types():
    with pytest.raises(ValueError):
        service.normalize_conflicts(cast := {"a": 1})

    assert service.normalize_conflicts([]) == []

    rows = [
        {
            "staff_id": 1,
            "lock_date": date(2026, 7, 1),
            "source_type": "unknown",
            "source_id": 10,
        }
    ]
    with pytest.raises(ValueError, match="invalid"):
        service.normalize_conflicts(rows)

    rows = [
        {
            "staff_id": "1",
            "lock_date": date(2026, 7, 1),
            "source_type": "assignment",
            "source_id": 10,
        }
    ]
    with pytest.raises(ValueError):
        service.normalize_conflicts(rows)

    rows = [
        {
            "staff_id": 1,
            "lock_date": "2026-07-01",
            "source_type": "schedule",
            "source_id": 10,
        }
    ]
    with pytest.raises(ValueError, match="must be date"):
        service.normalize_conflicts(rows)

    rows = [
        {
            "staff_id": 1,
            "lock_date": datetime(2026, 7, 1),
            "source_type": "assignment",
            "source_id": 10,
        }
    ]
    with pytest.raises(ValueError, match="must be date"):
        service.normalize_conflicts(rows)


def test_normalize_conflicts_dedup_and_ordered_output_and_source_preserve():
    conflicts = [
        {
            "staff_id": 2,
            "lock_date": date(2026, 7, 2),
            "source_type": "active_lock",
            "source_id": 5,
        },
        {
            "staff_id": 1,
            "lock_date": date(2026, 7, 1),
            "source_type": "assignment",
            "source_id": 4,
        },
        {
            "staff_id": 1,
            "lock_date": date(2026, 7, 1),
            "source_type": "assignment",
            "source_id": 4,
        },
        {
            "staff_id": 1,
            "lock_date": date(2026, 7, 1),
            "source_type": "schedule",
            "source_id": 4,
        },
    ]
    normalized = service.normalize_conflicts(conflicts)
    assert normalized == [
        {"staff_id": 1, "lock_date": "2026-07-01", "source_type": "assignment", "source_id": 4},
        {"staff_id": 1, "lock_date": "2026-07-01", "source_type": "schedule", "source_id": 4},
        {"staff_id": 2, "lock_date": "2026-07-02", "source_type": "active_lock", "source_id": 5},
    ]

    duplicate_diff_source = [
        {
            "staff_id": 1,
            "lock_date": date(2026, 7, 1),
            "source_type": "assignment",
            "source_id": 4,
        },
        {
            "staff_id": 1,
            "lock_date": date(2026, 7, 1),
            "source_type": "schedule",
            "source_id": 4,
        },
    ]
    normalized = service.normalize_conflicts(duplicate_diff_source)
    assert len(normalized) == 2


@pytest.mark.parametrize("segment_count", [1, 2, 3, 4])
def test_each_legal_segment_count_is_accepted(segment_count):
    start = date(2026, 7, 1)
    segments = []
    for index in range(segment_count):
        work_date = date(2026, 7, index + 1)
        segments.append(
            {
                "id": 10 + index,
                "plan_id": 100,
                "segment_order": index + 1,
                "staff_id": 20 + index,
                "assigned_start_date": work_date,
                "assigned_end_date": work_date,
            }
        )
    result = service.normalize_plan_snapshot(
        "CASE-001",
        100,
        _plan_row(start=start, end=date(2026, 7, segment_count)),
        segments,
    )
    assert len(result["segments"]) == segment_count
    assert len(result["lock_rows"]) == segment_count


@pytest.mark.parametrize(
    "segments",
    [
        [
            {
                "id": 10,
                "plan_id": 100,
                "segment_order": 1,
                "staff_id": 1,
                "assigned_start_date": date(2026, 7, 1),
                "assigned_end_date": date(2026, 7, 3),
            },
            {
                "id": 11,
                "plan_id": 100,
                "segment_order": 2,
                "staff_id": 2,
                "assigned_start_date": date(2026, 7, 3),
                "assigned_end_date": date(2026, 7, 4),
            },
        ],
        [
            {
                "id": 10,
                "plan_id": 100,
                "segment_order": 1,
                "staff_id": 1,
                "assigned_start_date": date(2026, 6, 30),
                "assigned_end_date": date(2026, 7, 2),
            },
            {
                "id": 11,
                "plan_id": 100,
                "segment_order": 2,
                "staff_id": 2,
                "assigned_start_date": date(2026, 7, 3),
                "assigned_end_date": date(2026, 7, 4),
            },
        ],
        [
            {
                "id": 10,
                "plan_id": 100,
                "segment_order": 1,
                "staff_id": 1,
                "assigned_start_date": date(2026, 7, 1),
                "assigned_end_date": date(2026, 7, 2),
            },
            {
                "id": 11,
                "plan_id": 100,
                "segment_order": 2,
                "staff_id": 2,
                "assigned_start_date": date(2026, 7, 3),
                "assigned_end_date": date(2026, 7, 5),
            },
        ],
    ],
)
def test_overlap_and_left_or_right_out_of_bounds_are_rejected(segments):
    with pytest.raises(ValueError):
        service.normalize_plan_snapshot("CASE-001", 100, _plan_row(), segments)


@pytest.mark.parametrize("invalid", [True, False, 0, -1, "1"])
@pytest.mark.parametrize("field", ["id", "plan_id", "segment_order", "staff_id"])
def test_every_segment_identifier_rejects_invalid_values(field, invalid):
    rows = _segment_rows()
    rows[0][field] = invalid
    with pytest.raises(ValueError):
        service.normalize_plan_snapshot("CASE-001", 100, _plan_row(), rows)


@pytest.mark.parametrize("invalid", [True, False, 0, -1, "1"])
@pytest.mark.parametrize("field", ["source_id", "staff_id"])
def test_every_conflict_identifier_rejects_invalid_values(field, invalid):
    rows = _conflict_rows()
    rows[0][field] = invalid
    with pytest.raises(ValueError):
        service.normalize_conflicts(rows)


def test_public_plan_helper_independently_rejects_bad_identity_arguments():
    with pytest.raises(ValueError):
        service.normalize_plan_snapshot(" CASE-001", 100, _plan_row(), _segment_rows())
    plan = _plan_row()
    plan["id"] = 1
    segments = _segment_rows()
    for row in segments:
        row["plan_id"] = 1
    with pytest.raises(ValueError):
        service.normalize_plan_snapshot("CASE-001", True, plan, segments)


@pytest.mark.parametrize("bad_value", [None, (), [], "bad", 1])
def test_each_public_mapping_helper_rejects_non_mapping_shapes(bad_value):
    with pytest.raises(ValueError):
        service.normalize_plan_snapshot("CASE-001", 100, bad_value, _segment_rows())
    with pytest.raises(ValueError):
        service.build_acquired_event_payload(bad_value, {})
    with pytest.raises(ValueError):
        service.build_acquired_event_payload({}, bad_value)


def test_payload_rejects_nested_noncanonical_or_wrong_ownership_and_is_isolated():
    request = service.normalize_lock_acquisition_request(
        "CASE-001", 100, "evt-1", "admin", 777
    )
    snapshot = service.normalize_plan_snapshot(
        "CASE-001", 100, _plan_row(), _segment_rows()
    )

    wrong_case = deepcopy(snapshot)
    wrong_case["case_no"] = "CASE-OTHER"
    with pytest.raises(ValueError):
        service.build_acquired_event_payload(request, wrong_case)

    wrong_plan = deepcopy(snapshot)
    wrong_plan["plan_id"] = 999
    with pytest.raises(ValueError):
        service.build_acquired_event_payload(request, wrong_plan)

    malformed = deepcopy(snapshot)
    malformed["segments"][0]["extra"] = "x"
    with pytest.raises(ValueError):
        service.build_acquired_event_payload(request, malformed)

    malformed = deepcopy(snapshot)
    malformed["lock_rows"] = 42
    with pytest.raises(ValueError):
        service.build_acquired_event_payload(request, malformed)

    payload = service.build_acquired_event_payload(request, snapshot)
    payload["segments"][0]["staff_id"] = 999
    payload["lock_rows"][0]["staff_id"] = 999
    assert snapshot["segments"][0]["staff_id"] == 2
    assert snapshot["lock_rows"][0]["staff_id"] == 2


def test_mapping_insertion_order_does_not_change_canonical_result():
    plan = _plan_row()
    reordered_plan = dict(reversed(list(plan.items())))
    segments = [dict(reversed(list(row.items()))) for row in reversed(_segment_rows())]
    conflicts = [dict(reversed(list(row.items()))) for row in reversed(_conflict_rows())]
    first = service.normalize_lock_acquisition_inputs(
        "CASE-001", 100, "evt", "actor", 777, plan, _segment_rows(), _conflict_rows()
    )
    second = service.normalize_lock_acquisition_inputs(
        "CASE-001", 100, "evt", "actor", 777, reordered_plan, segments, conflicts
    )
    assert first == second


def test_source_guard_prevents_external_io_and_db_side_effects():
    source = Path(service.__file__).read_text(encoding="utf-8")
    lowered = source.lower()

    for token in [
        "pymysql",
        "mysql",
        "db_service",
        "get_connection",
        ".commit(",
        ".rollback(",
        ".close(",
        "open(",
        "commit(",
        "cursor",
        "select ",
        "insert ",
        "update ",
        "delete ",
        "truncate ",
        "drop ",
        "create table",
    ]:
        assert token not in lowered

    tree = ast.parse(source)
    forbidden_import_roots = {
        "os",
        "subprocess",
        "pathlib",
        "time",
        "io",
        "shutil",
        "dotenv",
        "pymysql",
        "mysql",
    }
    forbidden_calls = {
        "open",
        "getenv",
        "connect",
        "get_connection",
        "cursor",
        "commit",
        "rollback",
        "close",
        "today",
        "now",
        "utcnow",
        "read_text",
        "write_text",
        "read_bytes",
        "write_bytes",
        "unlink",
        "rename",
        "replace",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".", 1)[0] not in forbidden_import_roots
                assert not alias.name.startswith("services.db_service")
                assert "staff_occupancy_mutex" not in alias.name
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if (
                module.split(".", 1)[0] in forbidden_import_roots
                or module == "services.db_service"
                or "staff_occupancy_mutex" in module
            ):
                raise AssertionError(f"disallowed import: {node.module}")
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                assert node.func.id not in forbidden_calls
            elif isinstance(node.func, ast.Attribute):
                assert node.func.attr not in forbidden_calls
        if isinstance(node, ast.Attribute):
            assert not (
                isinstance(node.value, ast.Name)
                and node.value.id == "os"
                and node.attr == "environ"
            )


def test_inputs_not_mutated_after_normalization():
    original_request = {
        "case_no": "CASE-001",
        "plan_id": 100,
        "event_key": "evt-001",
        "actor": "admin-01",
        "lock_id": 777,
    }
    plan_row = _plan_row()
    segment_rows = _segment_rows()
    conflict_rows = _conflict_rows()

    request_copy = deepcopy(original_request)
    plan_copy = deepcopy(plan_row)
    segment_copy = deepcopy(segment_rows)
    conflict_copy = deepcopy(conflict_rows)

    service.normalize_lock_acquisition_inputs(
        original_request["case_no"],
        original_request["plan_id"],
        original_request["event_key"],
        original_request["actor"],
        original_request["lock_id"],
        plan_row,
        segment_rows,
        conflict_rows,
    )

    assert original_request == request_copy
    assert plan_row == plan_copy
    assert segment_rows == segment_copy
    assert conflict_rows == conflict_copy


def test_build_acquired_event_payload_rejects_scalar_inputs():
    with pytest.raises(ValueError):
        service.build_acquired_event_payload("x", {})
    with pytest.raises(ValueError):
        service.build_acquired_event_payload({"case_no": "CASE-001", "plan_id": 1, "actor": "a"}, "y")
