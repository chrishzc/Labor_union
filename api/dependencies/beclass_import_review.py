"""Per-request BeClass import review application construction."""

from subsystems.case_import.beclass_review_application import (
    BeClassImportReviewApplication,
)
from subsystems.case_import.beclass_import_review_workflow import BeClassImportReviewWorkflow
from infrastructure.mysql.beclass_import_review_repository import (
    BeClassImportReviewMySqlUnitOfWork,
    MySqlBeClassImportReviewRepository,
)
from infrastructure.mysql.beclass_import_review_writer import (
    BeClassImportReviewOwnerCommandUnavailable,
)


def build_beclass_import_review_application(connection):
    repository = MySqlBeClassImportReviewRepository(connection)
    writer = BeClassImportReviewOwnerCommandUnavailable(connection)
    workflow = BeClassImportReviewWorkflow(
        repository, writer, lambda: BeClassImportReviewMySqlUnitOfWork(connection)
    )
    return BeClassImportReviewApplication(workflow)
from infrastructure.mysql.mysql_adapter import get_connection


def get_beclass_import_review_application():
    connection = get_connection()
    try:
        yield build_beclass_import_review_application(connection)
    finally:
        connection.close()


__all__ = [
    "BeClassImportReviewApplication",
    "get_beclass_import_review_application",
]
