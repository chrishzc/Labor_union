"""Pure owner receipt/readback tests; no connection, cursor or SQL execution."""

from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone

import pytest

from domains.contract_signing.external_signing import ExternalSigningState, SignedContractDocumentTarget
from subsystems.contract_signing.external_signing_contracts import ExternalSigningTypedError
from subsystems.contract_signing.final_document_workflow import (
    FinalContractDocumentReadback, FinalSignedContractApplyReceipt, SignedContractDocumentReadback,
    signed_contract_intent, signed_contract_object_key,
    signed_contract_file_apply_key,
)
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from subsystems.controlled_files.workflow import (
    ControlledFileApplyOutcome, ControlledFileApplyReceipt, ControlledFileOwner,
    ControlledFilePurpose, ControlledFileReadback, ControlledFileWorkflowError,
)
from subsystems.controlled_files.reconciliation import CommittedControlledFileApplyEvidence
from infrastructure.db.contract_external_signing_repository import (
    _final_contract_file_reference, _final_contract_reference_members,
    _final_receipt_snapshot, _signed_document_members,
    _read_legacy_member_apply_evidence,
    _legacy_aggregate_final_reference, MySqlContractExternalSigningRepository,
)


NOW = datetime(2026, 11, 6, tzinfo=timezone.utc)
DIGEST = "a" * 64
CASE = "CASE-001"
SESSION = "ces_" + "b" * 32
CLIENT = SignedContractDocumentTarget("client", None, 7)
STAFF = SignedContractDocumentTarget("staff", 11, 8)


def member(target=STAFF, *, frozen=True):
    purpose = (ControlledFilePurpose.FINAL_SIGNED_CONTRACT if target.scope == "client"
               else ControlledFilePurpose.SIGNED_STAFF_AGREEMENT)
    return SignedContractDocumentReadback(
        target, "cf_" + ("c" if target.scope == "client" else "d") * 32,
        1, f"{target.scope}.pdf", "application/pdf", 3,
        DIGEST if frozen else None, purpose if frozen else None,
    )


def receipt(members):
    client = member(CLIENT)
    document = FinalContractDocumentReadback(
        "cfd_" + "e" * 32, CASE, client.file_id, 1, client.filename,
        "application/pdf", 3, "completed", NOW,
    )
    return FinalSignedContractApplyReceipt(
        "cesr_" + "f" * 32, SESSION, 4, ExternalSigningState.COMPLETED,
        document, "contract-identity", tuple(members),
    )


def row(value):
    return {
        "object_id": 1 if value.target.scope == "client" else 2,
        "opaque_object_id": value.file_id,
        "object_key": signed_contract_object_key(SESSION, value.target),
        "owner_type": "contract_signing", "purpose": (
            "final_signed_contract" if value.target.scope == "client" else "signed_staff_agreement"
        ),
        "subject_reference": CASE, "case_no": CASE, "external_signing_session_id": SESSION,
        "version_number": 1, "filename": value.filename, "content_type": "application/pdf",
        "content_sha256": DIGEST, "size_bytes": 3, "is_current": 1,
        "primary_object_id": 1, "primary_content_sha256": DIGEST, "primary_size_bytes": 3,
    }


def test_client_and_staff_intents_use_their_exact_formal_purpose_and_owner():
    for target, purpose in ((CLIENT, ControlledFilePurpose.FINAL_SIGNED_CONTRACT),
                            (STAFF, ControlledFilePurpose.SIGNED_STAFF_AGREEMENT)):
        intent = signed_contract_intent(CASE, SESSION, target, "cfs_" + "a" * 32)
        assert intent.owner.value == "contract_signing" and intent.purpose is purpose
        assert intent.subject_reference == CASE
        assert intent.object_key == signed_contract_object_key(SESSION, target)


def test_new_member_receipt_preserves_each_file_version_digest_and_purpose():
    values = (member(CLIENT), member(STAFF))
    snapshot = _final_receipt_snapshot(receipt(values))
    assert _signed_document_members(snapshot) == values
    assert [entry["content_sha256"] for entry in snapshot["documents"]] == [DIGEST, DIGEST]
    assert [entry["purpose"] for entry in snapshot["documents"]] == [
        "final_signed_contract", "signed_staff_agreement",
    ]
    assert {entry["version_number"] for entry in snapshot["documents"]} == {1}


def test_legacy_member_stays_readable_without_fabricated_hash_or_purpose():
    values = (member(CLIENT, frozen=False), member(STAFF, frozen=False))
    snapshot = _final_receipt_snapshot(receipt(values))
    assert all("content_sha256" not in entry and "purpose" not in entry for entry in snapshot["documents"])
    assert _signed_document_members(snapshot) == values
    assert _final_contract_file_reference(row(values[0]), values).sha256_digest == DIGEST
    assert _final_contract_file_reference(row(values[1]), values) is None
    wrong_purpose = row(values[0])
    wrong_purpose["purpose"] = "signed_staff_agreement"
    assert _final_contract_file_reference(wrong_purpose, values) is None


def legacy_aggregate_facts():
    # Real pre-members shape: parent of Git commit 1d66ad44. It never recorded
    # per-target documents or an unsigned document version; do not fabricate one.
    value = member(CLIENT)
    snapshot = {
        "contract_identity": "legacy-aggregate",
        "document": {"applied_at": NOW.isoformat(), "case_no": CASE,
            "file_id": value.file_id, "filename": "aggregate.pdf", "final_document_id": "cfd_" + "e" * 32,
            "mime_type": "application/pdf", "size_bytes": 3, "status": "completed", "version": 7},
        "receipt_id": "cesr_" + "f" * 32, "resulting_state": "completed",
        "resulting_status_version": 4, "session_id": SESSION,
    }
    return {**row(value), "version_number": 2, "filename": "aggregate.pdf", "primary_final_version": 7,
        "receipt_id": snapshot["receipt_id"], "result_snapshot": snapshot,
        "final_document_id": snapshot["document"]["final_document_id"], "result_status_version": 4}


def test_original_aggregate_primary_receipt_is_read_without_fabricating_a_member_target():
    facts = legacy_aggregate_facts()
    class Owner(MySqlContractExternalSigningRepository):
        def _one(self, statement, parameters):
            assert parameters == (facts["opaque_object_id"],)
            return facts
        def _all(self, statement, parameters):
            assert parameters == (CASE,) and "AS primary_final_version" in statement
            return (facts,)
    class NoChildLookup:
        def get_committed_apply_evidence(self, _):
            pytest.fail("aggregate primary already has its own original root FK and hash")
    before = deepcopy(facts)
    reference = Owner(None).get_controlled_file_reference(facts["opaque_object_id"], apply_evidence_reader=NoChildLookup())
    assert reference.sha256_digest == DIGEST and reference.file_version == 2
    assert reference.target is None and reference.filename == "aggregate.pdf"
    assert reference.current and reference.completion_receipt_present
    assert facts == before and "documents" not in facts["result_snapshot"]


@pytest.mark.parametrize("field,value", [
    ("object_id", 2), ("owner_type", "staff"), ("purpose", "signed_staff_agreement"),
    ("subject_reference", "OTHER"), ("primary_content_sha256", "b" * 64),
    ("primary_size_bytes", 4), ("primary_final_version", 8), ("version_number", True),
    ("filename", "other.pdf"), ("content_type", "image/png"),
])
def test_original_aggregate_needs_exact_primary_owner_root_and_frozen_metadata(field, value):
    facts = legacy_aggregate_facts(); facts[field] = value
    assert _legacy_aggregate_final_reference(facts) is None


@pytest.mark.parametrize("field,value", [
    ("file_id", "cf_" + "9" * 32), ("version", True), ("version", 8),
    ("size_bytes", 4), ("filename", "other.pdf"), ("mime_type", "image/png"),
    ("status", "prepared"), ("applied_at", "2026-11-06T00:00:00"),
])
def test_original_aggregate_rejects_missing_or_changed_document_evidence(field, value):
    facts = legacy_aggregate_facts(); facts["result_snapshot"]["document"][field] = value
    assert _legacy_aggregate_final_reference(facts) is None


@pytest.mark.parametrize("documents", [[], None, {}, "malformed"])
def test_explicit_new_members_key_never_uses_aggregate_compatibility(documents):
    facts = legacy_aggregate_facts(); facts["result_snapshot"]["documents"] = documents
    assert _legacy_aggregate_final_reference(facts) is None


@pytest.mark.parametrize("test_only", [False, True])
def test_aggregate_completion_keeps_original_currentness_and_test_only_boundary(test_only):
    from infrastructure.db.controlled_file_repository import _contract_reference_status
    facts = legacy_aggregate_facts()
    if test_only:
        facts["filename"] = facts["result_snapshot"]["document"]["filename"] = "TEST-ONLY-aggregate.pdf"
    reference = _legacy_aggregate_final_reference(facts)
    readback = ControlledFileReadback(file_id=reference.file_id, owner=ControlledFileOwner.CONTRACT_SIGNING,
        purpose=ControlledFilePurpose.FINAL_SIGNED_CONTRACT, subject_reference=CASE,
        filename=reference.filename, logical_folder="contracts", version=2,
        sha256_digest=DIGEST, mime_type="application/pdf", size_bytes=3, status="registered", applied_at=NOW)
    status = _contract_reference_status(readback, reference)
    assert status["frozen_completion_reference"] == "matched"
    assert status["external_completion_reference"] == ("test_only" if test_only else "matched")
    facts["is_current"] = 0
    assert not _legacy_aggregate_final_reference(facts).current


@pytest.mark.parametrize("change", ["digest_only", "purpose_only", "invalid_hash", "wrong_purpose", "duplicate"])
def test_partial_or_malformed_member_evidence_is_rejected(change):
    snapshot = _final_receipt_snapshot(receipt((member(),)))
    value = snapshot["documents"][0]
    if change == "digest_only":
        value.pop("purpose")
    elif change == "purpose_only":
        value.pop("content_sha256")
    elif change == "invalid_hash":
        value["content_sha256"] = "not-a-hash"
    elif change == "wrong_purpose":
        value["purpose"] = "final_signed_contract"
    else:
        snapshot["documents"].append(deepcopy(value))
    with pytest.raises(ExternalSigningTypedError, match="final_contract_document_members_malformed"):
        _signed_document_members(snapshot)


def test_staff_freeze_uses_its_member_hash_and_never_borrows_primary_client_hash():
    value = member()
    facts = row(value)
    facts["primary_content_sha256"] = "b" * 64
    reference = _final_contract_file_reference(facts, (member(CLIENT), value))
    assert reference.file_id == value.file_id and reference.file_version == 1
    assert reference.sha256_digest == DIGEST and reference.purpose is value.purpose
    assert reference.target == STAFF and reference.completion_receipt_present
    assert not hasattr(reference, "outbound_delivered")
    # Return the independent owner hash, allowing the consumer to detect object drift.
    facts["content_sha256"] = "c" * 64
    assert _final_contract_file_reference(facts, (value,)).sha256_digest != facts["content_sha256"]


@pytest.mark.parametrize("field,value", [
    ("owner_type", "staff"), ("purpose", "final_signed_contract"),
    ("subject_reference", "OTHER"), ("case_no", "OTHER"),
    ("version_number", 2), ("size_bytes", 4), ("filename", "other.pdf"),
    ("content_type", "image/png"), ("object_key", "signed-contract:other:staff:11:v8"),
    ("external_signing_session_id", "other"), ("opaque_object_id", "cf_" + "f" * 32),
])
def test_member_reference_requires_the_exact_owner_target_and_registered_revision(field, value):
    source = member()
    facts = row(source)
    facts[field] = value
    assert _final_contract_file_reference(facts, (source,)) is None


def test_primary_document_digest_and_retired_currentness_are_not_ignored():
    value = member(CLIENT)
    facts = row(value)
    facts["primary_content_sha256"] = "b" * 64
    assert _final_contract_file_reference(facts, (value,)) is None
    facts = row(member())
    facts["is_current"] = 0
    assert not _final_contract_file_reference(facts, (member(),)).current


@pytest.mark.parametrize("field", [None, "receipt_id", "session_id", "case_no", "final_document_id", "resulting_state", "resulting_status_version"])
def test_member_json_must_belong_to_the_real_closed_receipt_and_final_document(field):
    value = receipt((member(CLIENT), member()))
    snapshot = _final_receipt_snapshot(value)
    facts = {"result_snapshot": snapshot, "receipt_id": value.receipt_id,
             "external_signing_session_id": SESSION, "case_no": CASE,
             "final_document_id": value.document.final_document_id, "result_status_version": 4}
    if field is None:
        assert _final_contract_reference_members(facts) == value.documents
        return
    if field in {"case_no", "final_document_id"}:
        snapshot["document"][field] = "other"
    else:
        snapshot[field] = "other"
    with pytest.raises(ExternalSigningTypedError, match="final_contract_document_members_lineage_invalid"):
        _final_contract_reference_members(facts)


def legacy_staff_evidence():
    value = member(STAFF, frozen=False)
    facts = row(value)
    facts.update(purpose="final_signed_contract", content_sha256="c" * 64,
        parent_idempotency_key="contract-final:legacy", parent_actor_ref="admin:7",
        parent_correlation_id="contract-final:legacy:correlation")
    readback = ControlledFileReadback(value.file_id, ControlledFileOwner.CONTRACT_SIGNING,
        ControlledFilePurpose.FINAL_SIGNED_CONTRACT, CASE, value.filename,
        "contract-signing/" + CASE, value.version, facts["content_sha256"], value.mime_type,
        value.size_bytes, "available", NOW)
    evidence = CommittedControlledFileApplyEvidence(
        ControlledFileApplyReceipt("cfr_" + "1" * 32, ControlledFileApplyOutcome.CREATED, readback),
        signed_contract_file_apply_key(IdempotencyKey(facts["parent_idempotency_key"]), STAFF),
        ActorContext(facts["parent_actor_ref"]), CorrelationId(facts["parent_correlation_id"]))
    return value, facts, evidence


class ApplyEvidenceReader:
    def __init__(self, evidence=None, error=None):
        self.evidence, self.error, self.reads = evidence, error, []
    def get_committed_apply_evidence(self, file_id):
        self.reads.append(file_id)
        if self.error is not None: raise self.error
        return self.evidence


def test_legacy_staff_uses_only_its_exact_original_apply_receipt_without_backfill_or_primary_hash():
    value, facts, evidence = legacy_staff_evidence()
    snapshot = _final_receipt_snapshot(receipt((member(CLIENT, frozen=False), value)))
    saved = deepcopy(snapshot)
    reader = ApplyEvidenceReader(evidence)
    proof = _read_legacy_member_apply_evidence(facts, (value,), reader)
    reference = _final_contract_file_reference(facts, (value,), apply_evidence=proof)
    assert reader.reads == [value.file_id]
    assert reference.sha256_digest == "c" * 64 != facts["primary_content_sha256"]
    assert reference.purpose is ControlledFilePurpose.FINAL_SIGNED_CONTRACT and reference.target == STAFF
    assert reference.file_version == value.version and reference.filename == value.filename
    assert reference.completion_receipt_present and reference.current
    assert value.sha256_digest is value.purpose is None and snapshot == saved


@pytest.mark.parametrize("field,value", [
    ("file_id", "cf_" + "f" * 32), ("version", 2), ("version", True),
    ("sha256_digest", "a" * 64), ("sha256_digest", "bad-hash"),
    ("owner", ControlledFileOwner.STAFF), ("purpose", ControlledFilePurpose.SIGNED_STAFF_AGREEMENT),
    ("subject_reference", "OTHER"), ("filename", "other.pdf"), ("mime_type", "image/png"),
    ("size_bytes", 4), ("size_bytes", True),
])
def test_legacy_bridge_rejects_any_mismatched_per_file_apply_fact(field, value):
    legacy, facts, evidence = legacy_staff_evidence()
    evidence = replace(evidence, receipt=replace(evidence.receipt,
        readback=replace(evidence.receipt.readback, **{field: value})))
    assert _final_contract_file_reference(facts, (legacy,), apply_evidence=evidence) is None


@pytest.mark.parametrize("field,value", [
    ("idempotency_key", IdempotencyKey("unrelated:file")),
    ("actor", ActorContext("admin:8")), ("correlation_id", CorrelationId("unrelated:correlation")),
])
def test_legacy_bridge_requires_original_parent_key_actor_and_correlation(field, value):
    legacy, facts, evidence = legacy_staff_evidence()
    assert _final_contract_file_reference(facts, (legacy,), apply_evidence=replace(evidence, **{field: value})) is None


@pytest.mark.parametrize("field", ["parent_idempotency_key", "parent_actor_ref", "parent_correlation_id"])
def test_legacy_bridge_missing_parent_provenance_stays_unknown_without_querying_an_apply_receipt(field):
    legacy, facts, evidence = legacy_staff_evidence()
    facts.pop(field)
    reader = ApplyEvidenceReader(evidence)
    assert _read_legacy_member_apply_evidence(facts, (legacy,), reader) is None and reader.reads == []
    assert _final_contract_file_reference(facts, (legacy,), apply_evidence=evidence) is None


@pytest.mark.parametrize("shape", ["new_member", "new_purpose_missing_metadata", "primary", "wrong_target"])
def test_bridge_never_downgrades_new_members_or_uses_unbound_files(shape):
    legacy, facts, evidence = legacy_staff_evidence()
    if shape == "new_member":
        legacy = member(STAFF)
        facts["purpose"] = legacy.purpose.value
    elif shape == "new_purpose_missing_metadata":
        facts["purpose"] = "signed_staff_agreement"
        evidence = replace(evidence, receipt=replace(evidence.receipt,
            readback=replace(evidence.receipt.readback, purpose=ControlledFilePurpose.SIGNED_STAFF_AGREEMENT)))
    elif shape == "primary":
        facts["primary_object_id"] = facts["object_id"]
        facts["primary_content_sha256"] = facts["content_sha256"]
    else:
        facts["object_key"] = "signed-contract:another:staff:11:v8"
    reader = ApplyEvidenceReader(evidence)
    assert _read_legacy_member_apply_evidence(facts, (legacy,), reader) is None and reader.reads == []
    if shape in {"new_purpose_missing_metadata", "wrong_target"}:
        assert _final_contract_file_reference(facts, (legacy,), apply_evidence=evidence) is None


def test_missing_own_receipt_stays_unknown_and_other_target_receipt_cannot_supply_a_hash():
    legacy, facts, evidence = legacy_staff_evidence()
    assert _final_contract_file_reference(facts, (legacy,), apply_evidence=None) is None
    borrowed = replace(evidence, idempotency_key=signed_contract_file_apply_key(
        IdempotencyKey(facts["parent_idempotency_key"]), CLIENT))
    assert _final_contract_file_reference(facts, (legacy,), apply_evidence=borrowed) is None


def test_corrupt_apply_receipt_becomes_typed_owner_fact_failure_for_existing_review_path():
    legacy, facts, _ = legacy_staff_evidence()
    reader = ApplyEvidenceReader(error=ControlledFileWorkflowError("controlled_file_receipt_corrupt", "invalid receipt"))
    with pytest.raises(ExternalSigningTypedError) as captured:
        _read_legacy_member_apply_evidence(facts, (legacy,), reader)
    assert captured.value.code == "final_contract_apply_receipt_invalid"
    assert captured.value.category == "conflict" and not captured.value.retryable


@pytest.mark.parametrize("kind", ["driver", "storage"])
def test_apply_evidence_transport_or_storage_errors_are_not_swallowed_as_empty_authority(kind):
    import pymysql
    legacy, facts, _ = legacy_staff_evidence()
    error = (pymysql.OperationalError(2006, "offline") if kind == "driver"
             else ControlledFileWorkflowError("controlled_file_storage_unavailable", "offline", retryable=True))
    reader = ApplyEvidenceReader(error=error)
    with pytest.raises(type(error)) as captured:
        _read_legacy_member_apply_evidence(facts, (legacy,), reader)
    assert captured.value is error


def test_derived_key_negative_oracle_detects_bypass_canary_and_is_restored(monkeypatch):
    from infrastructure.db import contract_external_signing_repository as module
    legacy, facts, evidence = legacy_staff_evidence()
    wrong = replace(evidence, idempotency_key=IdempotencyKey("unrelated:file"))
    assert module._final_contract_file_reference(facts, (legacy,), apply_evidence=wrong) is None
    with monkeypatch.context() as mutation:
        mutation.setattr(module, "_legacy_parent_file_identity", lambda *_: (
            wrong.idempotency_key, facts["parent_actor_ref"], facts["parent_correlation_id"]))
        # Deliberately bypassing the derivation makes the ordinary negative oracle fail.
        assert module._final_contract_file_reference(facts, (legacy,), apply_evidence=wrong) is not None
    assert module._final_contract_file_reference(facts, (legacy,), apply_evidence=wrong) is None
