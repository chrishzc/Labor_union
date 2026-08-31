"""Finance Import owner readback contract for ``IMPORT-006``.

This layer validates the closed subject and composes a bounded owner snapshot.
It does not project, resolve, or mutate Anomalies state.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from domains.anomalies.current_issue import OwnerSnapshot, RecheckScope
from domains.finance_import.anomaly_remediation import (
    FinanceImportIntegrityOwnerFact,
    FinanceImportSourceCorrectionApplyRequest,
    FinanceImportSourceCorrectionLineage,
    finance_import_integrity_fingerprint,
)
from shared_kernel.fingerprints import fingerprint_payload
from shared_kernel.validation import (
    require_canonical_text,
    require_nonnegative_integer,
)

FINANCE_IMPORT_ANOMALY_OWNER_DOMAIN = "finance_import"
FINANCE_IMPORT_ANOMALY_OWNER_ROOT_TYPE = "finance_import_batch"
IMPORT_006_SUBJECT_TYPE = "IMPORT-006"


class FinanceImportCurrentIssueCode(StrEnum):
    """Closed code discriminator without a generic owner fallback."""

    IMPORT_006 = IMPORT_006_SUBJECT_TYPE


class FinanceImportAnomalyOwnerRepository(Protocol):
    """Read-only port; concrete adapters must use the caller's transaction."""

    def read_integrity(
        self, batch_identity: str, *, for_update: bool = False
    ) -> FinanceImportIntegrityOwnerFact: ...

    def append_source_correction_lineage(
        self,
        request: FinanceImportSourceCorrectionApplyRequest,
        lineage: FinanceImportSourceCorrectionLineage,
    ) -> str: ...


class FinanceImportAnomalyOwnerReadback:
    """Dispatch ``IMPORT-006`` to Finance Import's typed owner port."""

    def __init__(self, repository: FinanceImportAnomalyOwnerRepository) -> None:
        self._repository = repository

    def read(
        self, definition_code: str, subject_identity: str, *, for_update: bool = False
    ) -> FinanceImportIntegrityOwnerFact:
        require_canonical_text(definition_code, "definition code", 32)
        batch_identity = _parse_batch_identity(subject_identity)
        if definition_code != IMPORT_006_SUBJECT_TYPE:
            raise ValueError("finance_import_owner_issue_not_supported")
        fact = self._repository.read_integrity(batch_identity, for_update=for_update)
        if not isinstance(fact, FinanceImportIntegrityOwnerFact):
            raise TypeError("finance_import owner readback is invalid")
        if fact.batch_identity != batch_identity:
            raise ValueError("finance_import_owner_mismatch")
        return fact

    def read_owner_snapshot(self, scope: RecheckScope) -> OwnerSnapshot:
        _validate_scope(scope)
        facts = tuple(
            self.read(IMPORT_006_SUBJECT_TYPE, subject, for_update=True)
            for subject in scope.subject_ids
        )
        token = fingerprint_payload(
            {
                "scope": tuple(scope.subject_ids),
                "facts": tuple(finance_import_integrity_fingerprint(fact).value for fact in facts),
            }
        ).value
        return OwnerSnapshot(
            scope,
            token,
            max((fact.batch_version for fact in facts), default=0),
            facts,
            all(fact.authoritative_complete for fact in facts),
        )


def read_finance_import_integrity(
    repository: FinanceImportAnomalyOwnerRepository,
    batch_identity: str,
    *,
    for_update: bool = False,
) -> FinanceImportIntegrityOwnerFact:
    """Small typed convenience port for owner workflows."""

    return FinanceImportAnomalyOwnerReadback(repository).read(
        IMPORT_006_SUBJECT_TYPE,
        batch_identity,
        for_update=for_update,
    )


def build_finance_import_recheck_request(
    batch_identity: str,
    fact: FinanceImportIntegrityOwnerFact,
    *,
    intent_identity: str,
) -> "FinanceImportAnomalyRecheckRequest":
    """Bind a recheck intent to the exact batch version and owner snapshot."""

    require_canonical_text(intent_identity, "recheck intent identity", 191)
    batch_identity = _parse_batch_identity(batch_identity)
    if not isinstance(fact, FinanceImportIntegrityOwnerFact):
        raise TypeError("Finance Import owner fact is required")
    if fact.batch_identity != batch_identity:
        raise ValueError("finance_import_recheck_batch_mismatch")
    return FinanceImportAnomalyRecheckRequest(
        IMPORT_006_SUBJECT_TYPE,
        (batch_identity,),
        (f"finance-import-batch:{batch_identity.removeprefix('finance-import-batch:')}",),
        fact.batch_version,
        fact.owner_snapshot_token,
        intent_identity,
    )


@dataclass(frozen=True, slots=True)
class FinanceImportAnomalyRecheckRequest:
    """Typed bounded recheck intent for the owner root."""

    definition_code: str
    subject_ids: tuple[str, ...]
    owner_root_ids: tuple[str, ...]
    owner_version: int
    owner_snapshot_token: str
    intent_identity: str

    def __post_init__(self) -> None:
        definition_code = self.definition_code
        subject_ids = self.subject_ids
        owner_root_ids = self.owner_root_ids
        owner_version = self.owner_version
        owner_snapshot_token = self.owner_snapshot_token
        intent_identity = self.intent_identity
        if definition_code != IMPORT_006_SUBJECT_TYPE:
            raise ValueError("finance_import recheck definition is invalid")
        if not isinstance(subject_ids, tuple) or not subject_ids or tuple(sorted(set(subject_ids))) != subject_ids:
            raise ValueError("finance_import recheck subject ids must be sorted and unique")
        if not isinstance(owner_root_ids, tuple) or not owner_root_ids or tuple(sorted(set(owner_root_ids))) != owner_root_ids:
            raise ValueError("finance_import recheck owner roots must be sorted and unique")
        for value in subject_ids:
            require_canonical_text(value, "finance_import recheck identity", 191)
        for value in owner_root_ids:
            require_canonical_text(value, "finance_import owner root id", 191)
        require_nonnegative_integer(owner_version, "owner version")
        require_canonical_text(owner_snapshot_token, "owner snapshot token", 191)
        require_canonical_text(intent_identity, "recheck intent identity", 191)


def _parse_batch_identity(value: str) -> str:
    require_canonical_text(value, "batch identity", 191)
    prefix = "finance-import-batch:"
    raw = value.removeprefix(prefix)
    if not value.startswith(prefix) or not raw.isdecimal() or int(raw) <= 0:
        raise ValueError("finance_import batch subject identity is invalid")
    return value


def _validate_scope(scope: RecheckScope) -> None:
    if (
        scope.owner_domain != FINANCE_IMPORT_ANOMALY_OWNER_DOMAIN
        or scope.owner_root_type != FINANCE_IMPORT_ANOMALY_OWNER_ROOT_TYPE
        or scope.subject_type != IMPORT_006_SUBJECT_TYPE
    ):
        raise ValueError("finance_import anomaly owner scope is invalid")
    for subject in scope.subject_ids:
        _parse_batch_identity(subject)


__all__ = [
    "FINANCE_IMPORT_ANOMALY_OWNER_DOMAIN",
    "FINANCE_IMPORT_ANOMALY_OWNER_ROOT_TYPE",
    "IMPORT_006_SUBJECT_TYPE",
    "FinanceImportAnomalyOwnerReadback",
    "FinanceImportAnomalyOwnerRepository",
    "FinanceImportAnomalyRecheckRequest",
    "FinanceImportCurrentIssueCode",
    "FinanceImportIntegrityOwnerFact",
    "FinanceImportSourceCorrectionApplyRequest",
    "FinanceImportSourceCorrectionLineage",
    "build_finance_import_recheck_request",
    "read_finance_import_integrity",
]
