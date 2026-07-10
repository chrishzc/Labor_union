# -*- coding: utf-8 -*-
import pandas as pd
import json

def main():
    file_path = 'document/資料庫、資料處理/假資料_範例.xlsx'
    
    xl = pd.ExcelFile(file_path)
    target_sheet = None
    for name in xl.sheet_names:
        if '客戶' in name and 'beclass' in name.lower():
            target_sheet = name
            break
            
    if target_sheet:
        df = pd.read_excel(file_path, sheet_name=target_sheet)
        columns = df.columns.tolist()
        print(json.dumps(columns, ensure_ascii=False, indent=2))
    else:
        print("Sheet not found")

if __name__ == '__main__':
    main()
