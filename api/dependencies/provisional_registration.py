"""Per-request composition for typed provisional LINE registration."""

from infrastructure.mysql.mysql_adapter import get_connection
from subsystems.case_import.provisional_registration_application import (
    ProvisionalRegistrationApplication,
    build_provisional_registration_application,
)


def get_provisional_registration_application():
    connection = get_connection()
    try:
        yield build_provisional_registration_application(connection)
    finally:
        connection.close()


__all__ = [
    "ProvisionalRegistrationApplication",
    "get_provisional_registration_application",
]
