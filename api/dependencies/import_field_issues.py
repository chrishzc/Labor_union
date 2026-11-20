"""Compose the Case Import current-field issue Query on one connection."""
from infrastructure.mysql.import_field_issues_repository import MySqlImportFieldIssuesRepository
from infrastructure.mysql.mysql_adapter import get_connection
from subsystems.case_import.current_import_field_issues import CurrentImportFieldIssuesQuery


def build_import_field_issues_query(connection) -> CurrentImportFieldIssuesQuery:
    return CurrentImportFieldIssuesQuery(MySqlImportFieldIssuesRepository(connection))


def get_import_field_issues_query():
    connection = get_connection()
    try:
        yield build_import_field_issues_query(connection)
    finally:
        connection.close()
