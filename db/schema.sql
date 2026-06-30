-- 建立資料庫 (若不存在)
CREATE DATABASE IF NOT EXISTS union_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE union_db;

-- 1. 客戶資料表 (對應 欄位.xlsx 結構)
CREATE TABLE IF NOT EXISTS clients (
    id INT AUTO_INCREMENT PRIMARY KEY,
    seq_num INT COMMENT '項次',
    status VARCHAR(50) COMMENT '案件狀態 (符合/不符合)',
    reject_reason TEXT COMMENT '不符合原因',
    case_no VARCHAR(50) UNIQUE COMMENT '查詢序號(案件編號) - 去重唯一識別碼',
    created_at DATETIME COMMENT '報名時間(建檔)',
    ip_address VARCHAR(45) COMMENT 'IP位址',
    name VARCHAR(100) COMMENT '姓名',
    gender VARCHAR(10) COMMENT '性別',
    phone VARCHAR(20) COMMENT '行動電話',
    city VARCHAR(50) COMMENT '縣市',
    address VARCHAR(255) COMMENT '地址',
    identity_status VARCHAR(100) COMMENT '身分資格',
    service_time VARCHAR(100) COMMENT '服務時間',
    due_month VARCHAR(100) COMMENT '預產期/預計服務開始月份',
    service_start_date VARCHAR(100) COMMENT '預計服務日期',
    notes TEXT COMMENT '其他事項',
    service_days INT COMMENT '希望服務天數',
    residence_type VARCHAR(100) COMMENT '居住型態',
    delivery_type VARCHAR(100) COMMENT '生產方式',
    service_type VARCHAR(100) COMMENT '服務方式',
    baby_info VARCHAR(255) COMMENT '寶寶資訊',
    line_id VARCHAR(100) COMMENT 'LINE ID',
    admin_notes TEXT COMMENT '管理者註記事項',
    db_created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '資料庫匯入時間',
    db_updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '資料庫更新時間',
    INDEX idx_case_no (case_no),
    INDEX idx_phone (phone),
    INDEX idx_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 2. FAQ 語意問答知識庫表
CREATE TABLE IF NOT EXISTS faq (
    id INT AUTO_INCREMENT PRIMARY KEY,
    question TEXT NOT NULL COMMENT '標準問題',
    answer TEXT NOT NULL COMMENT '預設答案',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 3. 爬蟲執行日誌表
CREATE TABLE IF NOT EXISTS crawler_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    crawled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(50) NOT NULL COMMENT '執行狀態 (SUCCESS/FAILED)',
    records_inserted INT DEFAULT 0 COMMENT '新增筆數',
    records_updated INT DEFAULT 0 COMMENT '更新筆數',
    message TEXT COMMENT '日誌詳細說明或錯誤原因'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 4. BeClass 報名紀錄表
CREATE TABLE IF NOT EXISTS beclass_records (
    id INT AUTO_INCREMENT PRIMARY KEY,
    seq_num INT COMMENT '項次',
    query_no VARCHAR(50) UNIQUE COMMENT '查詢序號',
    order_no VARCHAR(50) COMMENT '訂單編號',
    created_at VARCHAR(50) COMMENT '報名時間',
    name VARCHAR(100) COMMENT '姓名',
    gender VARCHAR(10) COMMENT '性別',
    email VARCHAR(100) COMMENT 'Email',
    birth_date DATE COMMENT '生日',
    phone VARCHAR(20) COMMENT '行動電話',
    tel VARCHAR(20) COMMENT '市話',
    ext VARCHAR(10) COMMENT '分機',
    city VARCHAR(50) COMMENT '縣市',
    zip_code VARCHAR(10) COMMENT '郵遞區號',
    address VARCHAR(255) COMMENT '地址',
    survey_details JSON COMMENT 'BeClass 問卷詳細內容 (包含餐點、用油、烹煮工具、特殊計費等 JSON)',
    admin_notes TEXT COMMENT '管理者註記事項',
    db_created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    db_updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_query_no (query_no),
    INDEX idx_phone (phone),
    INDEX idx_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 5. 服務人員主表
CREATE TABLE IF NOT EXISTS staff (
    id INT AUTO_INCREMENT PRIMARY KEY,
    registered_at DATETIME COMMENT '報名時間',
    ip_address VARCHAR(45) COMMENT '註冊IP',
    name VARCHAR(100) NOT NULL COMMENT '姓名',
    identity_card VARCHAR(20) UNIQUE COMMENT '身分證字號',
    phone VARCHAR(20) COMMENT '行動電話',
    tel VARCHAR(20) COMMENT '市話',
    tel_ext VARCHAR(10) COMMENT '分機',
    email VARCHAR(100) COMMENT 'EMAIL',
    birthday DATE COMMENT '生日 (由民國生日整合)',
    city VARCHAR(50) COMMENT '居住縣市',
    zip_code VARCHAR(10) COMMENT '郵遞區號',
    address VARCHAR(255) COMMENT '詳細地址',
    has_massage_cert BOOLEAN DEFAULT FALSE COMMENT '有嬰幼兒按摩證書嗎',
    status VARCHAR(20) DEFAULT 'active' COMMENT '在職狀態 (active/inactive)',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_staff_name (name),
    INDEX idx_staff_phone (phone)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 6. 服務人員銀行帳戶表 (支援 1:N 備用帳戶)
CREATE TABLE IF NOT EXISTS staff_bank_accounts (
    id INT AUTO_INCREMENT PRIMARY KEY,
    staff_id INT NOT NULL,
    bank_code VARCHAR(10) COMMENT '銀行代碼(3碼)',
    branch_code VARCHAR(10) COMMENT '分行代碼(4碼)',
    account_no VARCHAR(50) NOT NULL COMMENT '銀行帳號',
    is_primary BOOLEAN DEFAULT TRUE COMMENT '是否為主要帳戶',
    FOREIGN KEY (staff_id) REFERENCES staff(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 7. 可承接案件區域 (1:N 複選)
CREATE TABLE IF NOT EXISTS staff_regions (
    staff_id INT NOT NULL,
    region_name VARCHAR(50) NOT NULL COMMENT '區域名稱 (北區/東區/香山區/新竹縣/苗栗縣/其他)',
    custom_region_detail VARCHAR(100) NULL COMMENT '對應其他地區的補充說明',
    PRIMARY KEY (staff_id, region_name),
    FOREIGN KEY (staff_id) REFERENCES staff(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 8. 可承接案件時段 (1:N 複選)
CREATE TABLE IF NOT EXISTS staff_time_slots (
    staff_id INT NOT NULL,
    slot_name VARCHAR(50) NOT NULL COMMENT '時段名稱 (4小時_上午/4小時_下午/8小時/24小時/其他)',
    custom_slot_detail VARCHAR(100) NULL COMMENT '其他時段的補充說明',
    PRIMARY KEY (staff_id, slot_name),
    FOREIGN KEY (staff_id) REFERENCES staff(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 9. 月子餐點料理能力 (1:N 複選)
CREATE TABLE IF NOT EXISTS staff_cooking_skills (
    staff_id INT NOT NULL,
    skill_name VARCHAR(50) NOT NULL COMMENT '料理類型 (葷食/素食/其他)',
    custom_skill_detail VARCHAR(100) NULL COMMENT '其他料理的補充說明',
    PRIMARY KEY (staff_id, skill_name),
    FOREIGN KEY (staff_id) REFERENCES staff(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 10. 服務時交通工具 (1:N 複選)
CREATE TABLE IF NOT EXISTS staff_transportation (
    staff_id INT NOT NULL,
    vehicle_type VARCHAR(50) NOT NULL COMMENT '交通工具 (機車/轎車)',
    PRIMARY KEY (staff_id, vehicle_type),
    FOREIGN KEY (staff_id) REFERENCES staff(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 11. 特殊節日上班意願 (1:N 複選)
CREATE TABLE IF NOT EXISTS staff_holiday_availability (
    staff_id INT NOT NULL,
    holiday_name VARCHAR(50) NOT NULL COMMENT '節日名稱 (初一/初二/初三/端午/中秋/國定假日必休/其他)',
    custom_holiday_detail VARCHAR(100) NULL COMMENT '其他節日的補充說明',
    PRIMARY KEY (staff_id, holiday_name),
    FOREIGN KEY (staff_id) REFERENCES staff(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 12. 可服務週間 (1:N 複選)
CREATE TABLE IF NOT EXISTS staff_weekly_rest (
    staff_id INT NOT NULL,
    rest_type VARCHAR(50) NOT NULL COMMENT '放假類型 (連續服務/週休1日/週休2日/其他)',
    custom_rest_detail VARCHAR(100) NULL COMMENT '其他週間服務的補充說明',
    PRIMARY KEY (staff_id, rest_type),
    FOREIGN KEY (staff_id) REFERENCES staff(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 13. 可承接胎數 (1:N 複選)
CREATE TABLE IF NOT EXISTS staff_baby_types (
    staff_id INT NOT NULL,
    baby_type VARCHAR(50) NOT NULL COMMENT '胎數類型 (單胞胎/雙胞胎/其他)',
    custom_baby_detail VARCHAR(100) NULL COMMENT '其他胎數的補充說明',
    PRIMARY KEY (staff_id, baby_type),
    FOREIGN KEY (staff_id) REFERENCES staff(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 14. 人員可工作時間區間表
CREATE TABLE IF NOT EXISTS staff_availability (
    id INT AUTO_INCREMENT PRIMARY KEY,
    staff_id INT NOT NULL,
    start_date DATE NOT NULL COMMENT '可工作開始日期',
    end_date DATE NOT NULL COMMENT '可工作結束日期',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (staff_id) REFERENCES staff(id) ON DELETE CASCADE,
    INDEX idx_avail_dates (start_date, end_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 15. 人員已被預約/排班時間區間表
CREATE TABLE IF NOT EXISTS staff_bookings (
    id INT AUTO_INCREMENT PRIMARY KEY,
    staff_id INT NOT NULL,
    client_id INT NOT NULL COMMENT '對應 clients.id',
    start_date DATE NOT NULL COMMENT '服務開始日期',
    end_date DATE NOT NULL COMMENT '服務結束日期',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (staff_id) REFERENCES staff(id) ON DELETE CASCADE,
    INDEX idx_booking_dates (start_date, end_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

