"""Outer transaction owner for MySQL-backed application workflows."""

from __future__ import annotations

from typing import Protocol


class TransactionConnection(Protocol):
    def begin(self) -> None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...


class MySqlUnitOfWork:
    def __init__(self, connection: TransactionConnection) -> None:
        self._connection = connection
        self._committed = False
        self._rolled_back = False

    def __enter__(self) -> MySqlUnitOfWork:
        self._connection.begin()
        return self

    def __exit__(self, exception_type, exception, traceback) -> bool:
        if exception is not None:
            try:
                self.rollback()
            except Exception as rollback_error:
                if rollback_error is not exception:
                    # Cleanup is secondary. Keep the same primary object/TB
                    # and any explicit cause/suppression chosen by its owner.
                    # Python links a cleanup failure back to the primary;
                    # break that link before retaining it as diagnostic context.
                    rollback_error.__context__ = None
                    if rollback_error.__cause__ is exception:
                        rollback_error.__cause__ = None
                    exception.__context__ = rollback_error
            return False
        if not self._committed:
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
