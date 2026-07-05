import os
import sys
import glob
import openpyxl

sys.stdout.reconfigure(encoding='utf-8')

target_files = glob.glob("document/**/*.xlsx", recursive=True)
print("找到的 Excel 檔案列表：")
for f in target_files:
    print(" -", f)
    if "所需表格" in f and not os.path.basename(f).startswith("~$"):
        wb = openpyxl.load_workbook(f, data_only=False)
        print("  【所需表格.xlsx】的分頁列表 (Sheets):", wb.sheetnames)
