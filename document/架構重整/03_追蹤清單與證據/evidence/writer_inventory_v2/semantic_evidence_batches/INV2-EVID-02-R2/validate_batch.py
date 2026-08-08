from __future__ import annotations

from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess


WRAPPER_PATH = Path(__file__).resolve()
BATCH_ROOT = WRAPPER_PATH.parent
BATCHES_ROOT = BATCH_ROOT.parent
EVIDENCE_ROOT = BATCHES_ROOT.parent
REPOSITORY_ROOT = EVIDENCE_ROOT.parents[3]
PROFILE_PATH = BATCH_ROOT / "batch_profile.json"
EXPECTED_PROFILE_SHA256 = (
    "dc34e942ca584e88575ca271ac6dca4d9fae98d733af05bd0bc7e671ea3c537d"
)
PROTECTED_FILENAMES = frozenset({"batch_profile.json", "validate_batch.py"})
OUTPUT_FILENAMES = frozenset(
    {
        "batch_manifest.json",
        "finding_evidence.jsonl",
        "unresolved.md",
        "validation_receipt.json",
    }
)
MANIFEST_KEYS = {
    "contract",
    "batch_id",
    "row_start",
    "row_end",
    "processed_count",
    "input_manifest_sha256",
    "branch",
    "head",
    "profile_sha256",
    "schema_sha256",
    "validator_sha256",
    "gold_sample_hashes",
    "original_batch_hashes",
    "finding_evidence_sha256",
    "unresolved_row_numbers",
    "may_mutate",
    "execution_authority",
    "effective_disposition",
    "approved_to_remove_count",
    "generated_at",
}


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_path(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def canonical_json_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def strict_text(path: Path) -> str:
    payload = path.read_bytes()
    if payload.startswith(b"\xef\xbb\xbf"):
        raise ValueError(f"UTF-8 BOM is forbidden: {path}")
    if b"\r" in payload:
        raise ValueError(f"CR is forbidden: {path}")
    return payload.decode("utf-8", errors="strict")


def load_canonical_json(path: Path) -> dict:
    value = json.loads(strict_text(path))
    if path.read_bytes() != canonical_json_bytes(value):
        raise ValueError(f"non-canonical JSON: {path}")
    return value


def load_base_validator(path: Path):
    spec = importlib.util.spec_from_file_location(
        "inventory_v2_semantic_validator",
        path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load protected semantic validator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def require_exact_keys(value: dict, expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise ValueError(
            f"{label} keys differ: missing={sorted(expected - set(value))}, "
            f"extra={sorted(set(value) - expected)}"
        )


def resolve_repository_path(relative_path: str) -> Path:
    path = (REPOSITORY_ROOT / relative_path).resolve()
    try:
        path.relative_to(REPOSITORY_ROOT)
    except ValueError as error:
        raise ValueError(f"path escapes repository: {relative_path}") from error
    return path


def validate_hash_map(base_path: Path, hashes: dict[str, str]) -> None:
    for filename, expected_digest in hashes.items():
        path = base_path / filename
        if sha256_path(path) != expected_digest:
            raise ValueError(f"protected input changed: {path}")


# Kept cohesive so every protected hash is checked before the base validator loads.
def validate_protected_inputs(profile: dict) -> object:
    if sha256_path(PROFILE_PATH) != EXPECTED_PROFILE_SHA256:
        raise ValueError("batch profile hash changed")
    final_manifest = resolve_repository_path(
        profile["final_inventory"]["manifest_path"]
    )
    if sha256_path(final_manifest) != profile["final_inventory"]["manifest_sha256"]:
        raise ValueError("Final Inventory manifest changed")
    final_rows = resolve_repository_path(profile["final_inventory"]["rows_path"])
    if sha256_path(final_rows) != profile["final_inventory"]["rows_sha256"]:
        raise ValueError("Final Inventory findings changed")

    protected = profile["protected_inputs"]
    schema_path = resolve_repository_path(protected["schema_path"])
    validator_path = resolve_repository_path(protected["validator_path"])
    if sha256_path(schema_path) != protected["schema_sha256"]:
        raise ValueError("semantic evidence schema changed")
    if sha256_path(validator_path) != protected["validator_sha256"]:
        raise ValueError("semantic evidence validator changed")

    gold = profile["gold_sample"]
    gold_path = resolve_repository_path(gold["batch_path"])
    validate_hash_map(
        gold_path,
        {
            "batch_manifest.json": gold["batch_manifest_sha256"],
            "finding_evidence.jsonl": gold["finding_evidence_sha256"],
            "unresolved.md": gold["unresolved_sha256"],
            "validation_receipt.json": gold["validation_receipt_sha256"],
        },
    )
    original = profile["original_batch"]
    validate_hash_map(
        resolve_repository_path(original["path"]),
        original["hashes"],
    )
    return load_base_validator(validator_path)


def validate_output_scope(profile: dict) -> None:
    if set(profile["allowed_output_files"]) != OUTPUT_FILENAMES:
        raise ValueError("profile output allowlist differs from wrapper contract")
    allowed = PROTECTED_FILENAMES | OUTPUT_FILENAMES
    actual = set()
    for path in BATCH_ROOT.rglob("*"):
        relative_path = path.relative_to(BATCH_ROOT).as_posix()
        if path.is_dir():
            raise ValueError(f"batch subdirectories are forbidden: {relative_path}")
        actual.add(relative_path)
    unexpected = actual - allowed
    if unexpected:
        raise ValueError(f"unexpected batch files: {sorted(unexpected)}")


def current_git_identity() -> tuple[str, str]:
    branch = subprocess.check_output(
        ["git", "branch", "--show-current"],
        cwd=REPOSITORY_ROOT,
        text=True,
    ).strip()
    head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=REPOSITORY_ROOT,
        text=True,
    ).strip()
    return branch, head


# Kept cohesive so the closed batch contract is reviewed as one fail-closed gate.
def validate_manifest(manifest: dict, profile: dict) -> None:
    require_exact_keys(manifest, MANIFEST_KEYS, "batch manifest")
    if manifest["contract"] != "semantic-evidence-batch-manifest/v2":
        raise ValueError("unsupported batch manifest contract")
    if manifest["batch_id"] != profile["batch_id"]:
        raise ValueError("batch id mismatch")
    if (
        manifest["row_start"] != profile["row_start"]
        or manifest["row_end"] != profile["row_end"]
    ):
        raise ValueError("row range mismatch")
    if manifest["processed_count"] != 50:
        raise ValueError("processed count must be 50")
    if (
        manifest["input_manifest_sha256"]
        != profile["final_inventory"]["manifest_sha256"]
    ):
        raise ValueError("Final Inventory digest mismatch")
    branch, head = current_git_identity()
    if manifest["branch"] != branch or manifest["head"] != head:
        raise ValueError("git identity changed")
    if manifest["profile_sha256"] != EXPECTED_PROFILE_SHA256:
        raise ValueError("profile digest mismatch")
    protected = profile["protected_inputs"]
    if manifest["schema_sha256"] != protected["schema_sha256"]:
        raise ValueError("schema digest mismatch")
    if manifest["validator_sha256"] != protected["validator_sha256"]:
        raise ValueError("validator digest mismatch")
    expected_gold_hashes = {
        key: value
        for key, value in profile["gold_sample"].items()
        if key.endswith("_sha256")
    }
    if manifest["gold_sample_hashes"] != expected_gold_hashes:
        raise ValueError("Gold Sample hashes changed")
    if (
        manifest["original_batch_hashes"]
        != profile["original_batch"]["hashes"]
    ):
        raise ValueError("original Batch 02 hashes changed")
    if manifest["may_mutate"] is not False:
        raise ValueError("batch may not mutate production")
    if manifest["execution_authority"] != "none":
        raise ValueError("batch has forbidden execution authority")
    if manifest["effective_disposition"] != "blocked":
        raise ValueError("batch disposition must remain blocked")
    if manifest["approved_to_remove_count"] != 0:
        raise ValueError("batch cannot approve removal")
    unresolved_rows = manifest["unresolved_row_numbers"]
    if any(
        not isinstance(row, int)
        or not profile["row_start"] <= row <= profile["row_end"]
        for row in unresolved_rows
    ):
        raise ValueError("unresolved row is outside batch")
    if len(unresolved_rows) != len(set(unresolved_rows)):
        raise ValueError("unresolved rows must be unique")


def validate_rows(base_validator, profile: dict) -> list[dict]:
    evidence_path = BATCH_ROOT / "finding_evidence.jsonl"
    final_rows_path = resolve_repository_path(
        profile["final_inventory"]["rows_path"]
    )
    rows = base_validator.load_jsonl(evidence_path)
    final_rows = base_validator.load_jsonl(final_rows_path)
    final_by_number = {
        row["inventory_row_number"]: row
        for row in final_rows
    }
    expected_numbers = list(
        range(profile["row_start"], profile["row_end"] + 1)
    )
    actual_numbers = [row["inventory_row_number"] for row in rows]
    if actual_numbers != expected_numbers:
        raise ValueError("Batch 02 must contain rows 51 through 100 exactly once")
    if len({row["finding_identity_digest"] for row in rows}) != len(rows):
        raise ValueError("finding identity digests must be unique")
    for row in rows:
        base_validator.validate_row(
            row,
            final_by_number[row["inventory_row_number"]],
        )
    return rows


def validate_manifest_artifact_hash(
    manifest: dict,
    evidence_path: Path,
) -> None:
    if manifest["finding_evidence_sha256"] != sha256_path(evidence_path):
        raise ValueError("finding evidence digest mismatch")


# Kept cohesive so the receipt is a single projection of already-validated rows.
def build_receipt(
    rows: list[dict],
    manifest: dict,
    profile: dict,
) -> dict:
    disposition_counts = Counter(
        row["suggestion"]["candidate_type"]
        for row in rows
    )
    high_risk_rows = [
        row["inventory_row_number"]
        for row in rows
        if row["semantic_evidence"]["high_risk"]
    ]
    positive_caller_count = sum(
        len(row["semantic_evidence"]["caller_evidence"])
        for row in rows
    )
    negative_caller_count = sum(
        len(row["semantic_evidence"]["negative_caller_evidence"])
        for row in rows
    )
    return {
        "contract": "semantic-evidence-batch-validation-receipt/v1",
        "result": "pass",
        "validation_scope": (
            "protected-input hashes, exact batch range, canonical JSONL, "
            "live-source identity, positive AST callers, replayed negative "
            "searches, architecture-reference bounds, risk taxonomy and "
            "candidate consistency"
        ),
        "semantic_disposition_complete": False,
        "semantic_unresolved_rows": manifest["unresolved_row_numbers"],
        "profile_sha256": EXPECTED_PROFILE_SHA256,
        "wrapper_sha256": sha256_path(WRAPPER_PATH),
        "schema_sha256": profile["protected_inputs"]["schema_sha256"],
        "validator_sha256": profile["protected_inputs"]["validator_sha256"],
        "batch_manifest": {
            "path": (BATCH_ROOT / "batch_manifest.json")
            .relative_to(REPOSITORY_ROOT)
            .as_posix(),
            "sha256": sha256_path(BATCH_ROOT / "batch_manifest.json"),
        },
        "finding_evidence": {
            "path": (BATCH_ROOT / "finding_evidence.jsonl")
            .relative_to(REPOSITORY_ROOT)
            .as_posix(),
            "sha256": sha256_path(BATCH_ROOT / "finding_evidence.jsonl"),
        },
        "unresolved": {
            "path": (BATCH_ROOT / "unresolved.md")
            .relative_to(REPOSITORY_ROOT)
            .as_posix(),
            "sha256": sha256_path(BATCH_ROOT / "unresolved.md"),
        },
        "row_count": len(rows),
        "identity_unique_count": len(rows),
        "positive_caller_evidence_count": positive_caller_count,
        "negative_caller_evidence_count": negative_caller_count,
        "disposition_counts": dict(sorted(disposition_counts.items())),
        "high_risk_rows": high_risk_rows,
        "effective_disposition_blocked_count": sum(
            row["effective_disposition"] == "blocked"
            for row in rows
        ),
        "approved_to_remove_true_count": sum(
            row["approved_to_remove"] is True
            for row in rows
        ),
        "protected_inputs_unchanged": True,
        "validator_write_paths": [
            (BATCH_ROOT / "validation_receipt.json")
            .relative_to(REPOSITORY_ROOT)
            .as_posix()
        ],
    }


def main() -> None:
    profile = load_canonical_json(PROFILE_PATH)
    if profile["contract"] != "semantic-evidence-batch-profile/v1":
        raise ValueError("unsupported batch profile")
    base_validator = validate_protected_inputs(profile)
    validate_output_scope(profile)
    manifest_path = BATCH_ROOT / "batch_manifest.json"
    evidence_path = BATCH_ROOT / "finding_evidence.jsonl"
    unresolved_path = BATCH_ROOT / "unresolved.md"
    for required_path in (manifest_path, evidence_path, unresolved_path):
        if not required_path.is_file():
            raise ValueError(f"missing required output: {required_path.name}")
    manifest = load_canonical_json(manifest_path)
    validate_manifest(manifest, profile)
    validate_manifest_artifact_hash(manifest, evidence_path)
    strict_text(unresolved_path)
    rows = validate_rows(base_validator, profile)
    receipt = build_receipt(rows, manifest, profile)
    receipt_path = BATCH_ROOT / "validation_receipt.json"
    receipt_path.write_bytes(canonical_json_bytes(receipt))
    print(
        "BATCH_02_SEMANTIC_EVIDENCE_VALIDATION_PASS "
        f"rows={len(rows)} callers="
        f"{receipt['positive_caller_evidence_count']} "
        f"negative={receipt['negative_caller_evidence_count']} "
        f"high_risk={len(receipt['high_risk_rows'])}"
    )


if __name__ == "__main__":
    main()
