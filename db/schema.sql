-- 強制重建資料庫以確保 ENUM 編碼正確
DROP DATABASE IF EXISTS union_db;
CREATE DATABASE union_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE union_db;

-- 1. 客戶資料表 (對應 欄位.xlsx 結構)
CREATE TABLE IF NOT EXISTS clients (
    id INT AUTO_INCREMENT PRIMARY KEY,
    seq_num INT COMMENT '項次',
    reject_reason TEXT COMMENT '不符合原因',
    -- ponytail: 重構標記 - case_no 目前儲存的是 9 碼的「查詢序號(案件編號)」(例如 115000001)，舊式案號(HC115091)已被棄用。未來系統大改版時，此欄位將統一命名為 query_no 或 case_id。
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
    line_user_id VARCHAR(100) COMMENT 'LINE 平台用戶唯一識別碼 (Webhook 取得)',
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

-- 4. BeClass 報名紀錄表（主關聯欄位為 beclass_records.query_no <=> clients.case_no；案件識別一律以 clients.case_no 為準）
CREATE TABLE IF NOT EXISTS beclass_records (
    id INT AUTO_INCREMENT PRIMARY KEY,
    seq_num INT COMMENT '項次',
    query_no VARCHAR(50) UNIQUE COMMENT '查詢序號 - 與 clients.case_no 進行主關聯',
    created_at VARCHAR(50) COMMENT '報名時間',
    name VARCHAR(100) COMMENT '姓名',
    email VARCHAR(100) COMMENT 'Email',
    birth_date DATE COMMENT '生日',
    phone VARCHAR(20) COMMENT '行動電話',
    tel VARCHAR(20) COMMENT '市話',
    ext VARCHAR(10) COMMENT '分機',
    city VARCHAR(50) COMMENT '縣市',
    zip_code VARCHAR(10) COMMENT '郵遞區號',
    address VARCHAR(255) COMMENT '地址',
    refund_bank_code VARCHAR(50) COMMENT '補助款退款:銀行代號+分行代號',
    refund_account_no VARCHAR(50) COMMENT '補助款退款:銀行帳號',
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
    line_user_id VARCHAR(100) COMMENT 'LINE 平台用戶唯一識別碼 (Webhook 取得)',
    weekly_rest_days JSON COMMENT '固定休假偏好 JSON 陣列 (如 ["Sunday"])',
    care_babies INT DEFAULT 1 COMMENT '最大可照顧寶寶數量 (1:單胞胎, 2:雙胞胎, 3:三胞胎)',
    service_regions JSON COMMENT '接受服務區域 JSON 陣列',
    special_skills JSON COMMENT '特殊技能與偏好標籤 JSON 陣列',
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

-- 16. 專案與訂單資料表
CREATE TABLE IF NOT EXISTS orders (
    case_no VARCHAR(50) NOT NULL PRIMARY KEY COMMENT '案件唯一識別碼；對應 clients.case_no',
    client_id INT NOT NULL COMMENT '對應 clients.id',
    staff_id INT NULL COMMENT '對應 staff.id (可為 NULL，代表尚未配對成功)',
    `status` ENUM('洽談中', '訂單成立', '服務中', '訂單完成', '訂單取消') DEFAULT '洽談中' COMMENT '專案狀態 (生命週期: 洽談中→訂單成立→服務中→訂單完成, 任何階段可→訂單取消)',
    cancel_reason TEXT NULL COMMENT '當狀態變更為 訂單取消 時的取消原因說明',
    line_group_id VARCHAR(100) NULL COMMENT '三方服務 LINE 群組 ID',
    actual_start_date DATE NULL COMMENT '實際生產服務開始日',
    actual_end_date DATE NULL COMMENT '實際生產服務結束日',
    contract_id VARCHAR(100) NULL COMMENT '好好簽線上契約 ID',
    
    -- 新增與計算公式直接關聯的基礎欄位
    service_days INT DEFAULT 0 COMMENT '服務天數 (N)',
    service_hours_per_day INT DEFAULT 0 COMMENT '每日服務時數 (J)',
    subsidy_eligibility VARCHAR(100) DEFAULT '非市民' COMMENT '補助資格 (一般市民/補助市民/非市民)',
    floor_fee DECIMAL(10, 2) DEFAULT 0.00 COMMENT '樓層費用 (O)',
    deposit_date DATE NULL COMMENT '訂金收取日期',
    deposit_service_days INT NULL COMMENT '訂金服務天數；NULL 表示歷史案件待人工補登',
    start_date DATE NULL COMMENT '預計/實際服務開始日 (AK)',
    end_date DATE NULL COMMENT '預計/實際服務結束日 (AL)',
    custom_rest_dates JSON NULL COMMENT '排定/自訂休假日期 JSON 陣列 (如 ["2026-07-05", "2026-07-12"])',
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_orders_case_no FOREIGN KEY (case_no) REFERENCES clients(case_no) ON UPDATE CASCADE ON DELETE RESTRICT,
    FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE CASCADE,
    FOREIGN KEY (staff_id) REFERENCES staff(id) ON DELETE SET NULL,
    CONSTRAINT chk_orders_deposit_service_days_nonnegative CHECK (
        deposit_service_days IS NULL OR deposit_service_days >= 0
    ),
    INDEX idx_order_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 17. 媒合意願詢問中介表
CREATE TABLE IF NOT EXISTS matching_records (
    id INT AUTO_INCREMENT PRIMARY KEY,
    case_no VARCHAR(50) NOT NULL COMMENT '對應 orders.case_no',
    staff_id INT NOT NULL COMMENT '對應 staff.id',
    caregiver_accepted TINYINT NULL COMMENT '是否接受媒合 (NULL: 待回覆, 1: 願意, 0: 無意願)',
    sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '詢問發送時間',
    replied_at TIMESTAMP NULL COMMENT '回覆時間',
    sent_info_1_at DATETIME NULL COMMENT '給服務人員的訂單資訊-1 發送時間',
    sent_info_2_at DATETIME NULL COMMENT '給服務人員的訂單資訊-2 發送時間',
    CONSTRAINT fk_matching_case_no FOREIGN KEY (case_no) REFERENCES orders(case_no) ON UPDATE CASCADE ON DELETE CASCADE,
    FOREIGN KEY (staff_id) REFERENCES staff(id) ON DELETE CASCADE,
    UNIQUE KEY uq_matching_case_staff (case_no, staff_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 18. 案件財務收支與轉帳紀錄表 (對照 帳務.xlsx)
CREATE TABLE IF NOT EXISTS payments (
    id INT AUTO_INCREMENT PRIMARY KEY,
    case_no VARCHAR(50) NOT NULL COMMENT '對應 clients.case_no / 查詢序號；帳務唯一案件識別碼',
    client_name VARCHAR(100) NULL COMMENT '客戶姓名備份',
    deposit_receivable DECIMAL(10, 2) DEFAULT 0.00 COMMENT '訂金應收金額',
    deposit_received DECIMAL(10, 2) DEFAULT 0.00 COMMENT '訂金實收金額',
    deposit_due_date DATE NULL COMMENT '訂金應收日期',
    deposit_received_at DATE NULL COMMENT '訂金實收日期',
    first_payment_receivable DECIMAL(10, 2) DEFAULT 0.00 COMMENT '第一期應收金額',
    first_payment_received DECIMAL(10, 2) DEFAULT 0.00 COMMENT '第一期實收金額',
    first_payment_due_date DATE NULL COMMENT '第一期應收日期',
    first_payment_received_at DATE NULL COMMENT '第一期實收日期',
    second_payment_receivable DECIMAL(10, 2) DEFAULT 0.00 COMMENT '第二期應收金額',
    second_payment_received DECIMAL(10, 2) DEFAULT 0.00 COMMENT '第二期實收金額',
    second_payment_due_date DATE NULL COMMENT '第二期應收日期',
    second_payment_received_at DATE NULL COMMENT '第二期實收日期',
    amount_receivable DECIMAL(10, 2) DEFAULT 0.00 COMMENT '應收總額',
    amount_received DECIMAL(10, 2) DEFAULT 0.00 COMMENT '實收總額',
    caregiver_fee DECIMAL(10, 2) DEFAULT 0.00 COMMENT '應轉帳給服務人員的費用',
    caregiver_paid_at DATE NULL COMMENT '服務人員費用轉帳日期',
    payment_status VARCHAR(50) DEFAULT '待收訂金' COMMENT '帳務狀態 (待收訂金/已收訂金/已收一期款/已收二期款/已結案)',
    notes TEXT NULL COMMENT '帳務備註',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_payment_status (payment_status),
    UNIQUE KEY uq_payments_case_no (case_no),
    CONSTRAINT fk_payments_case_no FOREIGN KEY (case_no) REFERENCES clients(case_no) ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- 19. 客戶帳務摘要（一案一筆；實際金流保存在 client_payment_transactions）
CREATE TABLE IF NOT EXISTS client_payments (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    case_no VARCHAR(50) NOT NULL COMMENT '唯一案件鍵，對應 orders.case_no',
    deposit_receivable DECIMAL(12, 2) NOT NULL DEFAULT 0.00,
    deposit_received DECIMAL(12, 2) NOT NULL DEFAULT 0.00,
    deposit_due_date DATE NULL,
    deposit_received_at DATE NULL COMMENT '訂金全額核銷日；部分入款見交易明細',
    first_payment_receivable DECIMAL(12, 2) NOT NULL DEFAULT 0.00,
    first_payment_received DECIMAL(12, 2) NOT NULL DEFAULT 0.00,
    first_payment_due_date DATE NULL,
    first_payment_received_at DATE NULL COMMENT '第一期全額核銷日',
    second_payment_receivable DECIMAL(12, 2) NOT NULL DEFAULT 0.00,
    second_payment_received DECIMAL(12, 2) NOT NULL DEFAULT 0.00,
    second_payment_due_date DATE NULL,
    second_payment_received_at DATE NULL COMMENT '第二期全額核銷日',
    amount_receivable DECIMAL(12, 2) NOT NULL DEFAULT 0.00 COMMENT '三階段應收總額',
    amount_received DECIMAL(12, 2) NOT NULL DEFAULT 0.00 COMMENT '三階段實收總額',
    subsidy_refund_receivable DECIMAL(12, 2) NOT NULL DEFAULT 0.00,
    subsidy_refund_refunded DECIMAL(12, 2) NOT NULL DEFAULT 0.00,
    subsidy_refund_due_date DATE NULL,
    subsidy_refund_at DATE NULL COMMENT '補助退款全額完成日',
    subsidy_return_receivable DECIMAL(12, 2) NOT NULL DEFAULT 0.00,
    subsidy_return_refunded DECIMAL(12, 2) NOT NULL DEFAULT 0.00,
    subsidy_return_due_date DATE NULL,
    subsidy_return_at DATE NULL,
    payment_status VARCHAR(50) NOT NULL DEFAULT '待收訂金',
    notes TEXT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_client_payments_case_no (case_no),
    CONSTRAINT fk_client_payments_case_no FOREIGN KEY (case_no) REFERENCES orders(case_no) ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 20. 客戶實際金流明細（可記錄部分入款、退款、沖正及失敗交易）
CREATE TABLE IF NOT EXISTS client_payment_transactions (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    client_payment_id BIGINT NOT NULL,
    case_no VARCHAR(50) NOT NULL,
    stage ENUM('deposit', 'first_payment', 'second_payment', 'subsidy_refund', 'subsidy_return', 'adjustment') NOT NULL,
    transaction_type ENUM('receipt', 'refund', 'reversal') NOT NULL,
    transaction_status ENUM('succeeded', 'failed', 'reversed') NOT NULL DEFAULT 'succeeded',
    amount DECIMAL(12, 2) NOT NULL,
    occurred_at DATE NULL,
    external_reference VARCHAR(100) NULL COMMENT '銀行流水或金流平台唯一識別',
    reversal_of_transaction_id BIGINT NULL,
    notes TEXT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_client_payment_tx_reference (external_reference),
    INDEX idx_client_payment_tx_case_stage (case_no, stage),
    CONSTRAINT fk_client_payment_tx_summary FOREIGN KEY (client_payment_id) REFERENCES client_payments(id) ON DELETE CASCADE,
    CONSTRAINT fk_client_payment_tx_case_no FOREIGN KEY (case_no) REFERENCES orders(case_no) ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT fk_client_payment_tx_reversal FOREIGN KEY (reversal_of_transaction_id) REFERENCES client_payment_transactions(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 21. 案件月嫂服務指派（同一案件可分成多段，由不同月嫂承接）
CREATE TABLE IF NOT EXISTS case_staff_assignments (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    case_no VARCHAR(50) NOT NULL,
    staff_id INT NOT NULL,
    assignment_sequence INT NOT NULL COMMENT '同案服務區段順序，從 1 起',
    assigned_start_date DATE NULL,
    assigned_end_date DATE NULL,
    planned_hours DECIMAL(10, 2) NULL,
    actual_hours DECIMAL(10, 2) NULL,
    hourly_rate DECIMAL(10, 2) NULL,
    floor_fee_allocated DECIMAL(12, 2) NOT NULL DEFAULT 0.00,
    status ENUM('planned', 'active', 'completed', 'replaced', 'cancelled') NOT NULL DEFAULT 'planned',
    replacement_reason VARCHAR(255) NULL,
    replaced_assignment_id BIGINT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_case_assignment_sequence (case_no, assignment_sequence),
    INDEX idx_assignment_staff_status (staff_id, status),
    CONSTRAINT fk_assignment_case_no FOREIGN KEY (case_no) REFERENCES orders(case_no) ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT fk_assignment_staff FOREIGN KEY (staff_id) REFERENCES staff(id) ON DELETE RESTRICT,
    CONSTRAINT fk_assignment_replaced FOREIGN KEY (replaced_assignment_id) REFERENCES case_staff_assignments(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 22. 月嫂應付摘要（一筆正式服務指派最多對應一筆）
CREATE TABLE IF NOT EXISTS staff_payments (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    assignment_id BIGINT NOT NULL,
    case_no VARCHAR(50) NOT NULL,
    staff_id INT NOT NULL,
    service_hours DECIMAL(10, 2) NOT NULL DEFAULT 0.00,
    hourly_rate DECIMAL(10, 2) NOT NULL DEFAULT 0.00,
    service_salary DECIMAL(12, 2) NOT NULL DEFAULT 0.00,
    floor_fee_amount DECIMAL(12, 2) NOT NULL DEFAULT 0.00,
    adjustment_amount DECIMAL(12, 2) NOT NULL DEFAULT 0.00,
    total_payable DECIMAL(12, 2) NOT NULL DEFAULT 0.00,
    amount_paid DECIMAL(12, 2) NOT NULL DEFAULT 0.00,
    due_date DATE NULL,
    paid_at DATE NULL COMMENT '全額實付完成日；部分轉帳見交易明細',
    payment_status ENUM('pending', 'partially_paid', 'paid', 'cancelled', 'review_required') NOT NULL DEFAULT 'pending',
    notes TEXT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_staff_payment_assignment (assignment_id),
    INDEX idx_staff_payment_staff_status (staff_id, payment_status),
    INDEX idx_staff_payment_case_no (case_no),
    CONSTRAINT fk_staff_payment_assignment FOREIGN KEY (assignment_id) REFERENCES case_staff_assignments(id) ON DELETE RESTRICT,
    CONSTRAINT fk_staff_payment_case_no FOREIGN KEY (case_no) REFERENCES orders(case_no) ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT fk_staff_payment_staff FOREIGN KEY (staff_id) REFERENCES staff(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 23. 月嫂實際轉帳明細（可記錄分次轉帳、失敗、退匯與沖正）
CREATE TABLE IF NOT EXISTS staff_payment_transactions (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    staff_payment_id BIGINT NOT NULL,
    case_no VARCHAR(50) NOT NULL,
    staff_id INT NOT NULL,
    transaction_type ENUM('transfer', 'reversal', 'return') NOT NULL,
    transaction_status ENUM('succeeded', 'failed', 'reversed') NOT NULL DEFAULT 'succeeded',
    amount DECIMAL(12, 2) NOT NULL,
    occurred_at DATE NULL,
    external_reference VARCHAR(100) NULL,
    reversal_of_transaction_id BIGINT NULL,
    notes TEXT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_staff_payment_tx_reference (external_reference),
    INDEX idx_staff_payment_tx_staff (staff_id, occurred_at),
    CONSTRAINT fk_staff_payment_tx_summary FOREIGN KEY (staff_payment_id) REFERENCES staff_payments(id) ON DELETE CASCADE,
    CONSTRAINT fk_staff_payment_tx_case_no FOREIGN KEY (case_no) REFERENCES orders(case_no) ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT fk_staff_payment_tx_staff FOREIGN KEY (staff_id) REFERENCES staff(id) ON DELETE RESTRICT,
    CONSTRAINT fk_staff_payment_tx_reversal FOREIGN KEY (reversal_of_transaction_id) REFERENCES staff_payment_transactions(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 24. 舊 payments 中無法安全歸屬的月嫂金額待覆核項目
CREATE TABLE IF NOT EXISTS payment_migration_reviews (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    legacy_payment_id INT NOT NULL,
    case_no VARCHAR(50) NOT NULL,
    legacy_caregiver_fee DECIMAL(12, 2) NOT NULL,
    legacy_caregiver_paid_at DATE NULL,
    reason VARCHAR(255) NOT NULL,
    review_status ENUM('pending', 'resolved', 'dismissed') NOT NULL DEFAULT 'pending',
    resolved_at TIMESTAMP NULL,
    resolution_notes TEXT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_payment_migration_review_legacy (legacy_payment_id),
    INDEX idx_payment_migration_review_case (case_no, review_status),
    CONSTRAINT fk_payment_migration_review_case_no FOREIGN KEY (case_no) REFERENCES orders(case_no) ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 25. 訂單與帳務整合檢視表 (獨立拆分訂金與樓層費，並提供首筆應付加總)
CREATE OR REPLACE VIEW v_order_details AS
SELECT 
    o.case_no AS case_no,
    o.status AS order_status,
    o.cancel_reason,
    o.line_group_id,
    o.actual_start_date,
    o.actual_end_date,
    o.contract_id,
    c.id AS client_id,
    c.name AS client_name,
    c.phone AS client_phone,
    c.service_type AS service_mode,
    s.id AS staff_id,
    s.name AS staff_name,
    s.phone AS staff_phone,
    
    -- 基礎實體欄位
    o.service_days,
    o.service_hours_per_day,
    o.subsidy_eligibility,
    o.floor_fee,           -- 樓層費用 (獨立顯示，生成契約用)
    o.deposit_date,
    o.start_date,
    o.end_date,
    
    -- 1. 時數計算
    (o.service_days * o.service_hours_per_day) AS total_hours,
    
    -- 2. 補助時數與自費時數
    CASE 
        WHEN o.subsidy_eligibility = '一般市民' THEN 40
        WHEN o.subsidy_eligibility = '補助市民' THEN 120
        ELSE 0 
    END AS subsidy_hours,
    
    GREATEST(0, (o.service_days * o.service_hours_per_day) - 
        CASE 
            WHEN o.subsidy_eligibility = '一般市民' THEN 40
            WHEN o.subsidy_eligibility = '補助市民' THEN 120
            ELSE 0 
        END
    ) AS self_pay_hours,
    
    -- 3. 雇主單價與訂金天數
    CASE 
        WHEN o.subsidy_eligibility = '非市民' THEN 350
        ELSE 300 
    END AS employer_unit_price,
    
    CASE 
        WHEN o.subsidy_eligibility = '補助市民' THEN 0
        ELSE 5 
    END AS deposit_days,
    
    -- 4. 純訂金金額 (獨立欄位，生成契約用)
    (CASE 
        WHEN o.subsidy_eligibility = '補助市民' THEN 0
        ELSE 5 
    END * 
     CASE 
        WHEN o.subsidy_eligibility = '非市民' THEN 350
        ELSE 300 
     END * 
     o.service_hours_per_day
    ) AS deposit_amount,
    
    -- 5. 首筆應付總額 = 純訂金 + 樓層費
    ((CASE 
        WHEN o.subsidy_eligibility = '補助市民' THEN 0
        ELSE 5 
      END * 
      CASE 
        WHEN o.subsidy_eligibility = '非市民' THEN 350
        ELSE 300 
      END * 
      o.service_hours_per_day
     ) + COALESCE(o.floor_fee, 0)
    ) AS initial_payment_payable,
    
    -- 6. 後續款項計算 (門禁控制：非'洽談中'且非'訂單取消'時才計算，否則為 NULL)
    CASE 
        WHEN o.status NOT IN ('洽談中', '訂單取消') THEN o.start_date
        ELSE NULL 
    END AS first_payment_date,
    
    CASE 
        WHEN o.status NOT IN ('洽談中', '訂單取消') THEN 
            GREATEST(0, o.service_days - CASE WHEN o.subsidy_eligibility = '補助市民' THEN 0 ELSE 5 END)
        ELSE NULL 
    END AS remaining_days,
    
    CASE 
        WHEN o.status NOT IN ('洽談中', '訂單取消') THEN 
            LEAST(15, GREATEST(0, o.service_days - CASE WHEN o.subsidy_eligibility = '補助市民' THEN 0 ELSE 5 END))
        ELSE NULL 
    END AS first_payment_days,
    
    CASE 
        WHEN o.status NOT IN ('洽談中', '訂單取消') THEN 
            LEAST(15, GREATEST(0, o.service_days - CASE WHEN o.subsidy_eligibility = '補助市民' THEN 0 ELSE 5 END)) * 
            o.service_hours_per_day * 
            CASE WHEN o.subsidy_eligibility = '非市民' THEN 350 ELSE 300 END
        ELSE NULL 
    END AS first_payment_amount,
    
    CASE 
        WHEN o.status NOT IN ('洽談中', '訂單取消') AND 
             (o.service_days - CASE WHEN o.subsidy_eligibility = '補助市民' THEN 0 ELSE 5 END - 15) > 0 THEN 
            DATE_ADD(o.start_date, INTERVAL 15 DAY)
        ELSE NULL 
    END AS second_payment_date,
    
    CASE 
        WHEN o.status NOT IN ('洽談中', '訂單取消') THEN 
            GREATEST(0, o.service_days - CASE WHEN o.subsidy_eligibility = '補助市民' THEN 0 ELSE 5 END - 15)
        ELSE NULL 
    END AS second_payment_days,
    
    CASE 
        WHEN o.status NOT IN ('洽談中', '訂單取消') THEN 
            GREATEST(0, o.service_days - CASE WHEN o.subsidy_eligibility = '補助市民' THEN 0 ELSE 5 END - 15) * 
            o.service_hours_per_day * 
            CASE WHEN o.subsidy_eligibility = '非市民' THEN 350 ELSE 300 END
        ELSE NULL 
    END AS second_payment_amount,
    
    -- 7. 雇主自費合計金額 (首筆 + 後續款項之總和，若後續款項未計算則只包含首筆)
    (
      ((CASE WHEN o.subsidy_eligibility = '補助市民' THEN 0 ELSE 5 END * CASE WHEN o.subsidy_eligibility = '非市民' THEN 350 ELSE 300 END * o.service_hours_per_day) + COALESCE(o.floor_fee, 0)) +
      COALESCE(
        CASE 
            WHEN o.status NOT IN ('洽談中', '訂單取消') THEN 
                LEAST(15, GREATEST(0, o.service_days - CASE WHEN o.subsidy_eligibility = '補助市民' THEN 0 ELSE 5 END)) * 
                o.service_hours_per_day * 
                CASE WHEN o.subsidy_eligibility = '非市民' THEN 350 ELSE 300 END
            ELSE 0 
        END, 0
      ) +
      COALESCE(
        CASE 
            WHEN o.status NOT IN ('洽談中', '訂單取消') THEN 
                GREATEST(0, o.service_days - CASE WHEN o.subsidy_eligibility = '補助市民' THEN 0 ELSE 5 END - 15) * 
                o.service_hours_per_day * 
                CASE WHEN o.subsidy_eligibility = '非市民' THEN 350 ELSE 300 END
            ELSE 0 
        END, 0
      )
    ) AS total_employer_self_pay_payable,
    
    -- 8. 服務人員 (月嫂) 薪資與付款日計算
    CASE 
        WHEN o.subsidy_eligibility = '一般市民' THEN 300
        WHEN o.subsidy_eligibility = '補助市民' THEN 350
        ELSE 320 
    END AS service_unit_price,
    
    CASE 
        WHEN o.status NOT IN ('洽談中', '訂單取消') THEN 
            (o.service_days * o.service_hours_per_day) *
            CASE WHEN o.subsidy_eligibility = '一般市民' THEN 300 WHEN o.subsidy_eligibility = '補助市民' THEN 350 ELSE 320 END
        ELSE NULL 
    END AS service_salary, -- 月嫂純薪資；樓層費以 floor_fee 獨立顯示與支付
    
    CASE
        WHEN o.status NOT IN ('洽談中', '訂單取消') AND o.end_date IS NOT NULL
             AND o.subsidy_eligibility = '補助市民' THEN
            DATE_ADD(LAST_DAY(DATE_ADD(o.end_date, INTERVAL 1 MONTH)), INTERVAL 15 DAY)
        WHEN o.status NOT IN ('洽談中', '訂單取消') AND o.end_date IS NOT NULL THEN
            DATE_ADD(LAST_DAY(o.end_date), INTERVAL 15 DAY)
        ELSE NULL 
    END AS salary_payment_date_1, -- 單次發薪：一般次月 15 日；補助市民次次月 15 日
    
    CASE 
        WHEN o.status NOT IN ('洽談中', '訂單取消') THEN 
            (CASE WHEN o.subsidy_eligibility = '一般市民' THEN 40 WHEN o.subsidy_eligibility = '補助市民' THEN 120 ELSE 0 END * 
             CASE WHEN o.subsidy_eligibility = '一般市民' THEN 300 WHEN o.subsidy_eligibility = '補助市民' THEN 350 ELSE 320 END)
        ELSE NULL 
    END AS subsidy_salary,
    
    CASE 
        WHEN o.status NOT IN ('洽談中', '訂單取消') AND o.subsidy_eligibility != '非市民' AND o.end_date IS NOT NULL THEN 
            DATE_ADD(LAST_DAY(o.end_date), INTERVAL 5 DAY)
        ELSE NULL 
    END AS govt_claim_date
FROM orders o
JOIN clients c ON o.client_id = c.id
LEFT JOIN staff s ON o.staff_id = s.id;


-- 20. 中華民國國定假日表
CREATE TABLE IF NOT EXISTS holidays (
    holiday_date DATE PRIMARY KEY COMMENT '假日日期',
    holiday_name VARCHAR(100) NOT NULL COMMENT '假日名稱',
    is_double_pay_default BOOLEAN DEFAULT TRUE COMMENT '是否預設為雙倍薪資日'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- 21. 服務人員排班與行事曆明細表
CREATE TABLE IF NOT EXISTS staff_schedule (
    id INT AUTO_INCREMENT PRIMARY KEY,
    case_no VARCHAR(50) NOT NULL COMMENT '對應 orders.case_no',
    staff_id INT NOT NULL COMMENT '對應 staff.id',
    work_date DATE NOT NULL COMMENT '工作日期',
    is_work_day BOOLEAN DEFAULT TRUE COMMENT '是否為工作日 (FALSE代表放假/休假)',
    is_double_pay BOOLEAN DEFAULT FALSE COMMENT '是否為雙倍薪資日 (如特殊國定假日上班)',
    notes VARCHAR(255) NULL COMMENT '行政人員調整備註',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_schedule_case_no FOREIGN KEY (case_no) REFERENCES orders(case_no) ON UPDATE CASCADE ON DELETE CASCADE,
    FOREIGN KEY (staff_id) REFERENCES staff(id) ON DELETE CASCADE,
    UNIQUE KEY ukey_staff_date (staff_id, work_date),
    INDEX idx_schedule_case_no (case_no)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 22. LINE 待推播任務隊列
CREATE TABLE IF NOT EXISTS line_tasks (
    id INT AUTO_INCREMENT PRIMARY KEY,
    to_user_id VARCHAR(100) NOT NULL COMMENT '接收訊息的 LINE 用戶唯一識別碼',
    message_content TEXT NOT NULL COMMENT '推播訊息內容',
    status VARCHAR(20) DEFAULT 'pending' COMMENT '推播狀態 (pending:待發送/sent:已發送/failed:發送失敗)',
    scheduled_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '預定發送時間；未指定時立即執行',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_line_tasks_due (status, scheduled_at, id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 23. 系統異常事件紀錄表
CREATE TABLE IF NOT EXISTS system_alerts (
    id INT AUTO_INCREMENT PRIMARY KEY,
    event_type VARCHAR(50) NOT NULL COMMENT '異常事件類型',
    description TEXT NOT NULL COMMENT '詳細異常描述',
    status ENUM('pending', 'resolved') DEFAULT 'pending' COMMENT '處理狀態 (pending:待處理/resolved:已排除)',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP NULL COMMENT '排除時間',
    resolved_by VARCHAR(50) NULL COMMENT '處理人員',
    INDEX idx_alert_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

