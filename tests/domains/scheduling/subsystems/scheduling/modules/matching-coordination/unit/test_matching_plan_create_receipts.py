"""I281: immutable receipt replay for matching-plan create commands."""

import json
from unittest.mock import Mock

import pytest

from subsystems.scheduling import matching_plan_workflow as workflow


CASE_NO = "115000871"
EVENT_KEY = "i281-matching-plan-create-115000871"
SEGMENTS = [{
    "staff_id": 71,
    "assigned_start_date": "2026-12-01",
    "assigned_end_date": "2026-12-20",
}]


@pytest.mark.parametrize("is_active", [None, 1])
def test_only_current_accepted_plan_blocks_new_plan(is_active):
    cursor = Mock(lastrowid=72)
    cursor.fetchall.side_effect = [
        [{"id": 71, "version": 3, "status": "accepted", "is_active": is_active}],
        [],
        [],
        [],
    ]
    cursor.fetchone.return_value = {"max_version": 3}
    segments = workflow._normalize_segments(SEGMENTS)
    args = (object(), cursor, CASE_NO, segments, "operator", workflow._segments_signature(segments))

    if is_active:
        with pytest.raises(ValueError, match="while an accepted plan exists"):
            workflow._create_matching_plan_version_in_transaction(*args)
        assert cursor.execute.call_count == 1
    else:
        plan = workflow._create_matching_plan_version_in_transaction(*args)
        assert (plan["plan_id"], plan["version"], plan["status"], plan["result"]) == (
            72, 4, "proposed", "created",
        )


@pytest.mark.parametrize("latest_decision", ["accepted", "declined", "contact_requested", None])
def test_latest_customer_decision_protects_current_proposed_plan(latest_decision):
    cursor = Mock(lastrowid=72)
    cursor.fetchall.side_effect = [
        [
            {"id": 71, "version": 3, "status": "proposed", "is_active": 1},
            {"id": 70, "version": 2, "status": "accepted", "is_active": None},
        ],
        [],
        [],
        [],
    ]
    decision_query = (
        "SELECT response_value FROM matching_response_events "
        "WHERE plan_id = %s AND segment_id IS NULL AND response_type = 'customer_decision' "
        "ORDER BY occurred_at_utc DESC, id DESC LIMIT 1 FOR UPDATE"
    )

    def fetchone():
        statement, params = cursor.execute.call_args.args
        if "matching_response_events" in statement:
            assert " ".join(statement.split()) == decision_query
            assert params == (71,)
            return {"response_value": latest_decision} if latest_decision else None
        return {"max_version": 3}

    cursor.fetchone.side_effect = fetchone
    segments = workflow._normalize_segments(SEGMENTS)
    args = (object(), cursor, CASE_NO, segments, "operator", workflow._segments_signature(segments))

    if latest_decision == "accepted":
        with pytest.raises(ValueError, match="while an accepted plan exists"):
            workflow._create_matching_plan_version_in_transaction(*args)
        assert all(call.args[0].startswith("SELECT") for call in cursor.execute.call_args_list)
    else:
        plan = workflow._create_matching_plan_version_in_transaction(*args)
        assert (plan["plan_id"], plan["version"], plan["result"]) == (72, 4, "created")
    assert any("matching_response_events" in call.args[0] for call in cursor.execute.call_args_list)


def _receipt(*, fingerprint: str, case_no: str = CASE_NO) -> dict[str, object]:
    return {
        "plan_id": 71,
        "case_no": case_no,
        "version": 3,
        "status": "proposed",
        "result": "created",
        "segments": [{
            "segment_order": 1,
            "staff_id": 71,
            "assigned_start_date": "2026-12-01",
            "assigned_end_date": "2026-12-20",
        }],
        "actor": "operator",
        "as_of": "2026-09-12",
        "event_key": EVENT_KEY,
        "command_fingerprint": fingerprint,
        "replayed": False,
    }


@pytest.mark.parametrize(
    ("changed_command", "expected"),
    [
        ("exact", "replay"),
        ("actor", "reject"),
        ("as_of", "reject"),
        ("ordered_segments", "reject"),
    ],
)
def test_i281_matching_plan_create_receipt_replays_only_the_immutable_original_command(
    monkeypatch,
    changed_command,
    expected,
):
    """One aggregate oracle: replay, changed payload, and fresh-state bypass."""
    original = workflow._create_command_fingerprint(
        CASE_NO, SEGMENTS, "operator", "2026-09-12"
    )
    persisted = _receipt(fingerprint=original)
    calls = {"availability": 0, "writer": 0}
    monkeypatch.setattr(workflow, "_lock_matching_plan_case_root", lambda *_args: None)
    monkeypatch.setattr(
        workflow,
        "_load_matching_plan_create_receipt",
        lambda *_args, **_kwargs: persisted,
    )
    monkeypatch.setattr(
        workflow,
        "_validate_current_availability",
        lambda *_args, **_kwargs: calls.__setitem__("availability", calls["availability"] + 1),
    )
    monkeypatch.setattr(
        workflow,
        "_create_matching_plan_version_in_transaction",
        lambda *_args, **_kwargs: calls.__setitem__("writer", calls["writer"] + 1),
    )

    actor = "other-operator" if changed_command == "actor" else "operator"
    as_of = "2026-09-13" if changed_command == "as_of" else "2026-09-12"
    segments = (
        [{
            "staff_id": 72,
            "assigned_start_date": "2026-12-01",
            "assigned_end_date": "2026-12-20",
        }]
        if changed_command == "ordered_segments" else SEGMENTS
    )
    fingerprint = workflow._create_command_fingerprint(CASE_NO, segments, actor, as_of)

    if expected == "reject":
        with pytest.raises(ValueError, match="does not match original command"):
            workflow._create_matching_plan_version_with_receipt(
                object(), object(), CASE_NO, segments, actor, as_of, EVENT_KEY,
                fingerprint, object(), False,
            )
    else:
        replay = workflow._create_matching_plan_version_with_receipt(
            object(), object(), CASE_NO, segments, actor, as_of, EVENT_KEY,
            fingerprint, object(), False,
        )
        assert replay == {**persisted, "replayed": True}

    assert calls == {"availability": 0, "writer": 0}


def test_i281_matching_plan_create_receipt_persists_initial_result_and_readback_is_rollback_only(
    monkeypatch,
):
    fingerprint = workflow._create_command_fingerprint(
        CASE_NO, SEGMENTS, "operator", "2026-09-12"
    )
    saved = []
    monkeypatch.setattr(workflow, "_lock_matching_plan_case_root", lambda *_args: None)
    monkeypatch.setattr(workflow, "require_candidate_matching_open", lambda *_args: None)
    monkeypatch.setattr(workflow, "_load_matching_plan_create_receipt", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(workflow, "_validate_current_availability", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        workflow,
        "_create_matching_plan_version_in_transaction",
        lambda *_args, **_kwargs: _receipt(fingerprint=fingerprint),
    )
    monkeypatch.setattr(
        workflow,
        "_save_matching_plan_create_receipt",
        lambda _cursor, receipt: saved.append(receipt),
    )

    created = workflow._create_matching_plan_version_with_receipt(
        object(), object(), CASE_NO, SEGMENTS, "operator", "2026-09-12",
        EVENT_KEY, fingerprint, object(), False,
    )
    assert created == _receipt(fingerprint=fingerprint)
    assert saved == [created]

    class Cursor:
        def close(self):
            return None

    class Connection:
        def __init__(self):
            self.commits = 0
            self.rollbacks = 0

        def cursor(self):
            return Cursor()

        def commit(self):
            self.commits += 1

        def rollback(self):
            self.rollbacks += 1

        def close(self):
            return None

    connection = Connection()
    monkeypatch.setattr(workflow, "get_connection", lambda: connection)
    monkeypatch.setattr(workflow, "_load_matching_plan_create_receipt", lambda *_args, **_kwargs: created)
    assert workflow.get_matching_plan_create_receipt(CASE_NO, EVENT_KEY) == created
    assert (connection.commits, connection.rollbacks) == (0, 1)


@pytest.mark.parametrize("tampered_field", ["ordered_segments", "result_kind", "fingerprint"])
def test_i281_matching_plan_create_receipt_rejects_tampered_persisted_command_identity(
    tampered_field,
):
    fingerprint = workflow._create_command_fingerprint(
        CASE_NO, SEGMENTS, "operator", "2026-09-12"
    )
    receipt = _receipt(fingerprint=fingerprint)
    row = {
        "case_no": CASE_NO,
        "plan_id": 71,
        "plan_version": 3,
        "plan_status": "proposed",
        "actor": "operator",
        "as_of": "2026-09-12",
        "idempotency_key": EVENT_KEY,
        "command_fingerprint": fingerprint,
        "result_kind": "created",
        "ordered_segments": json.dumps(receipt["segments"]),
        "result_snapshot": json.dumps(receipt),
    }
    if tampered_field == "ordered_segments":
        row["ordered_segments"] = json.dumps([{**receipt["segments"][0], "staff_id": 72}])
    elif tampered_field == "result_kind":
        row["result_kind"] = "existing"
    else:
        row["command_fingerprint"] = "a" * 64

    class Cursor:
        def execute(self, *_args):
            return None

        def fetchone(self):
            return row

    with pytest.raises(ValueError, match="receipt is invalid"):
        workflow._load_matching_plan_create_receipt(Cursor(), EVENT_KEY, for_update=False)
