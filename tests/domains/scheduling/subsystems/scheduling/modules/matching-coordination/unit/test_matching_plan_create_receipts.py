"""I281: immutable receipt replay for matching-plan create commands."""

import json

import pytest

from subsystems.scheduling import matching_plan_workflow as workflow


CASE_NO = "115000871"
EVENT_KEY = "i281-matching-plan-create-115000871"
SEGMENTS = [{
    "staff_id": 71,
    "assigned_start_date": "2026-12-01",
    "assigned_end_date": "2026-12-20",
}]


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
