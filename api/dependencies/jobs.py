from fastapi import Depends
from infrastructure.mysql.background_job_repository import BackgroundJobRepository
from infrastructure.mysql.mysql_adapter import get_connection

def get_job_repository() -> BackgroundJobRepository:
    conn = get_connection()
    return BackgroundJobRepository(conn)
