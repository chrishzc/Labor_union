import os
import sys
import json

sys.stdout.reconfigure(encoding='utf-8')

json_path = os.path.join("db", "templates", "contracts", "contract_client_copy.json")

with open(json_path, "r", encoding="utf-8") as f:
    config = json.load(f)

mappings = config.get("param_mappings", {})

# 修復 1: E39 連結到 orders.service_hours_per_day
mappings["E39"] = {
    "label": "每日服務時數 (E39)",
    "db_table": "orders (訂單主表 - 36 大業務與金額 calculations)",
    "db_key": "service_hours_per_day"
}

# 修復 2: D40 連結到 clients.bank_code
mappings["D40"] = {
    "label": "雇主退款銀行代號 (D40)",
    "db_table": "clients (客戶主表 - 個人基本資料與市府申請表)",
    "db_key": "bank_code"
}

# 修復 3: E40 連結到 clients.bank_account
mappings["E40"] = {
    "label": "雇主退款銀行帳號 (E40)",
    "db_table": "clients (客戶主表 - 個人基本資料與市府申請表)",
    "db_key": "bank_account"
}

config["param_mappings"] = mappings

with open(json_path, "w", encoding="utf-8") as f:
    json.dump(config, f, ensure_ascii=False, indent=2)

print("✅ E39, D40, E40 在 contract_client_copy.json 中已修復連結成功！")
