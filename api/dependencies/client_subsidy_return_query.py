"""Own the read-only connection lifetime for the subsidy-return query."""

from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.subsidy_return_query_repository import MySqlSubsidyReturnQueryRepository


def get_subsidy_return_query_repository():
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute('START TRANSACTION READ ONLY')
        yield MySqlSubsidyReturnQueryRepository(connection)
    finally:
        connection.rollback()
        connection.close()
