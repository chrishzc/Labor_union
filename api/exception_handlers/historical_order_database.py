"""Closed, privacy-safe database diagnostics for historical workbook HTTP boundaries."""

import logging

from fastapi import HTTPException
from pymysql import MySQLError
from pymysql.constants import CR, ER


logger = logging.getLogger(__name__)
_DATABASE_ERRORS = {
    CR.CR_CONNECTION_ERROR: ("connect_failed", "無法連接資料庫；請檢查資料庫服務與連線設定", True),
    CR.CR_CONN_HOST_ERROR: ("connect_failed", "無法連接資料庫；請檢查主機、連接埠與網路", True),
    CR.CR_UNKNOWN_HOST: ("host_not_found", "無法解析資料庫主機名稱；請檢查主機設定與 DNS", False),
    CR.CR_SERVER_GONE_ERROR: ("connection_lost", "資料庫連線已中斷；請檢查服務狀態與連線紀錄", True),
    CR.CR_SERVER_LOST: ("connection_lost", "資料庫執行期間連線中斷；請檢查服務狀態與連線紀錄", True),
    CR.CR_SERVER_LOST_EXTENDED: ("connection_lost", "資料庫執行期間連線中斷；請檢查服務狀態與連線紀錄", True),
    CR.CR_SSL_CONNECTION_ERROR: ("tls_failed", "資料庫加密連線失敗；請檢查憑證與加密連線設定", False),
    ER.ACCESS_DENIED_ERROR: ("authentication_failed", "資料庫登入失敗；請管理員檢查連線帳號與驗證設定", False),
    **{code: ("permission_denied", "資料庫操作權限不足；請管理員核對匯入帳號的必要權限", False)
       for code in (ER.DBACCESS_DENIED_ERROR, ER.TABLEACCESS_DENIED_ERROR, ER.COLUMNACCESS_DENIED_ERROR,
                    ER.SPECIFIC_ACCESS_DENIED_ERROR, ER.PROCACCESS_DENIED_ERROR)},
    ER.BAD_DB_ERROR: ("not_found", "指定的資料庫不存在；請檢查資料庫名稱與部署設定", False),
    ER.NO_SUCH_TABLE: ("table_missing", "缺少必要資料表；請檢查連線目標與資料庫升級狀態", False),
    ER.BAD_FIELD_ERROR: ("column_missing", "缺少必要資料欄位；請檢查程式與資料庫版本是否一致", False),
    ER.SP_DOES_NOT_EXIST: ("routine_missing", "缺少必要資料庫程序；請檢查資料庫升級與程序安裝狀態", False),
    ER.LOCK_WAIT_TIMEOUT: ("lock_wait_exceeded", "等待資料庫資料鎖逾時；請查核佔鎖交易，再確認原匯入結果", True),
    ER.LOCK_DEADLOCK: ("deadlock", "資料庫交易發生死結；請查核交易紀錄，再確認原匯入結果", True),
    **{code: ("connection_limit_reached", "資料庫連線已達上限；請檢查連線使用量與連線限制", True)
       for code in (ER.CON_COUNT_ERROR, ER.TOO_MANY_USER_CONNECTIONS, ER.USER_LIMIT_REACHED)},
    ER.PARSE_ERROR: ("query_invalid", "資料庫指令語法錯誤；請系統人員檢查程式與資料庫相容性", False),
    ER.DATA_TOO_LONG: ("data_rejected", "資料超過資料庫欄位長度；請核對來源資料與欄位設定", False),
    **{code: ("constraint_rejected", "資料庫唯一性或關聯限制拒絕寫入；請查核既有資料與匯入規則", False)
       for code in (ER.DUP_ENTRY, ER.NO_REFERENCED_ROW_2, ER.ROW_IS_REFERENCED_2)},
}


def historical_database_http_error(error: MySQLError, correlation_id: str) -> HTTPException:
    raw_number = error.args[0] if error.args else None
    number = raw_number if type(raw_number) is int and 0 < raw_number <= 65535 else 0
    # These two known old-schema failures retain their established public code.
    raw_message = str(error.args[1]) if len(error.args) > 1 else ""
    if (number == 1265 and "resolution" in raw_message) or (
        number == 3819 and "chk_order_lifecycle_state_event_before_status" in raw_message
    ):
        suffix, message, retryable = "upgrade_required", "資料庫結構尚未升級；請完成資料庫更新後再確認匯入結果", False
    else:
        suffix, message, retryable = _DATABASE_ERRORS.get(number, (
            f"mysql_{number}" if number else "unknown_error",
            "資料庫回報未分類錯誤；請系統人員依錯誤代碼與追蹤編號查核", False,
        ))
    code = f"historical_order_database_{suffix}"
    logger.error("Historical workbook database failure code=%s mysql_errno=%s correlation_id=%s", code, number, correlation_id)
    return HTTPException(status_code=503, detail={"error": {
        "category": "unavailable", "code": code,
        "message": f"{message}（MySQL {number}）。" if number else f"{message}。",
        "field_errors": [], "domain_blockers": [], "retryable": retryable,
        "correlation_id": correlation_id, "current_version": None,
    }})
