from __future__ import annotations

import ast
import inspect
from copy import deepcopy

import pytest

from services import caregiver_segment_availability_service as service


def test_validate_segment_search_input_rejects_invalid_segment_count_and_dates():
    valid_common = {
        "segment_drafts": [],
        "candidate_staff_ids": [1, 2],
        "assignment_schedule_days": [],
        "active_lock_days": [],
    }

    for segment_count in [True, False, 0, 5, 1.5]:
        with pytest.raises(ValueError, match="segment_count"):
            service.validate_segment_search_input(
                "2026-07-01",
                "2026-07-03",
                segment_count,
                **valid_common,
            )

    for invalid_date in ["2026-7-01", "2026-07-1", "2026/07/01", " 2026-07-01", "2026-07-01 "]:
        with pytest.raises(ValueError, match="YYYY-MM-DD"):
            service.validate_segment_search_input(
                invalid_date,
                "2026-07-03",
                2,
                [],
                [1, 2],
                [],
                [],
            )


def test_validate_segment_search_input_rejects_set_candidate_staff_ids():
    with pytest.raises(ValueError, match="must be a list"):
        service.validate_segment_search_input(
            "2026-07-01",
            "2026-07-03",
            2,
            [],
            {1, 2},
            [],
            [],
        )


def test_validate_segment_search_input_rejects_tuple_candidate_staff_ids():
    with pytest.raises(ValueError, match="must be a list"):
        service.validate_segment_search_input(
            "2026-07-01",
            "2026-07-03",
            2,
            [],
            (1, 2),
            [],
            [],
        )


def test_validate_segment_search_input_rejects_unknown_draft_and_too_many_drafts():
    with pytest.raises(ValueError, match="unknown fields"):
        service.validate_segment_search_input(
            "2026-07-01",
            "2026-07-03",
            2,
            [{"staff_id": 1, "foo": "bar"}],
            [1, 2],
            [],
            [],
        )

    with pytest.raises(ValueError, match="exceed"):
        service.validate_segment_search_input(
            "2026-07-01",
            "2026-07-03",
            2,
            [
                {"staff_id": 1},
                {"staff_id": 2},
                {"staff_id": 1},
            ],
            [1, 2],
            [],
            [],
        )


def test_validate_preserves_temporarily_out_of_order_partial_drafts():
    for segment_drafts in [
        [
            {"start_date": "2026-07-05"},
            {"end_date": "2026-07-04"},
        ],
        [
            {"end_date": "2026-07-04"},
            {"start_date": "2026-07-04"},
        ],
        [
            {},
            {"start_date": "2026-07-05"},
            {"end_date": "2026-07-04"},
        ],
    ]:
        result = service.validate_segment_search_input(
            "2026-07-01",
            "2026-07-10",
            3,
            segment_drafts,
            [1, 2],
            [],
            [],
        )
        assert result["segment_drafts"] == segment_drafts


def test_derive_reports_overlap_and_outside_period_without_rejecting_draft():
    result = service.derive_segment_availability(
        "2026-07-01",
        "2026-07-05",
        2,
        [
            {"staff_id": 1, "start_date": "2026-06-30", "end_date": "2026-07-03"},
            {"staff_id": 2, "start_date": "2026-07-03", "end_date": "2026-07-06"},
        ],
        [1, 2],
        [],
        [],
    )

    reasons = {item["reason_code"] for item in result["conflicts"]}
    assert "draft_overlap" in reasons
    assert "outside_case_period" in reasons
    assert result["complete_combinations"] == []


def test_derive_segment_availability_returns_sorted_combinations():
    result = service.derive_segment_availability(
        "2026-07-01",
        "2026-07-03",
        2,
        [],
        [1, 2],
        [],
        [],
    )

    combos = result["complete_combinations"]
    assert len(combos) == 4
    assert combos[0] == [
        {"segment_index": 0, "staff_id": 1, "start_date": "2026-07-01", "end_date": "2026-07-01"},
        {"segment_index": 1, "staff_id": 2, "start_date": "2026-07-02", "end_date": "2026-07-03"},
    ]
    assert combos[1] == [
        {"segment_index": 0, "staff_id": 1, "start_date": "2026-07-01", "end_date": "2026-07-02"},
        {"segment_index": 1, "staff_id": 2, "start_date": "2026-07-03", "end_date": "2026-07-03"},
    ]
    assert combos[2] == [
        {"segment_index": 0, "staff_id": 2, "start_date": "2026-07-01", "end_date": "2026-07-01"},
        {"segment_index": 1, "staff_id": 1, "start_date": "2026-07-02", "end_date": "2026-07-03"},
    ]
    assert combos[3] == [
        {"segment_index": 0, "staff_id": 2, "start_date": "2026-07-01", "end_date": "2026-07-02"},
        {"segment_index": 1, "staff_id": 1, "start_date": "2026-07-03", "end_date": "2026-07-03"},
    ]


def test_derive_segment_availability_emits_schedule_and_active_lock_conflicts():
    result = service.derive_segment_availability(
        "2026-07-01",
        "2026-07-03",
        2,
        [
            {"staff_id": 1},
            {"staff_id": 2},
        ],
        [1, 2],
        [
            {"assignment_id": 100, "staff_id": 1, "work_date": "2026-07-01"},
            {"assignment_id": 101, "staff_id": 1, "work_date": "2026-07-02"},
            {"assignment_id": 102, "staff_id": 2, "work_date": "2026-07-02"},
        ],
        [{"active_marker": 1, "staff_id": 2, "work_date": "2026-07-03"}],
    )

    assert len(result["complete_combinations"]) == 0

    reason_codes = {item["reason_code"] for item in result["conflicts"]}
    assert reason_codes.issuperset({"schedule", "active_lock"})


def test_derive_segment_availability_rejects_invalid_active_lock_marker_types():
    with pytest.raises(ValueError, match="active_marker"):
        service.derive_segment_availability(
            "2026-07-01",
            "2026-07-03",
            2,
            [],
            [1, 2],
            [],
            [{"active_marker": True, "staff_id": 1, "work_date": "2026-07-01"}],
        )


def test_derive_segment_availability_fails_on_malformed_occupancy_facts():
    with pytest.raises(ValueError, match="list"):
        service.derive_segment_availability(
            "2026-07-01",
            "2026-07-03",
            2,
            [],
            [1, 2],
            assignment_schedule_days="not-a-list",
            active_lock_days=[],
        )

    with pytest.raises(ValueError, match="work_date|YYYY-MM-DD|must be"):
        service.derive_segment_availability(
            "2026-07-01",
            "2026-07-03",
            2,
            [],
            [1, 2],
            [{"assignment_id": 1, "staff_id": 1}],
            [],
        )

    with pytest.raises(ValueError, match="active_marker"):
        service.derive_segment_availability(
            "2026-07-01",
            "2026-07-03",
            2,
            [],
            [1, 2],
            [],
            [{"active_marker": "1", "staff_id": 1, "work_date": "2026-07-01"}],
        )


def test_derive_segment_availability_preserves_fixed_end_boundary():
    result = service.derive_segment_availability(
        "2026-07-01",
        "2026-07-02",
        2,
        [
            {},
            {"end_date": "2026-07-02"},
        ],
        [1, 2],
        [],
        [],
    )

    assert len(result["complete_combinations"]) == 2
    assert all(item["end_date"] == "2026-07-02" for item in [combo[1] for combo in result["complete_combinations"]])
    assert all(
        candidate["segment_index"] != 1 or candidate["end_date"] == "2026-07-02"
        for candidate in result["segment_candidates"]
    )


def test_derive_segment_availability_requires_review_when_assignment_missing():
    result = service.derive_segment_availability(
        "2026-07-01",
        "2026-07-02",
        2,
        [],
        [1, 2],
        [
            {"staff_id": 1, "work_date": "2026-07-01"},
            {"staff_id": 1, "work_date": "2026-07-02", "assignment_id": None},
        ],
        [],
    )

    reason_codes = {item["reason_code"] for item in result["conflicts"]}
    assert "requires_review" in reason_codes
    assert any(
        item["reason_code"] == "requires_review" and item["staff_id"] == 1
        for item in result["conflicts"]
    )
    assert not any(cand["segment_index"] == 0 and cand["staff_id"] == 1 for cand in result["segment_candidates"])
    assert not any(cand["segment_index"] == 1 and cand["staff_id"] == 1 for cand in result["segment_candidates"])
    assert result["complete_combinations"] == []


def test_derive_segment_availability_keeps_partial_results_when_no_full_match():
    result = service.derive_segment_availability(
        "2026-07-01",
        "2026-07-03",
        2,
        [],
        [1],
        [],
        [],
    )

    assert result["complete_combinations"] == []
    assert result["segment_candidates"]
    assert result["conflicts"]
    assert any(item["segment_index"] == 0 for item in result["segment_candidates"])
    assert any(item["segment_index"] == 1 for item in result["segment_candidates"])


def test_derive_segment_availability_does_not_mutate_inputs():
    planned_start = "2026-07-01"
    planned_end = "2026-07-03"
    segment_count = 2
    segment_drafts = [{"staff_id": 1}]
    candidate_staff_ids = [1, 2]
    assignment_schedule_days = [
        {"assignment_id": 100, "staff_id": 1, "work_date": "2026-07-01"},
    ]
    active_lock_days = [{"active_marker": 1, "staff_id": 2, "work_date": "2026-07-02"}]

    snapshot = {
        "planned_start": deepcopy(planned_start),
        "planned_end": deepcopy(planned_end),
        "segment_count": deepcopy(segment_count),
        "segment_drafts": deepcopy(segment_drafts),
        "candidate_staff_ids": deepcopy(candidate_staff_ids),
        "assignment_schedule_days": deepcopy(assignment_schedule_days),
        "active_lock_days": deepcopy(active_lock_days),
    }

    service.derive_segment_availability(
        planned_start,
        planned_end,
        segment_count,
        segment_drafts,
        candidate_staff_ids,
        assignment_schedule_days,
        active_lock_days,
    )

    assert planned_start == snapshot["planned_start"]
    assert planned_end == snapshot["planned_end"]
    assert segment_count == snapshot["segment_count"]
    assert segment_drafts == snapshot["segment_drafts"]
    assert candidate_staff_ids == snapshot["candidate_staff_ids"]
    assert assignment_schedule_days == snapshot["assignment_schedule_days"]
    assert active_lock_days == snapshot["active_lock_days"]


def test_derive_segment_availability_is_idempotent_with_same_input():
    result_first = service.derive_segment_availability(
        "2026-07-01",
        "2026-07-03",
        2,
        [
            {"staff_id": 1, "end_date": "2026-07-02"},
        ],
        [1, 2],
        [
            {"assignment_id": 100, "staff_id": 1, "work_date": "2026-07-01"},
        ],
        [{"active_marker": 0, "staff_id": 2, "work_date": "2026-07-02"}],
    )
    result_second = service.derive_segment_availability(
        "2026-07-01",
        "2026-07-03",
        2,
        [
            {"staff_id": 1, "end_date": "2026-07-02"},
        ],
        [1, 2],
        [
            {"assignment_id": 100, "staff_id": 1, "work_date": "2026-07-01"},
        ],
        [{"active_marker": 0, "staff_id": 2, "work_date": "2026-07-02"}],
    )

    assert result_first == result_second


def test_derive_segment_availability_rejects_active_marker_false():
    with pytest.raises(ValueError, match="active_marker"):
        service.derive_segment_availability(
            "2026-07-01",
            "2026-07-03",
            2,
            [],
            [1, 2],
            [],
            [{"active_marker": False, "staff_id": 1, "work_date": "2026-07-01"}],
        )


def test_derive_segment_availability_inactive_active_lock_does_not_block_candidates():
    result = service.derive_segment_availability(
        "2026-07-01",
        "2026-07-03",
        2,
        [],
        [1, 2],
        [],
        [
            {"active_marker": 0, "staff_id": 1, "work_date": "2026-07-01"},
            {"active_marker": None, "staff_id": 1, "work_date": "2026-07-02"},
        ],
    )

    reason_codes = {item["reason_code"] for item in result["conflicts"]}
    assert "active_lock" not in reason_codes
    assert any(item["staff_id"] == 1 for item in result["segment_candidates"])
    assert len(result["complete_combinations"]) > 0


def test_derive_segment_availability_rejects_invalid_occupancy_fact_shapes():
    with pytest.raises(ValueError, match="must be an object"):
        service.derive_segment_availability(
            "2026-07-01",
            "2026-07-03",
            2,
            [],
            [1, 2],
            [1, 2],
            [],
        )

    with pytest.raises(ValueError, match="must be an object"):
        service.derive_segment_availability(
            "2026-07-01",
            "2026-07-03",
            2,
            [],
            [1, 2],
            [],
            [1, 2],
        )

    with pytest.raises(ValueError, match="unknown fields"):
        service.derive_segment_availability(
            "2026-07-01",
            "2026-07-03",
            2,
            [],
            [1, 2],
            [{"assignment_id": 1, "staff_id": 1, "work_date": "2026-07-01", "foo": "bar"}],
            [],
        )

    with pytest.raises(ValueError, match="unknown fields"):
        service.derive_segment_availability(
            "2026-07-01",
            "2026-07-03",
            2,
            [],
            [1, 2],
            [],
            [{"active_marker": 1, "staff_id": 1, "work_date": "2026-07-01", "foo": "bar"}],
        )


def test_validate_segment_search_input_rejects_invalid_occupancy_shape():
    with pytest.raises(ValueError, match="assignment_schedule_days"):
        service.validate_segment_search_input(
            "2026-07-01",
            "2026-07-03",
            2,
            [],
            [1, 2],
            assignment_schedule_days="bad-list",
            active_lock_days=[],
        )

    with pytest.raises(ValueError, match="active_lock_days"):
        service.validate_segment_search_input(
            "2026-07-01",
            "2026-07-03",
            2,
            [],
            [1, 2],
            assignment_schedule_days=[],
            active_lock_days="bad-list",
        )


def test_derive_segment_availability_rejects_unknown_reason_code():
    with pytest.raises(ValueError, match="reason_code"):
        service.derive_segment_availability(
            "2026-07-01",
            "2026-07-03",
            2,
            [],
            [1, 2],
            [{"assignment_id": 1, "staff_id": 1, "work_date": "2026-07-01", "reason_code": "bad"}],
            [],
        )


def test_derive_segment_availability_distinguishes_assignment_and_schedule_reason_codes():
    result = service.derive_segment_availability(
        "2026-07-01",
        "2026-07-03",
        2,
        [],
        [1, 2],
        [
            {"assignment_id": 11, "staff_id": 1, "work_date": "2026-07-01", "reason_code": "assignment"},
            {"assignment_id": 12, "staff_id": 2, "work_date": "2026-07-02"},
        ],
        [],
    )

    reason_pairs = {(conflict["work_date"], conflict["reason_code"]) for conflict in result["conflicts"]}
    assert ("2026-07-01", "assignment") in reason_pairs
    assert ("2026-07-02", "schedule") in reason_pairs


def test_derive_segment_availability_rejects_lock_date_for_assignment_rows():
    with pytest.raises(ValueError, match="lock_date|work_date"):
        service.derive_segment_availability(
            "2026-07-01",
            "2026-07-03",
            2,
            [],
            [1, 2],
            [{"assignment_id": 1, "staff_id": 1, "lock_date": "2026-07-01"}],
            [],
        )


def test_derive_segment_availability_schedule_reason_blocks_candidate_and_complete_combinations():
    result = service.derive_segment_availability(
        "2026-07-01",
        "2026-07-02",
        2,
        [
            {"start_date": "2026-07-01", "end_date": "2026-07-01", "staff_id": 1},
            {"start_date": "2026-07-02", "end_date": "2026-07-02", "staff_id": 2},
        ],
        [1, 2],
        [{"assignment_id": 100, "staff_id": 1, "work_date": "2026-07-01"}],
        [],
    )

    assert result["complete_combinations"] == []
    assert not any(item["segment_index"] == 0 and item["staff_id"] == 1 for item in result["segment_candidates"])
    assert any(
        conflict["segment_index"] == 0
        and conflict["staff_id"] == 1
        and conflict["work_date"] == "2026-07-01"
        and conflict["reason_code"] == "schedule"
        for conflict in result["conflicts"]
    )


def test_derive_segment_availability_assignment_reason_blocks_candidate_and_complete_combinations():
    result = service.derive_segment_availability(
        "2026-07-01",
        "2026-07-02",
        2,
        [
            {"start_date": "2026-07-01", "end_date": "2026-07-01", "staff_id": 1},
            {"start_date": "2026-07-02", "end_date": "2026-07-02", "staff_id": 2},
        ],
        [1, 2],
        [{"assignment_id": 200, "staff_id": 1, "work_date": "2026-07-01", "reason_code": "assignment"}],
        [],
    )

    assert result["complete_combinations"] == []
    assert not any(item["segment_index"] == 0 and item["staff_id"] == 1 for item in result["segment_candidates"])
    assert any(
        conflict["segment_index"] == 0
        and conflict["staff_id"] == 1
        and conflict["work_date"] == "2026-07-01"
        and conflict["reason_code"] == "assignment"
        for conflict in result["conflicts"]
    )


def test_derive_segment_availability_uses_pure_function_no_external_io_or_clock_access():
    source = inspect.getsource(service)
    tree = ast.parse(source)
    disallowed_imports = {
        "os",
        "pathlib",
        "sqlite3",
        "pymysql",
        "mysql",
        "subprocess",
        "services.db_service",
    }
    disallowed_calls = {
        ("open",),
        ("os", "environ"),
        ("os", "getenv"),
        ("os", "listdir"),
        ("os", "system"),
        ("os", "remove"),
        ("datetime", "now"),
        ("datetime", "today"),
        ("date", "today"),
    }

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                module = alias.name
                assert module not in disallowed_imports
                assert not module.startswith("services.db_service"), f"Unexpected db_service import: {module}"
                assert not module.startswith("pymysql"), f"Unexpected db client import: {module}"
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            assert module not in disallowed_imports
            assert not module.startswith("services.db_service"), f"Unexpected db_service import: {module}"
            assert not module.startswith("pymysql"), f"Unexpected db client import: {module}"
            if module == "services":
                assert not any(alias.name == "db_service" for alias in node.names), "Unexpected db_service import from services"
        if isinstance(node, ast.Call):
            callee = node.func
            if isinstance(callee, ast.Name) and callee.id == "open":
                raise AssertionError("function body must not call open()")
            if isinstance(callee, ast.Attribute):
                full_name: list[str] = []
                while isinstance(callee, ast.Attribute):
                    full_name.append(callee.attr)
                    callee = callee.value
                if isinstance(callee, ast.Name):
                    full_name.append(callee.id)
                    full_name.reverse()
                    joined = tuple(full_name[:2]) if len(full_name) >= 2 else tuple(full_name)
                    assert joined not in disallowed_calls
