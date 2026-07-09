import sys
import os
import pymysql
from dotenv import load_dotenv

# 載入環境變數
load_dotenv()

# 確保中文輸出編碼正確
sys.stdout.reconfigure(encoding='utf-8')

# 資料庫連線配置 (同 import_excel.py，但先不指定 database，因為 sql 檔內含 CREATE DATABASE)
DB_CONFIG = {
    'host': os.getenv("DB_HOST", "127.0.0.1"),
    'port': int(os.getenv("DB_PORT", "3306")),
    'user': os.getenv("DB_USER", "root"),
    'password': os.getenv("DB_PASSWORD", "1234"),
    'charset': 'utf8mb4'
}

def main():
    schema_path = r'db/schema.sql'
    if not os.path.exists(schema_path):
        # 嘗試相對路徑
        schema_path = os.path.join(os.path.dirname(__file__), '..', 'db', 'schema.sql')
        
    if not os.path.exists(schema_path):
        print(f"錯誤：找不到 schema.sql 檔案，路徑：{schema_path}")
        return

    print(f"正在讀取 {schema_path}...")
    with open(schema_path, 'r', encoding='utf-8') as f:
        sql_content = f.read()

    # 簡單用分號分割 SQL 語句 (排除空行)
    # ponytail: split by semicolon and filter out comments or empty statements
    statements = []
    current_stmt = []
    for line in sql_content.split('\n'):
        # 忽略單行注釋
        if line.strip().startswith('--'):
            continue
        if ';' in line:
            parts = line.split(';')
            current_stmt.append(parts[0])
            statements.append('\n'.join(current_stmt).strip())
            current_stmt = [parts[1]] if len(parts) > 1 else []
        else:
            current_stmt.append(line)
            
    if current_stmt and '\n'.join(current_stmt).strip():
        statements.append('\n'.join(current_stmt).strip())

    print(f"解析出 {len(statements)} 個 SQL 語句，準備執行...")
    
    try:
        connection = pymysql.connect(**DB_CONFIG)
        with connection.cursor() as c:
            c.execute("SET NAMES utf8mb4;")
        print("成功連線至 MySQL 伺服器！")
    except Exception as e:
        print(f"無法連線至 MySQL 伺服器：{e}\n請確認 Docker 中的 MySQL 容器是否已啟動，且連接埠為 3306。")
        return

    success_count = 0
    try:
        with connection.cursor() as cursor:
            for i, stmt in enumerate(statements):
                stmt_clean = stmt.strip()
                if not stmt_clean:
                    continue
                try:
                    cursor.execute(stmt_clean)
                    success_count += 1
                except Exception as stmt_err:
                    print(f"執行第 {i+1} 個語句時出錯：{stmt_err}")
                    print(f"出錯語句：\n{stmt_clean[:200]}...\n")
                    raise stmt_err
            
            connection.commit()
            print(f"\n====== 資料庫 Schema 更新成功！共執行 {success_count} 個語句 ======")
            
            # 匯入預設國定假日到 roc_holidays 資料表
            try:
                project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
                if project_root not in sys.path:
                    sys.path.append(project_root)
                from admin.utils import ROC_HOLIDAYS
                
                with connection.cursor() as cursor_holiday:
                    cursor_holiday.execute("USE union_db;")
                    insert_query = """
                        INSERT INTO roc_holidays (holiday_date, holiday_name, is_custom) 
                        VALUES (%s, %s, FALSE) 
                        ON DUPLICATE KEY UPDATE holiday_name = VALUES(holiday_name);
                    """
                    holiday_data = [(date_str, name) for date_str, name in ROC_HOLIDAYS.items()]
                    cursor_holiday.executemany(insert_query, holiday_data)
                connection.commit()
                print(f"成功預載 {len(holiday_data)} 筆國定假日資料至 roc_holidays 表格。")
            except Exception as holiday_err:
                print(f"預載國定假日資料時出錯：{holiday_err}")
    except Exception as e:
        connection.rollback()
        print(f"執行失敗，已回滾所有變更。錯誤原因：{e}")
    finally:
        connection.close()
        print("資料庫連線已關閉。")

if __name__ == '__main__':
    main()
