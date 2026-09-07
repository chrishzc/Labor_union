"""
File: test_provisional_pairing.py
Description: 驗證未綁定訂單與狀態 C 產婦候選查詢、手動撮合與單一 UoW 交易約束。
"""

from __future__ import annotations

from datetime import datetime, timezone
import pytest

from domains.line.identities import LineUserId
from domains.line.identity_binding import (
    LineBindingSubjectType,
    LineIdentityBindingSnapshot,
    LineIdentityBindingStatus,
)
from shared_kernel.identities import (
    ActorContext,
    CorrelationId,
    ExpectedVersion,
    IdempotencyKey,
)
from subsystems.line.capabilities import LineCapability
from subsystems.line.identity_management_application import (
    LineIdentityManagementApplication,
)
from subsystems.line.identity_management_contracts import (
    PairProvisionalRegistrationCommand,
    UnboundOrderCandidate,
    UnboundProvisionalCandidate,
    UnboundPairingCandidatesView,
)


class _MockIdentities:
    def __init__(self) -> None:
        self.bindings: dict[str, LineIdentityBindingSnapshot] = {}
        self.bound_calls = []

    def get(self, line_user_id: LineUserId, subject_type=None):
        return self.bindings.get(f"{line_user_id.value}:{subject_type.value if subject_type else ''}")

    def save_claim(self, claim, version: ExpectedVersion):
        snapshot = LineIdentityBindingSnapshot(
            claim.line_user_id,
            LineIdentityBindingStatus.PENDING_REVIEW,
            ExpectedVersion(version.value + 1),
            claim.subject_type,
            claim.subject_reference,
        )
        self.bindings[f"{claim.line_user_id.value}:{claim.subject_type.value}"] = snapshot
        return snapshot

    def bind(self, claim, expected_version, actor_id, idempotency_key, correlation_id):
        snapshot = LineIdentityBindingSnapshot(
            claim.line_user_id,
            LineIdentityBindingStatus.BOUND,
            ExpectedVersion(expected_version.value + 1),
            claim.subject_type,
            claim.subject_reference,
        )
        self.bindings[f"{claim.line_user_id.value}:{claim.subject_type.value}"] = snapshot
        self.bound_calls.append((claim, expected_version, actor_id))
        return snapshot

    def list_by_user(self, line_user_id: LineUserId):
        return tuple(
            b for b in self.bindings.values() if b.line_user_id == line_user_id
        )

    def selected_role(self, line_user_id: LineUserId):
        return None, ExpectedVersion(0)


class _MockCustomers:
    def __init__(self) -> None:
        self.bound_customers = []

    def bind_customer(self, subject_reference, line_user_id, expected_current_line_user_id):
        self.bound_customers.append((subject_reference, line_user_id, expected_current_line_user_id))


class _MockIdentityManagementRepo:
    def __init__(self) -> None:
        self.orders = {
            "115000008": {
                "case_no": "115000008",
                "client_id": 6,
                "client_name": "王小明",
                "client_phone": "0988776655",
                "client_line_user_id": None,
                "status": "洽談中",
            }
        }
        self.provisionals = {
            1: {
                "id": 1,
                "line_user_id": "U1234567890abcdef",
                "active_line_user_id": "U1234567890abcdef",
                "status": "submitted",
                "client_id": None,
                "beclass_record_id": 10,
                "name": "王小明",
                "phone": "0988776655",
            }
        }
        self.consumed = []

    def list_unbound_pairing_candidates(self) -> UnboundPairingCandidatesView:
        orders = tuple(
            UnboundOrderCandidate(
                case_no=o["case_no"],
                client_id=o["client_id"],
                client_name=o["client_name"],
                client_phone=o["client_phone"],
                start_date=None,
                status=o["status"],
            )
            for o in self.orders.values()
            if not o.get("client_line_user_id")
        )
        provisional = tuple(
            UnboundProvisionalCandidate(
                registration_id=p["id"],
                name=p["name"],
                phone=p["phone"],
                line_user_id=p["line_user_id"],
                client_id=p["client_id"],
                submitted_at=None,
            )
            for p in self.provisionals.values()
            if p["status"] == "submitted"
        )
        return UnboundPairingCandidatesView(orders, provisional)

    def get_order_by_case_no(self, case_no: str) -> dict | None:
        return self.orders.get(case_no)

    def get_provisional_registration(self, registration_id: int) -> dict | None:
        return self.provisionals.get(registration_id)

    def consume_provisional_registration(
        self,
        registration_id: int,
        case_no: str,
        client_id: int,
        beclass_record_id: int | None,
    ) -> None:
        self.consumed.append((registration_id, case_no, client_id, beclass_record_id))
        if registration_id in self.provisionals:
            self.provisionals[registration_id]["status"] = "case_issued"
            self.provisionals[registration_id]["active_line_user_id"] = None
            self.provisionals[registration_id]["client_id"] = client_id


class _MockUnitOfWork:
    def __init__(self, repo: _MockIdentityManagementRepo, identities: _MockIdentities, customers: _MockCustomers) -> None:
        self.identity_management = repo
        self.identities = identities
        self.customers = customers
        self.audit = []
        self.outbox = []
        self.rich_menu_publications = self
        self.configurations = self
        self.order_audiences = self
        self.receipts = self
        self.commits = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def commit(self) -> None:
        self.commits += 1

    def append(self, item) -> None:
        pass

    def get(self, key):
        return None

    def default_publication(self, target):
        return None

    def list_publications_by_state(self, state):
        return ()

    def get_current(self, scope):
        return None

    def resolve_audience(self, line_user_id):
        return None


def _make_app(repo, identities, customers):
    uow = _MockUnitOfWork(repo, identities, customers)
    return LineIdentityManagementApplication(
        lambda: uow,
        lambda: datetime(2026, 9, 7, tzinfo=timezone.utc),
    ), uow


def test_unbound_pairing_candidates_listing() -> None:
    repo = _MockIdentityManagementRepo()
    identities = _MockIdentities()
    customers = _MockCustomers()
    app, _ = _make_app(repo, identities, customers)

    view = app.unbound_pairing_candidates()
    assert len(view.orders) == 1
    assert view.orders[0].case_no == "115000008"
    assert len(view.provisional_registrations) == 1
    assert view.provisional_registrations[0].registration_id == 1


def test_pair_provisional_registration_success() -> None:
    repo = _MockIdentityManagementRepo()
    identities = _MockIdentities()
    customers = _MockCustomers()
    app, uow = _make_app(repo, identities, customers)

    actor = ActorContext(
        "admin:manager",
        (LineCapability.IDENTITY_BINDING_MANAGE.value,),
    )
    command = PairProvisionalRegistrationCommand(
        provisional_registration_id=1,
        target_case_no="115000008",
        actor=actor,
        reason="專員手動配對狀態 C 產婦與訂單",
        idempotency_key=IdempotencyKey("test-pair-key-1"),
        correlation_id=CorrelationId("test-pair-corr-1"),
    )

    result = app.pair_provisional_registration(command)

    assert result["case_no"] == "115000008"
    assert result["client_id"] == 6
    assert result["status"] == "bound"
    assert result["line_user_id"] == "U1234567890abcdef"

    # Verify client table bound
    assert len(customers.bound_customers) == 1
    assert customers.bound_customers[0][0] == "6"
    assert customers.bound_customers[0][1].value == "U1234567890abcdef"

    # Verify provisional consumed
    assert len(repo.consumed) == 1
    assert repo.consumed[0] == (1, "115000008", 6, 10)
    assert repo.provisionals[1]["status"] == "case_issued"

    # Verify committed
    assert uow.commits == 1


def test_pair_provisional_registration_order_not_found() -> None:
    repo = _MockIdentityManagementRepo()
    identities = _MockIdentities()
    customers = _MockCustomers()
    app, _ = _make_app(repo, identities, customers)

    actor = ActorContext(
        "admin:manager",
        (LineCapability.IDENTITY_BINDING_MANAGE.value,),
    )
    command = PairProvisionalRegistrationCommand(
        provisional_registration_id=1,
        target_case_no="NON_EXISTENT",
        actor=actor,
        reason="測試不存在案號",
        idempotency_key=IdempotencyKey("test-pair-key-2"),
        correlation_id=CorrelationId("test-pair-corr-2"),
    )

    with pytest.raises(LookupError, match="line_unbound_order_not_found"):
        app.pair_provisional_registration(command)


def test_pair_provisional_registration_provisional_not_found() -> None:
    repo = _MockIdentityManagementRepo()
    identities = _MockIdentities()
    customers = _MockCustomers()
    app, _ = _make_app(repo, identities, customers)

    actor = ActorContext(
        "admin:manager",
        (LineCapability.IDENTITY_BINDING_MANAGE.value,),
    )
    command = PairProvisionalRegistrationCommand(
        provisional_registration_id=999,
        target_case_no="115000008",
        actor=actor,
        reason="測試不存在登記",
        idempotency_key=IdempotencyKey("test-pair-key-3"),
        correlation_id=CorrelationId("test-pair-corr-3"),
    )

    with pytest.raises(LookupError, match="line_provisional_registration_not_found"):
        app.pair_provisional_registration(command)


def test_pair_provisional_registration_already_bound_client() -> None:
    repo = _MockIdentityManagementRepo()
    repo.orders["115000008"]["client_line_user_id"] = "U_ALREADY_BOUND"
    identities = _MockIdentities()
    customers = _MockCustomers()
    app, _ = _make_app(repo, identities, customers)

    actor = ActorContext(
        "admin:manager",
        (LineCapability.IDENTITY_BINDING_MANAGE.value,),
    )
    command = PairProvisionalRegistrationCommand(
        provisional_registration_id=1,
        target_case_no="115000008",
        actor=actor,
        reason="測試已綁定客戶",
        idempotency_key=IdempotencyKey("test-pair-key-4"),
        correlation_id=CorrelationId("test-pair-corr-4"),
    )

    with pytest.raises(RuntimeError, match="line_order_client_already_bound"):
        app.pair_provisional_registration(command)


def test_api_routes_unbound_candidates_and_pair(monkeypatch) -> None:
    from api.routes import line_identity_management
    from api.schemas.line_identity_management import PairProvisionalRegistrationRequest
    from subsystems.access.authentication_session import AdminPrincipal
    from unittest.mock import MagicMock

    repo = _MockIdentityManagementRepo()
    identities = _MockIdentities()
    customers = _MockCustomers()
    app, _ = _make_app(repo, identities, customers)

    monkeypatch.setattr(line_identity_management, "_application", lambda: app)
    monkeypatch.setattr(line_identity_management, "publish_line_wakeup_best_effort", lambda: None)

    principal = AdminPrincipal(
        id=1,
        username="admin",
        display_name="Admin",
        role="system_admin",
        capabilities=frozenset({"line.identity.binding.manage"}),
    )

    # 1. Test GET /unbound-candidates
    resp = line_identity_management.list_unbound_candidates(_=principal)
    assert len(resp.data.orders) == 1
    assert resp.data.orders[0].case_no == "115000008"
    assert len(resp.data.provisional_registrations) == 1

    # 2. Test POST /pair-provisional
    mock_request = MagicMock()
    mock_request.state = MagicMock()
    payload = PairProvisionalRegistrationRequest(
        provisional_registration_id=1,
        target_case_no="115000008",
        reason="專員手動配對測試",
        idempotency_key="route-test-key-1",
        correlation_id="route-test-corr-1",
    )
    pair_resp = line_identity_management.pair_provisional_registration(
        payload=payload,
        request=mock_request,
        principal=principal,
    )
    assert pair_resp.data.case_no == "115000008"
    assert pair_resp.data.status == "bound"
    assert "成功配對" in pair_resp.message
