"""Client profile application-owned outer Unit of Work."""

from __future__ import annotations

from infrastructure.mysql.client_profile_repository import MySqlClientProfileRepository
from infrastructure.mysql.client_profile_binding_port import MySqlClientBindingPort
from infrastructure.mysql.mysql_adapter import get_connection


class ClientProfileUnitOfWork:
    def __init__(self, connection) -> None:
        self._connection = connection
        self.client_profiles = MySqlClientProfileRepository(connection)
        self.binding = MySqlClientBindingPort(connection)
        self._committed = False
        self._rolled_back = False

    def __enter__(self):
        self._connection.begin()
        return self

    def __exit__(self, exception_type, exception, traceback):
        if exception_type is not None or not self._committed:
            self.rollback()
        return False

    def commit(self) -> None:
        if self._committed or self._rolled_back:
            raise RuntimeError("transaction is already finalized")
        self._connection.commit()
        self._committed = True

    def rollback(self) -> None:
        if self._committed:
            raise RuntimeError("committed transaction cannot be rolled back")
        if self._rolled_back:
            return
        self._connection.rollback()
        self._rolled_back = True


class ManagedClientProfileUnitOfWork(ClientProfileUnitOfWork):
    def __exit__(self, exception_type, exception, traceback):
        try:
            return super().__exit__(exception_type, exception, traceback)
        finally:
            self._connection.close()


def open_client_profile_unit_of_work() -> ManagedClientProfileUnitOfWork:
    return ManagedClientProfileUnitOfWork(get_connection())


__all__ = ["ClientProfileUnitOfWork", "ManagedClientProfileUnitOfWork", "open_client_profile_unit_of_work"]
