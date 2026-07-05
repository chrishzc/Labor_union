import os
import sys
import json
import openpyxl

sys.stdout.reconfigure(encoding='utf-8')

# 純標籤表頭與公式引用剔除清單
EXCLUDE_TEXTS = [
    "三、自費服務時數及費用單價:", "服務時薪費用:", "款項", "金額", "匯款日期",
    "訂金", "第一期款", "第二期款", "樓層費用", "應匯款項 (逾時未匯款者，乙方可暫停合約。)",
    "新竹市月子照顧服務人員職業工會", "服務款項匯款帳號：(代收付)"
]

EXCLUDE_FORMULAS = ["=F24", "=F25", "=B38", "=E28", "=C10", "TODAY()"]

with open("scratch/param_list_step3.json", "r", encoding="utf-8") as f:
    raw_list = json.load(f)

refined_list = []
idx = 1
for item in raw_list:
    text = item["orig_text"]
    if text in EXCLUDE_TEXTS or text in EXCLUDE_FORMULAS or text.startswith("=IFERROR"):
        continue
    
    # 指派精確 P 標籤
    p_tag = f"P{idx}"
    item["param_tag"] = p_tag
    refined_list.append(item)
    idx += 1

print(f"🎯 經過精細審查，過濾掉純標題與公式引用後，共有 【{len(refined_list)}】 個核心動態資料填空點：\n")
print(f"{'標籤':<6s} | {'座標':<6s} | {'Excel 原始標籤內容':<35s}")
print("-" * 55)
for item in refined_list:
    print(f"{item['param_tag']:<6s} | {item['coord']:<6s} | {item['orig_text']:<35s}")

with open("scratch/param_list_refined.json", "w", encoding="utf-8") as f:
    json.dump(refined_list, f, ensure_ascii=False, indent=2)

