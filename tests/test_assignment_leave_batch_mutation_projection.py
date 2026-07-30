from copy import deepcopy
from datetime import date
from decimal import Decimal

from services.assignment_schedule_leave_resolution_preview import (
    compute_assignment_leave_resolution_batch_preview_from_snapshot,
)
from services.assignment_schedule_rest_date_service import (
    build_assignment_leave_resolution_batch_mutation_command,
    execute_assignment_leave_resolution_batch_mutations,
)
from tests.test_assignment_rest_date_service import (
    _ApplyMutationCursor,
    _batch_leave_resolution_transition_facts,
)


def test_batch_mutation_projection_maps_opaque_refs_and_excludes_deferred_day():
    original, snapshot = _batch_leave_resolution_transition_facts()
    snapshot["assignments"] = [
        {
            key: value
            for key, value in snapshot["assignments"][0].items()
            if key != "service_hours_per_day"
        }
    ]
    snapshot["assignment_schedule_days"] = [
        {
            **row,
            "is_double_pay": str(row["work_date"]) == "2026-08-02",
            "notes": None,
            "requires_review": False,
        }
        for row in snapshot["assignment_schedule_days"]
    ]
    request = {
        "contract_version": "assignment-leave-substitution-batch-preview/v1",
        "case_no": "CASE-1",
        "original_assignment_id": 11,
        "items": [
            {
                "original_schedule_id": 21,
                "work_date": "2026-08-01",
                "resolution_type": "defer_following_assignments",
                "substitute_staff_id": None,
            },
            {
                "original_schedule_id": 22,
                "work_date": "2026-08-02",
                "resolution_type": "substitute",
                "substitute_staff_id": 202,
            },
        ],
    }
    preview = compute_assignment_leave_resolution_batch_preview_from_snapshot(
        request, original, snapshot
    )
    authorization = {
        "canonical_intent": deepcopy(preview["canonical_intent"]),
        "double_pay_preferences": deepcopy(preview["double_pay_preferences"]),
        "service_plan_transition": deepcopy(preview["service_plan_transition"]),
        "canonical_eligibility": deepcopy(preview["canonical_eligibility"]),
        "preview_fingerprint": preview["preview_fingerprint"],
        "canonical_apply_identity": {
            "batch_key": "batch-1",
            "actor": "admin",
            "reason": "leave",
        },
    }
    locked_facts = {
        "original_assignment_schedule": deepcopy(original),
        "conflict_snapshot": deepcopy(snapshot),
        "lock_identity": {
            "case_no": "CASE-1",
            "staff_ids": [101, 202],
            "range_start": "2026-08-01",
            "range_end": "2026-08-04",
        },
    }

    command = build_assignment_leave_resolution_batch_mutation_command(
        authorization, locked_facts
    )

    assert "2026-08-01" not in command["ownership_by_date"]
    assert "2026-08-06" in command["ownership_by_date"]
    assert sum(row["actual_hours"] for row in command["assignments"]) == 40
    substitute = next(
        row for row in command["assignments"] if row["segment_kind"] == "single_day_substitute"
    )
    assert substitute["staff_id"] == 202
    assert substitute["actual_hours"] == 8
    substitute_item = next(
        item for item in command["items"] if item["resolution_type"] == "substitute"
    )
    assert substitute_item["is_double_pay"] is False


class _BatchMutationCursor(_ApplyMutationCursor):
    def __init__(self):
        super().__init__()
        self.schedule_rows = {
            (11, date(2026, 8, day)): {
                "id": 20 + day,
                "assignment_id": 11,
                "case_no": "CASE-1",
                "staff_id": 101,
                "work_date": date(2026, 8, day),
                "is_work_day": True,
                "is_double_pay": day == 2,
            }
            for day in range(1, 6)
        }

    def execute(self, sql, params=()):
        normalised = " ".join(sql.split()).lower()
        self.calls.append((sql, params))
        self._result = None
        self.rowcount = 0
        if normalised.startswith(
            "select id, assignment_id, case_no, staff_id, work_date from staff_schedule"
        ):
            ids = set(params)
            rows = [
                dict(row)
                for row in self.schedule_rows.values()
                if row["id"] in ids
            ]
            self._result = sorted(rows, key=lambda row: row["id"])
            self.rowcount = len(rows)
            return
        if normalised.startswith(
            "update case_staff_assignments set assignment_sequence = -id"
        ):
            case_no = params[0]
            for row in self.assignments.values():
                if row["case_no"] == case_no:
                    row["assignment_sequence"] = -row["id"]
                    self.rowcount += 1
            return
        if normalised.startswith(
            "update case_staff_assignments set staff_id = %s"
        ):
            assignment_id = params[7]
            row = self.assignments[assignment_id]
            row.update(
                {
                    "staff_id": params[0],
                    "assignment_sequence": params[1],
                    "assigned_start_date": params[2],
                    "assigned_end_date": params[3],
                    "actual_hours": params[5],
                    "status": params[6],
                }
            )
            self.rowcount = 1
            return
        if normalised.startswith(
            "select id from case_staff_assignments where case_no = %s and assignment_sequence < 0"
        ):
            self._result = [
                {"id": row["id"]}
                for row in sorted(self.assignments.values(), key=lambda row: row["id"])
                if row["case_no"] == params[0]
                and row.get("assignment_sequence", 0) < 0
            ]
            self.rowcount = len(self._result)
            return
        if normalised.startswith(
            "update staff_schedule set is_work_day = false, is_double_pay = false"
        ) and "assignment_id is not null" in normalised:
            case_no, start, end = params
            for row in self.schedule_rows.values():
                if (
                    row["case_no"] == case_no
                    and row["assignment_id"] is not None
                    and start <= row["work_date"] <= end
                ):
                    row["is_work_day"] = False
                    row["is_double_pay"] = False
                    self.rowcount += 1
            return
        if normalised.startswith("insert into staff_schedule"):
            assignment_id, case_no, staff_id, work_date, is_double_pay = params
            schedule_key = (assignment_id, work_date)
            existing = self.schedule_rows.get(schedule_key)
            if existing is None:
                self.schedule_rows[schedule_key] = {
                    "id": self.lastrowid + 1,
                    "assignment_id": assignment_id,
                    "case_no": case_no,
                    "staff_id": staff_id,
                    "work_date": work_date,
                    "is_work_day": True,
                    "is_double_pay": is_double_pay,
                }
            else:
                existing.update(
                    {
                        "assignment_id": assignment_id,
                        "case_no": case_no,
                        "staff_id": staff_id,
                        "is_work_day": True,
                        "is_double_pay": is_double_pay,
                    }
                )
            self.rowcount = 1
            return
        if normalised.startswith(
            "select id, staff_id, assignment_sequence, assigned_start_date"
        ):
            self._result = sorted(
                (
                    dict(row)
                    for row in self.assignments.values()
                    if row["case_no"] == params[0] and row["status"] != "cancelled"
                ),
                key=lambda row: row["assignment_sequence"],
            )
            self.rowcount = len(self._result)
            return
        if normalised.startswith(
            "select id, assignment_id, staff_id, work_date, is_work_day, is_double_pay"
        ):
            case_no, start, end = params
            self._result = [
                dict(row)
                for row in self.schedule_rows.values()
                if row["case_no"] == case_no and start <= row["work_date"] <= end
            ]
            self.rowcount = len(self._result)
            return
        self.calls.pop()
        super().execute(sql, params)


def test_batch_mutation_executor_writes_one_consistent_assignment_schedule_projection(
    monkeypatch,
):
    original, snapshot = _batch_leave_resolution_transition_facts()
    snapshot["assignments"] = [
        {
            key: value
            for key, value in snapshot["assignments"][0].items()
            if key != "service_hours_per_day"
        }
    ]
    snapshot["assignment_schedule_days"] = [
        {
            **row,
            "is_double_pay": str(row["work_date"]) == "2026-08-02",
            "notes": None,
            "requires_review": False,
        }
        for row in snapshot["assignment_schedule_days"]
    ]
    request = {
        "contract_version": "assignment-leave-substitution-batch-preview/v1",
        "case_no": "CASE-1",
        "original_assignment_id": 11,
        "items": [
            {
                "original_schedule_id": 21,
                "work_date": "2026-08-01",
                "resolution_type": "defer_following_assignments",
                "substitute_staff_id": None,
            },
            {
                "original_schedule_id": 22,
                "work_date": "2026-08-02",
                "resolution_type": "substitute",
                "substitute_staff_id": 202,
                "is_double_pay": True,
            },
        ],
    }
    preview = compute_assignment_leave_resolution_batch_preview_from_snapshot(
        request, original, snapshot
    )
    command = build_assignment_leave_resolution_batch_mutation_command(
        {
            "canonical_intent": deepcopy(preview["canonical_intent"]),
            "double_pay_preferences": deepcopy(preview["double_pay_preferences"]),
            "service_plan_transition": deepcopy(preview["service_plan_transition"]),
            "canonical_eligibility": deepcopy(preview["canonical_eligibility"]),
            "preview_fingerprint": preview["preview_fingerprint"],
            "canonical_apply_identity": {
                "batch_key": "batch-1",
                "actor": "admin",
                "reason": "leave",
            },
        },
        {
            "original_assignment_schedule": deepcopy(original),
            "conflict_snapshot": deepcopy(snapshot),
            "lock_identity": {
                "case_no": "CASE-1",
                "staff_ids": [101, 202],
                "range_start": "2026-08-01",
                "range_end": "2026-08-04",
            },
        },
    )
    cursor = _BatchMutationCursor()
    monkeypatch.setattr(
        "services.assignment_payroll_reconciliation_service.reconcile_assignment_payroll_with_cursor",
        lambda owned_cursor, case_no, pending_substitution_event=None: {
            "errors": [],
            "can_create_staff_payments": True,
            "target_hours": Decimal("40"),
        },
    )

    result = execute_assignment_leave_resolution_batch_mutations(cursor, command)

    assert len(result["assignments"]) == 3
    assert result["schedule_snapshot"]["ownership_by_date"].keys() == {
        "2026-08-02",
        "2026-08-03",
        "2026-08-04",
        "2026-08-05",
        "2026-08-06",
    }
    assert len(result["pending_event_payloads"]) == 2
    assert result["pending_event_payloads"][1]["substitute_assignment_id"] > 0
    assert result["schedule_snapshot"]["double_pay_by_date"]["2026-08-02"] is True
