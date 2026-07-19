from __future__ import annotations

from copy import deepcopy

import pytest

from scripts.migrate_adad_task_snapshots import build_v3_candidate, migrate_tasks, validate_v3_candidate


def _v2_task(status: str = "approved") -> dict:
    return {
        "schema_version": 2,
        "task_id": "ExampleTask@v1@123abc",
        "node_name": "ExampleTask",
        "exported_at": "2026-07-19T00:00:00+00:00",
        "system_map_version": 1,
        "source_hash": "source-hash",
        "status": status,
        "source_lock": {
            "source_path": "services/example.py",
            "node_name": "ExampleTask",
            "task_id": "ExampleTask@v1@123abc",
            "acquired_at": "2026-07-19T00:00:00+00:00",
        },
        "rollback": {
            "strategy": "preserve_diff",
            "source_path": "services/example.py",
            "baseline_file_hash": "baseline-hash",
        },
        "implementation_hash": "implementation-hash",
        "history": [{"event": "approved", "at": "2026-07-19T00:00:00+00:00"}],
        "spec": {
            "target_node": {
                "name": "ExampleTask",
                "type": "service",
                "state": "validated",
                "source": "services/example.py",
                "input": {},
                "output": {},
                "dependencies": [],
                "description": "Example task snapshot migration fixture.",
                "map_file": "system_map.md",
                "invariants": [],
                "verification": [],
                "observability": {"mode": "not_required", "signals": []},
                "complexity": "low",
                "algorithm": [],
                "preferred_pattern": "none",
            }
        },
    }


@pytest.mark.parametrize("status", ["assigned", "submitted", "approved"])
def test_build_v3_candidate_preserves_audit_fields_and_status(status):
    original = _v2_task(status)
    before = deepcopy(original)

    candidate = build_v3_candidate(original, "2026-07-19T01:02:03+00:00")

    assert original == before
    assert candidate["schema_version"] == 3
    assert candidate["status"] == status
    assert candidate["task_id"] == before["task_id"]
    assert candidate["source_hash"] == before["source_hash"]
    assert candidate["implementation_hash"] == before["implementation_hash"]
    assert candidate["source_lock"] == before["source_lock"]
    assert candidate["rollback"] == before["rollback"]
    assert candidate["history"][:-1] == before["history"]
    assert candidate["history"][-1] == {
        "event": "schema_v2_to_v3_migrated",
        "at": "2026-07-19T01:02:03+00:00",
        "from_schema_version": 2,
    }
    assert candidate["spec"]["target_node"]["non_goals"] == []
    assert validate_v3_candidate(candidate)["valid"] is True


def test_build_v3_candidate_rejects_non_v2_without_mutation():
    task = _v2_task()
    task["schema_version"] = 3
    before = deepcopy(task)

    with pytest.raises(ValueError, match="schema_version=2"):
        build_v3_candidate(task, "2026-07-19T01:02:03+00:00")

    assert task == before


def test_build_v3_candidate_surfaces_validator_errors_without_writing():
    task = _v2_task()
    before = deepcopy(task)

    def rejected_validator(_candidate, _expected_node_name):
        return {"valid": False, "errors": ["fixture rejection"]}

    with pytest.raises(ValueError, match="fixture rejection"):
        build_v3_candidate(task, "2026-07-19T01:02:03+00:00", rejected_validator)

    assert task == before


def _write_task(path, task):
    path.write_text(__import__("json").dumps(task, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def test_dry_run_is_zero_write_and_reports_v2(tmp_path):
    tasks_dir = tmp_path / ".agents" / "tasks"
    tasks_dir.mkdir(parents=True)
    task_path = tasks_dir / "ExampleTask.task.json"
    _write_task(task_path, _v2_task())
    before = task_path.read_bytes()

    manifest = migrate_tasks(tasks_dir, project_root=tmp_path, migrated_at="2026-07-19T01:02:03+00:00")

    assert manifest["mode"] == "dry-run"
    assert manifest["counts"] == {"would_migrate": 1}
    assert task_path.read_bytes() == before
    assert not (tmp_path / ".agents" / "archive").exists()


def test_apply_archives_byte_exactly_and_preserves_submitted_status(tmp_path):
    tasks_dir = tmp_path / ".agents" / "tasks"
    tasks_dir.mkdir(parents=True)
    legacy_path = tasks_dir / "ExampleTask.task.json"
    current_path = tasks_dir / "CurrentTask.task.json"
    legacy = _v2_task("submitted")
    current = build_v3_candidate(_v2_task("approved"), "2026-07-19T00:00:00+00:00")
    current["node_name"] = "CurrentTask"
    current["task_id"] = "CurrentTask@v1@123abc"
    current["source_lock"]["node_name"] = "CurrentTask"
    current["source_lock"]["task_id"] = "CurrentTask@v1@123abc"
    current["spec"]["target_node"]["name"] = "CurrentTask"
    _write_task(legacy_path, legacy)
    _write_task(current_path, current)
    original = legacy_path.read_bytes()

    manifest = migrate_tasks(
        tasks_dir,
        apply=True,
        archive_dir=".agents/archive",
        project_root=tmp_path,
        migrated_at="2026-07-19T01:02:03+00:00",
    )

    assert manifest["counts"] == {"migrated": 1, "skipped": 1}
    assert (tmp_path / ".agents" / "archive" / legacy_path.name).read_bytes() == original
    migrated = __import__("json").loads(legacy_path.read_text(encoding="utf-8"))
    assert migrated["schema_version"] == 3
    assert migrated["status"] == "submitted"
    assert validate_v3_candidate(migrated)["valid"] is True
    assert __import__("json").loads(current_path.read_text(encoding="utf-8")) == current


def test_apply_continues_after_one_blocked_task_without_overwriting_it(tmp_path):
    tasks_dir = tmp_path / ".agents" / "tasks"
    tasks_dir.mkdir(parents=True)
    blocked_path = tasks_dir / "Blocked.task.json"
    ready_path = tasks_dir / "Ready.task.json"
    blocked = _v2_task()
    blocked["spec"] = {}
    _write_task(blocked_path, blocked)
    _write_task(ready_path, _v2_task())
    before = blocked_path.read_bytes()

    manifest = migrate_tasks(
        tasks_dir,
        apply=True,
        archive_dir=".agents/archive",
        project_root=tmp_path,
        migrated_at="2026-07-19T01:02:03+00:00",
    )

    assert manifest["counts"] == {"blocked": 1, "migrated": 1}
    assert blocked_path.read_bytes() == before
    assert __import__("json").loads(ready_path.read_text(encoding="utf-8"))["schema_version"] == 3


def test_rejects_paths_outside_project_agents_directory(tmp_path):
    outside_tasks = tmp_path / "outside"
    outside_tasks.mkdir()

    with pytest.raises(ValueError, match=".agents"):
        migrate_tasks(outside_tasks, project_root=tmp_path)
