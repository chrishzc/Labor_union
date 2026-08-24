"""
File: jobs.py
Description: 組合 Durable Job query repository 與 canonical enqueue application，明確關閉 MySQL connection。
"""

from collections.abc import Iterator

from fastapi import HTTPException

from api.dependencies.admin_auth import admin_auth_is_enabled
from api.error_contracts import typed_http_error
from infrastructure.mysql.background_job_repository import BackgroundJobRepository
from infrastructure.mysql.mysql_adapter import get_connection
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.jobs.command_application import (
    DurableJobCancellationApplication,
    DurableJobCommandApplication,
)
from subsystems.jobs.contracts import DurableJobCommandConflict


def get_job_repository() -> Iterator[BackgroundJobRepository]:
    conn = get_connection()
    try:
        yield BackgroundJobRepository(conn)
    finally:
        conn.close()


def get_durable_job_application() -> Iterator[DurableJobCommandApplication]:
    connection = get_connection()
    try:
        repository = BackgroundJobRepository(connection)
        yield DurableJobCommandApplication(repository, connection)
    finally:
        connection.close()


def get_durable_job_cancellation() -> Iterator[DurableJobCancellationApplication]:
    connection = get_connection()
    try:
        repository = BackgroundJobRepository(connection)
        yield DurableJobCancellationApplication(repository, connection)
    finally:
        connection.close()


def immutable_admin_job_actor(principal: AdminPrincipal, correlation_id: str) -> str:
    if isinstance(principal.id, int) and principal.id > 0:
        return f"admin_user_id:{principal.id}"
    if (
        not admin_auth_is_enabled()
        and principal.id is None
        and principal.username == "development-bypass"
        and principal.role == "system_admin"
    ):
        return "system:local_bypass"
    raise typed_http_error(
        403,
        "authorization",
        "durable_job_actor_unavailable",
        "目前登入身分缺少可持久化的管理員識別。",
        correlation_id,
    )


def durable_job_conflict_http_error(
    error: DurableJobCommandConflict,
    correlation_id: str,
) -> HTTPException:
    del error
    return typed_http_error(
        409,
        "idempotency_mismatch",
        "durable_job_command_conflict",
        "相同冪等鍵已用於不同的 Durable Job 命令。",
        correlation_id,
    )
