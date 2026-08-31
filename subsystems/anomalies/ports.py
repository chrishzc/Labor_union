"""Typed dependency ports for the Anomalies subsystem.

Concrete database adapters are deliberately composed outside this package.
The subsystem receives this port from an application/worker composition root.
"""

from __future__ import annotations

from typing import Any, Protocol


class AnomalyRuntime(Protocol):
    """Dependencies required by anomaly consumers and the delivery worker."""

    def anomaly_application(self, connection: Any) -> Any: ...

    def anomaly_repository(self, connection: Any) -> Any: ...

    def hcm_resubmission_repository(self, connection: Any) -> Any: ...

    def subsidy_advance_recovery_repository(self, connection: Any) -> Any: ...

    def failure_unit_of_work(self, connection: Any) -> Any: ...

    def connection(self) -> Any: ...

    def auto_resolve_import_warning_occurrence(self, connection: Any, **kwargs: Any) -> int: ...

    def load_import_warning_review_resolution_state(self, connection: Any, **kwargs: Any) -> Any: ...

    def current_issue_repository(self, connection: Any, **kwargs: Any) -> Any: ...

    def current_issue_application(self, connection: Any, **kwargs: Any) -> Any: ...

    def run_current_issue_recheck(self, connection: Any, payload: dict[str, Any]) -> Any: ...

    def current_issue_key(self, definition_code: str, subject_identity: dict[str, Any]) -> str: ...

    @property
    def hcm_field_correction_terminal_predicate(self) -> str: ...


def require_runtime(runtime: AnomalyRuntime | None) -> AnomalyRuntime:
    if runtime is None:
        raise RuntimeError("anomaly_runtime_not_composed")
    return runtime


__all__ = ["AnomalyRuntime", "require_runtime"]
