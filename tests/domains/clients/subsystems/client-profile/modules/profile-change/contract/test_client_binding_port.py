"""Client profile consumes legal role-scoped LINE binding evidence."""

from domains.line.identity_binding import LineBindingSubjectType, LineIdentityBindingStatus
from infrastructure.mysql.client_profile_binding_port import MySqlClientBindingPort
from subsystems.line.identity_management_contracts import (
    LineIdentityCurrentFactBinding,
    LineIdentityCurrentFactFinding,
    LineIdentityCurrentFactReadback,
    LineIdentityCurrentFactReadbackStatus,
)


class _Reader:
    def __init__(self, fact):
        self.fact = fact

    def current_fact(self, _query):
        return self.fact


def test_legal_customer_staff_dual_role_uses_customer_role_binding():
    customer = LineIdentityCurrentFactBinding(
        LineBindingSubjectType.CUSTOMER,
        "7",
        binding_status=LineIdentityBindingStatus.BOUND,
        aggregate_version=4,
    )
    staff = LineIdentityCurrentFactBinding(
        LineBindingSubjectType.STAFF,
        "19",
        binding_status=LineIdentityBindingStatus.BOUND,
        aggregate_version=3,
    )
    fact = LineIdentityCurrentFactReadback(
        line_user_id="U-dual",
        root_status=None,
        root_version=None,
        root_binding=None,
        owner_projections=(customer, staff),
        findings=(LineIdentityCurrentFactFinding.LEGAL_CUSTOMER_STAFF_DUAL_ROLE,),
        readback_status=LineIdentityCurrentFactReadbackStatus.COMPLETE,
        manual_actions=(),
        root_bindings=(customer, staff),
        dual_role_persistence_supported=True,
    )
    adapter = object.__new__(MySqlClientBindingPort)
    adapter._connection = None
    adapter._line_reader = _Reader(fact)

    evidence = adapter.read_current("U-dual", client_id=7)

    assert evidence.client_id == 7
    assert evidence.binding_version == 4
    assert evidence.roles == ("customer", "staff")
    assert evidence.legal_customer_staff_dual_role is True
