"""
File: init_db.py
Description: 以唯一 schema assembly 初始化本機資料庫，不從目錄推導 fresh schema。
"""

import sys
import os
import re
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.sql_statements import split_sql
from scripts.schema_assembly import load_schema_assembly

# 確保中文輸出編碼正確
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

# 從專案根目錄的 .env 讀取資料庫連線設定 (若 .env 不存在或缺少某欄位，則回退為原本的預設值)
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

# 資料庫連線配置 (同 import_excel.py，但先不指定 database，因為 sql 檔內含 CREATE DATABASE)
DB_CONFIG = {
    'host': os.getenv('DB_HOST', '127.0.0.1'),
    'port': int(os.getenv('DB_PORT', 3306)),
    'user': os.getenv('DB_USER', 'root'),
    'password': os.getenv('DB_PASSWORD', '1234'),
    'charset': 'utf8mb4'
}


def load_schema_parts(cursor, schema_parts_dir):
    """Execute UTF-8 schema fragments in stable dependency order."""
    parts_dir = Path(schema_parts_dir)
    assert parts_dir.name == "schema_parts" or parts_dir.exists()
    return load_schema_paths(
        cursor, sorted(parts_dir.glob("*.sql"), key=_schema_part_sort_key)
    )


def load_schema_paths(cursor, part_paths):
    """Execute an explicitly selected ordered schema assembly."""
    loaded_parts = []
    for part_path in part_paths:
        sql_content = part_path.read_text(encoding="utf-8")
        try:
            for statement in split_sql(sql_content):
                cursor.execute(statement)
        except Exception as exc:
            raise RuntimeError(f"載入 schema part 失敗：{part_path.name}: {exc}") from exc
        loaded_parts.append(part_path.name)
    return loaded_parts


def _schema_part_sort_key(path: Path) -> tuple[int, str, str]:
    if path.name == "179_line_identity_canonical_menu_publication.sql":
        # Stage 13 was numbered before its stage-12 root; preserve release names,
        # but replay the additive repair immediately after part 186.
        return 186, "z", path.name
    match = re.match(r"^(\d+)([a-z]*)_", path.name, re.IGNORECASE)
    if match:
        return int(match.group(1)), match.group(2).lower(), path.name
    return 10**9, "", path.name

def main(argv: list[str] | None = None) -> int:
    """Retired executable entrypoint; schema helpers remain importable.

    Fresh schema work is owned by ``scripts.reset_fake_database``.  Keeping a
    fail-closed shim here prevents old runbooks from silently writing a
    configured database while preserving the helper functions used by tests
    and the canonical disposable bootstrapper.
    """
    del argv
    print(
        "[blocked] scripts.init_db is a library-only schema helper; "
        "use scripts.reset_fake_database for an explicit lu_test_* target.",
        file=sys.stderr,
    )
    return 2

if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
