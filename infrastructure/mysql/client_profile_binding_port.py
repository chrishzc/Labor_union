"""Client-owned binding port backed by LINE's typed current-fact readback."""

from __future__ import annotations

from typing import Any

from domains.line.identity_binding import LineBindingSubjectType, LineIdentityBindingStatus
from domains.line.identities import LineUserId
from infrastructure.mysql.line_identity_management_repository import MySqlLineIdentityManagementRepository
from subsystems.client_profile.contracts import ClientBindingEvidence, ClientProfileBindingError
from subsystems.line.identity_management_contracts import LineIdentityCurrentFactQuery


class MySqlClientBindingPort:
    """Translate complete LINE current-fact evidence to Client's generic port."""

    def __init__(self, connection: Any) -> None:
        self._connection = connection
        self._line_reader = MySqlLineIdentityManagementRepository(connection)

    def read_current(
        self,
        applicant_identity: str,
        *,
        client_id: int,
        lock: bool = False,
    ) -> ClientBindingEvidence:
        line_user_id = LineUserId(applicant_identity)
        if lock:
            with self._connection.cursor() as cursor:
                cursor.execute(
                    "SELECT line_user_id,subject_type,subject_reference,binding_status,aggregate_version "
                    "FROM line_identity_role_bindings WHERE line_user_id=%s FOR UPDATE",
                    (applicant_identity,),
                )
                cursor.fetchall()
                cursor.execute(
                    "SELECT id FROM clients WHERE id=%s AND line_user_id=%s FOR UPDATE",
                    (client_id, applicant_identity),
                )
                cursor.fetchone()
        fact = self._line_reader.current_fact(LineIdentityCurrentFactQuery(line_user_id))
        if fact.readback_status.value != "complete":
            raise ClientProfileBindingError("line_binding_current_fact_incomplete")
        if fact.is_conflict:
            raise ClientProfileBindingError("line_binding_current_fact_conflict")
        customer_bindings = tuple(
            item for item in fact.root_bindings
            if item.subject_type == LineBindingSubjectType.CUSTOMER
        )
        if len(customer_bindings) != 1 or not customer_bindings[0].subject_reference.isdigit():
            raise ClientProfileBindingError("client_binding_not_unique")
        if customer_bindings[0].binding_status != LineIdentityBindingStatus.BOUND:
            raise ClientProfileBindingError("line_binding_not_current")
        if int(customer_bindings[0].subject_reference) != client_id:
            raise ClientProfileBindingError("client_binding_subject_mismatch")
        roles = tuple(sorted(item.subject_type.value for item in fact.root_bindings))
        return ClientBindingEvidence(
            applicant_identity,
            client_id,
            int(customer_bindings[0].aggregate_version or 0),
            roles,
            True,
            fact.is_legal_dual_role,
        )


__all__ = ["MySqlClientBindingPort"]
