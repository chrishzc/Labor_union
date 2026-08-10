"""Transactional application service for one active LINE provisional registration."""

from __future__ import annotations

from domains.case_import.provisional_registration import (
    ProvisionalRegistrationDomainError,
    ProvisionalRegistrationIntent,
    build_provisional_registration_candidate,
)
from infrastructure.mysql.provisional_registration_repository import (
    MySqlProvisionalRegistrationRepository,
    ProvisionalRegistrationMySqlUnitOfWork,
    ProvisionalRegistrationStorageError,
)
from subsystems.case_import.provisional_registration_types import (
    ProvisionalRegistrationConflict,
    ProvisionalRegistrationConflictError,
    ProvisionalRegistrationReceipt,
)


class ProvisionalRegistrationApplication:
    def __init__(self, repository, unit_of_work_factory) -> None:
        self._repository = repository
        self._unit_of_work_factory = unit_of_work_factory

    def apply(self, intent: ProvisionalRegistrationIntent) -> ProvisionalRegistrationReceipt:
        candidate = build_provisional_registration_candidate(intent)
        with self._unit_of_work_factory() as unit_of_work:
            outcome = self._repository.apply(candidate)
            unit_of_work.commit()
        if isinstance(outcome, ProvisionalRegistrationConflict):
            raise ProvisionalRegistrationConflictError("registration_conflict")
        return outcome


def build_provisional_registration_application(connection):
    repository = MySqlProvisionalRegistrationRepository(connection)
    return ProvisionalRegistrationApplication(
        repository,
        lambda: ProvisionalRegistrationMySqlUnitOfWork(connection),
    )


__all__ = [
    "ProvisionalRegistrationApplication",
    "ProvisionalRegistrationConflictError",
    "ProvisionalRegistrationDomainError",
    "ProvisionalRegistrationReceipt",
    "ProvisionalRegistrationStorageError",
    "build_provisional_registration_application",
]
