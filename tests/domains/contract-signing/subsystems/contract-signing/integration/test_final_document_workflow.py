"""
File: test_final_document_workflow.py
Description: 驗證最終 PDF Preview、opaque token、單一交易、重播與 readback 門禁。
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, time, timedelta, timezone
import hashlib
from types import SimpleNamespace

import pytest

from domains.contract_signing.external_signing import (
    ExternalSigningSessionFacts,
    ExternalSigningState,
    StaffSigningReportTarget,
    SignedContractDocumentTarget,
    ExternalSigningRuleError,
)
from shared_kernel.clock import FixedBusinessClock
from shared_kernel.money import MoneyNTD
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import (
    ActorContext,
    CorrelationId,
    ExpectedVersion,
    IdempotencyKey,
)
from subsystems.contract_signing.final_document_preview_token import (
    HmacFinalDocumentPreviewTokenCodec,
)
from subsystems.contract_signing.final_document_workflow import (
    ApplyFinalSignedContractUpload,
    FinalContractDocumentReadback,
    FinalDocumentWorkflowError,
    FinalSignedContractWorkflow,
    PreviewFinalSignedContractUpload,
    SignedContractDocumentUpload,
    signed_contract_intent,
)
from subsystems.controlled_files.workflow import (
    ControlledFileApplyOutcome,
    ControlledFileApplyReceipt,
    ControlledFileCandidate,
    ControlledFileIntent,
    ControlledFileOwner,
    ControlledFilePreview,
    ControlledFilePurpose,
    ControlledFileReadback,
)
from domains.client_finance.obligation_planning import ClientChargeDay, ClientFinanceTermsFacts, ClientPaymentTerms
from domains.orders.contract_completion import ContractCompletionFacts
from domains.orders.lifecycle import OrderLifecycleStatus
from domains.orders.terms import ServiceTimeTerms
from subsystems.orders.contract_completion_workflow import (
    ContractCompletionWorkflow, ContractCompletionWorkflowFacts, ContractCompletionCommandClaimState,
)


NOW = datetime(2026, 8, 26, 12, tzinfo=timezone.utc)


def test_preview_is_zero_write_and_hides_internal_fingerprints() -> None:
    workflow, repository, controlled, orders, _ = _workflow()

    preview = workflow.preview(_preview_command())

    assert preview.preview_token.startswith("cp_")
    assert preview.blockers == ()
    assert all(row.mime_type == "application/pdf" for row in preview.documents)
    assert len(preview.documents) == 2
    assert repository.writes == []
    projection = repr(preview)
    assert "a" * 64 not in projection
    assert "b" * 64 not in projection
    assert controlled.applies == []
    assert orders.applies == []


@pytest.mark.parametrize(("testing_documents", "testing_confirmed"), [(True, False), (False, True)])
def test_test_documents_require_distinct_confirmation_before_business_writes(testing_documents, testing_confirmed):
    workflow, repository, controlled, orders, uows = _workflow()
    original = controlled.preview

    def preview_file(intent):
        preview = original(intent)
        return replace(preview, candidate=replace(preview.candidate, filename="TEST-ONLY-fixture.pdf")) if testing_documents else preview

    controlled.preview = preview_file
    preview = workflow.preview(_preview_command())
    with pytest.raises(FinalDocumentWorkflowError, match="final_contract_testing_confirmation_required"):
        workflow.apply(replace(_apply_command(preview.preview_token), testing_skip_confirmed=testing_confirmed))
    assert repository.writes == controlled.applies == orders.applies == []
    assert uows.instances[-1].commits == 0


def test_test_completion_uses_same_atomic_workflow_and_replays_only_same_mode():
    workflow, repository, controlled, orders, uows = _workflow()
    original = controlled.preview
    def preview_file(intent):
        value = original(intent)
        return replace(value, candidate=replace(value.candidate, filename="TEST-ONLY-fixture.pdf"))

    controlled.preview = preview_file
    preview = workflow.preview(_preview_command())
    command = replace(_apply_command(preview.preview_token), testing_skip_confirmed=True, reason="testing skip; no real signatures")
    first = workflow.apply(command)
    second = workflow.apply(command)
    assert first.resulting_state is ExternalSigningState.COMPLETED
    assert second.replayed
    assert len(controlled.applies) == 2 and len(orders.applies) == 1
    assert all(uow.commits == 1 for uow in uows.instances)
    assert orders.applies[0].reason == command.reason
    with pytest.raises(FinalDocumentWorkflowError):
        workflow.apply(replace(command, testing_skip_confirmed=False))


def test_testing_skip_recovers_files_for_existing_completed_order_without_repeating_business_completion():
    workflow, repository, controlled, orders, uows = _workflow()
    orders.completed = True
    orders.identity = "client-contract:existing"
    original = controlled.preview
    controlled.preview = lambda intent: replace(original(intent), candidate=replace(
        original(intent).candidate, filename="TEST-ONLY-fixture.pdf"))
    preview = workflow.preview(_preview_command())
    assert preview.blockers == ()
    command = replace(_apply_command(preview.preview_token), testing_skip_confirmed=True)
    receipt = workflow.apply(command)
    replay = workflow.apply(command)
    assert receipt.resulting_state is ExternalSigningState.COMPLETED
    assert receipt.contract_identity == orders.identity
    assert replay.replayed
    assert len(controlled.applies) == 2
    assert orders.applies == []
    assert "orders:preview" not in repository.events
    assert "prerequisites:apply" not in repository.events
    assert "orders:query:lock" in repository.events
    assert "prerequisites:existing:lock" in repository.events
    assert repository.writes == ["document", "session", "receipt"]
    assert [uow.commits for uow in uows.instances] == [1, 1]


@pytest.mark.parametrize("case_no", ["GENERIC-SIGNING-A", "GENERIC-SIGNING-B"])
@pytest.mark.parametrize("signing_state", ["new", "identity_recorded", "completed"])
def test_testing_skip_completes_different_cases_with_real_orders_workflow(case_no, signing_state):
    workflow, repository, controlled, _, uows = _workflow()
    identity = None if signing_state == "new" else "client-contract:original"
    owner = _CompletionRepository(ContractCompletionWorkflowFacts(
        ContractCompletionFacts(case_no, 7, identity, signing_state == "completed",
            OrderLifecycleStatus.DISCUSSION, False, ServiceTimeTerms(time(8), time(16), 0)),
        ClientFinanceTermsFacts(case_no, 4, 8, MoneyNTD(0), (ClientChargeDay(NOW.date(), False),),
            ClientPaymentTerms(0, MoneyNTD(100), NOW.date(), NOW.date(), None), ()),
        1,
    ))
    workflow._contract_completion = ContractCompletionWorkflow(owner, FakeUow, FixedBusinessClock(NOW))
    workflow._prerequisites.case_no = case_no
    repository.session = replace(repository.session, case_no=case_no)
    original = controlled.preview
    controlled.preview = lambda intent: replace(original(intent), candidate=replace(
        original(intent).candidate, filename="TEST-ONLY-fixture.pdf"))
    request = _preview_command(case_no)
    preview = workflow.preview(request)
    assert preview.blockers == ()
    assert owner.completion_events == []
    command = replace(_apply_command(preview.preview_token), preview=request,
        testing_skip_confirmed=True, idempotency_key=IdempotencyKey("test-final:" + case_no))
    receipt = workflow.apply(command)
    replay = workflow.apply(command)
    assert receipt.resulting_state is ExternalSigningState.COMPLETED
    assert replay.replayed
    assert receipt.contract_identity == (identity or owner.facts.order.contract_identity)
    assert owner.facts.order.contract_completed
    assert len(controlled.applies) == 2
    assert owner.lock_reads > 0
    expected_writes = 0 if signing_state == "completed" else 1
    assert len(owner.completion_events) == len(owner.finance_commands) == expected_writes
    assert [unit.commits for unit in uows.instances] == [1, 1]


class _CompletionRepository:
    """Typed owner storage double; candidate, version and identity checks stay real."""
    def __init__(self, facts):
        self.facts, self.receipt = facts, None
        self.completion_events, self.finance_commands = [], []
        self.lock_reads = 0

    def load_for_preview(self, case_no):
        assert case_no == self.facts.order.case_no
        return self.facts

    def load_for_apply(self, case_no):
        self.lock_reads += 1
        return self.load_for_preview(case_no)

    def record_contract_identity(self, case_no, identity):
        current = self.load_for_preview(case_no).order.contract_identity
        if current is not None and current != identity:
            raise ValueError("contract_identity_already_recorded")
        self.facts = replace(self.facts, order=replace(self.facts.order, contract_identity=identity))

    def claim_command(self, *_):
        return ContractCompletionCommandClaimState.CREATED

    def find_receipt(self, *_args, **_kwargs):
        return self.receipt

    def append_contract_completion_event(self, request, preview):
        self.completion_events.append(preview)
        self.facts = replace(self.facts, order=replace(self.facts.order, contract_completed=True))
        return 1

    def persist_client_finance_impact(self, command):
        self.finance_commands.append(command)

    def append_lifecycle_event(self, *_):
        return 1

    def update_order_projection(self, command):
        self.facts = replace(self.facts, order=replace(self.facts.order,
            aggregate_version=command.resulting_order_version, lifecycle_status=command.lifecycle_status))

    def append_outbox_intent(self, *_):
        pass

    def save_receipt(self, command):
        self.receipt = command.stored_receipt


def test_existing_completion_cannot_be_reused_for_real_signature_documents():
    workflow, repository, controlled, orders, _ = _workflow()
    orders.completed = True
    orders.identity = "client-contract:existing"
    with pytest.raises(ValueError, match="contract_identity_already_recorded"):
        workflow.preview(_preview_command())
    assert repository.writes == controlled.applies == orders.applies == []


def test_testing_recovery_requires_the_original_commitment_for_the_current_plan():
    workflow, repository, controlled, orders, _ = _workflow()
    orders.completed = True
    orders.identity = "client-contract:existing"
    original = controlled.preview
    controlled.preview = lambda intent: replace(original(intent), candidate=replace(
        original(intent).candidate, filename="TEST-ONLY-fixture.pdf"))
    workflow._prerequisites.existing_commitment = lambda *args, **kwargs: None
    with pytest.raises(FinalDocumentWorkflowError, match="contract_testing_completed_commitment_missing"):
        workflow.preview(_preview_command())
    assert repository.writes == controlled.applies == orders.applies == []


@pytest.mark.parametrize("change", ["order_version", "identity"])
def test_existing_completed_order_change_invalidates_testing_file_preview(change):
    workflow, repository, controlled, orders, uows = _workflow()
    orders.completed = True
    orders.identity = "client-contract:existing"
    original = controlled.preview
    controlled.preview = lambda intent: replace(original(intent), candidate=replace(
        original(intent).candidate, filename="TEST-ONLY-fixture.pdf"))
    preview = workflow.preview(_preview_command())
    if change == "order_version":
        orders.order_version += 1
    else:
        orders.identity = "client-contract:changed"
    with pytest.raises(FinalDocumentWorkflowError, match="final_document_preview_stale"):
        workflow.apply(replace(_apply_command(preview.preview_token), testing_skip_confirmed=True))
    assert repository.writes == controlled.applies == orders.applies == []
    assert uows.instances[-1].commits == 0


def test_apply_uses_one_outer_uow_and_required_lock_order() -> None:
    workflow, repository, controlled, orders, uows = _workflow()
    preview = workflow.preview(_preview_command())
    repository.events.clear()

    receipt = workflow.apply(_apply_command(preview.preview_token))

    assert receipt.resulting_state is ExternalSigningState.COMPLETED
    assert receipt.document.file_id == "cf_" + "c" * 32
    assert uows.instances[0].commits == 1
    assert repository.events == [
        "session:lock",
        "file:preview",
        "file:preview",
        "prerequisites:preview",
        "orders:preview",
        "prerequisites:apply",
        "prerequisites:preview",
        "orders:preview",
        "orders:apply",
        "file:apply",
        "file:apply",
        "final:register",
        "session:complete",
        "receipt:save",
    ]
    assert len(controlled.applies) == 2
    assert {member.target.key for member in receipt.documents} == {"client", "staff:11"}
    assert len(orders.applies) == 1
    assert orders.applies[0].expected_client_finance_version.value == 5


def test_stale_token_rolls_back_before_domain_writes() -> None:
    workflow, repository, controlled, orders, uows = _workflow()
    preview = workflow.preview(_preview_command())
    controlled.digest = "d" * 64
    repository.writes.clear()

    with pytest.raises(FinalDocumentWorkflowError) as captured:
        workflow.apply(_apply_command(preview.preview_token))

    assert captured.value.code == "final_document_preview_stale"
    assert repository.writes == []
    assert controlled.applies == []
    assert orders.applies == []
    assert uows.instances[0].commits == 0


def test_new_occupancy_after_document_preview_blocks_signing_apply_without_partial_writes():
    workflow, repository, controlled, orders, uows = _workflow()
    preview = workflow.preview(_preview_command())
    workflow._prerequisites.signing_blockers = lambda *args, **kwargs: ("signing_staff_occupancy_conflict",)
    with pytest.raises(FinalDocumentWorkflowError, match="signing_staff_occupancy_conflict"):
        workflow.apply(_apply_command(preview.preview_token))
    assert repository.writes == controlled.applies == orders.applies == []
    assert uows.instances[-1].commits == 0
    assert uows.instances[0].rollbacks == 1


def test_two_staff_segments_require_three_separate_files_and_complete_once():
    workflow, repository, controlled, orders, uows = _workflow()
    repository.session = replace(repository.session, staff_targets=(
        *repository.session.staff_targets, StaffSigningReportTarget(12, "502", 102),
    ))
    command = _preview_command()
    with pytest.raises(ExternalSigningRuleError):
        workflow.preview(command)
    assert repository.writes == controlled.applies == orders.applies == []
    target = SignedContractDocumentTarget("staff", 12, 102)
    command = replace(command, documents=(*command.documents, SignedContractDocumentUpload(
        target, signed_contract_intent(command.case_no, command.session_id, target, "cfs_" + "4" * 32), ExpectedVersion(2),
    )))
    preview = workflow.preview(command)
    receipt = workflow.apply(replace(_apply_command(preview.preview_token), preview=command))
    assert {member.target.key for member in receipt.documents} == {"client", "staff:11", "staff:12"}
    assert len({member.file_id for member in receipt.documents}) == 3
    assert len({applied.idempotency_key.value for applied in controlled.applies}) == 3
    assert len(orders.applies) == 1
    assert uows.instances[0].commits == 1
    assert uows.instances[0].rollbacks == 0


def test_same_command_replays_without_second_final_write() -> None:
    workflow, repository, controlled, orders, _ = _workflow()
    preview = workflow.preview(_preview_command())
    command = _apply_command(preview.preview_token)
    first = workflow.apply(command)
    repository.writes.clear()
    controlled.applies.clear()
    orders.applies.clear()

    replay = workflow.apply(command)

    assert replay.receipt_id == first.receipt_id
    assert replay.replayed is True
    assert repository.writes == []
    assert controlled.applies == []
    assert orders.applies == []


def test_readback_is_safe_and_missing_is_typed() -> None:
    workflow, repository, _, _, _ = _workflow()

    with pytest.raises(FinalDocumentWorkflowError) as captured:
        workflow.readback("CASE-001")
    repository.document = _document()

    assert captured.value.category == "not_found"
    assert workflow.readback("CASE-001") == _document()
    assert "sha256" not in repr(workflow.readback("CASE-001")).casefold()


class FakeRepository:
    def __init__(self, events) -> None:
        self.events = events
        self.writes = []
        self.receipts = {}
        self.document = None
        self.session = _session()

    def load_final_session(self, case_no, session_id, *, for_update):
        self.events.append("session:lock" if for_update else "session:read")
        facts = self.session
        return facts if (case_no, session_id) == (facts.case_no, facts.session_id) else None

    def find_final_receipt(self, key, *, for_update):
        return self.receipts.get(key.value)

    def register_final_document(self, session, controlled_file, **_):
        self.events.append("final:register")
        self.writes.append("document")
        self.document = replace(_document(), case_no=session.case_no)
        return self.document

    def complete_session_and_recovery(self, *_args, **_kwargs):
        self.events.append("session:complete")
        self.writes.append("session")

    def save_final_receipt(self, key, stored, *_args, **_kwargs):
        self.events.append("receipt:save")
        self.writes.append("receipt")
        self.receipts[key.value] = stored

    def get_final_document(self, case_no):
        return self.document if case_no == "CASE-001" else None


class FakeControlledFiles:
    def __init__(self, events) -> None:
        self.events = events
        self.applies = []
        self.digest = "b" * 64

    def preview(self, intent):
        self.events.append("file:preview")
        candidate = ControlledFileCandidate(
            staging_id=intent.staging_id,
            staging_version=2,
            owner=intent.owner,
            purpose=intent.purpose,
            subject_reference=intent.subject_reference,
            object_key=intent.object_key,
            logical_folder=intent.logical_folder,
            filename="final-contract.pdf",
            mime_type="application/pdf",
            size_bytes=1024,
            sha256_digest=self.digest,
            expires_at=NOW + timedelta(hours=1),
        )
        return ControlledFilePreview(
            candidate,
            PreviewFingerprint(self.digest),
            ExpectedVersion(2),
            (),
        )

    def apply_borrowed(self, command):
        self.events.append("file:apply")
        self.applies.append(command)
        readback = ControlledFileReadback(
            file_id="cf_" + ("c" * 32 if ":client:" in command.intent.object_key else hashlib.sha256(command.intent.object_key.encode()).hexdigest()[:32]),
            owner=ControlledFileOwner.CONTRACT_SIGNING,
            purpose=ControlledFilePurpose.FINAL_SIGNED_CONTRACT,
            subject_reference=command.intent.subject_reference,
            filename="final-contract.pdf",
            logical_folder="contracts",
            version=1,
            sha256_digest=self.digest,
            mime_type="application/pdf",
            size_bytes=1024,
            status="active",
            applied_at=NOW,
        )
        return ControlledFileApplyReceipt(
            "cfr_" + "d" * 32, ControlledFileApplyOutcome.CREATED, readback
        )


class FakeOrders:
    def __init__(self, events) -> None:
        self.events = events
        self.applies = []
        self.completed = False
        self.identity = None
        self.order_version = 7

    def query(self, case_no, *, for_update=False):
        self.events.append("orders:query:lock" if for_update else "orders:query:read")
        assert case_no == "CASE-001"
        return SimpleNamespace(facts=SimpleNamespace(contract_completed=self.completed,
            contract_identity=self.identity, aggregate_version=self.order_version))

    def preview_with_identity(
        self, case_no, _intent, contract_identity, *, fallback_service_dates
    ):
        self.events.append("orders:preview")
        if self.completed:
            raise ValueError("contract_identity_already_recorded")
        assert contract_identity in {self.identity, None} or contract_identity.startswith("external-final-set:")
        assert fallback_service_dates == (NOW.date(),)
        account_version = 5 if "prerequisites:apply" in self.events else 4
        return SimpleNamespace(
            candidate=SimpleNamespace(expected_order_version=7, contract_identity=contract_identity),
            client_finance_impact=SimpleNamespace(expected_account_version=account_version),
            fingerprint=PreviewFingerprint("e" * 64),
        )

    def apply_borrowed_with_identity(self, command, contract_identity):
        self.events.append("orders:apply")
        self.applies.append(command)
        return SimpleNamespace(contract_identity=contract_identity)


class FakePrerequisites:
    def signing_blockers(self, facts, *, for_update=False):
        return ()

    def __init__(self, events) -> None:
        self.events = events
        self.case_no = "CASE-001"

    def existing_commitment(self, facts, *, for_update):
        self.events.append("prerequisites:existing:lock" if for_update else "prerequisites:existing:read")
        assert facts.case_no == self.case_no
        return 44

    def preview_service_dates(self, facts):
        self.events.append("prerequisites:preview")
        assert facts.case_no == self.case_no
        return (NOW.date(),)

    def establish_prerequisites(self, command, facts, resulting_status_version):
        self.events.append("prerequisites:apply")
        assert command.case_no == facts.case_no
        assert command.matching_plan_id == facts.matching_plan_id
        assert resulting_status_version == facts.status_version + 1
        return SimpleNamespace(commitment_id=44)


class FakeUow:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    def __enter__(self):
        return self

    def __exit__(self, error_type, *_):
        if error_type is not None:
            self.rollbacks += 1
        return False

    def commit(self):
        self.commits += 1


class FakeUowFactory:
    def __init__(self) -> None:
        self.instances = []

    def __call__(self):
        unit = FakeUow()
        self.instances.append(unit)
        return unit


def _workflow():
    events = []
    repository = FakeRepository(events)
    controlled = FakeControlledFiles(events)
    orders = FakeOrders(events)
    uows = FakeUowFactory()
    workflow = FinalSignedContractWorkflow(
        repository,
        controlled,
        orders,
        FakePrerequisites(events),
        uows,
        FixedBusinessClock(NOW),
        HmacFinalDocumentPreviewTokenCodec("s" * 32),
    )
    return workflow, repository, controlled, orders, uows


def _session():
    return ExternalSigningSessionFacts(
        session_id="ces_" + "1" * 32,
        case_no="CASE-001",
        matching_plan_id=9,
        document_set_fingerprint="a" * 64,
        staff_targets=(StaffSigningReportTarget(11, "501", 101),),
        reported_staff_segment_ids=(),
        client_subject_reference="301",
        client_document_version_id=201,
        commitment_id=None,
        client_reported=False,
        state=ExternalSigningState.STAFF_REPORTING,
        status_version=1,
    )


def _preview_command(case_no="CASE-001"):
    session = replace(_session(), case_no=case_no)
    targets = (SignedContractDocumentTarget("client", None, 201), SignedContractDocumentTarget("staff", 11, 101))
    return PreviewFinalSignedContractUpload(
        session.session_id, session.case_no, ExpectedVersion(1),
        tuple(SignedContractDocumentUpload(target, signed_contract_intent(
            session.case_no, session.session_id, target, "cfs_" + str(index + 2) * 32
        ), ExpectedVersion(2)) for index, target in enumerate(targets)),
    )


def _apply_command(token):
    return ApplyFinalSignedContractUpload(
        preview=_preview_command(),
        preview_token=token,
        idempotency_key=IdempotencyKey("contract-final:case-001"),
        actor=ActorContext("admin:1"),
        reason="verified final signed PDF",
        correlation_id=CorrelationId("corr-final-001"),
    )


def _document():
    return FinalContractDocumentReadback(
        final_document_id="cfd_" + "3" * 32,
        case_no="CASE-001",
        file_id="cf_" + "c" * 32,
        version=1,
        filename="final-contract.pdf",
        mime_type="application/pdf",
        size_bytes=1024,
        status="active",
        applied_at=NOW,
    )


@pytest.mark.parametrize("documents", [(), _preview_command().documents[:1], (_preview_command().documents[0], _preview_command().documents[0])])
def test_incomplete_or_duplicate_documents_cannot_complete_contract(documents):
    workflow, repository, controlled, orders, _ = _workflow()
    with pytest.raises(ExternalSigningRuleError):
        workflow.preview(replace(_preview_command(), documents=documents))
    assert repository.writes == []
    assert controlled.applies == []
    assert orders.applies == []


def test_file_from_other_target_or_unsigned_version_is_rejected_before_any_write():
    workflow, repository, controlled, orders, _ = _workflow()
    command = _preview_command()
    staff = command.documents[1]
    wrong = replace(staff, target=replace(staff.target, document_version_id=999))
    with pytest.raises(ExternalSigningRuleError) as captured:
        workflow.preview(replace(command, documents=(command.documents[0], wrong)))
    assert captured.value.code.value == "external_staff_report_document_stale"
    wrong = replace(staff, controlled_file_intent=command.documents[0].controlled_file_intent)
    with pytest.raises(FinalDocumentWorkflowError):
        workflow.preview(replace(command, documents=(command.documents[0], wrong)))
    assert repository.writes == controlled.applies == orders.applies == []


def test_any_member_staging_change_invalidates_whole_confirmed_preview():
    workflow, repository, controlled, orders, uows = _workflow()
    preview = workflow.preview(_preview_command())
    original = controlled.preview
    def changed(intent):
        result = original(intent)
        if "staff:" in intent.object_key:
            return replace(result, candidate=replace(result.candidate, sha256_digest="f" * 64))
        return result
    controlled.preview = changed
    with pytest.raises(FinalDocumentWorkflowError) as captured:
        workflow.apply(_apply_command(preview.preview_token))
    assert captured.value.code == "final_document_preview_stale"
    assert repository.writes == controlled.applies == orders.applies == []
    assert uows.instances[0].commits == 0
