"""Apply one approved LIFF change request in a single caller-owned transaction."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, field
from typing import Any
from uuid import UUID

from domains.staff.case_preference_manual import RELATION_OPTIONS
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from subsystems.scheduling.staff_matching_preference_workflow import (
    PreferenceApplyRequest,
    StaffMatchingPreferenceWorkflow,
)
from subsystems.staff.bank_account_workflow import StaffBankAccountWorkflow
from subsystems.staff.case_preference_manual_workflow import (
    CasePreferenceManualApplyRequest,
    StaffCasePreferenceManualWorkflow,
)
from subsystems.staff.profile_workflow import StaffProfileMutationWorkflow
from subsystems.staff.qualification_editing_workflow import StaffQualificationEditingWorkflow


CONTACT_FIELDS = frozenset({
    "phone", "tel", "tel_ext", "email", "city", "zip_code", "address",
    "emergency_contact_name", "emergency_contact_phone",
})
RELATION_FIELDS = frozenset(RELATION_OPTIONS) - {"cooking_skills"}
MATCHING_FIELDS = frozenset({"preferred_service_days", "daily_service_hours"})


@dataclass(frozen=True, slots=True)
class VersionedChange:
    proposed: Mapping[str, Any] = field(repr=False)
    expected_version: ExpectedVersion
    preview: PreviewFingerprint


@dataclass(frozen=True, slots=True)
class SnapshotChange:
    proposed: Mapping[str, Any] = field(repr=False)
    expected_snapshot: PreviewFingerprint
    preview: PreviewFingerprint


@dataclass(frozen=True, slots=True)
class StaffProfileChange:
    staff_id: int
    profile: VersionedChange | None = None
    bank: VersionedChange | None = None
    relations: SnapshotChange | None = None
    transportation: SnapshotChange | None = None
    matching: VersionedChange | None = None


class StaffProfileChangeApproval:
    def __init__(
        self,
        unit_of_work_factory: Callable[[], Any],
        profile: StaffProfileMutationWorkflow,
        bank: StaffBankAccountWorkflow,
        relations: StaffCasePreferenceManualWorkflow,
        qualifications: StaffQualificationEditingWorkflow,
        matching: StaffMatchingPreferenceWorkflow,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._profile = profile
        self._bank = bank
        self._relations = relations
        self._qualifications = qualifications
        self._matching = matching

    def form(self, staff_id: int) -> dict[str, Any]:
        profile = self._profile.query(staff_id)
        bank = self._bank.query(staff_id)
        relations = self._relations.query(staff_id)
        qualification = self._qualifications.query(staff_id)
        matching = self._matching.query_profile(staff_id)
        primary = _primary(bank.accounts)
        return {
            "profile": {key: profile.values.get(key) for key in CONTACT_FIELDS},
            "bank": None if primary is None else {
                "bank_code": primary.bank_code, "branch_code": primary.branch_code,
                "account_last4": primary.account_no[-4:],
            },
            "relations": {key: [item.canonical_payload() for item in relations.relations[key]]
                          for key in RELATION_FIELDS},
            "relation_options": {key: RELATION_OPTIONS[key] for key in RELATION_FIELDS},
            "transportation": qualification["before"]["transportation"],
            "matching": {key: value for key, value in matching.after.items() if key in MATCHING_FIELDS},
            "basis": {
                "profile": profile.version, "bank": bank.version,
                "relations": relations.snapshot_fingerprint.value,
                "transportation": qualification["snapshot_fingerprint"],
                "matching": matching.version,
            },
        }

    def prepare(self, staff_id: int, proposed, basis):
        sections = {}
        review = {}
        if proposed.get("profile"):
            values = proposed["profile"]
            if not values.keys() <= CONTACT_FIELDS:
                raise ValueError("staff_profile_change_fields_invalid")
            version = ExpectedVersion(basis["profile"])
            preview = self._profile.preview(staff_id, values, version)
            if dict(preview.before) != dict(preview.after):
                sections["profile"] = VersionedChange(dict(preview.after), version, preview.preview_fingerprint)
                review["profile"] = {"before": dict(preview.before), "after": dict(preview.after)}
        if proposed.get("bank"):
            snapshot = self._bank.query(staff_id)
            primary = _primary(snapshot.accounts)
            if primary is None:
                raise ValueError("staff_profile_change_primary_required")
            version = ExpectedVersion(basis["bank"])
            values = {**proposed["bank"], "operation": "replace", "account_id": primary.account_id}
            preview = self._bank.preview(staff_id, values, version)
            sections["bank"] = VersionedChange(values, version, preview.preview_fingerprint)
            review["bank"] = {"before": preview.before, "after": preview.after}
        if proposed.get("relations"):
            edits = proposed["relations"]
            if not edits.keys() <= RELATION_FIELDS:
                raise ValueError("staff_profile_change_relations_invalid")
            snapshot = self._relations.query(staff_id)
            _require_basis(snapshot.snapshot_fingerprint.value, basis["relations"])
            values = {key: [item.canonical_payload() for item in rows]
                      for key, rows in snapshot.relations.items()}
            preview = self._relations.preview(staff_id, {**values, **edits})
            _require_basis(preview.snapshot_fingerprint.value, basis["relations"])
            after = {key: [item.canonical_payload() for item in rows] for key, rows in preview.after.items()}
            if values != after:
                sections["relations"] = SnapshotChange(after, preview.snapshot_fingerprint, preview.preview_fingerprint)
                review["relations"] = _diff(values, after, edits)
        if "transportation" in proposed:
            snapshot = self._qualifications.query(staff_id)
            _require_basis(snapshot["snapshot_fingerprint"], basis["transportation"])
            values = {**snapshot["before"], "transportation": proposed["transportation"]}
            preview = self._qualifications.preview(staff_id, values)
            _require_basis(preview["snapshot_fingerprint"], basis["transportation"])
            if preview["before"]["transportation"] != preview["after"]["transportation"]:
                sections["transportation"] = SnapshotChange(
                    preview["after"], PreviewFingerprint(preview["snapshot_fingerprint"]),
                    PreviewFingerprint(preview["preview_fingerprint"]),
                )
                review["transportation"] = _diff(preview["before"], preview["after"], {"transportation"})
        if proposed.get("matching"):
            edits = proposed["matching"]
            if not edits.keys() <= MATCHING_FIELDS:
                raise ValueError("staff_profile_change_matching_invalid")
            snapshot = self._matching.query_profile(staff_id)
            _require_basis(snapshot.version, basis["matching"])
            preview = self._matching.preview_profile(staff_id, {**snapshot.after, **edits})
            _require_basis(preview.version, basis["matching"])
            if preview.before != preview.after:
                sections["matching"] = VersionedChange(
                    dict(preview.after), ExpectedVersion(preview.version), preview.fingerprint,
                )
                review["matching"] = _diff(preview.before, preview.after, edits)
        if not sections:
            raise ValueError("staff_profile_change_empty")
        return {key: asdict(change) for key, change in sections.items()}, review

    def apply(
        self, change: StaffProfileChange, operation_id: UUID, actor: ActorContext, reason: str
    ) -> None:
        """Apply the staged owner previews and receipts, or roll all of them back."""
        profile, bank, relations, transportation, matching = (
            change.profile, change.bank, change.relations, change.transportation, change.matching
        )
        if all(section is None for section in (profile, bank, relations, transportation, matching)):
            raise ValueError("staff_profile_change_empty")
        if profile and not profile.proposed.keys() <= CONTACT_FIELDS:
            raise ValueError("staff_profile_change_fields_invalid")
        if bank and (
            bank.proposed.keys() != {"operation", "account_id", "bank_code", "branch_code", "account_no"}
            or bank.proposed["operation"] != "replace"
        ):
            raise ValueError("staff_profile_change_bank_replacement_required")
        operation = f"staff-profile-change:{operation_id}"
        correlation = CorrelationId(operation)
        with self._unit_of_work_factory() as unit_of_work:
            if profile:
                self._profile.apply_in_current_uow(
                    change.staff_id, profile.proposed, profile.expected_version, profile.preview,
                    IdempotencyKey(f"{operation}:profile"), actor, reason, correlation,
                )
            if bank:
                self._bank.apply_in_current_uow(
                    change.staff_id, bank.proposed, bank.expected_version, bank.preview,
                    IdempotencyKey(f"{operation}:bank"), actor, reason, correlation,
                )
            if relations:
                self._relations.apply_in_current_uow(
                    change.staff_id, relations.proposed, CasePreferenceManualApplyRequest(
                        relations.expected_snapshot, relations.preview,
                        IdempotencyKey(f"{operation}:relations"), actor, reason, correlation,
                    ),
                )
            if transportation:
                self._qualifications.apply_in_current_uow(
                    change.staff_id, transportation.proposed,
                    expected_snapshot=transportation.expected_snapshot.value,
                    preview=transportation.preview.value, key=f"{operation}:transportation",
                    actor=actor.actor_id, reason=reason, correlation=correlation.value,
                )
            if matching:
                self._matching.apply_profile_in_current_uow(
                    change.staff_id, matching.proposed, PreferenceApplyRequest(
                        matching.expected_version, matching.preview,
                        IdempotencyKey(f"{operation}:matching"), actor, reason, correlation,
                    ),
                )
            unit_of_work.commit()


def restore_staff_profile_change(staff_id: int, content: Mapping[str, Any]) -> StaffProfileChange:
    sections = {}
    for key, saved in content.items():
        preview = PreviewFingerprint(saved["preview"]["value"])
        if key in {"relations", "transportation"}:
            sections[key] = SnapshotChange(
                saved["proposed"], PreviewFingerprint(saved["expected_snapshot"]["value"]), preview,
            )
        else:
            sections[key] = VersionedChange(
                saved["proposed"], ExpectedVersion(saved["expected_version"]["value"]), preview,
            )
    return StaffProfileChange(staff_id, **sections)


def _primary(accounts):
    return next((account for account in accounts if account.is_primary and account.is_active), None)


def _require_basis(actual, expected):
    if actual != expected:
        raise StaffProfileChangeConflict("staff_profile_change_stale")


class StaffProfileChangeConflict(ValueError):
    pass


def _diff(before, after, keys):
    changed = [key for key in keys if before.get(key) != after.get(key)]
    return {"before": {key: before.get(key) for key in changed},
            "after": {key: after.get(key) for key in changed}}
