"""MySQL composition adapter from LINE current facts to an owner snapshot."""

from __future__ import annotations

from domains.anomalies.current_issue import OwnerSnapshot, RecheckScope
from domains.line.identities import LineUserId
from infrastructure.mysql.line_identity_management_repository import (
    MySqlLineIdentityManagementRepository,
)
from shared_kernel.fingerprints import fingerprint_payload
from subsystems.anomalies.line_identity_current_issue_consumer import (
    LINE_IDENTITY_OWNER_DOMAIN,
    LINE_IDENTITY_OWNER_ROOT_TYPE,
)
from subsystems.line.identity_management_contracts import (
    LineIdentityCurrentFactBinding,
    LineIdentityCurrentFactQuery,
    LineIdentityCurrentFactReadback,
)


class MySqlLineIdentityCurrentIssueAdapter:
    """Read only through the LINE repository's typed current-fact contract."""

    def __init__(self, connection) -> None:
        self._repository = MySqlLineIdentityManagementRepository(connection)

    def read_owner_snapshot(self, scope: RecheckScope) -> OwnerSnapshot:
        if (
            scope.owner_domain != LINE_IDENTITY_OWNER_DOMAIN
            or scope.owner_root_type != LINE_IDENTITY_OWNER_ROOT_TYPE
        ):
            raise ValueError("LINE-004 owner scope is invalid")
        readbacks = tuple(
            self._repository.current_fact(
                LineIdentityCurrentFactQuery(LineUserId(line_user_id))
            )
            for line_user_id in scope.subject_ids
        )
        snapshot_token = fingerprint_payload(
            {"readbacks": [_readback_payload(item) for item in readbacks]}
        ).value
        return OwnerSnapshot(
            scope=scope,
            snapshot_token=snapshot_token,
            owner_version=max(
                (item.root_version or 0 for item in readbacks), default=0
            ),
            facts=readbacks,
            authoritative_complete=True,
        )


def _binding_payload(binding: LineIdentityCurrentFactBinding | None):
    if binding is None:
        return None
    return {
        "subject_type": binding.subject_type.value,
        "subject_reference": binding.subject_reference,
        "owner_line_user_id": binding.owner_line_user_id,
    }


def _readback_payload(readback: LineIdentityCurrentFactReadback) -> dict[str, object]:
    return {
        "line_user_id": readback.line_user_id,
        "root_status": readback.root_status.value if readback.root_status else None,
        "root_version": readback.root_version,
        "root_binding": _binding_payload(readback.root_binding),
        "owner_projections": [
            _binding_payload(item) for item in readback.owner_projections
        ],
        "findings": [item.value for item in readback.findings],
        "readback_status": readback.readback_status.value,
        "dual_role_persistence_supported": readback.dual_role_persistence_supported,
    }


__all__ = ["MySqlLineIdentityCurrentIssueAdapter"]
