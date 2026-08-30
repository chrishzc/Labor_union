"""Typed dependency ports for Scheduling subsystem composition.

The subsystem owns orchestration and business decisions; database connections,
repositories, and transaction implementations are supplied by an outer
composition root.  The legacy ``get_connection`` test seams in individual
modules are intentionally only unconfigured callables, never concrete
adapters.
"""

from __future__ import annotations

from typing import Any, Callable, Protocol


class SchedulingConnection(Protocol):
    def cursor(self, *args: Any, **kwargs: Any) -> Any: ...

    def close(self) -> None: ...


class SchedulingUnitOfWork(Protocol):
    def __enter__(self) -> "SchedulingUnitOfWork": ...

    def __exit__(self, exception_type: Any, exception: Any, traceback: Any) -> bool | None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...


class SchedulingConnectionFactory(Protocol):
    def __call__(self) -> SchedulingConnection: ...


class SegmentedAvailabilityFactsPort(Protocol):
    def load_case_facts(self, case_no: str) -> dict[str, Any]: ...


ConnectionFactory = Callable[[], Any]


def unconfigured_connection_factory() -> Any:
    """Fail closed until an outer composition supplies a connection factory."""
    raise RuntimeError("scheduling connection factory is not configured")


__all__ = [
    "ConnectionFactory",
    "SchedulingConnection",
    "SchedulingConnectionFactory",
    "SchedulingUnitOfWork",
    "SegmentedAvailabilityFactsPort",
    "unconfigured_connection_factory",
]
