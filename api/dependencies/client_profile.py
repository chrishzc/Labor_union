"""Composition root for Client profile workflows."""

from functools import lru_cache

from domains.line.identity_binding import LineBindingSubjectType, LineIdentityBindingStatus
from domains.line.identities import LineUserId
from infrastructure.line.liff_token_verifier import LineLoginTokenVerifier
from infrastructure.mysql.line_identity_management_repository import MySqlLineIdentityManagementRepository
from infrastructure.mysql.mysql_adapter import get_connection
from domains.case_import.client_import_validation import VALID_CITIES
from subsystems.line.identity_management_contracts import LineIdentityCurrentFactQuery
from subsystems.client_profile.application import ClientProfileApplication
from subsystems.client_profile.mysql_unit_of_work import open_client_profile_unit_of_work
from subsystems.client_profile.contracts import ClientProfileBindingError


@lru_cache(maxsize=1)
def get_client_profile_application() -> ClientProfileApplication:
    return ClientProfileApplication(
        open_client_profile_unit_of_work,
        # Composition reuses the current intake allowlist without creating a
        # Client -> Case Import dependency inside either owning subsystem.
        city_allowlist=VALID_CITIES,
    )


def get_verified_client_identity(token: str, verifier: LineLoginTokenVerifier | None = None) -> tuple[str, int]:
    identity = (verifier or _verifier()).verify(token).line_user_id.value
    return identity, _resolve_bound_client_id(identity)


def validate_client_binding(applicant_identity: str, client_id: int) -> None:
    if _resolve_bound_client_id(applicant_identity) != client_id:
        raise ClientProfileBindingError("client_binding_mismatch")


def _resolve_bound_client_id(line_user_id: str) -> int:
    connection = get_connection()
    try:
        reader = MySqlLineIdentityManagementRepository(connection)
        fact = reader.current_fact(LineIdentityCurrentFactQuery(LineUserId(line_user_id)))
    finally:
        connection.close()
    if fact.readback_status.value != "complete":
        raise ClientProfileBindingError("line_binding_current_fact_incomplete")
    bindings = tuple(item for item in fact.root_bindings if item.subject_type == LineBindingSubjectType.CUSTOMER)
    if len(bindings) != 1 or not bindings[0].subject_reference.isdigit():
        raise ClientProfileBindingError("client_binding_not_unique")
    if bindings[0].binding_status != LineIdentityBindingStatus.BOUND:
        raise ClientProfileBindingError("line_binding_not_current")
    return int(bindings[0].subject_reference)


@lru_cache(maxsize=1)
def _verifier() -> LineLoginTokenVerifier:
    import os
    return LineLoginTokenVerifier(os.getenv("LINE_LOGIN_CHANNEL_ID", ""))


__all__ = ["get_client_profile_application", "get_verified_client_identity", "validate_client_binding"]
