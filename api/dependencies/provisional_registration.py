"""Composition root for LINE provisional registration."""

from infrastructure.mysql.provisional_registration_repository import (
    MySqlProvisionalRegistrationRepository,
    ProvisionalRegistrationMySqlUnitOfWork,
)
from subsystems.case_import.provisional_registration_application import ProvisionalRegistrationApplication


def build_provisional_registration_application(connection):
    repository = MySqlProvisionalRegistrationRepository(connection)
    return ProvisionalRegistrationApplication(repository, lambda: ProvisionalRegistrationMySqlUnitOfWork(connection))


__all__ = ["build_provisional_registration_application"]
