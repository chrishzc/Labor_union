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
import argparse
from collections import Counter
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import random
import pandas as pd
from datetime import datetime, timedelta, date
from services.db_service import save_order_rest_dates, generate_default_schedule, get_connection

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
        row['縣市'] = random.choice(['新竹市', '新竹縣', '苗栗縣'])
        row['地址'] = p_data['address']
        row['LINE ID'] = p_data['line_id']
        
        row['希望服務天數'] = random.choice([15, 20, 30, 40])
        row['生產方式'] = random.choice(['自然產', '剖腹產'])
        row['寶寶資訊'] = random.choice(['第一胎', '第二胎', '雙胞胎'])
        
        # 增加多樣性隨機欄位
        row['身分資格'] = random.choice(['一般市民', '一般市民', '一般市民', '低收入戶', '中低收入戶', '非市民'])
        row['服務時間'] = random.choice(['9小時', '9小時', '8小時', '24小時'])
        row['居住型態'] = random.choice(['公寓', '大樓', '透天'])
        row['服務方式'] = random.choice(['週休1日', '週休2日', '連續服務'])
        
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
    
    # 預先生成各筆案件的隨機日數、單價與金額，以確保兩分頁一致
    case_details = {}
    for idx, case_no in enumerate(base_cases):
        days = random.choice([15, 20, 25, 30])
        rate = random.choice([2000, 2200, 2500])
        amount_receivable = days * rate
        deposit = random.choice([1, 2]) * rate
        balance = amount_receivable - deposit

        # ponytail: Split balance into first and second payments
        first_payment = balance // 2
        second_payment = balance - first_payment

        caregiver_fee = int(amount_receivable * 0.85)
        case_details[case_no] = {
            'days': days,
            'rate': rate,
            'amount_receivable': amount_receivable,
            'deposit': deposit,
            'first_payment': first_payment,
            'second_payment': second_payment,
            'caregiver_fee': caregiver_fee
        }

    # 1. 生成「資料庫」分頁 (案件對照表)
    db_rows = []
    for idx, case_no in enumerate(base_cases):
        seq = idx + 1
        name = client_names[idx]
        
        # 虛擬帳號後 6 碼為：年度 (115) + 流水號後三碼 (001-010)
        va_suffix = f"115{seq:03d}"
        virtual_account = f"99781699{va_suffix}"
        
        details = case_details[case_no]
        
        db_rows.append([
            "HC", seq, "新竹市月子服務工會", name, 115.0, seq, 1.0, virtual_account,
            details['amount_receivable'], details['caregiver_fee'], name, f"{case_no}案"
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
    # 1. 存入訂金
    # 2. 存入尾款 (部分案件)
    # 3. 支出月嫂費用 (部分案件)
    for idx, case_no in enumerate(base_cases):
        seq = idx + 1
        va_suffix = f"115{seq:03d}"
        va = f"99781699{va_suffix}"
        
        details = case_details[case_no]
        
        tx_time_dep = f"2026/07/{seq:02d} 10:00:00"
        tx_date_dep = f"2026/07/{seq:02d}"
        
        # 1. 存入訂金
        current_balance += details['deposit']
        tx_rows.append([
            base_account, tx_time_dep, tx_date_dep, tx_date_dep, "虛擬帳入", "TWD", None, details['deposit'], current_balance, va, None
        ])
        
        # 2. 存入第一期款 (只有 seq 1-7 有存入)
        if seq <= 7:
            tx_time_p1 = f"2026/07/{seq+10:02d} 14:00:00"
            tx_date_p1 = f"2026/07/{seq+10:02d}"
            current_balance += details['first_payment']
            tx_rows.append([
                base_account, tx_time_p1, tx_date_p1, tx_date_p1, "虛擬帳入", "TWD", None, details['first_payment'], current_balance, va, None
            ])

        # 3. 存入第二期款 (只有 seq 1-5 有存入)
        if seq <= 5:
            tx_time_p2 = f"2026/07/{seq+18:02d} 11:00:00"
            tx_date_p2 = f"2026/07/{seq+18:02d}"
            current_balance += details['second_payment']
            tx_rows.append([
                base_account, tx_time_p2, tx_date_p2, tx_date_p2, "虛擬帳入", "TWD", None, details['second_payment'], current_balance, va, None
            ])
            
        # 3. 支出月嫂費用 (只有 seq 1-5 結案撥款)
        if seq <= 5:
            tx_time_pay = f"2026/07/{seq+15:02d} 16:00:00"
            tx_date_pay = f"2026/07/{seq+15:02d}"
            current_balance -= details['caregiver_fee']
            tx_rows.append([
                base_account, tx_time_pay, tx_date_pay, tx_date_pay, "一般轉出", "TWD", details['caregiver_fee'], None, current_balance, f"月嫂撥款 {personal_data_pool[idx]['name']}", None
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

def generate_schedule_data():
    """
    為系統中的服務人員與訂單建立豐富且多樣化的月掃排班與檔期 (staff_schedule) 假資料。
    涵蓋全部 5 種訂單狀態 ('洽談中', '訂單成立', '服務中', '訂單完成', '訂單取消')
    以及天數精算系統所需的不同休假模式 (連續服務 / 週休1日 / 週休2日) 與國定假日自主出勤/休假邏輯。
    """
    print("-> 正在生成多樣化月掃檔期、訂單生命週期狀態與行事曆假資料...")
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    from services.db_service import get_connection, generate_default_schedule
    from datetime import date, timedelta
    import json

    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            # 1. 清空舊有排班資料
            cursor.execute("TRUNCATE TABLE staff_schedule")
            conn.commit()

            # 2. 獲取服務人員與訂單
            cursor.execute("SELECT id, name FROM staff ORDER BY id ASC")
            staff_list = cursor.fetchall()
            
            cursor.execute("SELECT case_no, client_id FROM orders ORDER BY case_no ASC")
            orders_list = cursor.fetchall()

            if not staff_list or not orders_list:
                print("⚠️ 提示: 資料庫尚未匯入服務人員或訂單，跳過檔期生成。")
                return

            # 3. 為月嫂配置多樣化的休假偏好 (連續服務 / 週休1日 / 週休2日)
            rest_preferences = [
                json.dumps(["Sunday"]),                # 週休1日 (週日)
                json.dumps(["Saturday", "Sunday"]),    # 週休2日 (週六、週日)
                json.dumps([]),                        # 連續服務 (不週休)
                json.dumps(["Monday"])                 # 週休1日 (週一)
            ]
            for idx, staff in enumerate(staff_list):
                pref = rest_preferences[idx % len(rest_preferences)]
                cursor.execute("UPDATE staff SET weekly_rest_days = %s WHERE id = %s", (pref, staff['id']))
            conn.commit()

            # 4. 時間軸推進演算法 (Sequential Timeline Generator): 確保每位月嫂的檔期絕對零重疊
            today = date(2026, 7, 6) # 當前系統基準日
            order_idx = 0
            total_orders_assigned = 0
            target_staff_count = min(30, len(staff_list))

            cancel_reasons = [
                '客戶因家人可協助接應而取消訂單',
                '產婦預產期大幅提前變更，協調取消',
                '客戶改選擇月子中心服務'
            ]

            for s_idx in range(target_staff_count):
                staff = staff_list[s_idx]
                staff_id = staff['id']

                # 每位月嫂從 2026年4月開始維護獨立的時間軸游標
                # 為製造不同月嫂開工的時間差，加上小隨機偏移
                cursor_date = date(2026, 4, 1) + timedelta(days=random.randint(0, 5))
                num_scenarios = random.choice([2, 3, 4])

                for _ in range(num_scenarios):
                    if order_idx >= len(orders_list):
                        break
                    
                    case_no = orders_list[order_idx]['case_no']
                    order_idx += 1

                    # 15% 概率產生訂單取消的範例
                    is_cancelled = (random.random() < 0.15)
                    
                    # 算起訖區間
                    start_d = cursor_date + timedelta(days=random.randint(3, 8))
                    service_days = random.choice([15, 20, 25, 30])
                    hours = random.choice([4, 8, 24])
                    subsidy = random.choice(['一般市民', '補助市民', '非市民'])

                    if is_cancelled:
                        status = '訂單取消'
                        actual_start = None
                        cancel_reason = random.choice(cancel_reasons)
                        end_d = start_d + timedelta(days=service_days)
                        # 取消案件不影響時間軸推進，月嫂檔期保持釋放
                    else:
                        cancel_reason = None
                        # 先生成排班明細以取得精算後的正確結束日
                        generate_default_schedule(case_no, staff_id, start_d, service_days)
                        
                        # 30% 機會為該訂單動態設定 1~3 天自訂放假日期並測試持久化與完工日自動順延
                        if random.random() < 0.3:
                            sample_rests = [
                                (start_d + timedelta(days=random.randint(2, service_days - 2))).strftime("%Y-%m-%d")
                                for _ in range(random.randint(1, 3))
                            ]
                            save_order_rest_dates(case_no, sample_rests)

                        # 查出最新的 end_date
                        cursor.execute("SELECT end_date FROM orders WHERE case_no = %s", (case_no,))
                        res = cursor.fetchone()
                        end_d = res['end_date'] if (res and res['end_date']) else start_d + timedelta(days=service_days)

                        # 按真實時間軸關聯狀態 (Today = 2026-07-06)
                        if end_d < today:
                            status = '訂單完成'
                        elif start_d <= today <= end_d:
                            status = '服務中'
                        else:
                            status = random.choice(['訂單成立', '訂單成立', '洽談中'])

                        actual_start = start_d if status in ['訂單成立', '服務中', '訂單完成'] else None
                        
                        # 時間軸推進至此案件結束日之後 (休息 4~12 天接下一案)
                        cursor_date = end_d + timedelta(days=random.randint(4, 12))

                    cursor.execute("""
                        UPDATE orders 
                        SET staff_id = %s,
                            status = %s,
                            start_date = %s,
                            actual_start_date = %s,
                            end_date = %s,
                            actual_end_date = %s,
                            service_days = %s,
                            service_hours_per_day = %s,
                            subsidy_eligibility = %s,
                            floor_fee = %s,
                            cancel_reason = %s
                        WHERE case_no = %s
                    """, (
                        staff_id, status, start_d, actual_start, end_d,
                        end_d, service_days, hours, subsidy,
                        random.choice([0.0, 500.0, 1000.0]), cancel_reason, case_no
                    ))
                    
                    total_orders_assigned += 1
                    conn.commit()

            # 5. 增添國定假日自主出勤 / 自主休假與請假補班註記 (精算系統測試情境)
            # 端午節 (2026-06-19) - 示範自主出勤與自主休假
            cursor.execute("""
                UPDATE staff_schedule 
                SET is_work_day = TRUE, notes = '端午節國定假日月嫂自主出勤(正常算1天工作日)' 
                WHERE work_date = '2026-06-19' AND case_no IS NOT NULL AND staff_id % 2 = 0
            """)
            cursor.execute("""
                UPDATE staff_schedule 
                SET is_work_day = FALSE, notes = '端午節國定假日月嫂自主休假(結束日順延1天)' 
                WHERE work_date = '2026-06-19' AND case_no IS NOT NULL AND staff_id % 2 = 1
            """)

            # 隨機模擬動態請假與補班
            cursor.execute("SELECT id, case_no, staff_id, work_date FROM staff_schedule WHERE is_work_day = TRUE ORDER BY RAND() LIMIT 12")
            random_days = cursor.fetchall()
            for r_day in random_days:
                note = random.choice([
                    '月嫂因事請假1日 (已自動順延補齊)',
                    '產婦安排產檢彈性休假1日',
                    '行政專員微調出勤時數與日期'
                ])
                cursor.execute("UPDATE staff_schedule SET is_work_day = FALSE, notes = %s WHERE id = %s", (note, r_day['id']))

            conn.commit()

            cursor.execute("SELECT COUNT(*) AS c FROM staff_schedule")
            total_schedules = cursor.fetchone()['c']
            
            cursor.execute("SELECT status, COUNT(*) as cnt FROM orders WHERE staff_id IS NOT NULL GROUP BY status")
            status_summary = cursor.fetchall()
            status_str = ", ".join([f"{item['status']}: {item['cnt']}筆" for item in status_summary])

            print(f"成功！已為 {target_staff_count} 位月嫂建立多樣化檔期，涵蓋訂單狀態 [{status_str}]，共生成 {total_schedules} 筆 `staff_schedule` 每日排班精算紀錄。")

    except Exception as e:
        conn.rollback()
        print(f"生成多樣化檔期假資料失敗: {e}")
    finally:
        conn.close()


LIFECYCLE_SCENARIOS = (
    "new_inquiry",
    "matching_in_progress",
    "deposit_received",
    "in_service",
    "completed_pending_settlement",
    "closed",
    "cancelled",
)


def _scenario_counts(total: int, overrides: dict | None = None) -> dict:
    """Return a deterministic, complete lifecycle mix for the available orders."""
    weights = {
        "new_inquiry": 20,
        "matching_in_progress": 15,
        "deposit_received": 15,
        "in_service": 20,
        "completed_pending_settlement": 10,
        "closed": 15,
        "cancelled": 5,
    }
    if overrides:
        weights.update({name: max(0, int(value)) for name, value in overrides.items() if name in weights})
        return {name: min(total, weights[name]) for name in LIFECYCLE_SCENARIOS}

    counts = {name: total * weight // 100 for name, weight in weights.items()}
    remainder = total - sum(counts.values())
    for name in LIFECYCLE_SCENARIOS[:remainder]:
        counts[name] += 1
    return counts


def _scenario_note(scenario: str, boundary_tag: str | None = None) -> str | None:
    notes = {
        "new_inquiry": [None, "客戶初次來電，待確認服務天數與預產期。", "等待客戶補齊地址及家庭需求。"],
        "matching_in_progress": ["已發送多位月嫂媒合邀請，等待回覆。", "客戶偏好具雙胞胎照護經驗的服務人員。"],
        "deposit_received": ["已收訂金，待產期前一週再次確認。", "服務開始前一天請月嫂先電話聯繫客戶。"],
        "in_service": ["客戶反映寶寶夜間作息不穩，已請月嫂加強紀錄。", "國定假日由月嫂自主出勤，依規則計薪。"],
        "completed_pending_settlement": ["服務已完成，待客戶確認尾款匯入。", "月嫂費預計次月 15 日撥款。"],
        "closed": ["帳務與服務紀錄均已確認，案件結案。", "客戶滿意度回訪完成。"],
        "cancelled": ["客戶改由家人照護，取消服務。", "預產期變動，暫停本次申請。"],
    }
    note = random.choice(notes[scenario])
    return f"{note or ''} [{boundary_tag}]".strip() if boundary_tag else note


def _upsert_payment(cursor, case_no, client_name, status, amount, deposit, first_pay, second_pay, caregiver_fee, notes,
                    deposit_at=None, first_pay_at=None, second_pay_at=None, caregiver_paid_at=None):
    assert case_no
    assert amount == deposit + first_pay + second_pay
    planned_deposit = max(1000, amount // 10)
    planned_balance = max(0, amount - planned_deposit)
    planned_first = planned_balance // 2
    planned_second = planned_balance - planned_first
    amount_received = deposit + first_pay + second_pay
    cursor.execute("""
        INSERT INTO client_payments (
            case_no,
            deposit_receivable, deposit_received, deposit_due_date, deposit_received_at,
            first_payment_receivable, first_payment_received, first_payment_due_date, first_payment_received_at,
            second_payment_receivable, second_payment_received, second_payment_due_date, second_payment_received_at,
            amount_receivable, amount_received,
            payment_status, notes
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            amount_receivable = VALUES(amount_receivable),
            amount_received = VALUES(amount_received),
            deposit_receivable = VALUES(deposit_receivable), deposit_received = VALUES(deposit_received),
            deposit_due_date = VALUES(deposit_due_date), deposit_received_at = VALUES(deposit_received_at),
            first_payment_receivable = VALUES(first_payment_receivable), first_payment_received = VALUES(first_payment_received),
            first_payment_due_date = VALUES(first_payment_due_date), first_payment_received_at = VALUES(first_payment_received_at),
            second_payment_receivable = VALUES(second_payment_receivable), second_payment_received = VALUES(second_payment_received),
            second_payment_due_date = VALUES(second_payment_due_date), second_payment_received_at = VALUES(second_payment_received_at),
            payment_status = VALUES(payment_status), notes = VALUES(notes)
    """, (
        case_no,
        planned_deposit, deposit, deposit_at, deposit_at,
        planned_first, first_pay, first_pay_at, first_pay_at,
        planned_second, second_pay, second_pay_at, second_pay_at,
        amount, amount_received,
        status, notes,
    ))
    cursor.execute("SELECT id FROM client_payments WHERE case_no = %s", (case_no,))
    client_payment_id = cursor.fetchone()["id"]

    # Only replace transaction rows generated by this fixture.  Manual ledger
    # entries are intentionally left untouched.
    cursor.execute("""
        DELETE FROM client_payment_transactions
        WHERE client_payment_id = %s AND external_reference LIKE %s
    """, (client_payment_id, f"fake:{case_no}:%"))

    staged_receipts = (
        ("deposit", deposit, deposit_at),
        ("first_payment", first_pay, first_pay_at),
        ("second_payment", second_pay, second_pay_at),
    )
    for stage, received_amount, occurred_at in staged_receipts:
        if received_amount <= 0:
            continue
        cursor.execute("""
            INSERT INTO client_payment_transactions (
                client_payment_id, case_no, stage, transaction_type,
                transaction_status, amount, occurred_at, external_reference, notes
            ) VALUES (%s, %s, %s, 'receipt', 'succeeded', %s, %s, %s, %s)
        """, (
            client_payment_id,
            case_no,
            stage,
            received_amount,
            occurred_at or date.today(),
            f"fake:{case_no}:{stage}",
            "假資料產生器建立的收款明細",
        ))


def _write_scenario_schedule(cursor, case_no: str, staff_id: int, start: date, service_days: int) -> date:
    """Create a simple deterministic schedule in the caller's transaction."""
    work_days = 0
    current_day = start
    last_day = start
    while work_days < service_days:
        is_sunday = current_day.weekday() == 6
        is_work_day = not is_sunday
        note = "週日預設休假" if is_sunday else "生命週期假資料正常服務日"
        cursor.execute("""
            INSERT INTO staff_schedule (case_no, staff_id, work_date, is_work_day, is_double_pay, notes)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (case_no, staff_id, current_day, is_work_day, False, note))
        if is_work_day:
            work_days += 1
        last_day = current_day
        current_day += timedelta(days=1)
    return last_day


def _assign_available_staff(cursor, staff_ids: list[int], desired_start: date) -> tuple[int, date]:
    """Choose a staff member whose generated schedule does not overlap the requested start."""
    availability = []
    for staff_id in staff_ids:
        cursor.execute("SELECT MAX(work_date) AS last_date FROM staff_schedule WHERE staff_id = %s", (staff_id,))
        last_date = cursor.fetchone()["last_date"]
        if last_date is None or last_date < desired_start:
            availability.append((staff_id, desired_start))
        else:
            availability.append((staff_id, last_date + timedelta(days=4)))
    available_now = [item for item in availability if item[1] == desired_start]
    return random.choice(available_now) if available_now else min(availability, key=lambda item: item[1])


def validate_lifecycle_data(cursor, reference_date: date) -> list[str]:
    """Validate the database invariants required by the generated lifecycle fixtures."""
    errors = []
    checks = [
        ("""SELECT COUNT(*) AS count FROM orders
            WHERE status = '洽談中' AND (staff_id IS NOT NULL OR actual_start_date IS NOT NULL OR actual_end_date IS NOT NULL
            OR start_date < %s)""", (reference_date,), "洽談中案件違反未指派或兩週後開始規則"),
        ("""SELECT COUNT(*) AS count FROM orders o
            LEFT JOIN clients c ON c.id = o.client_id
            WHERE status IN ('服務中', '訂單完成') AND (o.staff_id IS NULL OR o.actual_start_date IS NULL)""", (), "服務中/完成案件缺少月嫂或實際開始日"),
        ("""SELECT COUNT(*) AS count FROM orders o
            LEFT JOIN staff_schedule ss ON ss.case_no = o.case_no AND ss.work_date > %s
            WHERE o.status = '訂單取消' AND (o.cancel_reason IS NULL OR o.cancel_reason = '' OR ss.id IS NOT NULL)""", (reference_date,), "取消案件缺少原因或仍有未來排班"),
        ("""SELECT COUNT(*) AS count FROM client_payments cp
            LEFT JOIN orders o ON o.case_no = cp.case_no
            WHERE o.case_no IS NULL""", (), "客戶帳務資料含不存在的 case_no"),
    ]
    for query, params, message in checks:
        cursor.execute(query, params)
        if cursor.fetchone()["count"]:
            errors.append(message)
    return errors


def generate_lifecycle_scenarios(reference_date: date, seed: int | None = None,
                                 scenario_counts: dict | None = None) -> dict:
    """Generate valid lifecycle, payment, matching, note, and boundary fixtures in MySQL."""
    if seed is not None:
        random.seed(seed)

    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT o.case_no, c.id AS client_id, c.name AS client_name
                FROM orders o JOIN clients c ON c.id = o.client_id
                WHERE o.case_no IS NOT NULL AND o.case_no <> '' ORDER BY o.case_no
            """)
            orders = cursor.fetchall()
            cursor.execute("SELECT id FROM staff ORDER BY id")
            staff_ids = [row["id"] for row in cursor.fetchall()]
            if not orders or not staff_ids:
                return {
                    "generation_summary": {},
                    "validation_result": "skipped: orders, clients, or staff data is not imported yet",
                }

            cursor.execute("DELETE FROM matching_records")
            cursor.execute("DELETE FROM staff_schedule")
            cursor.execute("""
                UPDATE orders SET staff_id = NULL, actual_start_date = NULL, actual_end_date = NULL,
                    cancel_reason = NULL, custom_rest_dates = NULL
            """)

            counts = _scenario_counts(len(orders), scenario_counts)
            plan = [name for name, count in counts.items() for _ in range(count)]
            while len(plan) < len(orders):
                plan.append("new_inquiry")
            random.shuffle(plan)
            summary = Counter()

            for index, order in enumerate(orders):
                scenario = plan[index]
                days = random.choice([15, 20, 25, 30])
                hours = random.choice([8, 9, 24])
                floor_fee = random.choice([0, 0, 500, 1000])
                amount = days * hours * random.choice([300, 350]) + floor_fee
                caregiver_fee = int(amount * 0.75)
                boundary_tag = None
                if index == 0:
                    boundary_tag = "BOUNDARY_CROSS_MONTH"
                elif index == 1:
                    boundary_tag = "BOUNDARY_WEEKEND_HOLIDAY"
                elif index == 2:
                    boundary_tag = "CONFLICT_TEST_EXCLUDED_FROM_NORMAL_SCHEDULE"
                note = _scenario_note(scenario, boundary_tag)

                if scenario == "new_inquiry":
                    start = reference_date + timedelta(days=14 + random.randint(0, 45))
                    end = start + timedelta(days=days)
                    cursor.execute("""
                        UPDATE orders SET staff_id = NULL, status = '洽談中', start_date = %s, end_date = %s,
                            actual_start_date = NULL, actual_end_date = NULL, service_days = %s,
                            service_hours_per_day = %s, floor_fee = %s, cancel_reason = NULL WHERE case_no = %s
                    """, (start, end, days, hours, floor_fee, order["case_no"]))
                    _upsert_payment(cursor, order["case_no"], order["client_name"], "待收訂金", amount, 0, 0, 0, 0, note)

                elif scenario == "matching_in_progress":
                    start = reference_date + timedelta(days=14 + random.randint(0, 30))
                    end = start + timedelta(days=days)
                    cursor.execute("""
                        UPDATE orders SET staff_id = NULL, status = '洽談中', start_date = %s, end_date = %s,
                            actual_start_date = NULL, actual_end_date = NULL, service_days = %s,
                            service_hours_per_day = %s, floor_fee = %s WHERE case_no = %s
                    """, (start, end, days, hours, floor_fee, order["case_no"]))
                    for candidate_id in random.sample(staff_ids, min(len(staff_ids), random.randint(2, 5))):
                        reply = random.choice([None, None, 0, 1])
                        cursor.execute("""
                            INSERT INTO matching_records (case_no, staff_id, caregiver_accepted, sent_at, replied_at)
                            VALUES (%s, %s, %s, NOW(), CASE WHEN %s IS NULL THEN NULL ELSE NOW() END)
                        """, (order["case_no"], candidate_id, reply, reply))
                    _upsert_payment(cursor, order["case_no"], order["client_name"], "待收訂金", amount, 0, 0, 0, 0, note)

                elif scenario == "cancelled":
                    start = reference_date + timedelta(days=random.randint(2, 30))
                    cursor.execute("""
                        UPDATE orders SET staff_id = NULL, status = '訂單取消', start_date = %s, end_date = %s,
                            actual_start_date = NULL, actual_end_date = NULL, service_days = %s,
                            service_hours_per_day = %s, floor_fee = %s, cancel_reason = %s WHERE case_no = %s
                    """, (start, start + timedelta(days=days), days, hours, floor_fee,
                          "客戶改由家人照護，取消服務", order["case_no"]))
                    _upsert_payment(cursor, order["case_no"], order["client_name"], "待收訂金", amount, 0, 0, 0, 0, note)

                else:
                    deposit = max(1000, amount // 10)
                    balance = amount - deposit
                    first_pay = balance // 2
                    second_pay = balance - first_pay

                    if scenario == "deposit_received":
                        start = reference_date + timedelta(days=random.randint(7, 40))
                        status = "訂單成立"
                        p_status = "已收訂金"
                        p_deposit = deposit
                        p_first = 0
                        p_second = 0
                        p_first_at = None
                        p_second_at = None
                        actual_start, actual_end = None, None
                    elif scenario == "in_service":
                        start = reference_date - timedelta(days=random.randint(1, min(days - 1, 10)))
                        status = "服務中"
                        p_status = "已收一期款"
                        p_deposit = deposit
                        p_first = first_pay
                        p_second = 0
                        p_first_at = start + timedelta(days=5)
                        p_second_at = None
                        actual_start, actual_end = start, start + timedelta(days=days)
                    elif scenario == "completed_pending_settlement":
                        start = reference_date - timedelta(days=days + random.randint(3, 20))
                        status = "訂單完成"
                        p_status = "已收一期款"
                        p_deposit = deposit
                        p_first = first_pay
                        p_second = 0
                        p_first_at = start + timedelta(days=5)
                        p_second_at = None
                        actual_start, actual_end = start, start + timedelta(days=days)
                    else:  # closed
                        start = reference_date - timedelta(days=days + random.randint(10, 40))
                        status = "訂單完成"
                        p_status = "已結案"
                        p_deposit = deposit
                        p_first = first_pay
                        p_second = second_pay
                        p_first_at = start + timedelta(days=5)
                        p_second_at = start + timedelta(days=days)
                        actual_start, actual_end = start, start + timedelta(days=days)

                    staff_id, start = _assign_available_staff(cursor, staff_ids, start)
                    if scenario in ("in_service", "completed_pending_settlement", "closed"):
                        actual_start = start
                        actual_end = start + timedelta(days=days)

                    cursor.execute("""
                        UPDATE orders SET staff_id = %s, status = %s, start_date = %s, end_date = %s,
                            actual_start_date = %s, actual_end_date = %s, service_days = %s,
                            service_hours_per_day = %s, floor_fee = %s, cancel_reason = NULL WHERE case_no = %s
                    """, (staff_id, status, start, start + timedelta(days=days), actual_start, actual_end,
                          days, hours, floor_fee, order["case_no"]))

                    # A conflict fixture stays visible in orders but deliberately has no schedule row.
                    if boundary_tag != "CONFLICT_TEST_EXCLUDED_FROM_NORMAL_SCHEDULE":
                        scheduled_end = _write_scenario_schedule(cursor, order["case_no"], staff_id, start, days)
                        if scenario == "deposit_received":
                            cursor.execute("""
                                UPDATE orders SET end_date = %s, actual_start_date = NULL, actual_end_date = NULL WHERE case_no = %s
                            """, (scheduled_end, order["case_no"]))
                        else:
                            cursor.execute("""
                                UPDATE orders SET end_date = %s, actual_end_date = %s WHERE case_no = %s
                            """, (scheduled_end, scheduled_end, order["case_no"]))

                    _upsert_payment(
                        cursor, order["case_no"], order["client_name"],
                        p_status, amount, p_deposit, p_first, p_second,
                        caregiver_fee if scenario == "closed" else 0, note,
                        start - timedelta(days=3), p_first_at, p_second_at,
                        actual_end + timedelta(days=15) if scenario == "closed" else None,
                    )

                cursor.execute("UPDATE clients SET admin_notes = %s WHERE id = %s", (note, order["client_id"]))
                summary[scenario] += 1

            errors = validate_lifecycle_data(cursor, reference_date)
            if errors:
                raise RuntimeError("; ".join(errors))
            conn.commit()
            return {"generation_summary": dict(summary), "validation_result": "pass"}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def parse_cli_args():
    parser = argparse.ArgumentParser(description="Generate lifecycle-aware fake data")
    parser.add_argument("--reference-date", default=date.today().isoformat(), help="YYYY-MM-DD baseline for lifecycle data")
    parser.add_argument("--seed", type=int, default=20260713, help="Deterministic random seed")
    return parser.parse_args()


def main():
    args = parse_cli_args()
    try:
        reference_date = datetime.strptime(args.reference_date, "%Y-%m-%d").date()
    except ValueError as exc:
        raise SystemExit(f"--reference-date must use YYYY-MM-DD: {exc}")
    random.seed(args.seed)
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
        
    # 3. 產生月掃檔期與行事曆假資料
    try:
        lifecycle_result = generate_lifecycle_scenarios(reference_date, args.seed)
        print(f"Lifecycle summary: {lifecycle_result['generation_summary']}; validation: {lifecycle_result['validation_result']}")
    except Exception as e:
        print(f"Lifecycle generation failed: {e}")
        sys.exit(1)

    print("\n====== 所有假資料生成完成，名冊、財務與月掃檔期測試數據已 100% 關聯對齊！ ======")

if __name__ == "__main__":
    main()

