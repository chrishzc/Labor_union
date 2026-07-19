# -*- coding: utf-8 -*-
import os
import sys
import pandas as pd
import pymysql
from datetime import datetime, date, timedelta
from dotenv import load_dotenv

# 讀取環境變數
load_dotenv()

# 取得資料庫配置
DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("DB_PORT", 3306))
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "1234")
DB_DATABASE = os.getenv("DB_DATABASE", "union_db")

HISTORICAL_HEADER_ALIASES = {
    "client_name": {"client_name", "name", "客戶", "客戶姓名", "姓名"},
    "case_no": {"case_no", "案件編號", "查詢序號", "訂單編號"},
    "start_date": {"start_date", "服務開始", "服務開始日", "實際服務開始日"},
    "end_date": {"end_date", "服務結束", "服務結束日", "實際服務結束日"},
    "status": {"status", "狀態", "訂單狀態", "訂單成立狀態"},
    "staff_name": {"staff_name", "服務人員", "月嫂", "月嫂姓名"},
}
LEGACY_IDENTIFIER_HEADERS = {"id", "order_id", "orderid", "訂單id", "訂單_id"}


def normalize_header(value) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip().lower().replace(" ", "")


def normalize_case_no(value) -> str | None:
    if pd.isna(value) or str(value).strip() == "":
        return None
    text = str(value).strip()
    return text[:-2] if text.endswith(".0") and text[:-2].isdigit() else text


def load_historical_frame(excel_path: str) -> pd.DataFrame:
    """Load a named export or the strict six-column legacy layout.

    Named imports use an allowlist, so unknown columns (including id/order_id)
    are ignored. Headerless files with extra columns are rejected rather than
    silently shifting values into the wrong fields.
    """
    raw = pd.read_excel(excel_path, header=None)
    if raw.empty:
        return raw

    first_row = [normalize_header(value) for value in raw.iloc[0].tolist()]
    alias_to_field = {
        normalize_header(alias): field
        for field, aliases in HISTORICAL_HEADER_ALIASES.items()
        for alias in aliases
    }
    recognized = {alias_to_field[value] for value in first_row if value in alias_to_field}
    if {"client_name", "case_no"}.issubset(recognized):
        selected = {}
        for position, header in enumerate(first_row):
            if header in LEGACY_IDENTIFIER_HEADERS:
                continue
            field = alias_to_field.get(header)
            if field and field not in selected:
                selected[field] = raw.iloc[1:, position].reset_index(drop=True)
        return pd.DataFrame(selected)

    if raw.shape[1] != 6:
        raise ValueError(
            "無表頭歷史訂單必須正好有 6 欄；偵測到額外欄位，為避免 id/order_id 造成欄位位移已停止匯入"
        )
    raw = raw.copy()
    raw.columns = ["client_name", "case_no", "start_date", "end_date", "status", "staff_name"]
    return raw

def parse_excel_date(val):
    if pd.isna(val) or val == "" or str(val).strip() == "":
        return None
    try:
        # 若為 Excel 數值型態日期 (以 1899-12-30 為基準)
        num_val = float(val)
        return (datetime(1899, 12, 30) + timedelta(days=int(num_val))).date()
    except (ValueError, TypeError):
        # 若為一般日期字串 (如 2025/6/4)
        try:
            return pd.to_datetime(val).date()
        except:
            return None

def map_status(val):
    if pd.isna(val) or val == "" or str(val).strip() == "":
        return "訂單取消"
    try:
        status_num = int(float(val))
        if status_num == 0:
            return "訂單取消"
        elif status_num == 1:
            return "訂單完成"
        elif status_num == 2:
            return "洽談中"
    except (ValueError, TypeError):
        pass
    return "洽談中"

def _result(inserted=0, skipped_existing=0, review_required=0, failed=0):
    return {
        "inserted": inserted,
        "skipped_existing": skipped_existing,
        "review_required": review_required,
        "failed": failed,
    }


def _count_value(row):
    if not row:
        return 0
    if isinstance(row, dict):
        value = row.get("record_count", 0)
    else:
        value = row[0]
    return int(value or 0)


def process_import(excel_path):
    if not os.path.exists(excel_path):
        print(f"錯誤: 找不到 Excel 檔案 {excel_path}")
        return _result(review_required=1)
        
    try:
        df = load_historical_frame(excel_path)
    except Exception as e:
        print(f"錯誤: 無法讀取 Excel 檔案 - {str(e)}")
        return _result(review_required=1)
        
    print(f"成功讀取 Excel 檔案，共 {len(df)} 筆資料。開始進行新增檢查...")
    
    try:
        conn = pymysql.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_DATABASE,
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor
        )
    except Exception as e:
        print(f"錯誤: 無法連線至資料庫 - {str(e)}")
        return _result(failed=1)

    inserted = 0
    skipped_existing = 0
    review_required = 0

    try:
        with conn.cursor() as cursor:
            for _, row in df.iterrows():
                case_no = normalize_case_no(row.get("case_no"))
                if not case_no:
                    review_required += 1
                    continue

                cursor.execute(
                    "SELECT COUNT(*) AS record_count FROM orders WHERE case_no = %s",
                    (case_no,),
                )
                if _count_value(cursor.fetchone()) > 0:
                    skipped_existing += 1
                    continue

                cursor.execute(
                    "SELECT id FROM clients WHERE case_no = %s",
                    (case_no,),
                )
                clients = cursor.fetchall()
                if len(clients) != 1:
                    review_required += 1
                    continue

                client_id = clients[0]["id"] if isinstance(clients[0], dict) else clients[0][0]
                cursor.execute(
                    """
                    INSERT INTO orders
                        (case_no, client_id, actual_start_date, actual_end_date, status)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (
                        case_no,
                        client_id,
                        parse_excel_date(row.get("start_date")),
                        parse_excel_date(row.get("end_date")),
                        map_status(row.get("status")),
                    ),
                )
                inserted += 1

        conn.commit()
    except Exception as err:
        conn.rollback()
        print(f"執行發生錯誤，已 Rollback：{err}")
        return _result(
            inserted=0,
            skipped_existing=skipped_existing,
            review_required=review_required,
            failed=1,
        )
    finally:
        conn.close()

    print(
        f"匯入完成：新增 {inserted} 筆歷史訂單、"
        f"略過既有 {skipped_existing} 筆、待確認 {review_required} 筆。"
    )
    return _result(
        inserted=inserted,
        skipped_existing=skipped_existing,
        review_required=review_required,
    )


def main():
    if len(sys.argv) < 2:
        print("使用方式: python scripts/import_historical_orders.py <excel_file_path>")
        sys.exit(1)
    result = process_import(sys.argv[1])
    if result["failed"]:
        sys.exit(1)

if __name__ == "__main__":
    main()
