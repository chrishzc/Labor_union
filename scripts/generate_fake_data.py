# -*- coding: utf-8 -*-
"""
專案名稱: Lobar_union
檔案名稱: scripts/generate_fake_data.py
作者: Antigravity
描述: 統一生成系統測試所需的各類 Excel 假資料。
      此腳本合併並取代了舊有的 generate_fake_excel.py 與 generate_fake_finance.py，
      同時為名冊（HCM、BeClass、服務人員）與財務流水帳生成一致、對齊且無隱私問題的測試數據。
"""
import sys
import os
import random
import pandas as pd
from datetime import datetime, timedelta

# 確保中文輸出編碼正確
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

# 常用中文姓名隨機元素
surnames = ['王', '陳', '張', '劉', '李', '吳', '黃', '蔡', '楊', '許', '林', '賴', '徐', '周', '趙', '郭', '胡', '高']
names = ['明', '華', '強', '偉', '洋', '豪', '傑', '翔', '安', '美', '婷', '欣', '晴', '宇', '廷', '冠', '奕', '宥', '建', '俊', '雅', '涵', '萱', '茹', '君', '嘉', '琪', '威', '宏', '英', '玲', '芳']

def generate_fake_name():
    length = random.choice([2, 3])
    if length == 2:
        return random.choice(surnames) + random.choice(names)
    else:
        return random.choice(surnames) + random.choice(names) + random.choice(names)

def generate_fake_phone():
    return "09" + "".join([str(random.randint(0, 9)) for _ in range(8)])

def generate_fake_ip():
    return f"100.100.{random.randint(1, 254)}.{random.randint(1, 254)}"

def generate_fake_address():
    districts = ['香山區', '東區', '北區', '竹北市', '竹東鎮', '湖口鄉']
    streets = ['中華路', '光復路', '經國路', '測試路', '和平街', '民權路', '中央路', '中山路']
    return f"新竹市{random.choice(districts)}{random.choice(streets)}{random.randint(1, 999)}號"

def generate_fake_line_id():
    return f"user_{random.randint(100000, 999999)}"

def generate_fake_id_card():
    letter = random.choice('ABCDEFGHJKLMNPQRSTUVXYWZIO')
    gender_digit = random.choice(['1', '2']) # 1 for male, 2 for female
    digits = "".join([str(random.randint(0, 9)) for _ in range(7)])
    
    letter_values = {
        'A':10, 'B':11, 'C':12, 'D':13, 'E':14, 'F':15, 'G':16, 'H':17, 'J':18,
        'K':19, 'L':20, 'M':21, 'N':22, 'P':23, 'Q':24, 'R':25, 'S':26, 'T':27,
        'U':28, 'V':29, 'X':30, 'Y':31, 'W':32, 'Z':33, 'I':34, 'O':35
    }
    val = letter_values[letter]
    sum_val = (val // 10) + (val % 10) * 9
    sum_val += int(gender_digit) * 8
    for idx, d in enumerate(digits):
        sum_val += int(d) * (7 - idx)
    check_digit = (10 - (sum_val % 10)) % 10
    return f"{letter}{gender_digit}{digits}{check_digit}"

def generate_fake_signup_time():
    start_date = datetime.now() - timedelta(days=60)
    random_days = random.randint(0, 60)
    random_hours = random.randint(0, 23)
    random_minutes = random.randint(0, 59)
    random_seconds = random.randint(0, 59)
    fake_date = start_date + timedelta(days=random_days, hours=random_hours, minutes=random_minutes, seconds=random_seconds)
    return fake_date.strftime("%Y/%m/%d %H:%M:%S")

def generate_fake_due_date():
    start_date = datetime.now() + timedelta(days=30)
    random_days = random.randint(0, 150)
    due_date = start_date + timedelta(days=random_days)
    return due_date.strftime("%Y/%m/%d")

def generate_fake_service_start_date(due_date_str):
    try:
        due_date = datetime.strptime(due_date_str, "%Y/%m/%d")
    except Exception:
        due_date = datetime.now()
    service_date = due_date + timedelta(days=random.randint(3, 10))
    return service_date.strftime("%Y/%m/%d")

def fill_checkbox_group(row_dict, options, summary_col):
    k = random.randint(1, len(options))
    selected = random.sample(options, k)
    for opt in options:
        row_dict[opt] = 'Y' if opt in selected else None
    row_dict[summary_col] = '、'.join(selected)

def generate_roster_data(input_file, output_file, personal_data_pool, num_records):
    """
    產生包含 HCM 客戶、BeClass 客戶與服務人員的測試名冊 Excel 檔案。
    """
    print("正在讀取原始範本 Excel 的三個分頁...")
    df_clients_template = pd.read_excel(input_file, sheet_name='HCM 月子平台 -市府')
    df_beclass_template = pd.read_excel(input_file, sheet_name='beclass')
    df_staff_template = pd.read_excel(input_file, sheet_name='服務人員')
    
    if len(df_clients_template) == 0 or len(df_beclass_template) == 0 or len(df_staff_template) == 0:
        raise ValueError("範本 Excel 中缺少必要欄位或資料。")

    print(f"-> 正在生成 HCM 月子平台 -市府 假資料 (案號與財務流水帳對齊)...")
    clients_template_row = df_clients_template.iloc[0].to_dict()
    fake_clients_rows = []
    base_case_no = 115000000  # 使用 115 年度案號，與財務對帳對齊

    for i in range(num_records):
        row = clients_template_row.copy()
        p_data = personal_data_pool[i]
        case_no = base_case_no + (i + 1)
        
        row['項次'] = i + 1
        row['案件狀態'] = random.choice(['符合', '符合', '符合', '不符合'])
        row['不符合原因'] = '資格不符測試' if row['案件狀態'] == '不符合' else None
        row['查詢序號(案件編號)'] = case_no
        row['查詢序號(案件編號).1'] = case_no
        
        signup_time = generate_fake_signup_time()
        due_date = generate_fake_due_date()
        service_date = generate_fake_service_start_date(due_date)
        
        row['報名時間(建檔)'] = signup_time
        row['預產期/預計服務開始月份'] = due_date
        row['預計服務日期'] = service_date
        
        row['IP位址'] = p_data['ip']
        row['姓名'] = p_data['name']
        row['性別'] = random.choice(['男', '女'])
        row['行動電話'] = p_data['phone']
        row['地址'] = p_data['address']
        row['LINE ID'] = p_data['line_id']
        
        row['希望服務天數'] = random.choice([15, 20, 30, 40])
        row['生產方式'] = random.choice(['自然產', '剖腹產'])
        row['寶寶資訊'] = random.choice(['第一胎', '第二胎', '雙胞胎'])
        row['管理者註記事項'] = f"服務期間:{due_date}~{service_date} (測試)"
        
        fake_clients_rows.append(row)

    df_clients_result = pd.DataFrame(fake_clients_rows)

    print("-> 正在生成 服務人員 假資料...")
    staff_template_row = df_staff_template.iloc[0].to_dict()
    fake_staff_rows = []

    for i in range(num_records):
        row = staff_template_row.copy()
        p_data = personal_data_pool[i]
        
        row['項次'] = i + 1
        row['查詢序號'] = f"E{100+i:03d}{p_data['name']}"
        row['報名時間'] = generate_fake_signup_time()
        row['IP位址'] = f"E{100+i:03d}"
        row['姓名'] = p_data['name']
        row['銀行帳號'] = str(random.randint(100000000000, 999999999999))
        row['銀行代3碼+分行代號4碼'] = f"{random.randint(100, 999):03d}{random.randint(1000, 9999):04d}"
        row['身分證字號'] = p_data['id_card']
        row['行動電話'] = p_data['phone']
        row['EMAIL'] = p_data['email']
        
        birth_year = random.randint(50, 85)
        birth_month = random.randint(1, 12)
        birth_day = random.randint(1, 28)
        row['出生年'] = birth_year
        row['月'] = birth_month
        row['日'] = birth_day
        row['民國出生年月日'] = f"{birth_year + 1911}-{birth_month:02d}-{birth_day:02d}"
        row['市話'] = f"03-5{random.randint(100, 999):03d}{random.randint(100, 999):03d}" if random.random() > 0.5 else None
        row['分機'] = None
        row['縣市'] = random.choice(['新竹市', '新竹縣', '苗栗縣'])
        
        zip_mapping = {'新竹市': '300', '新竹縣': '302', '苗栗縣': '350'}
        row['郵遞區號'] = zip_mapping[row['縣市']]
        row['地址'] = p_data['address']
        row['若有其它同銀行帳號，請一併提供。(永豐或台新)'] = None
        row['承上題'] = random.choice(['我提供的帳號是永豐銀行帳戶', '我提供的帳號是台新銀行帳戶', None])
        
        fill_checkbox_group(row, ['葷食', '素食'], '月子餐點料理')
        row['[其它]'] = None
        
        fill_checkbox_group(row, ['北區', '東區', '香山區', '新竹縣', '苗栗縣'], '可承接案件區域')
        row['[其它].1'] = None
        
        fill_checkbox_group(row, ['4小時(上午8:30-12:30)', '4小時(下午13:00-17:00)', '8小時', '24小時'], '可承接案件時段')
        row['[其它].2'] = None
        
        fill_checkbox_group(row, ['連續服務', '週休1日', '週休2日'], '可服務週間')
        row['[其它].3'] = None
        
        fill_checkbox_group(row, ['單胞胎', '雙胞胎'], '可承接的胎數')
        row['[其它].4'] = None
        
        fill_checkbox_group(row, ['機車', '轎車'], '服務時交通工具')
        
        holiday_opts = ['年節農曆過年初一', '年節農曆過年初二', '年節農曆過年初三', '端午節', '中秋節', '國定假日必休']
        fill_checkbox_group(row, holiday_opts, '特殊節日可上班的部分(計費:服務費雙倍)')
        row['[其它].5'] = None
        row['有嬰幼兒按摩證書嗎?'] = random.choice(['有', '無'])
        
        fake_staff_rows.append(row)

    df_staff_result = pd.DataFrame(fake_staff_rows)

    print("-> 正在生成 beclass 假資料...")
    df_beclass_template_row = df_beclass_template.iloc[0].to_dict()
    fake_beclass_rows = []
    base_query_no = 28755000

    for i in range(num_records):
        row = df_beclass_template_row.copy()
        p_data = personal_data_pool[i]
        
        row['項次'] = i + 1
        row['查詢序號'] = base_query_no + i
        
        clients_signup_dt = datetime.strptime(fake_clients_rows[i]['報名時間(建檔)'], "%Y/%m/%d %H:%M:%S")
        row['報名時間'] = clients_signup_dt.strftime("%m-%d %H:%M")
        
        row['訂單編號'] = f"HC115{random.randint(100, 999):03d}"
        row['姓名'] = p_data['name']
        row['性別'] = random.choice(['男', '女'])
        row['Email'] = p_data['email']
        row['出生年'] = random.randint(1980, 2000)
        row['月'] = random.randint(1, 12)
        row['日'] = random.randint(1, 28)
        row['行動電話'] = p_data['phone']
        row['地址'] = p_data['address']
        row['市話'] = f"03-5{random.randint(100, 999):03d}{random.randint(100, 999):03d}" if random.random() > 0.5 else None
        
        for col in row.keys():
            if col.startswith('□') or col in ['葷食', '素食', '全酒', '半酒', '米酒水', '無酒料理', '有', '無(願意負擔停車費用)']:
                row[col] = 'Y' if random.random() > 0.5 else None
        
        row['管理者註記事項'] = random.choice(['大寶1歲', '二寶出生', '需要提早', None])
        
        fake_beclass_rows.append(row)

    df_beclass_result = pd.DataFrame(fake_beclass_rows)

    print("正在將三個分頁寫入名冊 Excel 檔案中...")
    with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
        df_clients_result.to_excel(writer, sheet_name='HCM 月子平台 -市府', index=False)
        df_staff_result.to_excel(writer, sheet_name='服務人員', index=False)
        df_beclass_result.to_excel(writer, sheet_name='beclass', index=False)
        
    print(f"成功！已生成名冊檔案：{output_file}")

def generate_finance_data(output_file, personal_data_pool):
    """
    產生包含「合作社帳戶」(流水帳) 與「資料庫」(案件財務對照表) 的測試假帳務 Excel 檔案。
    """
    print("-> 正在生成財務假資料...")
    
    # 使用前 10 筆個人資料的姓名作為財務測試案例，確保兩份 Excel 名字與案號 100% 對齊
    base_cases = [f"1150000{i:02d}" for i in range(1, 11)]
    client_names = [personal_data_pool[i]['name'] for i in range(10)]
    
    # 1. 生成「資料庫」分頁 (案件對照表)
    db_rows = []
    for idx, case_no in enumerate(base_cases):
        seq = idx + 1
        name = client_names[idx]
        
        # 虛擬帳號後 6 碼為：年度 (115) + 流水號後三碼 (001-010)
        va_suffix = f"115{seq:03d}"
        virtual_account = f"99781699{va_suffix}"
        
        amount_receivable = 80000
        caregiver_fee = 60000
        
        db_rows.append([
            "HC", seq, "新竹市月子服務工會", name, 115.0, seq, 1.0, virtual_account,
            amount_receivable, caregiver_fee, name, f"{case_no}案"
        ])
        
    df_db = pd.DataFrame(db_rows)
    df_db.columns = [f"Unnamed: {i}" for i in range(df_db.shape[1])]
    
    # 2. 生成「合作社帳戶」分頁 (銀行流水帳)
    tx_rows = []
    base_account = "03201800231313"
    current_balance = 500000.0
    
    tx_rows.append([
        "帳號/姓名:03201800231313 新竹市月子照顧服務人員職業工會\n帳戶:03201800231313 TWD\n區間:2026/07/01 00:00~2026/07/31 23:59",
        None, None, None, None, None, None, None, "列印時間:2026/08/01 10:00:00", None, None
    ])
    tx_rows.append([
        "帳號", "交易時間", "記帳日期", "入帳日期", "交易摘要", "幣別", "支出", "存入", "餘額", "虛擬帳號/轉帳備註", "備用"
    ])
    
    # 依序為 10 筆案件生成：
    # 1. 存入訂金 12,000 (所有案件)
    # 2. 存入尾款 68,000 (部分案件)
    # 3. 支出月嫂費用 60,000 (部分案件)
    for idx, case_no in enumerate(base_cases):
        seq = idx + 1
        va_suffix = f"115{seq:03d}"
        va = f"99781699{va_suffix}"
        
        tx_time_dep = f"2026/07/{seq:02d} 10:00:00"
        tx_date_dep = f"2026/07/{seq:02d}"
        
        # 1. 存入訂金 (12,000)
        current_balance += 12000
        tx_rows.append([
            base_account, tx_time_dep, tx_date_dep, tx_date_dep, "虛擬帳入", "TWD", None, 12000, current_balance, va, None
        ])
        
        # 2. 存入尾款 (68,000) (只有 seq 1-7 有存入尾款)
        if seq <= 7:
            tx_time_bal = f"2026/07/{seq+10:02d} 14:00:00"
            tx_date_bal = f"2026/07/{seq+10:02d}"
            current_balance += 68000
            tx_rows.append([
                base_account, tx_time_bal, tx_date_bal, tx_date_bal, "虛擬帳入", "TWD", None, 68000, current_balance, va, None
            ])
            
        # 3. 支出月嫂費用 (60,000) (只有 seq 1-5 結案撥款)
        if seq <= 5:
            tx_time_pay = f"2026/07/{seq+15:02d} 16:00:00"
            tx_date_pay = f"2026/07/{seq+15:02d}"
            current_balance -= 60000
            tx_rows.append([
                base_account, tx_time_pay, tx_date_pay, tx_date_pay, "一般轉出", "TWD", 60000, None, current_balance, f"月嫂撥款 {personal_data_pool[idx]['name']}", None
            ])
            
    # 4. 插入雜訊款項 (非 997816 開頭，或分類碼非 99 的托育學費等雜訊，用來驗證 Pipeline 過濾能力)
    noise_transactions = [
        ("2026/07/05 09:30:00", 2500, "網銀轉入", "99781601001001", "托育課程費"), # 分類碼 01 (托育) 非 99
        ("2026/07/12 11:20:00", 15000, "臨櫃存入", "12345678901234", "常規捐款"),     # 帳號完全不符合前綴
        ("2026/07/20 15:45:00", 3000, "虛擬帳入", "99781602002002", "保母課程費")   # 分類碼 02 (保母)
    ]
    for idx, (tx_time, amt, summary, memo, backup) in enumerate(noise_transactions):
        current_balance += amt
        tx_rows.append([
            base_account, tx_time, tx_time[:10], tx_time[:10], summary, "TWD", None, amt, current_balance, memo, backup
        ])
        
    df_tx = pd.DataFrame(tx_rows)
    df_tx.columns = [f"Unnamed: {i}" for i in range(df_tx.shape[1])]
    
    print("正在將分頁寫入財務對帳 Excel 檔案中...")
    with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
        df_tx.to_excel(writer, sheet_name='合作社帳戶', index=False, header=False)
        df_db.to_excel(writer, sheet_name='資料庫', index=False, header=False)
        
    print(f"成功！已生成財務對帳檔案：{output_file}")

def main():
    print("正在初始化生成假資料程序...")
    
    # 確保資料處理資料夾存在
    base_dir = os.path.dirname(os.path.abspath(__file__))
    output_dir = os.path.join(base_dir, '..', 'document', '資料庫、資料處理')
    os.makedirs(output_dir, exist_ok=True)
    
    input_file = os.path.join(output_dir, '資料庫來源表.xlsx')
    roster_output_file = os.path.join(output_dir, '假資料_範例.xlsx')
    finance_output_file = os.path.join(output_dir, '帳務.xlsx')
    
    if not os.path.exists(input_file):
        print(f"錯誤：找不到來源模板檔案，預計路徑為：{input_file}")
        sys.exit(1)
        
    num_records = 50
    print(f"開始生成 {num_records} 筆核心測試個人資訊...")
    
    personal_data_pool = []
    for i in range(num_records):
        name = generate_fake_name()
        phone = generate_fake_phone()
        email = f"test_{phone[-4:]}@example.com"
        address = generate_fake_address()
        line_id = generate_fake_line_id()
        ip = generate_fake_ip()
        id_card = generate_fake_id_card()
        
        personal_data_pool.append({
            'name': name,
            'phone': phone,
            'email': email,
            'address': address,
            'line_id': line_id,
            'ip': ip,
            'id_card': id_card
        })
        
    # 1. 產生名冊假資料
    try:
        generate_roster_data(input_file, roster_output_file, personal_data_pool, num_records)
    except Exception as e:
        print(f"生成名冊假資料失敗: {e}")
        sys.exit(1)
        
    # 2. 產生財務假資料 (傳入相同個人資料池，對齊前 10 筆)
    try:
        generate_finance_data(finance_output_file, personal_data_pool)
    except Exception as e:
        print(f"生成財務假資料失敗: {e}")
        sys.exit(1)
        
    print("\n====== 所有假資料生成完成，名冊與財務測試數據已 100% 關聯對齊！ ======")

if __name__ == "__main__":
    main()
