"""Per-request BeClass import review application construction."""

from subsystems.case_import.beclass_review_application import (
    BeClassImportReviewApplication,
    build_beclass_import_review_application,
)
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
