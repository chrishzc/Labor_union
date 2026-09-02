"""
File: private_operations.py
Description: 組合 private runtime operations，將 runtime persistence 交給 typed applications。
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Mapping

from fastapi import Request

from api.dependencies.runtime_heartbeat import (
    get_runtime_heartbeat_application,
    record_runtime_heartbeat,
)
from api.dependencies.durable_job_handlers import default_job_handlers
from api.schemas.private_operations import MonitorCycleRequest, WorkerRuntimeIdentity
from infrastructure.knowledge.chroma_gateway import ChromaKnowledgeGateway
from infrastructure.knowledge.gemini_selector import GeminiCandidateSelector
from infrastructure.mysql.background_job_repository import BackgroundJobRepository
from infrastructure.mysql.knowledge_retrieval_unit_of_work import (
    open_knowledge_retrieval_unit_of_work,
)
from infrastructure.mysql.line_delivery_task_repository import MySqlLineDeliveryTaskRepository
from infrastructure.mysql.line_runtime_repository import MySqlLineRuntimeRepository
from infrastructure.mysql.line_unit_of_work import open_line_unit_of_work
from infrastructure.mysql.mysql_adapter import get_connection
from subsystems.jobs.durable_job_worker import DurableJobWorker
from subsystems.knowledge_retrieval.application import KnowledgeWorker
from subsystems.line.runtime_monitoring import RuntimeHealthObservation
from subsystems.line.runtime_alert_application import RuntimeMonitoringApplication


def inspect_react_admin_artifact_health(request: Request) -> Mapping[str, object]:
    """Read the startup-validated artifact attestation without touching DB/runtime state."""
    provider = getattr(request.app.state, "react_admin_artifact_health", None)
    if not callable(provider):
        raise RuntimeError("react admin artifact hosting is not configured")
    result = provider()
    if not isinstance(result, Mapping):
        raise RuntimeError("react admin artifact health provider returned an invalid value")
    return result


def run_durable_job_cycle(
    worker_id: str,
    lease_seconds: int,
    retry_delay_seconds: int,
    runtime_identity: WorkerRuntimeIdentity,
    *,
    check_only: bool,
) -> int:
    connection = get_connection()
    try:
        repository = BackgroundJobRepository(connection)
        repository.assert_durable_queue_schema()
        if check_only:
            _write_durable_job_heartbeat(connection, runtime_identity, 0)
            return 0
        worker = DurableJobWorker(
            repository,
            connection,
            default_job_handlers(),
            worker_id,
            lease_seconds,
            retry_delay_seconds,
        )
        processed = int(worker.recover_and_run_once())
        _write_durable_job_heartbeat(connection, runtime_identity, processed)
        return processed
    finally:
        connection.close()


def _write_durable_job_heartbeat(
    connection,
    runtime_identity: WorkerRuntimeIdentity,
    processed: int,
) -> None:
    """Delegate the post-worker heartbeat to the runtime application."""
    get_runtime_heartbeat_application().record(runtime_identity, processed)


def run_knowledge_cycle(worker_id: str, runtime_identity: WorkerRuntimeIdentity) -> int:
    gateway = ChromaKnowledgeGateway(
        os.getenv("KNOWLEDGE_CHROMA_PATH", "db/chroma_knowledge"),
        llm=GeminiCandidateSelector(),
    )
    worker = KnowledgeWorker(open_knowledge_retrieval_unit_of_work, gateway, worker_id)
    processed = int(worker.run_once())
    record_runtime_heartbeat(runtime_identity, processed)
    return processed


def record_monitor_cycle(request: MonitorCycleRequest) -> tuple[int, int]:
    return _runtime_monitoring_application().record_cycle(
        request.runtime_identity,
        request.observations,
    )


def inspect_runtime_readiness() -> tuple[RuntimeHealthObservation, ...]:
    return _runtime_monitoring_application().inspect_readiness()


@lru_cache(maxsize=1)
def _runtime_monitoring_application() -> RuntimeMonitoringApplication:
    return RuntimeMonitoringApplication(
        open_line_unit_of_work,
        lambda unit_of_work: MySqlLineRuntimeRepository(unit_of_work._connection),
        lambda unit_of_work: MySqlLineDeliveryTaskRepository(unit_of_work._connection),
        lambda unit_of_work: unit_of_work._connection,
    )
