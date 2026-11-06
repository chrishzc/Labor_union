"""Pure owner receipt/readback tests; no connection, cursor or SQL execution."""

from copy import deepcopy
from datetime import datetime, timezone

import pytest

from domains.contract_signing.external_signing import ExternalSigningState, SignedContractDocumentTarget
from subsystems.contract_signing.external_signing_contracts import ExternalSigningTypedError
from subsystems.contract_signing.final_document_workflow import (
    FinalContractDocumentReadback, FinalSignedContractApplyReceipt, SignedContractDocumentReadback,
    signed_contract_intent, signed_contract_object_key,
)
from subsystems.controlled_files.workflow import ControlledFilePurpose
from infrastructure.db.contract_external_signing_repository import (
    _final_contract_file_reference, _final_contract_reference_members,
    _final_receipt_snapshot, _signed_document_members,
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
