"""Fail-closed gate until BeClass owning-domain commands are available.

BeClass review Apply used to write ``beclass_records`` or ``staff`` directly
from the Case Import adapter. Neither owning-domain command exists today:
Client only exposes the narrower HCM correction command, while Staff's
historical adoption path is not a current profile command. Keeping the old
writer reachable would therefore bypass ownership and version contracts.
"""

from __future__ import annotations

from domains.case_import.beclass_import_review import BeClassImportSourceKind
from shared_kernel.errors import ErrorCategory
from subsystems.case_import.beclass_import_review_workflow import (
    BeClassImportReviewWriteReceipt,
    BeClassImportReviewWriterError,
)


class BeClassImportReviewOwnerCommandUnavailable:
    """Reject review payload Apply until an owning typed command is composed."""

    def __init__(self, connection=None) -> None:
        # Kept argument-compatible with the old dependency factory. The
        # retired adapter must never inspect or use the borrowed connection.
        del connection

    def apply_corrected_row(self, candidate) -> BeClassImportReviewWriteReceipt:
        code = {
            BeClassImportSourceKind.CLIENT:
                "beclass_import_review_client_owner_command_unavailable",
            BeClassImportSourceKind.STAFF:
                "beclass_import_review_staff_owner_command_unavailable",
            BeClassImportSourceKind.HCM:
                "beclass_import_review_hcm_owner_command_unavailable",
        }.get(candidate.source_kind, "beclass_import_review_owner_command_unavailable")
        raise BeClassImportReviewWriterError(code, ErrorCategory.DOMAIN_BLOCKED)


__all__ = ["BeClassImportReviewOwnerCommandUnavailable"]
