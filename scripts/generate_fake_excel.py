import sys
import os
import random
import pandas as pd
from datetime import datetime, timedelta

# 確保中文輸出編碼正確
sys.stdout.reconfigure(encoding='utf-8')

# 常用中文姓名隨機元素
surnames = ['王', '陳', '張', '劉', '李', '吳', '黃', '蔡', '楊', '許', '林', '賴', '徐', '周', '趙', '郭', '胡', '高', '黃']
names = ['明', '華', '強', '偉', '洋', '豪', '傑', '翔', '安', '美', '婷', '欣', '晴', '宇', '廷', '冠', '奕', '宥', '建', '俊', '雅', '涵', '萱', '茹', '君', '嘉', '琪', '婷', '威', '宏']

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

def generate_fake_time():
    start_date = datetime.now() - timedelta(days=30)
    random_days = random.randint(0, 30)
    random_hours = random.randint(0, 23)
    random_minutes = random.randint(0, 59)
    random_seconds = random.randint(0, 59)
    fake_date = start_date + timedelta(days=random_days, hours=random_hours, minutes=random_minutes, seconds=random_seconds)
    return fake_date.strftime("%Y/%m/%d %H:%M:%S")

def main():
    input_file = r'C:\Users\chris\Desktop\project\union\欄位.xlsx'
    output_file = r'C:\Users\chris\Desktop\project\union\欄位_測試用.xlsx'

    if not os.path.exists(input_file):
        print(f"錯誤：找不到來源檔案 {input_file}")
        return

    print("正在讀取原始範本 Excel 的兩個分頁...")
    df_clients_template = pd.read_excel(input_file, sheet_name='HCM 月子平台 -市府')
    df_beclass_template = pd.read_excel(input_file, sheet_name='beclass')
    
    if len(df_clients_template) == 0 or len(df_beclass_template) == 0:
        print("錯誤：範本 Excel 中缺少必要欄位或資料。")
        return

    num_records = 50
    print(f"\n====== 開始生成 {num_records} 筆「對應個人資訊」的測試資料 ======")

    # 1. 先產生 50 筆個人核心資料，用於跨工作表對應
    personal_data_pool = []
    for i in range(num_records):
        name = generate_fake_name()
        phone = generate_fake_phone()
        email = f"test_{phone[-4:]}@example.com"
        address = generate_fake_address()
        line_id = generate_fake_line_id()
        ip = generate_fake_ip()
        
        personal_data_pool.append({
            'name': name,
            'phone': phone,
            'email': email,
            'address': address,
            'line_id': line_id,
            'ip': ip
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
        
        # 唯一的案件編號
        row['查詢序號(案件編號)'] = base_case_no + i
        row['查詢序號(案件編號).1'] = base_case_no + i
        
        row['報名時間(建檔)'] = generate_fake_time()
        row['IP位址'] = p_data['ip']
        row['姓名'] = p_data['name']
        row['性別'] = random.choice(['男', '女'])
        row['行動電話'] = p_data['phone']
        row['地址'] = p_data['address']
        row['LINE ID'] = p_data['line_id']
        
        row['希望服務天數'] = random.choice([15, 20, 30, 40])
        row['生產方式'] = random.choice(['自然產', '剖腹產'])
        row['寶寶資訊'] = random.choice(['第一胎', '第二胎', '雙胞胎'])
        
        fake_clients_rows.append(row)

    df_clients_result = pd.DataFrame(fake_clients_rows)

    # ---------------------------------------------
    # 3. 生成第二個分頁 (beclass) 假資料
    # ---------------------------------------------
    print("-> 正在生成 beclass 資料，並對應個人資訊...")
    beclass_template_row = df_beclass_template.iloc[0].to_dict()
    fake_beclass_rows = []
    base_query_no = 28755000

    for i in range(num_records):
        row = beclass_template_row.copy()
        p_data = personal_data_pool[i]
        
        row['項次'] = i + 1
        row['查詢序號'] = base_query_no + i
        row['報名時間'] = f"{random.randint(1, 12):02d}-{random.randint(1, 28):02d} {random.randint(0, 23):02d}:{random.randint(0, 59):02d}"
        row['訂單編號'] = f"HC115{random.randint(100, 999):03d}"
        
        # 複用對應的個人資訊，確保能聯表比對
        row['姓名'] = p_data['name']
        row['性別'] = random.choice(['男', '女'])
        row['Email'] = p_data['email']
        row['出生年'] = random.randint(1980, 2000)
        row['月'] = random.randint(1, 12)
        row['日'] = random.randint(1, 28)
        row['行動電話'] = p_data['phone']
        row['地址'] = p_data['address']
        
        # 其他選填與勾選欄位做隨機模擬
        row['市話'] = f"03-5{random.randint(100, 999):03d}{random.randint(100, 999):03d}" if random.random() > 0.5 else None
        
        # 對所有問項欄位做隨機勾選模擬 ('Y' 或 None)
        for col in row.keys():
            # 針對以 "□" 開頭的欄位或特定的勾選欄位做隨機
            if col.startswith('□') or col in ['葷食', '素食', '全酒', '半酒', '米酒水', '無酒料理', '有', '無(願意負擔停車費用)']:
                row[col] = 'Y' if random.random() > 0.5 else None
        
        row['管理者註記事項'] = random.choice(['大寶1歲', '二寶出生', '需要提早', None])
        
        fake_beclass_rows.append(row)

    df_beclass_result = pd.DataFrame(fake_beclass_rows)

    # ---------------------------------------------
    # 4. 同時將兩個分頁寫入同一個 Excel 檔案中
    # ---------------------------------------------
    print("正在將兩個分頁寫入新的測試 Excel 檔案中...")
    with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
        df_clients_result.to_excel(writer, sheet_name='HCM 月子平台 -市府', index=False)
        df_beclass_result.to_excel(writer, sheet_name='beclass', index=False)
        
    print(f"成功！已生成包含 2 個分頁對應資料的測試檔案：{output_file}")

if __name__ == "__main__":
    main()
