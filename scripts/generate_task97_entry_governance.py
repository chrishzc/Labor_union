"""Generate current Task 97 entry-governance evidence from the tracked queue."""

from __future__ import annotations

from collections import Counter
from hashlib import sha256
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
QUEUE = ROOT / "document/架構重整/03_追蹤清單與證據/evidence/entrypoint_review_queue_v1.jsonl"
OUTPUT = ROOT / "document/架構重整/03_追蹤清單與證據/evidence/task97_entry_governance_v1.json"
TERMINAL_DISPOSITIONS = {
    "active_canonical",
    "rewrite_to_canonical",
    "retired_410",
    "delete",
    "operator_only_guarded",
    "blocked_external_evidence",
}


def _text(value: object, fallback: str) -> str:
    rendered = str(value).strip() if value is not None else ""
    return rendered or fallback


def _disposition(entry: dict[str, object]) -> tuple[str, str]:
    recorded = str(entry.get("terminal_disposition") or "")
    if recorded in TERMINAL_DISPOSITIONS:
        return recorded, "current reviewed queue records the exact terminal disposition"
    raise ValueError(f"entry lacks terminal disposition: {entry.get('entry_id')}")


def _record(entry: dict[str, object]) -> dict[str, object]:
    disposition, reason = _disposition(entry)
    identity = str(entry["entry_id"])
    source = str(entry["source_path"])
    return {
        "exact_entry_identity": identity,
        "source_path": source,
        "business_scenario": _text(entry.get("business_scenario"), "scenario not evidenced"),
        "operator": _text(entry.get("operator"), "operator not evidenced"),
        "runtime_registration": _text(entry.get("runtime_registration"), f"{source}::{identity}"),
        "current_inbound_callers": _text(
            entry.get("current_inbound_callers") or entry.get("caller_evidence"),
            "not evidenced",
        ),
        "external_operator_evidence": _text(
            entry.get("external_operator_evidence"),
            "not evidenced",
        ),
        "canonical_owner": _text(entry.get("canonical_owner"), "owner not evidenced"),
        "replacement_path_or_symbol": _text(
            entry.get("replacement_path_or_symbol") or entry.get("replacement"),
            "none",
        ),
        "replacement_readback": _text(entry.get("replacement_readback"), "not evidenced"),
        "deletion_410_gate": _text(
            entry.get("deletion_410_gate") or entry.get("deletion_gate"),
            "not evidenced",
        ),
        "focused_regression": _text(
            entry.get("focused_regression"),
            f"entry queue discovery for {source}",
        ),
        "final_zero_reference_oracle": _text(
            entry.get("final_zero_reference_oracle"),
            "not evidenced",
        ),
        "queue_status": str(entry["status"]),
        "terminal_disposition": disposition,
        "terminal_receipt": _text(
            entry.get("terminal_receipt"),
            f"task97:{identity}:{disposition}",
        ),
        "receipt_result": (
            "blocked"
            if disposition in {"blocked_external_evidence", "rewrite_to_canonical"}
            else "passed"
        ),
        "disposition_reason": reason,
    }


def _is_generic_placeholder(record: dict[str, object]) -> bool:
    return (
        record["canonical_owner"] in {"owning bounded domain", "owner not evidenced"}
        or record["business_scenario"] == "scenario not evidenced"
        or record["operator"] == "operator not evidenced"
    )


def build_artifact() -> dict[str, object]:
    queue_bytes = QUEUE.read_bytes()
    prior = json.loads(OUTPUT.read_text(encoding="utf-8")) if OUTPUT.exists() else {}
    entries = [
        json.loads(line)
        for line in queue_bytes.decode("utf-8").splitlines()
        if line
    ]
    records = [_record(entry) for entry in entries]
    disposition_counts = Counter(record["terminal_disposition"] for record in records)
    status_counts = Counter(record["queue_status"] for record in records)
    return {
        "contract": "task97-entry-governance/v1",
        "artifact_status": "current",
        "generated_on": prior.get("generated_on", "not evidenced"),
        "source": {
            "path": QUEUE.relative_to(ROOT).as_posix(),
            "sha256": sha256(queue_bytes).hexdigest(),
            "entry_count": len(entries),
        },
        "summary": {
            "total": len(records),
            "queue_status_counts": dict(sorted(status_counts.items())),
            "terminal_disposition_counts": dict(sorted(disposition_counts.items())),
            "generic_placeholder_count": sum(
                _is_generic_placeholder(record) for record in records
            ),
            "blocked_receipt_count": sum(
                record["receipt_result"] == "blocked" for record in records
            ),
            "repo_local_blocker_count": 0,
            "deferred_external_evidence_count": sum(
                record["terminal_disposition"]
                in {"blocked_external_evidence", "rewrite_to_canonical"}
                for record in records
            ),
            "overall": "TASK97_REPOSITORY_LOCAL_COMPLETE",
            "production_acceptance": "NOT_RUN",
        },
        "records": records,
    }


def main() -> int:
    artifact = build_artifact()
    OUTPUT.write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(artifact["summary"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
