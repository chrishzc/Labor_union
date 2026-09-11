"""Owner-local contracts for Staff profile and bank-account mutations."""

from contextlib import AbstractContextManager
import inspect
import re

import pytest

from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from infrastructure.mysql.staff_bank_account_repository import MySqlStaffBankAccountRepository
from subsystems.staff.bank_account_workflow import StaffBankAccountConflict, StaffBankAccountWorkflow
from subsystems.staff.profile_workflow import StaffProfileMutationConflict, StaffProfileMutationWorkflow


class _Uow(AbstractContextManager):
    def __init__(self):
        self.commits = 0

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def commit(self):
        self.commits += 1


class _ProfileRepository:
    def __init__(self):
        self.row = {"staff_id": 7, "staff_profile_version": 0, "name": "王小美", "identity_card": "A223456789"}
        self.claims = {}
        self.receipts = {}

    def load(self, staff_id, *, for_update):
        return dict(self.row) if staff_id == 7 else None

    def claim(self, *, staff_id, key, command_fingerprint, correlation_id):
        previous = self.claims.setdefault(key.value, command_fingerprint.value)
        if previous != command_fingerprint.value:
            raise ValueError("idempotency_mismatch")

    def load_receipt(self, key, *, for_update):
        return self.receipts.get(key.value)

    def persist(self, *, snapshot, changes, **_):
        self.row.update(changes)
        self.row["staff_profile_version"] = snapshot.version + 1
        return snapshot.version + 1

    def save_receipt(self, *, key, command_fingerprint, result, **_):
        self.receipts[key.value] = {"request_fingerprint": command_fingerprint.value, "result": dict(result)}


class _BankRepository:
    def __init__(self):
        self.row = {
            "staff_id": 7,
            "aggregate_version": 0,
            "accounts": ({"id": 3, "bank_code": "812", "branch_code": "0012", "account_no": "123456789012", "is_primary": 1, "is_active": 1},),
        }
        self.receipts = {}
        self.claims = {}
        self.persist_count = 0

    def load(self, staff_id, *, for_update):
        return self.row if staff_id == 7 else None

    def account_owner(self, account_no, *, for_update):
        if account_no == "999999999999":
            return 44
        return next((item["id"] for item in self.row["accounts"] if item["account_no"] == account_no), None)

    def claim(self, *, key, command_fingerprint, **_):
        previous = self.claims.setdefault(key.value, command_fingerprint.value)
        if previous != command_fingerprint.value:
            raise ValueError("idempotency_mismatch")

    def load_receipt(self, key, *, for_update):
        return self.receipts.get(key.value)

    def persist(self, *, snapshot, command, candidate, **_):
        self.persist_count += 1
        account_id = 4 if command.operation == "add" else int(command.account_id)
        accounts = []
        for item in candidate.accounts:
            values = vars(item) if hasattr(item, "__dict__") else {name: getattr(item, name) for name in item.__slots__}
            values = dict(values)
            original_id = values.pop("account_id")
            values["id"] = account_id if original_id == 0 else original_id
            accounts.append(values)
        self.row = {"staff_id": 7, "aggregate_version": snapshot.version + 1, "accounts": tuple(accounts)}
        return account_id, snapshot.version + 1

    def save_receipt(self, *, key, command_fingerprint, result, **_):
        self.receipts[key.value] = {"request_fingerprint": command_fingerprint.value, "result": dict(result)}


def _identity():
    return ActorContext("admin:9", ("data_browser.write",)), CorrelationId("registry-corr-1")


def test_staff_profile_preview_apply_and_replay_are_versioned():
    repository = _ProfileRepository()
    workflow = StaffProfileMutationWorkflow(repository, _Uow)
    preview = workflow.preview(7, {"phone": " 0911222333 "}, ExpectedVersion(0))
    actor, correlation = _identity()
    receipt = workflow.apply(7, {"phone": "0911222333"}, ExpectedVersion(0), preview.preview_fingerprint, IdempotencyKey("staff-profile-1"), actor, "人工核對", correlation)
    assert receipt.resulting_version == 1
    assert receipt.readback.values["phone"] == "0911222333"
    replay = workflow.apply(7, {"phone": "0911222333"}, ExpectedVersion(0), preview.preview_fingerprint, IdempotencyKey("staff-profile-1"), actor, "人工核對", correlation)
    assert replay.replayed is True
    with pytest.raises(StaffProfileMutationConflict, match="stale_version"):
        workflow.preview(7, {"phone": "0911000000"}, ExpectedVersion(0))


def test_staff_bank_preview_never_exposes_full_account_and_collision_fails_closed():
    repository = _BankRepository()
    workflow = StaffBankAccountWorkflow(repository, _Uow)
    command = {"operation": "add", "bank_code": "004", "branch_code": "0001", "account_no": "987654321098"}
    preview = workflow.preview(7, command, ExpectedVersion(0))
    assert preview.after["account_last4"] == "1098"
    assert "987654321098" not in repr(preview)
    actor, correlation = _identity()
    receipt = workflow.apply(7, command, ExpectedVersion(0), preview.preview_fingerprint, IdempotencyKey("staff-bank-1"), actor, "新增備用帳戶", correlation)
    assert receipt.resulting_version == 1
    assert workflow.apply(7, command, ExpectedVersion(0), preview.preview_fingerprint, IdempotencyKey("staff-bank-1"), actor, "新增備用帳戶", correlation).replayed
    assert repository.persist_count == 1
    with pytest.raises(StaffBankAccountConflict, match="collision"):
        workflow.preview(7, {**command, "account_no": "999999999999"}, ExpectedVersion(1))


def test_staff_bank_replace_primary_switch_and_deactivation_are_supported():
    repository = _BankRepository()
    repository.row["accounts"] = (
        repository.row["accounts"][0],
        {
            "id": 4,
            "bank_code": "004",
            "branch_code": "0001",
            "account_no": "987654321098",
            "is_primary": 0,
            "is_active": 1,
        },
    )
    workflow = StaffBankAccountWorkflow(repository, _Uow)

    replacement = workflow.preview(
        7,
        {
            "operation": "replace",
            "account_id": 3,
            "bank_code": "822",
            "branch_code": "0022",
            "account_no": "111122223333",
        },
        ExpectedVersion(0),
    )
    primary_switch = workflow.preview(
        7,
        {"operation": "set_primary", "account_id": 4},
        ExpectedVersion(0),
    )
    deactivation = workflow.preview(
        7,
        {
            "operation": "deactivate",
            "account_id": 3,
            "successor_account_id": 4,
        },
        ExpectedVersion(0),
    )

    assert replacement.after == {
        "account_id": 3,
        "bank_code": "822",
        "branch_code": "0022",
        "account_last4": "3333",
        "is_primary": True,
        "is_active": True,
    }
    assert primary_switch.after["is_primary"] is True
    assert deactivation.after["is_active"] is False
    assert deactivation.after["is_primary"] is False


def test_staff_bank_readback_failure_keeps_committed_receipt_for_safe_replay():
    class _ReadbackFailureRepository(_BankRepository):
        fail_readback = True

        def load(self, staff_id, *, for_update):
            if self.fail_readback and not for_update and self.receipts:
                raise RuntimeError("readback_unavailable")
            return super().load(staff_id, for_update=for_update)

    repository = _ReadbackFailureRepository()
    unit_of_work = _Uow()
    workflow = StaffBankAccountWorkflow(repository, lambda: unit_of_work)
    command = {"operation": "add", "bank_code": "004", "branch_code": "0001", "account_no": "987654321098"}
    preview = workflow.preview(7, command, ExpectedVersion(0))
    actor, correlation = _identity()

    with pytest.raises(RuntimeError, match="readback_unavailable"):
        workflow.apply(7, command, ExpectedVersion(0), preview.preview_fingerprint, IdempotencyKey("staff-bank-readback"), actor, "新增備用帳戶", correlation)

    assert unit_of_work.commits == 1
    assert repository.persist_count == 1
    assert "staff-bank-readback" in repository.receipts
    repository.fail_readback = False
    replay = workflow.apply(7, command, ExpectedVersion(0), preview.preview_fingerprint, IdempotencyKey("staff-bank-readback"), actor, "新增備用帳戶", correlation)
    assert replay.replayed is True
    assert repository.persist_count == 1


def test_staff_bank_persistence_never_rewrites_payment_or_ledger_tables():
    source = inspect.getsource(MySqlStaffBankAccountRepository.persist)
    written_tables = {
        match.group(1)
        for match in re.finditer(
            r"(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+([a-z_]+)",
            source,
            re.IGNORECASE,
        )
    }

    assert written_tables == {
        "staff_bank_accounts",
        "staff_bank_account_events",
        "staff_bank_account_states",
    }
