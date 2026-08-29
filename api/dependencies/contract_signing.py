"""Composition root for contract-signing applications."""

from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path

from infrastructure.mysql.contract_signing_document_query_repository import (
    MySqlContractSigningDocumentQueryRepository,
)
from infrastructure.mysql.mysql_adapter import get_connection
from subsystems.contract_signing.client_contract_application import (
    ClientContractSigningApplication,
)
from subsystems.contract_signing.staff_contract_application import (
    StaffContractSigningApplication,
)
from subsystems.contract_signing.document_query import (
    ContractSigningDocumentQueryApplication,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def get_staff_contract_signing_application() -> StaffContractSigningApplication:
    return StaffContractSigningApplication(
        get_connection,
        archive_root=_archive_root(),
        now=lambda: datetime.now(timezone.utc),
    )


def get_client_contract_signing_application() -> ClientContractSigningApplication:
    return ClientContractSigningApplication(
        get_connection,
        archive_root=_archive_root(),
        now=lambda: datetime.now(timezone.utc),
    )


def get_contract_signing_document_query_application():
    connection = get_connection()
    try:
        yield ContractSigningDocumentQueryApplication(
            MySqlContractSigningDocumentQueryRepository(connection)
        )
    finally:
        connection.close()


def _archive_root() -> Path:
    configured = os.getenv("CONTRACT_DOCUMENT_ARCHIVE_ROOT", "").strip()
    return Path(configured) if configured else PROJECT_ROOT / "runtime_data" / "contracts"
