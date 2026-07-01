import sys
import os
import random
import pandas as pd
from datetime import datetime, timedelta

# 確保中文輸出編碼正確
sys.stdout.reconfigure(encoding='utf-8')

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
    # ponytail: simple valid ROC ID generator
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

# 1. 隨機產生建檔/報名時間 (最近 60 天內)
def generate_fake_signup_time():
    start_date = datetime.now() - timedelta(days=60)
    random_days = random.randint(0, 60)
    random_hours = random.randint(0, 23)
    random_minutes = random.randint(0, 59)
    random_seconds = random.randint(0, 59)
    fake_date = start_date + timedelta(days=random_days, hours=random_hours, minutes=random_minutes, seconds=random_seconds)
    return fake_date.strftime("%Y/%m/%d %H:%M:%S")

# 2. 隨機產生預產期 (今天起往後 30-180 天)
def generate_fake_due_date():
    start_date = datetime.now() + timedelta(days=30)
    random_days = random.randint(0, 150)
    due_date = start_date + timedelta(days=random_days)
    return due_date.strftime("%Y/%m/%d")

# 3. 隨機產生預計服務日期 (預產期往後 3-10 天)
def generate_fake_service_start_date(due_date_str):
    try:
        due_date = datetime.strptime(due_date_str, "%Y/%m/%d")
    except:
        due_date = datetime.now()
    service_date = due_date + timedelta(days=random.randint(3, 10))
    return service_date.strftime("%Y/%m/%d")

def fill_checkbox_group(row_dict, options, summary_col):
    # ponytail: randomly select a subset and populate both individual columns and the summary column
    k = random.randint(1, len(options))
    selected = random.sample(options, k)
    for opt in options:
        row_dict[opt] = 'Y' if opt in selected else None
    row_dict[summary_col] = '、'.join(selected)

def main():
    input_file = 'document/資料庫、資料處理/資料庫來源表.xlsx'
    output_file = 'document/資料庫、資料處理/假資料_範例.xlsx'
    
    if not os.path.exists(input_file):
        base_dir = os.path.dirname(__file__)
        input_file = os.path.join(base_dir, '..', 'document', '資料庫、資料處理', '資料庫來源表.xlsx')
        output_file = os.path.join(base_dir, '..', 'document', '資料庫、資料處理', '假資料_範例.xlsx')
        
    if not os.path.exists(input_file):
        print(f"錯誤：找不到來源檔案，路徑為：{input_file}")
        return

    print("正在讀取原始範本 Excel 的三個分頁...")
    df_clients_template = pd.read_excel(input_file, sheet_name='HCM 月子平台 -市府')
    df_beclass_template = pd.read_excel(input_file, sheet_name='beclass')
    df_staff_template = pd.read_excel(input_file, sheet_name='服務人員')
    
    if len(df_clients_template) == 0 or len(df_beclass_template) == 0 or len(df_staff_template) == 0:
        print("錯誤：範本 Excel 中缺少必要欄位或資料。")
        return

    num_records = 50
    print(f"\n====== 開始生成 {num_records} 筆「對應個人資訊」與「不同測試日期」的資料 ======")

    # 1. 產生 50 筆個人核心資料，用於跨工作表對應
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

    # ---------------------------------------------
    # 2. 生成第一個分頁 (HCM 月子平台 -市府) 假資料
    # ---------------------------------------------
    print("-> 正在生成 HCM 月子平台 -市府 資料...")
    clients_template_row = df_clients_template.iloc[0].to_dict()
    fake_clients_rows = []
    base_case_no = 113000000

    for i in range(num_records):
        row = clients_template_row.copy()
        p_data = personal_data_pool[i]
        
        row['項次'] = i + 1
        row['案件狀態'] = random.choice(['符合', '符合', '符合', '不符合'])
        row['不符合原因'] = '資格不符測試' if row['案件狀態'] == '不符合' else None
        row['查詢序號(案件編號)'] = base_case_no + i
        row['查詢序號(案件編號).1'] = base_case_no + i
        
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

    # ---------------------------------------------
    # 3. 生成第二個分頁 (服務人員) 假資料
    # ---------------------------------------------
    print("-> 正在生成 服務人員 資料...")
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
        
        # 生日欄位 (民國與西元對應)
        birth_year = random.randint(50, 85) # 民國 50 - 85 年 (1961 - 1996)
        birth_month = random.randint(1, 12)
        birth_day = random.randint(1, 28)
        row['出生年'] = birth_year
        row['月'] = birth_month
        row['日'] = birth_day
        
        # 民國出生年月日儲存格式例如：1972-12-24 (西元格式，配合 pandas 寫入)
        row['民國出生年月日'] = f"{birth_year + 1911}-{birth_month:02d}-{birth_day:02d}"
        
        row['市話'] = f"03-5{random.randint(100, 999):03d}{random.randint(100, 999):03d}" if random.random() > 0.5 else None
        row['分機'] = None
        
        # 縣市地區與地址
        row['縣市'] = random.choice(['新竹市', '新竹縣', '苗栗縣'])
        zip_mapping = {'新竹市': '300', '新竹縣': '302', '苗栗縣': '350'}
        row['郵遞區號'] = zip_mapping[row['縣市']]
        row['地址'] = p_data['address']
        
        # 備用帳號
        row['若有其它同銀行帳號，請一併提供。(永豐或台新)'] = None
        row['承上題'] = random.choice(['我提供的帳號是永豐銀行帳戶', '我提供的帳號是台新銀行帳戶', None])
        
        # 填充複選題
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
        
        # 特殊節日複選
        holiday_opts = ['年節農曆過年初一', '年節農曆過年初二', '年節農曆過年初三', '端午節', '中秋節', '國定假日必休']
        fill_checkbox_group(row, holiday_opts, '特殊節日可上班的部分(計費:服務費雙倍)')
        row['[其它].5'] = None
        
        row['有嬰幼兒按摩證書嗎?'] = random.choice(['有', '無'])
        
        fake_staff_rows.append(row)

    df_staff_result = pd.DataFrame(fake_staff_rows)

    # ---------------------------------------------
    # 4. 生成第三個分頁 (beclass) 假資料
    # ---------------------------------------------
    print("-> 正在生成 beclass 資料...")
    beclass_template_row = df_beclass_template.iloc[0].to_dict()
    fake_beclass_rows = []
    base_query_no = 28755000

    for i in range(num_records):
        row = beclass_template_row.copy()
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

    # ---------------------------------------------
    # 5. 同時將三個分頁寫入同一個 Excel 檔案中
    # ---------------------------------------------
    print("正在將三個分頁寫入新的測試 Excel 檔案中...")
    with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
        df_clients_result.to_excel(writer, sheet_name='HCM 月子平台 -市府', index=False)
        df_staff_result.to_excel(writer, sheet_name='服務人員', index=False)
        df_beclass_result.to_excel(writer, sheet_name='beclass', index=False)
        
    print(f"成功！已生成包含多樣測試日期對應資料的檔案：{output_file}")
if __name__ == "__main__":
    main()

