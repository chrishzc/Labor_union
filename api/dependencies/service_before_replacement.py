"""
File: service_before_replacement.py
Description: 組裝服務前換人 application；缺少安全 facts/source loader 時 fail closed。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Header, HTTPException

from subsystems.scheduling.service_before_replacement_workflow import (
    ServiceBeforeReplacementQueryRequest,
)


_CorrelationHeader = Annotated[
    str,
    Header(alias="X-Correlation-ID", min_length=1, max_length=191),
]


class ServiceBeforeReplacementApplication:
    """Typed façade kept small so routes cannot reach repositories directly."""

    def __init__(self, workflow) -> None:
        self.workflow = workflow

    def query(self, request: ServiceBeforeReplacementQueryRequest):
        return self.workflow.query(request)

    def preview(self, request):
        return self.workflow.preview(request)

    def apply(self, command):
        return self.workflow.apply(command)


def get_service_before_replacement_application(
    correlation_id: _CorrelationHeader = "service-before-replacement-dependency",
):
    """Do not construct a production writer without both authoritative loaders."""
    raise HTTPException(
        status_code=503,
        detail={
            "error": {
                "category": "unavailable",
                "code": "replacement_source_unavailable",
                "message": "服務前換人根事實來源尚未安全接通。",
                "field_errors": [],
                "domain_blockers": ["facts_loader_unavailable", "matching_source_loader_unavailable"],
                "retryable": True,
                "correlation_id": correlation_id,
                "current_version": None,
            }
        },
    )


__all__ = [
    "ServiceBeforeReplacementApplication",
    "get_service_before_replacement_application",
]
