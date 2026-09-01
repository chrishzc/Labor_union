from __future__ import annotations

import json
from pathlib import Path

from scripts.generate_entrypoint_review_queue import build_review_queue
from scripts.generate_task97_entry_governance import build_artifact


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "document/架構重整/03_追蹤清單與證據/evidence/task97_entry_governance_v1.json"


def test_task97_entry_governance_is_fresh_clone_reproducible():
    queue = build_review_queue()
    artifact = build_artifact()
    persisted = json.loads(ARTIFACT.read_text(encoding="utf-8"))

    assert len(queue) == 724
    assert artifact == persisted
    assert artifact["source"]["entry_count"] == 724
    assert artifact["summary"]["generic_placeholder_count"] == 0
    assert artifact["summary"]["queue_status_counts"] == {
        "active": 496,
        "operator_only": 75,
        "retired_410": 79,
        "review_required": 74,
    }
    assert artifact["summary"]["terminal_disposition_counts"] == {
        "active_canonical": 496,
            "blocked_external_evidence": 72,
        "operator_only_guarded": 75,
        "retired_410": 79,
        "rewrite_to_canonical": 2,
    }
    assert artifact["summary"]["blocked_receipt_count"] == 74
    assert artifact["summary"]["repo_local_blocker_count"] == 0
    assert artifact["summary"]["deferred_external_evidence_count"] == 74
    assert artifact["summary"]["overall"] == "TASK97_REPOSITORY_LOCAL_COMPLETE"
    assert artifact["summary"]["production_acceptance"] == "NOT_RUN"
    assert len(artifact["records"]) == len(
        {record["exact_entry_identity"] for record in artifact["records"]}
    )


def test_every_entry_has_exact_terminal_evidence():
    artifact = build_artifact()
    allowed = {
        "active_canonical",
        "rewrite_to_canonical",
        "retired_410",
        "delete",
        "operator_only_guarded",
        "blocked_external_evidence",
    }

    for record in artifact["records"]:
        assert record["terminal_disposition"] in allowed
        assert record["canonical_owner"] not in {
            "owning bounded domain",
            "owner not evidenced",
        }
        assert record["business_scenario"] != "scenario not evidenced"
        assert record["operator"] != "operator not evidenced"
        assert record["runtime_registration"]
        assert record["current_inbound_callers"]
        assert record["replacement_path_or_symbol"]
        assert record["replacement_readback"]
        assert record["deletion_410_gate"]
        assert record["focused_regression"]
        assert record["final_zero_reference_oracle"]
        assert record["terminal_receipt"]
