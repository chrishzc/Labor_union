"""Root-gated composition; the connection's isolation protects non-FK gap reads."""

from fastapi import Depends

from api.dependencies.admin_auth import require_admin
from api.error_contracts import typed_http_error
from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.registry_deletion_repository import MySqlRegistryDeletionRepository
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.registry_deletion import RegistryDeletionApplication


def require_registry_deletion_root(principal: AdminPrincipal = Depends(require_admin)) -> AdminPrincipal:
    if principal.id is None or not principal.enabled or not principal.is_root:
        raise typed_http_error(403, "forbidden", "registry_deletion_root_required", "僅已登入的 root 管理員可永久刪除資料。", "registry-deletion-auth")
    return principal


def get_registry_deletion_application(_principal: AdminPrincipal = Depends(require_registry_deletion_root)):
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        yield RegistryDeletionApplication(MySqlRegistryDeletionRepository(connection), lambda: MySqlUnitOfWork(connection))
    finally:
        connection.close()
