-- GENERATED FILE. Do not edit by hand.
-- Release: labor-union-validation-schema-2026-08-26-v10
-- Replace __LU_TEST_DATABASE__ with an explicitly confirmed lu_test_* database.
-- Rebuild with: python scripts/build_validation_schema_release.py

-- BEGIN SOURCE: db/schema.sql
-- File: schema.sql
-- Description: 定義 Labor Union fresh bootstrap 的基礎 MySQL schema。

-- 強制重建資料庫以確保 ENUM 編碼正確
DROP DATABASE IF EXISTS __LU_TEST_DATABASE__;
CREATE DATABASE __LU_TEST_DATABASE__ CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE __LU_TEST_DATABASE__;

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

-- 2. BeClass 報名紀錄表（舊版主關聯欄位為 query_no；後續 release 會加上 transition binding）
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

-- 39. 人員生命週期狀態、事件與冪等套用收據
CREATE TABLE IF NOT EXISTS staff_lifecycle_states (
    staff_id INT NOT NULL PRIMARY KEY,
    lifecycle_state ENUM('active','retired') NOT NULL DEFAULT 'active',
    aggregate_version BIGINT UNSIGNED NOT NULL DEFAULT 0,
    effective_at DATETIME(6) NULL,
    reason_code VARCHAR(64) NULL,
    updated_by VARCHAR(100) NULL,
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    CONSTRAINT fk_staff_lifecycle_state_staff FOREIGN KEY (staff_id) REFERENCES staff(id) ON DELETE RESTRICT,
    CONSTRAINT chk_staff_lifecycle_state_version CHECK (aggregate_version >= 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS staff_lifecycle_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    staff_id INT NOT NULL,
    event_type ENUM('retired','reactivated') NOT NULL,
    before_state ENUM('active','retired') NOT NULL,
    resulting_state ENUM('active','retired') NOT NULL,
    effective_at DATETIME(6) NOT NULL,
    reason_code VARCHAR(64) NOT NULL,
    expected_version BIGINT UNSIGNED NOT NULL,
    resulting_version BIGINT UNSIGNED NOT NULL,
    actor VARCHAR(100) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_staff_lifecycle_event_version (staff_id, resulting_version),
    INDEX idx_staff_lifecycle_event_time (staff_id, effective_at),
    CONSTRAINT fk_staff_lifecycle_event_staff FOREIGN KEY (staff_id) REFERENCES staff(id) ON DELETE RESTRICT,
    CONSTRAINT chk_staff_lifecycle_event_version CHECK (resulting_version = expected_version + 1)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS staff_lifecycle_apply_receipts (
    idempotency_key VARCHAR(191) NOT NULL PRIMARY KEY,
    command_fingerprint CHAR(64) NOT NULL,
    preview_fingerprint CHAR(64) NOT NULL,
    staff_id INT NOT NULL,
    resulting_state ENUM('active','retired') NOT NULL,
    resulting_version BIGINT UNSIGNED NOT NULL,
    event_id BIGINT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT fk_staff_lifecycle_receipt_staff FOREIGN KEY (staff_id) REFERENCES staff(id) ON DELETE RESTRICT,
    CONSTRAINT fk_staff_lifecycle_receipt_event FOREIGN KEY (event_id) REFERENCES staff_lifecycle_events(id) ON DELETE RESTRICT
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

-- 14. 人員已被預約/排班時間區間表
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
    `lifecycle_version` BIGINT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'ORD-01 aggregate revision；每個非 replay command 恰遞增一次',
    cancel_reason TEXT NULL COMMENT '當狀態變更為 訂單取消 時的取消原因說明',
    line_group_id VARCHAR(100) NULL COMMENT '三方服務 LINE 群組 ID',
    actual_start_date DATE NULL COMMENT '實際生產服務開始日',
    actual_end_date DATE NULL COMMENT '實際生產服務結束日',
    contract_identity VARCHAR(191) NULL COMMENT '訂單契約識別；不得綁定特定簽署平台',
    
    -- 新增與計算公式直接關聯的基礎欄位
    service_days INT DEFAULT 0 COMMENT '服務天數 (N)',
    service_hours_per_day INT DEFAULT 0 COMMENT '每日服務時數 (J)',
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
    sent_resume_at DATETIME NULL COMMENT '履歷發送給客戶的時間',
    CONSTRAINT fk_matching_case_no FOREIGN KEY (case_no) REFERENCES orders(case_no) ON UPDATE CASCADE ON DELETE CASCADE,
    FOREIGN KEY (staff_id) REFERENCES staff(id) ON DELETE CASCADE,
    UNIQUE KEY uq_matching_case_staff (case_no, staff_id)
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
    subsidy_return_review_status ENUM('review_required') NULL COMMENT '補助退還人工覆核狀態；NULL 表示未暫停自動核銷',
    subsidy_return_review_reason TEXT NULL COMMENT '補助退還需人工覆核的原因',
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
    original_assigned_start_date DATE NULL,
    original_assigned_end_date DATE NULL,
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

-- 21a. 多月嫂例外實際時數人工覆寫稽核（append-only）
CREATE TABLE IF NOT EXISTS actual_hours_adjustments (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    assignment_id BIGINT NOT NULL,
    previous_actual_hours DECIMAL(10, 2) NOT NULL,
    adjusted_actual_hours DECIMAL(10, 2) NOT NULL,
    adjustment_reason VARCHAR(255) NOT NULL,
    adjusted_by VARCHAR(100) NOT NULL,
    adjusted_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_actual_hours_adjustment_assignment (assignment_id, adjusted_at),
    CONSTRAINT chk_actual_hours_adjustment_previous_nonnegative CHECK (previous_actual_hours >= 0),
    CONSTRAINT chk_actual_hours_adjustment_adjusted_nonnegative CHECK (adjusted_actual_hours >= 0),
    CONSTRAINT fk_actual_hours_adjustment_assignment
        FOREIGN KEY (assignment_id) REFERENCES case_staff_assignments(id) ON DELETE RESTRICT
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



-- 26. 中華民國國定假日表
CREATE TABLE IF NOT EXISTS holidays (
    holiday_date DATE PRIMARY KEY COMMENT '假日日期',
    holiday_name VARCHAR(100) NOT NULL COMMENT '假日名稱',
    is_double_pay_default BOOLEAN DEFAULT FALSE COMMENT '相容欄位；排班不因國定假日自動套用雙倍薪資'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS admin_command_receipts (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    command_family VARCHAR(100) NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    request_fingerprint CHAR(64) NOT NULL,
    preview_fingerprint CHAR(64) NOT NULL,
    actor VARCHAR(100) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    result_snapshot JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_admin_command_receipt (command_family, idempotency_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- 27. 服務人員排班與行事曆明細表
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

-- 28. LINE 待推播任務隊列
CREATE TABLE IF NOT EXISTS line_tasks (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    to_user_id VARCHAR(100) NOT NULL COMMENT '接收訊息的 LINE 用戶唯一識別碼',
    task_type VARCHAR(50) NOT NULL DEFAULT 'line_push' COMMENT 'line_push/line_push_message/rag_reply/rich_menu_link/rich_menu_unlink',
    message_content TEXT NULL COMMENT '文字推播內容',
    payload_json JSON NULL COMMENT '非純文字任務參數',
    status ENUM('pending','processing','sent','failed','cancelled') NOT NULL DEFAULT 'pending',
    scheduled_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '預定發送時間；未指定時立即執行',
    processing_started_at DATETIME NULL,
    retry_count INT NOT NULL DEFAULT 0,
    max_retries INT NOT NULL DEFAULT 3,
    next_retry_at DATETIME NULL,
    sent_at DATETIME NULL,
    failed_at DATETIME NULL,
    error_code VARCHAR(100) NULL,
    error_message TEXT NULL,
    line_request_id VARCHAR(100) NULL,
    source_event_id VARCHAR(64) NULL,
    idempotency_key VARCHAR(100) NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_line_task_idempotency (idempotency_key),
    INDEX idx_line_tasks_due (status, scheduled_at, next_retry_at, id),
    INDEX idx_line_tasks_processing (status, processing_started_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 29. LINE Webhook 事件收件匣與去重
CREATE TABLE IF NOT EXISTS line_webhook_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    webhook_event_id VARCHAR(64) NOT NULL,
    event_type VARCHAR(50) NOT NULL,
    source_type VARCHAR(30) NULL,
    source_user_id VARCHAR(100) NULL,
    source_group_id VARCHAR(100) NULL,
    event_timestamp BIGINT NULL,
    is_redelivery BOOLEAN NOT NULL DEFAULT FALSE,
    processing_status ENUM('received','processing','completed','failed','ignored') NOT NULL DEFAULT 'received',
    payload_json JSON NOT NULL,
    received_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    processed_at DATETIME NULL,
    error_message TEXT NULL,
    UNIQUE KEY uk_line_webhook_event_id (webhook_event_id),
    INDEX idx_line_webhook_status (processing_status, received_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 30. LINE 使用者角色與好友狀態
CREATE TABLE IF NOT EXISTS line_users (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    line_user_id VARCHAR(100) NOT NULL,
    role ENUM('customer','staff','union_staff') NOT NULL DEFAULT 'customer',
    status ENUM('active','blocked','unknown') NOT NULL DEFAULT 'active',
    followed_at DATETIME NULL,
    blocked_at DATETIME NULL,
    last_event_at DATETIME NULL,
    onboarding_started_at DATETIME NULL,
    onboarding_completed_at DATETIME NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_line_user_id (line_user_id),
    INDEX idx_line_user_role_status (role, status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 31. LINE 人工確認請求（月嫂身分確認與舊客戶重新綁定）
CREATE TABLE IF NOT EXISTS line_confirmation_requests (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    request_type ENUM('staff_verification','client_rebind') NOT NULL,
    line_user_id VARCHAR(100) NOT NULL,
    client_id INT NULL,
    client_name VARCHAR(100) NULL,
    old_line_user_id VARCHAR(100) NULL,
    new_line_user_id VARCHAR(100) NULL,
    status ENUM('pending','approved','rejected','cancelled') NOT NULL DEFAULT 'pending',
    reviewed_by_admin_user_id BIGINT NULL COMMENT 'Web 管理中心處理者；開發終端處理時可為 NULL',
    reviewed_by_line_user_id VARCHAR(100) NULL,
    decision_reason TEXT NULL COMMENT '核准備註或拒絕原因',
    reviewed_at DATETIME NULL,
    resolved_at DATETIME NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_confirmation_pending (request_type, status, created_at),
    INDEX idx_confirmation_status_time (status, created_at),
    INDEX idx_confirmation_admin_reviewer (reviewed_by_admin_user_id, reviewed_at),
    INDEX idx_confirmation_requester (line_user_id, request_type, status),
    CONSTRAINT fk_confirmation_client FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 32. 管理後台帳號（LINE 管理中心與其他內部管理功能共用）
CREATE TABLE IF NOT EXISTS admin_users (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(100) NOT NULL,
    password_hash VARCHAR(512) NOT NULL COMMENT 'scrypt 雜湊；不得保存明碼密碼',
    display_name VARCHAR(100) NOT NULL,
    linked_line_user_id VARCHAR(100) NULL COMMENT '選填：對應 line_users.line_user_id',
    role ENUM('line_viewer','line_agent','line_manager','system_admin') NOT NULL DEFAULT 'line_viewer',
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    last_login_at DATETIME NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_admin_username (username),
    UNIQUE KEY uk_admin_linked_line_user (linked_line_user_id),
    CONSTRAINT fk_admin_linked_line_user FOREIGN KEY (linked_line_user_id)
        REFERENCES line_users(line_user_id) ON UPDATE CASCADE ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 33. 管理後台短時效登入 Session
CREATE TABLE IF NOT EXISTS admin_sessions (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    admin_user_id BIGINT NOT NULL,
    session_token_hash CHAR(64) NOT NULL COMMENT 'SHA-256；原始 Session Token 只回傳一次',
    expires_at DATETIME NOT NULL,
    last_seen_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revoked_at DATETIME NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_admin_session_token_hash (session_token_hash),
    INDEX idx_admin_session_active (admin_user_id, revoked_at, expires_at),
    CONSTRAINT fk_admin_session_user FOREIGN KEY (admin_user_id)
        REFERENCES admin_users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 33a. 唯一 root 帳號（root 是帳號中心授權事實，不是業務角色）
CREATE TABLE IF NOT EXISTS admin_root_account (
    singleton_key TINYINT NOT NULL DEFAULT 1,
    admin_user_id BIGINT NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (singleton_key),
    UNIQUE KEY uk_admin_root_account_user (admin_user_id),
    CONSTRAINT chk_admin_root_account_singleton CHECK (singleton_key = 1),
    CONSTRAINT fk_admin_root_account_user FOREIGN KEY (admin_user_id)
        REFERENCES admin_users(id) ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 33b. 管理員 TOTP factor；seed 只保存 application-key 加密後的 ciphertext。
CREATE TABLE IF NOT EXISTS admin_totp_factors (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    admin_user_id BIGINT NOT NULL,
    factor_state ENUM('enrollment_pending','active','revoked') NOT NULL,
    seed_ciphertext TEXT NOT NULL,
    encryption_key_version VARCHAR(64) NOT NULL,
    enrollment_challenge_hash CHAR(64) NOT NULL,
    enrollment_expires_at DATETIME(6) NOT NULL,
    last_successful_step BIGINT NULL,
    activated_at DATETIME(6) NULL,
    revoked_at DATETIME(6) NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    UNIQUE KEY uk_admin_totp_factor_user (admin_user_id),
    INDEX idx_admin_totp_factor_enrollment (factor_state,enrollment_expires_at),
    CONSTRAINT fk_admin_totp_factor_user FOREIGN KEY (admin_user_id)
        REFERENCES admin_users(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_admin_totp_factor_activation CHECK (
        (factor_state = 'active' AND activated_at IS NOT NULL AND revoked_at IS NULL)
        OR (factor_state = 'enrollment_pending' AND activated_at IS NULL AND revoked_at IS NULL)
        OR (factor_state = 'revoked' AND revoked_at IS NOT NULL)
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 33c. 每個 enrollment challenge 僅保存 hash，成功或逾期後不可重播。
CREATE TABLE IF NOT EXISTS admin_mfa_enrollment_challenges (
    id CHAR(36) PRIMARY KEY,
    admin_user_id BIGINT NOT NULL,
    challenge_hash CHAR(64) NOT NULL,
    expires_at DATETIME(6) NOT NULL,
    consumed_at DATETIME(6) NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uk_admin_mfa_challenge_hash (challenge_hash),
    INDEX idx_admin_mfa_challenge_user_expiry (admin_user_id,expires_at,consumed_at),
    CONSTRAINT fk_admin_mfa_challenge_user FOREIGN KEY (admin_user_id)
        REFERENCES admin_users(id) ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 33d. Recovery code 只存 scrypt hash，使用後不可再次通過驗證。
CREATE TABLE IF NOT EXISTS admin_totp_recovery_codes (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    factor_id BIGINT UNSIGNED NOT NULL,
    code_hash VARCHAR(512) NOT NULL,
    consumed_at DATETIME(6) NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uk_admin_totp_recovery_code_hash (code_hash),
    INDEX idx_admin_totp_recovery_factor (factor_id,consumed_at),
    CONSTRAINT fk_admin_totp_recovery_factor FOREIGN KEY (factor_id)
        REFERENCES admin_totp_factors(id) ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 33e. 登入嘗試與 rate-limit 決策事實；只保存去識別化的帳號與來源雜湊。
CREATE TABLE IF NOT EXISTS admin_login_attempts (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    username_hash CHAR(64) NOT NULL,
    source_hash CHAR(64) NOT NULL,
    outcome ENUM('failed','succeeded','rate_limited','mfa_replay') NOT NULL,
    occurred_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    INDEX idx_admin_login_attempt_subject (username_hash,source_hash,occurred_at),
    INDEX idx_admin_login_attempt_time (occurred_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 34. 管理後台操作稽核紀錄
CREATE TABLE IF NOT EXISTS admin_audit_logs (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    admin_user_id BIGINT NULL,
    action VARCHAR(100) NOT NULL,
    resource_type VARCHAR(100) NULL,
    resource_id VARCHAR(255) NULL,
    request_path VARCHAR(500) NULL,
    http_method VARCHAR(10) NULL,
    result_status INT NULL,
    ip_address VARCHAR(64) NULL,
    details_json JSON NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_admin_audit_actor_time (admin_user_id, created_at),
    INDEX idx_admin_audit_resource (resource_type, resource_id, created_at),
    CONSTRAINT fk_admin_audit_user FOREIGN KEY (admin_user_id)
        REFERENCES admin_users(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 34a. 管理後台高風險操作告警投遞箱（audit 同一交易寫入、incident worker 非同步投影）
CREATE TABLE IF NOT EXISTS admin_security_alert_outbox (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    source_audit_id BIGINT NOT NULL,
    alert_code VARCHAR(64) NOT NULL,
    alert_identity CHAR(64) NOT NULL,
    payload_snapshot JSON NOT NULL,
    processing_status ENUM('pending','processing','completed','dead') NOT NULL DEFAULT 'pending',
    attempt_count INT UNSIGNED NOT NULL DEFAULT 0,
    max_attempts INT UNSIGNED NOT NULL DEFAULT 5,
    next_attempt_at DATETIME(6) NULL,
    lease_owner VARCHAR(191) NULL,
    lease_expires_at DATETIME(6) NULL,
    last_error_code VARCHAR(64) NULL,
    completed_at DATETIME(6) NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    UNIQUE KEY uk_admin_security_alert_outbox_audit (source_audit_id),
    INDEX idx_admin_security_alert_outbox_due (processing_status, next_attempt_at, lease_expires_at, id),
    CONSTRAINT fk_admin_security_alert_outbox_audit FOREIGN KEY (source_audit_id)
        REFERENCES admin_audit_logs(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_admin_security_alert_outbox_payload CHECK (JSON_TYPE(payload_snapshot) = 'OBJECT'),
    CONSTRAINT chk_admin_security_alert_outbox_attempts CHECK (max_attempts > 0 AND attempt_count <= max_attempts)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 35. 系統異常事件紀錄表 (非財務類「流程提醒」警示：滾動更新，非不可竄改稽核軌跡；
--     財務類警示仍走 finance_alerts/finance_alert_events 的不可變事件溯源機制)
CREATE TABLE IF NOT EXISTS system_alerts (
    id INT AUTO_INCREMENT PRIMARY KEY,
    alert_code VARCHAR(50) NOT NULL COMMENT '異常代碼，例如 IMPORT-001, ORDER-001',
    source_domain VARCHAR(50) NOT NULL COMMENT '來源領域',
    case_key VARCHAR(100) NOT NULL COMMENT '案件識別鍵：正常為 case_no，查無案號時用 error_姓名_行動電話',
    reason VARCHAR(500) NOT NULL COMMENT '人類可讀的簡述',
    details JSON NOT NULL COMMENT '目前偵測到的異常內容，每次掃描直接覆蓋更新',
    status ENUM('open', 'claimed', 'resolved') NOT NULL DEFAULT 'open' COMMENT '處理狀態',
    claimed_by VARCHAR(100) NULL COMMENT '認領人員',
    claimed_at DATETIME NULL COMMENT '認領時間',
    resolved_by VARCHAR(100) NULL COMMENT '處理人員',
    resolved_at DATETIME NULL COMMENT '排除時間',
    resolution_reason VARCHAR(500) NULL COMMENT '處理原因',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_alert_case (alert_code, case_key),
    INDEX idx_system_alert_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 36. LINE 任務每次執行嘗試紀錄
CREATE TABLE IF NOT EXISTS line_task_attempts (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    task_id BIGINT NOT NULL,
    attempt_no INT NOT NULL,
    outcome ENUM('running','sent','retry_scheduled','failed') NOT NULL DEFAULT 'running',
    retryable BOOLEAN NULL,
    error_code VARCHAR(100) NULL,
    error_message TEXT NULL,
    line_request_id VARCHAR(100) NULL,
    started_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at DATETIME NULL,
    UNIQUE KEY uk_line_task_attempt_no (task_id, attempt_no),
    INDEX idx_line_task_attempt_outcome_time (outcome, started_at),
    CONSTRAINT fk_line_task_attempt_task FOREIGN KEY (task_id)
        REFERENCES line_tasks(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 37. 共用媒體資產中繼資料（圖片本體存於受控檔案系統／NAS／物件儲存）
CREATE TABLE IF NOT EXISTS media_assets (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    category ENUM('rich_menu','line_user_upload','contract','other') NOT NULL,
    owner_type VARCHAR(50) NULL,
    owner_id VARCHAR(100) NULL,
    storage_provider ENUM('local','nas','s3') NOT NULL DEFAULT 'local',
    storage_key VARCHAR(500) NOT NULL,
    original_filename VARCHAR(255) NULL,
    mime_type VARCHAR(100) NOT NULL,
    file_size BIGINT NOT NULL,
    sha256 CHAR(64) NOT NULL,
    width INT NULL,
    height INT NULL,
    created_by_admin_user_id BIGINT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at DATETIME NULL,
    UNIQUE KEY uk_media_storage_key (storage_key),
    INDEX idx_media_owner (category, owner_type, owner_id, deleted_at),
    INDEX idx_media_sha256 (sha256),
    CONSTRAINT fk_media_created_by FOREIGN KEY (created_by_admin_user_id)
        REFERENCES admin_users(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 38. LINE Rich Menu 發布工作與版本歷史
CREATE TABLE IF NOT EXISTS line_rich_menu_publications (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    menu_config_id VARCHAR(100) NOT NULL,
    audience_role ENUM('customer','staff','union_staff') NOT NULL,
    config_revision CHAR(64) NOT NULL,
    config_snapshot JSON NOT NULL,
    status ENUM('pending','processing','published','failed') NOT NULL DEFAULT 'pending',
    line_rich_menu_id VARCHAR(100) NULL,
    previous_line_rich_menu_id VARCHAR(100) NULL,
    image_asset_id BIGINT NULL,
    requested_by_admin_user_id BIGINT NULL,
    retry_count INT NOT NULL DEFAULT 0,
    max_retries INT NOT NULL DEFAULT 3,
    next_retry_at DATETIME NULL,
    processing_started_at DATETIME NULL,
    is_current BOOLEAN NOT NULL DEFAULT FALSE,
    error_code VARCHAR(100) NULL,
    error_message TEXT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    started_at DATETIME NULL,
    published_at DATETIME NULL,
    failed_at DATETIME NULL,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_rich_menu_publish_due (status, next_retry_at, id),
    INDEX idx_rich_menu_current (menu_config_id, is_current, published_at),
    INDEX idx_rich_menu_role (audience_role, status, published_at),
    CONSTRAINT fk_rich_menu_publish_asset FOREIGN KEY (image_asset_id)
        REFERENCES media_assets(id) ON DELETE SET NULL,
    CONSTRAINT fk_rich_menu_publish_admin FOREIGN KEY (requested_by_admin_user_id)
        REFERENCES admin_users(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
-- END SOURCE: db/schema.sql

-- BEGIN SOURCE: db/schema_parts/202_scheduling_staff_leave_intake.sql
-- File: 202_scheduling_staff_leave_intake.sql
-- Description: 新增月嫂 LINE 請假待辦的版本化根事實、事件、receipt 與正式排班關聯。

CREATE TABLE IF NOT EXISTS scheduling_staff_leave_request_aggregates (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    staff_id INT NOT NULL,
    line_user_id VARCHAR(191) NOT NULL,
    leave_start_date DATE NOT NULL,
    leave_end_date DATE NOT NULL,
    request_reason VARCHAR(1000) NOT NULL DEFAULT '',
    request_status ENUM('pending','accepted_for_processing','rejected','cancelled','resolved') NOT NULL,
    aggregate_version INT UNSIGNED NOT NULL DEFAULT 1,
    request_fingerprint CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_staff_leave_request_fingerprint (staff_id, request_fingerprint),
    INDEX idx_staff_leave_request_queue (request_status, created_at, id),
    CONSTRAINT fk_staff_leave_request_staff FOREIGN KEY (staff_id) REFERENCES staff(id),
    CONSTRAINT chk_staff_leave_request_dates CHECK (leave_start_date <= leave_end_date),
    CONSTRAINT chk_staff_leave_request_fingerprint CHECK (request_fingerprint REGEXP '^[0-9a-f]{64}$')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS scheduling_staff_leave_request_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    request_id BIGINT NOT NULL,
    aggregate_version INT UNSIGNED NOT NULL,
    event_type VARCHAR(64) NOT NULL,
    actor_id VARCHAR(191) NOT NULL,
    reason VARCHAR(1000) NOT NULL DEFAULT '',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_staff_leave_request_event_version (request_id, aggregate_version),
    CONSTRAINT fk_staff_leave_request_event_root FOREIGN KEY (request_id) REFERENCES scheduling_staff_leave_request_aggregates(id),
    CONSTRAINT chk_staff_leave_request_event_text CHECK (CHAR_LENGTH(TRIM(event_type)) > 0 AND CHAR_LENGTH(TRIM(actor_id)) > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS scheduling_staff_leave_request_receipts (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    idempotency_key VARCHAR(191) NOT NULL,
    request_id BIGINT NOT NULL,
    request_fingerprint CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    result_snapshot JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_staff_leave_request_receipt_key (idempotency_key),
    CONSTRAINT fk_staff_leave_request_receipt_root FOREIGN KEY (request_id) REFERENCES scheduling_staff_leave_request_aggregates(id),
    CONSTRAINT chk_staff_leave_request_receipt_fingerprint CHECK (request_fingerprint REGEXP '^[0-9a-f]{64}$'),
    CONSTRAINT chk_staff_leave_request_receipt_snapshot CHECK (JSON_TYPE(result_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS scheduling_staff_leave_request_resolution_links (
    request_id BIGINT PRIMARY KEY,
    leave_substitution_receipt_key VARCHAR(191) NOT NULL,
    linked_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_staff_leave_resolution_receipt (leave_substitution_receipt_key),
    CONSTRAINT fk_staff_leave_resolution_root FOREIGN KEY (request_id) REFERENCES scheduling_staff_leave_request_aggregates(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TRIGGER trg_staff_leave_request_events_before_update
BEFORE UPDATE ON scheduling_staff_leave_request_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'scheduling_staff_leave_request_events cannot be updated';

CREATE TRIGGER trg_staff_leave_request_events_before_delete
BEFORE DELETE ON scheduling_staff_leave_request_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'scheduling_staff_leave_request_events cannot be deleted';

CREATE TRIGGER trg_staff_leave_request_receipts_before_update
BEFORE UPDATE ON scheduling_staff_leave_request_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'scheduling_staff_leave_request_receipts cannot be updated';

CREATE TRIGGER trg_staff_leave_request_receipts_before_delete
BEFORE DELETE ON scheduling_staff_leave_request_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'scheduling_staff_leave_request_receipts cannot be deleted';

CREATE TRIGGER trg_staff_leave_resolution_links_before_update
BEFORE UPDATE ON scheduling_staff_leave_request_resolution_links
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'scheduling_staff_leave_request_resolution_links cannot be updated';

CREATE TRIGGER trg_staff_leave_resolution_links_before_delete
BEFORE DELETE ON scheduling_staff_leave_request_resolution_links
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'scheduling_staff_leave_request_resolution_links cannot be deleted';
-- END SOURCE: db/schema_parts/202_scheduling_staff_leave_intake.sql

-- BEGIN SOURCE: db/schema_parts/20_staff_monthly_settlements.sql
-- 服務人員月結摘要：每位服務人員、每個薪資歸屬月、每個修訂版一筆。
-- settlement_month 是薪資歸屬月份，不得由銀行交易日期回寫。
CREATE TABLE IF NOT EXISTS staff_monthly_settlements (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    staff_id INT NOT NULL,
    settlement_month DATE NOT NULL COMMENT '薪資歸屬月份；固定使用該月首日',
    revision INT UNSIGNED NOT NULL DEFAULT 1 COMMENT '同一服務人員同月的月結修訂版，從 1 起',
    total_payable DECIMAL(12, 2) NOT NULL DEFAULT 0.00 COMMENT '月結明細應付快照合計',
    total_paid DECIMAL(12, 2) NOT NULL DEFAULT 0.00 COMMENT '成功轉帳分配的淨額投影，不得人工覆寫',
    status ENUM(
        'draft',
        'finalized',
        'partially_paid',
        'paid',
        'cancelled',
        'review_required'
    ) NOT NULL DEFAULT 'draft',
    finalized_at TIMESTAMP NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_staff_monthly_settlement_revision (staff_id, settlement_month, revision),
    INDEX idx_staff_monthly_settlement_status (settlement_month, status),
    CONSTRAINT fk_staff_monthly_settlement_staff
        FOREIGN KEY (staff_id) REFERENCES staff(id) ON DELETE RESTRICT,
    CONSTRAINT chk_staff_monthly_settlement_month_start
        CHECK (DAY(settlement_month) = 1),
    CONSTRAINT chk_staff_monthly_settlement_revision
        CHECK (revision >= 1),
    CONSTRAINT chk_staff_monthly_settlement_totals
        CHECK (
            total_payable >= 0
            AND total_paid >= 0
            AND total_paid <= total_payable
        ),
    CONSTRAINT chk_staff_monthly_settlement_finalized_at
        CHECK (
            status <> 'finalized'
            OR finalized_at IS NOT NULL
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
-- END SOURCE: db/schema_parts/20_staff_monthly_settlements.sql

-- BEGIN SOURCE: db/schema_parts/30_staff_monthly_settlement_details.sql
-- 服務人員月結明細：凍結逐案件、逐服務指派的應付構成。
-- 實際銀行轉帳另由月結付款分配記錄，不得反寫本表的應付快照。
CREATE TABLE IF NOT EXISTS staff_monthly_settlement_details (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    settlement_id BIGINT NOT NULL,
    staff_payment_id BIGINT NOT NULL,
    case_no VARCHAR(50) NOT NULL,
    assignment_id BIGINT NOT NULL,
    staff_id INT NOT NULL,
    service_salary DECIMAL(12, 2) NOT NULL DEFAULT 0.00 COMMENT '一般服務薪資快照',
    legacy_subsidy_payable DECIMAL(12, 2) NOT NULL DEFAULT 0.00 COMMENT '舊制補助應付構成快照',
    floor_fee_amount DECIMAL(12, 2) NOT NULL DEFAULT 0.00 COMMENT '樓層費快照',
    adjustment_amount DECIMAL(12, 2) NOT NULL DEFAULT 0.00 COMMENT '可正可負的人工調整快照',
    payable_amount DECIMAL(12, 2) NOT NULL COMMENT '應付構成合計快照',
    legacy_subsidy_status ENUM(
        'not_applicable',
        'confirmed',
        'review_required'
    ) NOT NULL DEFAULT 'not_applicable',
    review_required BOOLEAN NOT NULL DEFAULT FALSE,
    review_note VARCHAR(500) NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_staff_monthly_settlement_detail_payment (settlement_id, staff_payment_id),
    INDEX idx_staff_monthly_settlement_detail_staff (staff_id, settlement_id),
    INDEX idx_staff_monthly_settlement_detail_case (case_no, assignment_id),
    CONSTRAINT fk_staff_monthly_settlement_detail_settlement
        FOREIGN KEY (settlement_id) REFERENCES staff_monthly_settlements(id) ON DELETE RESTRICT,
    CONSTRAINT fk_staff_monthly_settlement_detail_payment
        FOREIGN KEY (staff_payment_id) REFERENCES staff_payments(id) ON DELETE RESTRICT,
    CONSTRAINT fk_staff_monthly_settlement_detail_case
        FOREIGN KEY (case_no) REFERENCES orders(case_no) ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT fk_staff_monthly_settlement_detail_assignment
        FOREIGN KEY (assignment_id) REFERENCES case_staff_assignments(id) ON DELETE RESTRICT,
    CONSTRAINT fk_staff_monthly_settlement_detail_staff
        FOREIGN KEY (staff_id) REFERENCES staff(id) ON DELETE RESTRICT,
    CONSTRAINT chk_staff_monthly_settlement_detail_components
        CHECK (
            service_salary >= 0
            AND legacy_subsidy_payable >= 0
            AND floor_fee_amount >= 0
            AND payable_amount >= 0
            AND payable_amount = (
                service_salary
                + legacy_subsidy_payable
                + floor_fee_amount
                + adjustment_amount
            )
        ),
    CONSTRAINT chk_staff_monthly_settlement_detail_review_state
        CHECK (
            (
                legacy_subsidy_status = 'review_required'
                AND review_required = TRUE
            )
            OR (
                legacy_subsidy_status <> 'review_required'
                AND review_required = FALSE
            )
        ),
    CONSTRAINT chk_staff_monthly_settlement_detail_legacy_subsidy
        CHECK (
            legacy_subsidy_payable = 0
            OR legacy_subsidy_status IN ('confirmed', 'review_required')
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
-- END SOURCE: db/schema_parts/30_staff_monthly_settlement_details.sql

-- BEGIN SOURCE: db/schema_parts/40_staff_actual_transfers.sql
-- 服務人員實際銀行轉帳事件。
-- 每筆銀行流水只保存一次；跨訂單分配由獨立 allocation schema 負責。
CREATE TABLE IF NOT EXISTS staff_actual_transfers (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    settlement_id BIGINT NOT NULL,
    staff_id INT NOT NULL,
    payment_phase ENUM('normal', 'first_salary', 'second_subsidy', 'unknown')
        NOT NULL DEFAULT 'unknown',
    transaction_type ENUM('transfer', 'return', 'reversal') NOT NULL,
    transaction_status ENUM('succeeded', 'failed', 'reversed')
        NOT NULL DEFAULT 'succeeded',
    amount DECIMAL(12, 2) NOT NULL,
    occurred_at DATE NULL,
    source_bank VARCHAR(100) NOT NULL,
    source_account VARCHAR(100) NULL,
    counterparty_account VARCHAR(100) NULL,
    external_reference VARCHAR(191) NOT NULL,
    reversal_of_transfer_id BIGINT NULL,
    raw_import_reference VARCHAR(255) NULL,
    review_status ENUM('not_required', 'pending', 'confirmed')
        NOT NULL DEFAULT 'pending',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_staff_actual_transfer_reference UNIQUE (external_reference),
    INDEX idx_staff_actual_transfer_settlement (settlement_id, occurred_at),
    INDEX idx_staff_actual_transfer_staff (staff_id, occurred_at),
    INDEX idx_staff_actual_transfer_reversal (reversal_of_transfer_id),

    CONSTRAINT fk_staff_actual_transfer_settlement
        FOREIGN KEY (settlement_id)
        REFERENCES staff_monthly_settlements(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_staff_actual_transfer_staff
        FOREIGN KEY (staff_id)
        REFERENCES staff(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_staff_actual_transfer_reversal
        FOREIGN KEY (reversal_of_transfer_id)
        REFERENCES staff_actual_transfers(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,

    CONSTRAINT chk_staff_actual_transfer_amount
        CHECK (amount > 0),
    CONSTRAINT chk_staff_actual_transfer_succeeded_date
        CHECK (transaction_status <> 'succeeded' OR occurred_at IS NOT NULL),
    CONSTRAINT chk_staff_actual_transfer_original
        CHECK (
            (transaction_type = 'transfer' AND reversal_of_transfer_id IS NULL)
            OR
            (transaction_type IN ('return', 'reversal') AND reversal_of_transfer_id IS NOT NULL)
        ),
    CONSTRAINT chk_staff_actual_transfer_unknown_review
        CHECK (payment_phase <> 'unknown' OR review_status = 'pending')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
-- END SOURCE: db/schema_parts/40_staff_actual_transfers.sql

-- BEGIN SOURCE: db/schema_parts/50_staff_transfer_allocations.sql
CREATE TABLE IF NOT EXISTS staff_transfer_allocations (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    transfer_id BIGINT NOT NULL,
    settlement_detail_id BIGINT NOT NULL,
    allocated_amount DECIMAL(12, 2) NOT NULL,
    component_type ENUM(
        'regular_salary',
        'legacy_subsidy',
        'floor_fee',
        'adjustment',
        'unknown'
    ) NOT NULL DEFAULT 'unknown',
    allocation_method ENUM('explicit', 'inferred') NOT NULL DEFAULT 'explicit',
    review_status ENUM('approved', 'review_required', 'rejected')
        NOT NULL DEFAULT 'review_required',
    reversal_of_allocation_id BIGINT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_staff_transfer_allocation_target (
        transfer_id,
        settlement_detail_id,
        component_type
    ),
    INDEX idx_staff_transfer_allocation_detail (
        settlement_detail_id,
        review_status
    ),
    CONSTRAINT chk_staff_transfer_allocation_amount
        CHECK (allocated_amount > 0),
    CONSTRAINT chk_staff_transfer_allocation_inference_review
        CHECK (
            allocation_method <> 'inferred'
            OR review_status <> 'approved'
        ),
    CONSTRAINT fk_staff_transfer_allocation_transfer
        FOREIGN KEY (transfer_id)
        REFERENCES staff_actual_transfers(id)
        ON DELETE RESTRICT,
    CONSTRAINT fk_staff_transfer_allocation_detail
        FOREIGN KEY (settlement_detail_id)
        REFERENCES staff_monthly_settlement_details(id)
        ON DELETE RESTRICT,
    CONSTRAINT fk_staff_transfer_allocation_reversal
        FOREIGN KEY (reversal_of_allocation_id)
        REFERENCES staff_transfer_allocations(id)
        ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 既有資料庫可能仍使用 transfer/detail 兩欄唯一鍵。依實際欄位順序調整
-- 索引，讓 migration 可重跑；ALTER 僅改索引，不改寫既有 allocation 資料。
SET @staff_transfer_allocation_target_columns = (
    SELECT GROUP_CONCAT(
        COLUMN_NAME
        ORDER BY SEQ_IN_INDEX
        SEPARATOR ','
    )
    FROM INFORMATION_SCHEMA.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'staff_transfer_allocations'
      AND INDEX_NAME = 'uq_staff_transfer_allocation_target'
);
SET @staff_transfer_allocation_index_sql = CASE
    WHEN @staff_transfer_allocation_target_columns =
         'transfer_id,settlement_detail_id' THEN
        'ALTER TABLE `staff_transfer_allocations` DROP INDEX `uq_staff_transfer_allocation_target`, ADD UNIQUE KEY `uq_staff_transfer_allocation_target` (`transfer_id`, `settlement_detail_id`, `component_type`)'
    WHEN @staff_transfer_allocation_target_columns IS NULL THEN
        'ALTER TABLE `staff_transfer_allocations` ADD UNIQUE KEY `uq_staff_transfer_allocation_target` (`transfer_id`, `settlement_detail_id`, `component_type`)'
    ELSE 'SELECT 1'
END;
PREPARE staff_transfer_allocation_index_stmt
    FROM @staff_transfer_allocation_index_sql;
EXECUTE staff_transfer_allocation_index_stmt;
DEALLOCATE PREPARE staff_transfer_allocation_index_stmt;
-- END SOURCE: db/schema_parts/50_staff_transfer_allocations.sql

-- BEGIN SOURCE: db/schema_parts/60_finance_import_staging.sql
-- 每次 Excel 正規化結果的匯入批次；欄位名稱與 staging service 契約一致。
CREATE TABLE IF NOT EXISTS finance_import_batches (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    format_id ENUM('legacy', 'taishin', 'sinopac') NOT NULL,
    source_file VARCHAR(1024) NULL COMMENT '空批次或過渡期多來源輸入允許 NULL',
    sheet_name VARCHAR(191) NOT NULL,
    header_row INT UNSIGNED NOT NULL,
    row_count INT UNSIGNED NOT NULL DEFAULT 0,
    status ENUM('staged', 'completed', 'failed') NOT NULL DEFAULT 'staged',
    failure_message TEXT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP NULL,

    INDEX idx_finance_import_batch_status (status, created_at),
    CONSTRAINT chk_finance_import_batch_header_row CHECK (header_row >= 1)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- 跨批次唯一的 canonical 銀行流水。
-- batch_id 與來源位置欄位保留給既有 staging writer；新流程的每次實際出現位置
-- 必須另外寫入 finance_import_occurrences。dedup_fingerprint 必須由正式指紋服務
-- 產生；既有資料若仍有 NULL，後續 ALTER 會明確失敗，不得以偽造值補齊。
CREATE TABLE IF NOT EXISTS finance_import_rows (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    dedup_fingerprint CHAR(64) NOT NULL,
    batch_id BIGINT NULL COMMENT '首度建立 canonical row 的相容批次；後續出現以 occurrence 為準',
    format_id ENUM('legacy', 'taishin', 'sinopac') NOT NULL,
    source_file VARCHAR(1024) NULL COMMENT '首度出現來源，相容既有 writer',
    source_bank_account VARCHAR(191) NULL,
    sheet_name VARCHAR(191) NULL COMMENT '首度出現工作表，相容既有 writer',
    source_row INT UNSIGNED NULL COMMENT '首度出現的一基底列號，相容既有 writer',
    source_reference VARCHAR(191) NULL COMMENT '銀行原始參考值；不承擔唯一性',
    transaction_date DATE NULL,
    transaction_time TIME NULL,
    posting_date DATE NULL,
    value_date DATE NULL,
    debit DECIMAL(18, 2) NULL,
    credit DECIMAL(18, 2) NULL,
    direction ENUM('incoming', 'outgoing', 'unknown') NOT NULL,
    balance DECIMAL(18, 2) NULL,
    currency VARCHAR(16) NULL,
    summary TEXT NULL,
    memo TEXT NULL,
    counterparty_name VARCHAR(255) NULL,
    counterparty_account VARCHAR(191) NULL,
    -- Parsed only from a supported source field.  The raw bank value above is
    -- intentionally preserved for audit and manual review.
    resolved_counterparty_account VARCHAR(191) NULL,
    cancellation_code VARCHAR(191) NULL,
    bank_references JSON NOT NULL,
    warnings JSON NOT NULL,
    raw_payload JSON NOT NULL,
    matched_identity_ids JSON NOT NULL DEFAULT (JSON_ARRAY()),

    classification_type VARCHAR(100) NOT NULL DEFAULT 'pending',
    classification_reason VARCHAR(255) NULL,
    classified_at TIMESTAMP NULL,
    reconciliation_status VARCHAR(50) NOT NULL DEFAULT 'pending',
    reconciliation_reference VARCHAR(191) NULL,
    reconciled_at TIMESTAMP NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE KEY uq_finance_import_row_fingerprint (dedup_fingerprint),
    INDEX idx_finance_import_row_classification (
        classification_type,
        reconciliation_status
    ),
    INDEX idx_finance_import_row_account_date (
        source_bank_account,
        transaction_date
    ),

    CONSTRAINT fk_finance_import_row_compat_batch
        FOREIGN KEY (batch_id)
        REFERENCES finance_import_batches(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_finance_import_row_fingerprint CHECK (
        dedup_fingerprint REGEXP '^[0-9a-f]{64}$'
    ),
    CONSTRAINT chk_finance_import_row_source_row CHECK (
        source_row IS NULL OR source_row >= 1
    ),
    CONSTRAINT chk_finance_import_row_amounts CHECK (
        (debit IS NULL OR debit >= 0)
        AND (credit IS NULL OR credit >= 0)
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- Idempotent upgrade for an existing staging table. MySQL rejects this ALTER
-- when any legacy row still has a NULL fingerprint, forcing explicit data
-- review instead of manufacturing an identifier. Replaying it after a
-- successful upgrade is harmless.
ALTER TABLE finance_import_rows
    MODIFY COLUMN dedup_fingerprint CHAR(64) NOT NULL;


-- Additive, replayable upgrade for databases created before the resolved
-- account was introduced.  MySQL versions used by this project do not all
-- support ADD COLUMN IF NOT EXISTS, so use dynamic DDL after a metadata check.
-- Existing canonical rows deliberately remain NULL: this schema migration must
-- never infer or backfill a bank account.
SET @resolved_counterparty_account_exists = (
    SELECT COUNT(*)
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'finance_import_rows'
      AND COLUMN_NAME = 'resolved_counterparty_account'
);
SET @resolved_counterparty_account_ddl = IF(
    @resolved_counterparty_account_exists = 0,
    'ALTER TABLE finance_import_rows ADD COLUMN resolved_counterparty_account VARCHAR(191) NULL AFTER counterparty_account',
    'SELECT 1'
);
PREPARE add_resolved_counterparty_account FROM @resolved_counterparty_account_ddl;
EXECUTE add_resolved_counterparty_account;
DEALLOCATE PREPARE add_resolved_counterparty_account;


-- canonical 流水在每個來源檔／批次中的實際出現位置。
CREATE TABLE IF NOT EXISTS finance_import_occurrences (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    batch_id BIGINT NOT NULL,
    finance_import_row_id BIGINT NOT NULL,
    source_file VARCHAR(1024) NULL,
    sheet_name VARCHAR(191) NOT NULL,
    source_row INT UNSIGNED NOT NULL,
    warnings JSON NOT NULL DEFAULT (JSON_ARRAY()),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE KEY uq_finance_import_occurrence_position (
        batch_id,
        sheet_name,
        source_row
    ),
    INDEX idx_finance_import_occurrence_row (finance_import_row_id, batch_id),

    CONSTRAINT fk_finance_import_occurrence_batch
        FOREIGN KEY (batch_id)
        REFERENCES finance_import_batches(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_finance_import_occurrence_row
        FOREIGN KEY (finance_import_row_id)
        REFERENCES finance_import_rows(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_finance_import_occurrence_source_row CHECK (source_row >= 1)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
-- END SOURCE: db/schema_parts/60_finance_import_staging.sql

-- BEGIN SOURCE: db/schema_parts/61_finance_import_reprocessing.sql
-- Append-only audit for an explicitly requested historical finance reprocess.
-- The application inserts the completed run and its changed-row events in one
-- outer transaction. A dry run rolls that transaction back and leaves no IDs.
-- Add the replayable composite parent key used to prove that a referenced
-- import batch is completed. This changes no existing row values.
SET @finance_import_batch_status_key_exists = (
    SELECT COUNT(*)
    FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'finance_import_batches'
      AND INDEX_NAME = 'uq_finance_import_batch_id_status'
);
SET @finance_import_batch_status_key_ddl = IF(
    @finance_import_batch_status_key_exists = 0,
    'ALTER TABLE finance_import_batches ADD UNIQUE KEY uq_finance_import_batch_id_status (id, status)',
    'SELECT 1'
);
PREPARE add_finance_import_batch_status_key
    FROM @finance_import_batch_status_key_ddl;
EXECUTE add_finance_import_batch_status_key;
DEALLOCATE PREPARE add_finance_import_batch_status_key;


CREATE TABLE IF NOT EXISTS finance_import_reprocess_runs (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    batch_id BIGINT NOT NULL,
    batch_status ENUM('staged', 'completed', 'failed')
        NOT NULL DEFAULT 'completed',
    actor VARCHAR(255) NOT NULL,
    classifier_version VARCHAR(191) NOT NULL,
    plan_fingerprint CHAR(64) NOT NULL,
    selected_count INT UNSIGNED NOT NULL,
    changed_count INT UNSIGNED NOT NULL,
    dispatch_count INT UNSIGNED NOT NULL,
    reconciled_count INT UNSIGNED NOT NULL,
    pending_count INT UNSIGNED NOT NULL,
    request_summary JSON NOT NULL,
    result_summary JSON NOT NULL,
    status ENUM('completed') NOT NULL DEFAULT 'completed',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE KEY uq_finance_import_reprocess_run_plan (
        batch_id,
        plan_fingerprint
    ),
    INDEX idx_finance_import_reprocess_run_created (
        created_at,
        batch_id
    ),

    CONSTRAINT fk_finance_import_reprocess_run_batch
        FOREIGN KEY (batch_id, batch_status)
        REFERENCES finance_import_batches(id, status)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_finance_import_reprocess_run_batch_completed CHECK (
        batch_status = 'completed'
    ),
    CONSTRAINT chk_finance_import_reprocess_run_actor CHECK (
        CHAR_LENGTH(TRIM(actor)) > 0
    ),
    CONSTRAINT chk_finance_import_reprocess_run_classifier CHECK (
        CHAR_LENGTH(TRIM(classifier_version)) > 0
    ),
    CONSTRAINT chk_finance_import_reprocess_run_fingerprint CHECK (
        plan_fingerprint REGEXP '^[0-9a-f]{64}$'
    ),
    CONSTRAINT chk_finance_import_reprocess_run_counts CHECK (
        changed_count <= selected_count
        AND dispatch_count <= changed_count
        AND reconciled_count <= dispatch_count
        AND pending_count <= dispatch_count
        AND reconciled_count + pending_count <= dispatch_count
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- One event exists for each canonical row whose classification tuple changed.
CREATE TABLE IF NOT EXISTS finance_import_reclassification_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    run_id BIGINT NOT NULL,
    finance_import_row_id BIGINT NOT NULL,
    actor VARCHAR(255) NOT NULL,
    before_classification_type VARCHAR(100) NOT NULL,
    before_classification_reason VARCHAR(255) NULL,
    before_matched_identity_ids JSON NOT NULL,
    before_resolved_counterparty_account VARCHAR(191) NULL,
    after_classification_type VARCHAR(100) NOT NULL,
    after_classification_reason VARCHAR(255) NULL,
    after_matched_identity_ids JSON NOT NULL,
    after_resolved_counterparty_account VARCHAR(191) NULL,
    dispatch_result VARCHAR(100) NOT NULL,
    dispatch_reason VARCHAR(255) NULL,
    dispatch_references JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE KEY uq_finance_import_reclassification_event_row (
        run_id,
        finance_import_row_id
    ),
    INDEX idx_finance_import_reclassification_event_row (
        finance_import_row_id,
        created_at
    ),

    CONSTRAINT fk_finance_import_reclassification_event_run
        FOREIGN KEY (run_id)
        REFERENCES finance_import_reprocess_runs(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_finance_import_reclassification_event_row
        FOREIGN KEY (finance_import_row_id)
        REFERENCES finance_import_rows(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_finance_import_reclassification_event_actor CHECK (
        CHAR_LENGTH(TRIM(actor)) > 0
    ),
    CONSTRAINT chk_finance_import_reclassification_event_changed CHECK (
        NOT (
            before_classification_type <=> after_classification_type
            AND before_classification_reason <=> after_classification_reason
            AND before_matched_identity_ids <=> after_matched_identity_ids
            AND before_resolved_counterparty_account
                <=> after_resolved_counterparty_account
        )
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


DROP TRIGGER IF EXISTS trg_finance_import_reprocess_runs_before_update;
CREATE TRIGGER trg_finance_import_reprocess_runs_before_update
BEFORE UPDATE ON finance_import_reprocess_runs
FOR EACH ROW
SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'finance_import_reprocess_runs records cannot be updated';

DROP TRIGGER IF EXISTS trg_finance_import_reprocess_runs_before_delete;
CREATE TRIGGER trg_finance_import_reprocess_runs_before_delete
BEFORE DELETE ON finance_import_reprocess_runs
FOR EACH ROW
SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'finance_import_reprocess_runs records cannot be deleted';

DROP TRIGGER IF EXISTS trg_finance_import_reclassification_events_before_update;
CREATE TRIGGER trg_finance_import_reclassification_events_before_update
BEFORE UPDATE ON finance_import_reclassification_events
FOR EACH ROW
SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'finance_import_reclassification_events records cannot be updated';

DROP TRIGGER IF EXISTS trg_finance_import_reclassification_events_before_delete;
CREATE TRIGGER trg_finance_import_reclassification_events_before_delete
BEFORE DELETE ON finance_import_reclassification_events
FOR EACH ROW
SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'finance_import_reclassification_events records cannot be deleted';
-- END SOURCE: db/schema_parts/61_finance_import_reprocessing.sql

-- BEGIN SOURCE: db/schema_parts/65_client_payment_finance_link.sql
-- 讓客戶實際金流可追溯至 canonical 銀行流水。
-- 既有與人工補登交易允許 NULL；使用 INFORMATION_SCHEMA 讓 migration 可重跑。
SET @client_payment_finance_link_column_exists = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'client_payment_transactions'
      AND COLUMN_NAME = 'finance_import_row_id'
);
SET @client_payment_finance_link_sql = IF(
    @client_payment_finance_link_column_exists = 0,
    'ALTER TABLE `client_payment_transactions` ADD COLUMN `finance_import_row_id` BIGINT NULL COMMENT ''canonical 銀行流水；人工補登允許 NULL'' AFTER `external_reference`',
    'SELECT 1'
);
PREPARE client_payment_finance_link_stmt FROM @client_payment_finance_link_sql;
EXECUTE client_payment_finance_link_stmt;
DEALLOCATE PREPARE client_payment_finance_link_stmt;

SET @client_payment_finance_link_index_exists = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'client_payment_transactions'
      AND INDEX_NAME = 'idx_client_payment_tx_finance_import_row'
);
SET @client_payment_finance_link_sql = IF(
    @client_payment_finance_link_index_exists = 0,
    'ALTER TABLE `client_payment_transactions` ADD INDEX `idx_client_payment_tx_finance_import_row` (`finance_import_row_id`)',
    'SELECT 1'
);
PREPARE client_payment_finance_link_stmt FROM @client_payment_finance_link_sql;
EXECUTE client_payment_finance_link_stmt;
DEALLOCATE PREPARE client_payment_finance_link_stmt;

SET @client_payment_finance_link_fk_exists = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
    WHERE CONSTRAINT_SCHEMA = DATABASE()
      AND TABLE_NAME = 'client_payment_transactions'
      AND CONSTRAINT_NAME = 'fk_client_payment_tx_finance_import_row'
      AND CONSTRAINT_TYPE = 'FOREIGN KEY'
);
SET @client_payment_finance_link_sql = IF(
    @client_payment_finance_link_fk_exists = 0,
    'ALTER TABLE `client_payment_transactions` ADD CONSTRAINT `fk_client_payment_tx_finance_import_row` FOREIGN KEY (`finance_import_row_id`) REFERENCES `finance_import_rows` (`id`) ON UPDATE RESTRICT ON DELETE RESTRICT',
    'SELECT 1'
);
PREPARE client_payment_finance_link_stmt FROM @client_payment_finance_link_sql;
EXECUTE client_payment_finance_link_stmt;
DEALLOCATE PREPARE client_payment_finance_link_stmt;
-- END SOURCE: db/schema_parts/65_client_payment_finance_link.sql

-- BEGIN SOURCE: db/schema_parts/70_subsidy_claim_batches.sql
-- 正式季度政府補助申請批次；revision 由建立流程明確提供。
CREATE TABLE IF NOT EXISTS subsidy_claim_batches (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    application_year SMALLINT UNSIGNED NOT NULL,
    quarter TINYINT UNSIGNED NOT NULL,
    revision INT UNSIGNED NOT NULL,
    status ENUM(
        'draft',
        'submitted',
        'approved',
        'partially_paid',
        'paid'
    ) NOT NULL DEFAULT 'draft',
    requested_amount DECIMAL(12, 2) NOT NULL DEFAULT 0.00 COMMENT '送件時凍結的批次申請總額',
    approved_amount DECIMAL(12, 2) NOT NULL DEFAULT 0.00 COMMENT '政府核准總額，不覆寫申請總額',
    paid_amount DECIMAL(12, 2) NOT NULL DEFAULT 0.00 COMMENT '銀行撥款分配總額，不覆寫申請或核准總額',
    submitted_at DATETIME NULL,
    approved_at DATETIME NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_subsidy_claim_batch_revision (application_year, quarter, revision),
    INDEX idx_subsidy_claim_batch_status (application_year, quarter, status),
    CONSTRAINT chk_subsidy_claim_batch_year CHECK (application_year >= 1),
    CONSTRAINT chk_subsidy_claim_batch_quarter CHECK (quarter BETWEEN 1 AND 4),
    CONSTRAINT chk_subsidy_claim_batch_revision CHECK (revision >= 1),
    CONSTRAINT chk_subsidy_claim_batch_amounts CHECK (
        requested_amount >= 0
        AND approved_amount >= 0
        AND paid_amount >= 0
    ),
    CONSTRAINT chk_subsidy_claim_batch_state_times CHECK (
        (status = 'draft' AND submitted_at IS NULL AND approved_at IS NULL)
        OR (status = 'submitted' AND submitted_at IS NOT NULL AND approved_at IS NULL)
        OR (status IN ('approved', 'partially_paid', 'paid')
            AND submitted_at IS NOT NULL
            AND approved_at IS NOT NULL)
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 批次內逐服務指派的申請、核准與已撥快照。
CREATE TABLE IF NOT EXISTS subsidy_claim_batch_items (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    batch_id BIGINT NOT NULL,
    case_no VARCHAR(50) NOT NULL,
    assignment_id BIGINT NOT NULL,
    staff_id INT NOT NULL,
    claimed_hours DECIMAL(10, 2) NOT NULL DEFAULT 0.00,
    unit_price DECIMAL(10, 2) NOT NULL DEFAULT 0.00,
    requested_amount DECIMAL(12, 2) NOT NULL DEFAULT 0.00 COMMENT '建立批次時凍結，不由核准或撥款流程覆寫',
    approved_amount DECIMAL(12, 2) NOT NULL DEFAULT 0.00,
    paid_amount DECIMAL(12, 2) NOT NULL DEFAULT 0.00,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_subsidy_claim_batch_assignment (batch_id, assignment_id),
    INDEX idx_subsidy_claim_batch_item_case (case_no),
    INDEX idx_subsidy_claim_batch_item_staff (staff_id),
    CONSTRAINT fk_subsidy_claim_batch_item_batch
        FOREIGN KEY (batch_id) REFERENCES subsidy_claim_batches(id) ON DELETE RESTRICT,
    CONSTRAINT fk_subsidy_claim_batch_item_case
        FOREIGN KEY (case_no) REFERENCES orders(case_no) ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT fk_subsidy_claim_batch_item_assignment
        FOREIGN KEY (assignment_id) REFERENCES case_staff_assignments(id) ON DELETE RESTRICT,
    CONSTRAINT fk_subsidy_claim_batch_item_staff
        FOREIGN KEY (staff_id) REFERENCES staff(id) ON DELETE RESTRICT,
    CONSTRAINT chk_subsidy_claim_batch_item_values CHECK (
        claimed_hours >= 0
        AND unit_price >= 0
        AND requested_amount >= 0
        AND approved_amount >= 0
        AND paid_amount >= 0
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
-- END SOURCE: db/schema_parts/70_subsidy_claim_batches.sql

-- BEGIN SOURCE: db/schema_parts/80_government_subsidy_transactions.sql
-- 已唯一匹配正式申請批次的政府補助銀行事件。
-- 未唯一匹配的銀行流水只保留於 finance_import_rows，不建立本表資料。
-- 複合 FK 需要 claim item 提供 id + batch_id 候選鍵；以名稱守門使 loader 可重跑。
SET @gov_subsidy_allocation_table_exists = (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'government_subsidy_allocations'
);

SET @gov_subsidy_schema_exists = (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'subsidy_claim_batch_items'
      AND INDEX_NAME = 'uq_subsidy_claim_item_id_batch'
);
SET @gov_subsidy_schema_sql = IF(
    @gov_subsidy_schema_exists = 0,
    'ALTER TABLE `subsidy_claim_batch_items` ADD UNIQUE KEY `uq_subsidy_claim_item_id_batch` (`id`, `batch_id`)',
    'SELECT 1'
);
PREPARE gov_subsidy_schema_stmt FROM @gov_subsidy_schema_sql;
EXECUTE gov_subsidy_schema_stmt;
DEALLOCATE PREPARE gov_subsidy_schema_stmt;

CREATE TABLE IF NOT EXISTS government_subsidy_transactions (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    claim_batch_id BIGINT NOT NULL,
    finance_import_row_id BIGINT NOT NULL,
    transaction_type ENUM('receipt', 'reversal') NOT NULL,
    transaction_status ENUM('succeeded', 'failed', 'reversed')
        NOT NULL DEFAULT 'succeeded',
    amount DECIMAL(18, 2) NOT NULL,
    occurred_at DATE NULL,
    external_reference VARCHAR(191) NOT NULL,
    reversal_of_transaction_id BIGINT NULL,
    reversal_target_type ENUM('receipt', 'reversal') NOT NULL DEFAULT 'receipt',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE KEY uq_government_subsidy_transaction_import_row (
        finance_import_row_id
    ),
    UNIQUE KEY uq_government_subsidy_transaction_reference (
        external_reference
    ),
    UNIQUE KEY uq_government_subsidy_transaction_id_batch (
        id,
        claim_batch_id
    ),
    UNIQUE KEY uq_government_subsidy_transaction_reversal_target (
        id,
        claim_batch_id,
        transaction_type
    ),
    INDEX idx_government_subsidy_transaction_batch (
        claim_batch_id,
        occurred_at
    ),
    INDEX idx_government_subsidy_transaction_reversal (
        reversal_of_transaction_id
    ),

    CONSTRAINT fk_government_subsidy_transaction_batch
        FOREIGN KEY (claim_batch_id)
        REFERENCES subsidy_claim_batches(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_government_subsidy_transaction_import_row
        FOREIGN KEY (finance_import_row_id)
        REFERENCES finance_import_rows(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_government_subsidy_transaction_reversal_receipt
        FOREIGN KEY (reversal_of_transaction_id, claim_batch_id, reversal_target_type)
        REFERENCES government_subsidy_transactions(id, claim_batch_id, transaction_type)
        ON UPDATE RESTRICT ON DELETE RESTRICT,

    CONSTRAINT chk_government_subsidy_transaction_amount
        CHECK (amount > 0),
    CONSTRAINT chk_government_subsidy_transaction_succeeded_date
        CHECK (transaction_status <> 'succeeded' OR occurred_at IS NOT NULL),
    CONSTRAINT chk_government_subsidy_transaction_original
        CHECK (
            (transaction_type = 'receipt' AND reversal_of_transaction_id IS NULL)
            OR
            (transaction_type = 'reversal' AND reversal_of_transaction_id IS NOT NULL)
        ),
    CONSTRAINT chk_government_subsidy_transaction_reversal_target
        CHECK (reversal_target_type = 'receipt')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- 將複合同批次約束補到既有表；每一步獨立守門，中斷後仍可重跑。
SET @gov_subsidy_schema_exists = (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'government_subsidy_transactions'
      AND COLUMN_NAME = 'reversal_target_type'
);
SET @gov_subsidy_schema_sql = IF(
    @gov_subsidy_schema_exists = 0,
    'ALTER TABLE `government_subsidy_transactions` ADD COLUMN `reversal_target_type` ENUM(''receipt'', ''reversal'') NOT NULL DEFAULT ''receipt'' AFTER `reversal_of_transaction_id`',
    'SELECT 1'
);
PREPARE gov_subsidy_schema_stmt FROM @gov_subsidy_schema_sql;
EXECUTE gov_subsidy_schema_stmt;
DEALLOCATE PREPARE gov_subsidy_schema_stmt;

SET @gov_subsidy_schema_exists = (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'government_subsidy_transactions'
      AND INDEX_NAME = 'uq_government_subsidy_transaction_id_batch'
);
SET @gov_subsidy_schema_sql = IF(
    @gov_subsidy_schema_exists = 0,
    'ALTER TABLE `government_subsidy_transactions` ADD UNIQUE KEY `uq_government_subsidy_transaction_id_batch` (`id`, `claim_batch_id`)',
    'SELECT 1'
);
PREPARE gov_subsidy_schema_stmt FROM @gov_subsidy_schema_sql;
EXECUTE gov_subsidy_schema_stmt;
DEALLOCATE PREPARE gov_subsidy_schema_stmt;

SET @gov_subsidy_schema_exists = (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'government_subsidy_transactions'
      AND INDEX_NAME = 'uq_government_subsidy_transaction_reversal_target'
);
SET @gov_subsidy_schema_sql = IF(
    @gov_subsidy_schema_exists = 0,
    'ALTER TABLE `government_subsidy_transactions` ADD UNIQUE KEY `uq_government_subsidy_transaction_reversal_target` (`id`, `claim_batch_id`, `transaction_type`)',
    'SELECT 1'
);
PREPARE gov_subsidy_schema_stmt FROM @gov_subsidy_schema_sql;
EXECUTE gov_subsidy_schema_stmt;
DEALLOCATE PREPARE gov_subsidy_schema_stmt;

SET @gov_subsidy_schema_exists = (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
    WHERE CONSTRAINT_SCHEMA = DATABASE()
      AND TABLE_NAME = 'government_subsidy_transactions'
      AND CONSTRAINT_NAME = 'chk_government_subsidy_transaction_reversal_target'
);
SET @gov_subsidy_schema_sql = IF(
    @gov_subsidy_schema_exists = 0,
    'ALTER TABLE `government_subsidy_transactions` ADD CONSTRAINT `chk_government_subsidy_transaction_reversal_target` CHECK (`reversal_target_type` = ''receipt'')',
    'SELECT 1'
);
PREPARE gov_subsidy_schema_stmt FROM @gov_subsidy_schema_sql;
EXECUTE gov_subsidy_schema_stmt;
DEALLOCATE PREPARE gov_subsidy_schema_stmt;

SET @gov_subsidy_schema_exists = (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
    WHERE CONSTRAINT_SCHEMA = DATABASE()
      AND TABLE_NAME = 'government_subsidy_transactions'
      AND CONSTRAINT_NAME = 'fk_government_subsidy_transaction_reversal_receipt'
      AND CONSTRAINT_TYPE = 'FOREIGN KEY'
);
SET @gov_subsidy_schema_sql = IF(
    @gov_subsidy_schema_exists = 0,
    'ALTER TABLE `government_subsidy_transactions` ADD CONSTRAINT `fk_government_subsidy_transaction_reversal_receipt` FOREIGN KEY (`reversal_of_transaction_id`, `claim_batch_id`, `reversal_target_type`) REFERENCES `government_subsidy_transactions` (`id`, `claim_batch_id`, `transaction_type`) ON UPDATE RESTRICT ON DELETE RESTRICT',
    'SELECT 1'
);
PREPARE gov_subsidy_schema_stmt FROM @gov_subsidy_schema_sql;
EXECUTE gov_subsidy_schema_stmt;
DEALLOCATE PREPARE gov_subsidy_schema_stmt;

SET @gov_subsidy_schema_exists = (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'government_subsidy_allocations'
      AND COLUMN_NAME = 'reversal_target_type'
);
SET @gov_subsidy_schema_sql = IF(
    @gov_subsidy_allocation_table_exists = 1 AND @gov_subsidy_schema_exists = 0,
    'ALTER TABLE `government_subsidy_allocations` ADD COLUMN `reversal_target_type` ENUM(''receipt'', ''reversal'') NOT NULL DEFAULT ''receipt'' AFTER `reversal_of_allocation_id`',
    'SELECT 1'
);
PREPARE gov_subsidy_schema_stmt FROM @gov_subsidy_schema_sql;
EXECUTE gov_subsidy_schema_stmt;
DEALLOCATE PREPARE gov_subsidy_schema_stmt;

SET @gov_subsidy_schema_exists = (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'government_subsidy_allocations'
      AND INDEX_NAME = 'uq_government_subsidy_allocation_reversal_target'
);
SET @gov_subsidy_schema_sql = IF(
    @gov_subsidy_allocation_table_exists = 1 AND @gov_subsidy_schema_exists = 0,
    'ALTER TABLE `government_subsidy_allocations` ADD UNIQUE KEY `uq_government_subsidy_allocation_reversal_target` (`id`, `claim_batch_id`, `allocation_type`)',
    'SELECT 1'
);
PREPARE gov_subsidy_schema_stmt FROM @gov_subsidy_schema_sql;
EXECUTE gov_subsidy_schema_stmt;
DEALLOCATE PREPARE gov_subsidy_schema_stmt;

SET @gov_subsidy_schema_exists = (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
    WHERE CONSTRAINT_SCHEMA = DATABASE()
      AND TABLE_NAME = 'government_subsidy_allocations'
      AND CONSTRAINT_NAME = 'chk_government_subsidy_allocation_reversal_target'
);
SET @gov_subsidy_schema_sql = IF(
    @gov_subsidy_allocation_table_exists = 1 AND @gov_subsidy_schema_exists = 0,
    'ALTER TABLE `government_subsidy_allocations` ADD CONSTRAINT `chk_government_subsidy_allocation_reversal_target` CHECK (`reversal_target_type` = ''receipt'')',
    'SELECT 1'
);
PREPARE gov_subsidy_schema_stmt FROM @gov_subsidy_schema_sql;
EXECUTE gov_subsidy_schema_stmt;
DEALLOCATE PREPARE gov_subsidy_schema_stmt;

SET @gov_subsidy_schema_exists = (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
    WHERE CONSTRAINT_SCHEMA = DATABASE()
      AND TABLE_NAME = 'government_subsidy_allocations'
      AND CONSTRAINT_NAME = 'fk_government_subsidy_allocation_transaction_batch'
      AND CONSTRAINT_TYPE = 'FOREIGN KEY'
);
SET @gov_subsidy_schema_sql = IF(
    @gov_subsidy_allocation_table_exists = 1 AND @gov_subsidy_schema_exists = 0,
    'ALTER TABLE `government_subsidy_allocations` ADD CONSTRAINT `fk_government_subsidy_allocation_transaction_batch` FOREIGN KEY (`transaction_id`, `claim_batch_id`) REFERENCES `government_subsidy_transactions` (`id`, `claim_batch_id`) ON UPDATE RESTRICT ON DELETE RESTRICT',
    'SELECT 1'
);
PREPARE gov_subsidy_schema_stmt FROM @gov_subsidy_schema_sql;
EXECUTE gov_subsidy_schema_stmt;
DEALLOCATE PREPARE gov_subsidy_schema_stmt;

SET @gov_subsidy_schema_exists = (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
    WHERE CONSTRAINT_SCHEMA = DATABASE()
      AND TABLE_NAME = 'government_subsidy_allocations'
      AND CONSTRAINT_NAME = 'fk_government_subsidy_allocation_item_batch'
      AND CONSTRAINT_TYPE = 'FOREIGN KEY'
);
SET @gov_subsidy_schema_sql = IF(
    @gov_subsidy_allocation_table_exists = 1 AND @gov_subsidy_schema_exists = 0,
    'ALTER TABLE `government_subsidy_allocations` ADD CONSTRAINT `fk_government_subsidy_allocation_item_batch` FOREIGN KEY (`claim_item_id`, `claim_batch_id`) REFERENCES `subsidy_claim_batch_items` (`id`, `batch_id`) ON UPDATE RESTRICT ON DELETE RESTRICT',
    'SELECT 1'
);
PREPARE gov_subsidy_schema_stmt FROM @gov_subsidy_schema_sql;
EXECUTE gov_subsidy_schema_stmt;
DEALLOCATE PREPARE gov_subsidy_schema_stmt;

SET @gov_subsidy_schema_exists = (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
    WHERE CONSTRAINT_SCHEMA = DATABASE()
      AND TABLE_NAME = 'government_subsidy_allocations'
      AND CONSTRAINT_NAME = 'fk_government_subsidy_allocation_reversal_receipt'
      AND CONSTRAINT_TYPE = 'FOREIGN KEY'
);
SET @gov_subsidy_schema_sql = IF(
    @gov_subsidy_allocation_table_exists = 1 AND @gov_subsidy_schema_exists = 0,
    'ALTER TABLE `government_subsidy_allocations` ADD CONSTRAINT `fk_government_subsidy_allocation_reversal_receipt` FOREIGN KEY (`reversal_of_allocation_id`, `claim_batch_id`, `reversal_target_type`) REFERENCES `government_subsidy_allocations` (`id`, `claim_batch_id`, `allocation_type`) ON UPDATE RESTRICT ON DELETE RESTRICT',
    'SELECT 1'
);
PREPARE gov_subsidy_schema_stmt FROM @gov_subsidy_schema_sql;
EXECUTE gov_subsidy_schema_stmt;
DEALLOCATE PREPARE gov_subsidy_schema_stmt;


-- 政府入款逐筆分配至同一申請批次的案件／服務指派明細。
-- requested_amount 與 approved_amount 屬申請快照，不由本表覆寫。
CREATE TABLE IF NOT EXISTS government_subsidy_allocations (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    transaction_id BIGINT NOT NULL,
    claim_batch_id BIGINT NOT NULL,
    claim_item_id BIGINT NOT NULL,
    allocation_type ENUM('receipt', 'reversal') NOT NULL DEFAULT 'receipt',
    allocated_amount DECIMAL(18, 2) NOT NULL,
    reversal_of_allocation_id BIGINT NULL,
    reversal_target_type ENUM('receipt', 'reversal') NOT NULL DEFAULT 'receipt',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE KEY uq_government_subsidy_allocation_target (
        transaction_id,
        claim_item_id
    ),
    UNIQUE KEY uq_government_subsidy_allocation_reversal_target (
        id,
        claim_batch_id,
        allocation_type
    ),
    INDEX idx_government_subsidy_allocation_batch_item (
        claim_batch_id,
        claim_item_id
    ),
    INDEX idx_government_subsidy_allocation_reversal (
        reversal_of_allocation_id
    ),

    CONSTRAINT fk_government_subsidy_allocation_transaction_batch
        FOREIGN KEY (transaction_id, claim_batch_id)
        REFERENCES government_subsidy_transactions(id, claim_batch_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_government_subsidy_allocation_batch
        FOREIGN KEY (claim_batch_id)
        REFERENCES subsidy_claim_batches(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_government_subsidy_allocation_item_batch
        FOREIGN KEY (claim_item_id, claim_batch_id)
        REFERENCES subsidy_claim_batch_items(id, batch_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_government_subsidy_allocation_reversal_receipt
        FOREIGN KEY (reversal_of_allocation_id, claim_batch_id, reversal_target_type)
        REFERENCES government_subsidy_allocations(id, claim_batch_id, allocation_type)
        ON UPDATE RESTRICT ON DELETE RESTRICT,

    CONSTRAINT chk_government_subsidy_allocation_amount
        CHECK (allocated_amount > 0),
    CONSTRAINT chk_government_subsidy_allocation_original
        CHECK (
            (allocation_type = 'receipt' AND reversal_of_allocation_id IS NULL)
            OR
            (allocation_type = 'reversal' AND reversal_of_allocation_id IS NOT NULL)
        ),
    CONSTRAINT chk_government_subsidy_allocation_reversal_target
        CHECK (reversal_target_type = 'receipt')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
-- END SOURCE: db/schema_parts/80_government_subsidy_transactions.sql

-- BEGIN SOURCE: db/schema_parts/90_finance_alerts.sql
-- 財務邊界警示的目前人工處理狀態。
-- 本表只保存例外案件與稽核快照，不建立或修改任何正式交易、分配或淨額。
CREATE TABLE IF NOT EXISTS finance_alerts (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    alert_key VARCHAR(191) NOT NULL,
    alert_code VARCHAR(100) NOT NULL,
    source_domain VARCHAR(100) NOT NULL,
    source_type VARCHAR(100) NOT NULL,
    source_id VARCHAR(191) NOT NULL,
    finance_import_row_id BIGINT NULL,
    finance_import_batch_id BIGINT NULL,
    reason TEXT NOT NULL,
    expected_amount DECIMAL(18, 2) NULL,
    actual_amount DECIMAL(18, 2) NULL,
    difference_amount DECIMAL(18, 2) NULL,
    candidate_snapshot JSON NOT NULL,
    status ENUM('open', 'claimed', 'resolved') NOT NULL DEFAULT 'open',
    claimed_by VARCHAR(191) NULL,
    claimed_at DATETIME NULL,
    resolved_by VARCHAR(191) NULL,
    resolved_at DATETIME NULL,
    resolution_reason TEXT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,

    UNIQUE KEY uq_finance_alert_key (alert_key),
    INDEX idx_finance_alert_status (status, created_at),
    INDEX idx_finance_alert_source (
        source_domain,
        source_type,
        source_id
    ),
    INDEX idx_finance_alert_import_row (finance_import_row_id),
    INDEX idx_finance_alert_import_batch (finance_import_batch_id),

    CONSTRAINT fk_finance_alert_import_row
        FOREIGN KEY (finance_import_row_id)
        REFERENCES finance_import_rows(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_finance_alert_import_batch
        FOREIGN KEY (finance_import_batch_id)
        REFERENCES finance_import_batches(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_finance_alert_expected_amount
        CHECK (expected_amount IS NULL OR expected_amount >= 0),
    CONSTRAINT chk_finance_alert_actual_amount
        CHECK (actual_amount IS NULL OR actual_amount >= 0),
    CONSTRAINT chk_finance_alert_workflow
        CHECK (
            (
                status = 'open'
                AND claimed_by IS NULL
                AND claimed_at IS NULL
                AND resolved_by IS NULL
                AND resolved_at IS NULL
                AND resolution_reason IS NULL
            )
            OR
            (
                status = 'claimed'
                AND claimed_by IS NOT NULL
                AND claimed_at IS NOT NULL
                AND resolved_by IS NULL
                AND resolved_at IS NULL
                AND resolution_reason IS NULL
            )
            OR
            (
                status = 'resolved'
                AND (
                    (claimed_by IS NULL AND claimed_at IS NULL)
                    OR
                    (claimed_by IS NOT NULL AND claimed_at IS NOT NULL)
                )
                AND resolved_by IS NOT NULL
                AND resolved_at IS NOT NULL
                AND resolution_reason IS NOT NULL
            )
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- 警示的 append-only 稽核歷程。event_key 由服務依事件來源建立，
-- 唯一鍵使完全相同的匯入重跑或服務重試不會新增第二筆事件。
CREATE TABLE IF NOT EXISTS finance_alert_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    alert_id BIGINT NOT NULL,
    event_key VARCHAR(191) NOT NULL,
    event_type VARCHAR(50) NOT NULL,
    source_domain VARCHAR(100) NOT NULL,
    source_type VARCHAR(100) NOT NULL,
    source_id VARCHAR(191) NOT NULL,
    actor VARCHAR(191) NULL,
    reason TEXT NULL,
    event_snapshot JSON NOT NULL,
    occurred_at DATETIME NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE KEY uq_finance_alert_event_key (event_key),
    INDEX idx_finance_alert_event_history (alert_id, occurred_at, id),
    INDEX idx_finance_alert_event_source (
        source_domain,
        source_type,
        source_id
    ),

    CONSTRAINT fk_finance_alert_event_alert
        FOREIGN KEY (alert_id)
        REFERENCES finance_alerts(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
-- END SOURCE: db/schema_parts/90_finance_alerts.sql

-- BEGIN SOURCE: db/schema_parts/95_multi_caregiver_schedule.sql
-- 將日層級排班連回正式服務指派。既有排班一律保留 NULL，不能由 migration 推測歸屬。
-- 本 Schema Part 為可重跑 (idempotent)、純擴充 (additive-only) 的 DDL 守衛，嚴禁破壞性異動與寫入。
-- 遇到表缺失、同名錯誤規格或異名等價 metadata 時，一律以 MySQL PREPARE 相容之固定 sentinel 語句執行 fail-closed。

-- 1. 前置資料表存在性守衛 (staff_schedule 與 case_staff_assignments 均必須存在)
SET @ss_table_exists = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'staff_schedule'
);

SET @csa_table_exists = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'case_staff_assignments'
);

SET @prereq_action_sql = IF(
    @ss_table_exists = 0,
    'SELECT * FROM `FAIL_CLOSED_STAFF_SCHEDULE_TABLE_NOT_FOUND`',
    IF(
        @csa_table_exists = 0,
        'SELECT * FROM `FAIL_CLOSED_CASE_STAFF_ASSIGNMENTS_TABLE_NOT_FOUND`',
        'SELECT 1'
    )
);

PREPARE stmt_prereq FROM @prereq_action_sql;
EXECUTE stmt_prereq;
DEALLOCATE PREPARE stmt_prereq;

-- 2. assignment_id 欄位守衛 (BIGINT NULL)
SET @col_any_count = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'staff_schedule'
      AND COLUMN_NAME = 'assignment_id'
);

SET @col_exact_match = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'staff_schedule'
      AND COLUMN_NAME = 'assignment_id'
      AND (DATA_TYPE = 'bigint' OR COLUMN_TYPE LIKE '%bigint%')
      AND IS_NULLABLE = 'YES'
);

SET @col_action_sql = IF(
    @col_any_count > 0 AND @col_exact_match = 0,
    'SELECT * FROM `FAIL_CLOSED_ASSIGNMENT_ID_COLUMN_INVALID_SPEC_REVIEW_REQUIRED`',
    IF(
        @col_any_count = 0,
        'ALTER TABLE `staff_schedule` ADD COLUMN `assignment_id` BIGINT NULL COMMENT \'正式服務指派；既有未覆核排班保留 NULL\' AFTER `staff_id`',
        'SELECT 1'
    )
);

PREPARE stmt_col FROM @col_action_sql;
EXECUTE stmt_col;
DEALLOCATE PREPARE stmt_col;

-- 3. idx_staff_schedule_assignment 索引守衛 (NON_UNIQUE = 1, assignment_id)
SET @idx_any_cols = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'staff_schedule'
      AND INDEX_NAME = 'idx_staff_schedule_assignment'
);

SET @idx_exact_match = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'staff_schedule'
      AND INDEX_NAME = 'idx_staff_schedule_assignment'
      AND NON_UNIQUE = 1
      AND COLUMN_NAME = 'assignment_id'
      AND SEQ_IN_INDEX = 1
);

SET @idx_has_invalid_spec = IF(@idx_any_cols > 0 AND NOT (@idx_any_cols = 1 AND @idx_exact_match = 1), 1, 0);

SET @eq_idx_count = (
    SELECT COUNT(DISTINCT INDEX_NAME)
    FROM (
        SELECT INDEX_NAME,
               COUNT(*) AS total_cols,
               SUM(IF(COLUMN_NAME = 'assignment_id' AND SEQ_IN_INDEX = 1, 1, 0)) AS match_cols,
               MIN(NON_UNIQUE) AS min_non_unique
        FROM INFORMATION_SCHEMA.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'staff_schedule'
          AND INDEX_NAME != 'idx_staff_schedule_assignment'
        GROUP BY INDEX_NAME
    ) t
    WHERE min_non_unique = 1 AND total_cols = 1 AND match_cols = 1
);

SET @idx_action_sql = IF(
    @idx_has_invalid_spec = 1,
    'SELECT * FROM `FAIL_CLOSED_IDX_ASSIGNMENT_INVALID_SPEC_REVIEW_REQUIRED`',
    IF(
        @eq_idx_count > 0,
        'SELECT * FROM `FAIL_CLOSED_EQUIVALENT_ASSIGNMENT_INDEX_REVIEW_REQUIRED`',
        IF(
            @idx_any_cols = 0,
            'ALTER TABLE `staff_schedule` ADD INDEX `idx_staff_schedule_assignment` (`assignment_id`)',
            'SELECT 1'
        )
    )
);

PREPARE stmt_idx FROM @idx_action_sql;
EXECUTE stmt_idx;
DEALLOCATE PREPARE stmt_idx;

-- 4. fk_staff_schedule_assignment 外鍵守衛 (ON UPDATE RESTRICT ON DELETE RESTRICT)
SET @fk_any_count = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
    WHERE CONSTRAINT_SCHEMA = DATABASE()
      AND TABLE_NAME = 'staff_schedule'
      AND CONSTRAINT_NAME = 'fk_staff_schedule_assignment'
      AND CONSTRAINT_TYPE = 'FOREIGN KEY'
);

SET @fk_exact_match = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE k
    JOIN INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS r
      ON k.CONSTRAINT_SCHEMA = r.CONSTRAINT_SCHEMA
     AND k.TABLE_NAME = r.TABLE_NAME
     AND k.CONSTRAINT_NAME = r.CONSTRAINT_NAME
    WHERE k.CONSTRAINT_SCHEMA = DATABASE()
      AND k.TABLE_NAME = 'staff_schedule'
      AND k.CONSTRAINT_NAME = 'fk_staff_schedule_assignment'
      AND k.COLUMN_NAME = 'assignment_id'
      AND k.REFERENCED_TABLE_NAME = 'case_staff_assignments'
      AND k.REFERENCED_COLUMN_NAME = 'id'
      AND r.UPDATE_RULE = 'RESTRICT'
      AND r.DELETE_RULE = 'RESTRICT'
);

SET @fk_has_invalid_spec = IF(@fk_any_count > 0 AND @fk_exact_match = 0, 1, 0);

SET @eq_fk_count = (
    SELECT COUNT(DISTINCT k.CONSTRAINT_NAME)
    FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE k
    JOIN INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS r
      ON k.CONSTRAINT_SCHEMA = r.CONSTRAINT_SCHEMA
     AND k.TABLE_NAME = r.TABLE_NAME
     AND k.CONSTRAINT_NAME = r.CONSTRAINT_NAME
    WHERE k.CONSTRAINT_SCHEMA = DATABASE()
      AND k.TABLE_NAME = 'staff_schedule'
      AND k.CONSTRAINT_NAME != 'fk_staff_schedule_assignment'
      AND k.COLUMN_NAME = 'assignment_id'
      AND k.REFERENCED_TABLE_NAME = 'case_staff_assignments'
      AND k.REFERENCED_COLUMN_NAME = 'id'
      AND r.UPDATE_RULE = 'RESTRICT'
      AND r.DELETE_RULE = 'RESTRICT'
);

SET @fk_action_sql = IF(
    @fk_has_invalid_spec = 1,
    'SELECT * FROM `FAIL_CLOSED_FK_ASSIGNMENT_INVALID_SPEC_REVIEW_REQUIRED`',
    IF(
        @eq_fk_count > 0,
        'SELECT * FROM `FAIL_CLOSED_EQUIVALENT_ASSIGNMENT_FK_REVIEW_REQUIRED`',
        IF(
            @fk_any_count = 0,
            'ALTER TABLE `staff_schedule` ADD CONSTRAINT `fk_staff_schedule_assignment` FOREIGN KEY (assignment_id) REFERENCES case_staff_assignments (id) ON UPDATE RESTRICT ON DELETE RESTRICT',
            'SELECT 1'
        )
    )
);

PREPARE stmt_fk FROM @fk_action_sql;
EXECUTE stmt_fk;
DEALLOCATE PREPARE stmt_fk;

-- 5. staff_schedule_assignment_reviews 覆核表動態守衛與建立 (含完整 9 欄位規格、UQ、FK 與 RESTRICT 契約核對)
SET @reviews_table_exists = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'staff_schedule_assignment_reviews'
);

SET @reviews_col_exact_count = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'staff_schedule_assignment_reviews'
      AND (
          (COLUMN_NAME = 'id' AND (DATA_TYPE = 'bigint' OR COLUMN_TYPE LIKE '%bigint%') AND EXTRA LIKE '%auto_increment%' AND IS_NULLABLE = 'NO')
       OR (COLUMN_NAME = 'schedule_id' AND (DATA_TYPE = 'int' OR COLUMN_TYPE LIKE '%int%') AND IS_NULLABLE = 'NO')
       OR (COLUMN_NAME = 'review_reason' AND (DATA_TYPE = 'varchar' OR COLUMN_TYPE LIKE '%varchar%') AND CHARACTER_MAXIMUM_LENGTH = 100 AND IS_NULLABLE = 'NO')
       OR (COLUMN_NAME = 'review_status' AND (DATA_TYPE = 'enum' OR COLUMN_TYPE LIKE '%enum%') AND COLUMN_TYPE LIKE '%review_required%' AND COLUMN_TYPE LIKE '%resolved%' AND COLUMN_DEFAULT = 'review_required' AND IS_NULLABLE = 'NO')
       OR (COLUMN_NAME = 'resolved_assignment_id' AND (DATA_TYPE = 'bigint' OR COLUMN_TYPE LIKE '%bigint%') AND IS_NULLABLE = 'YES')
       OR (COLUMN_NAME = 'resolved_by' AND (DATA_TYPE = 'varchar' OR COLUMN_TYPE LIKE '%varchar%') AND CHARACTER_MAXIMUM_LENGTH = 100 AND IS_NULLABLE = 'YES')
       OR (COLUMN_NAME = 'resolved_at' AND (DATA_TYPE = 'timestamp' OR COLUMN_TYPE LIKE '%timestamp%') AND IS_NULLABLE = 'YES')
       OR (COLUMN_NAME = 'created_at' AND (DATA_TYPE = 'timestamp' OR COLUMN_TYPE LIKE '%timestamp%') AND UPPER(COALESCE(COLUMN_DEFAULT, '')) LIKE 'CURRENT_TIMESTAMP%' AND IS_NULLABLE = 'NO')
       OR (COLUMN_NAME = 'updated_at' AND (DATA_TYPE = 'timestamp' OR COLUMN_TYPE LIKE '%timestamp%') AND UPPER(COALESCE(COLUMN_DEFAULT, '')) LIKE 'CURRENT_TIMESTAMP%' AND IS_NULLABLE = 'NO')
      )
);

SET @reviews_updated_at_on_update_count = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'staff_schedule_assignment_reviews'
      AND COLUMN_NAME = 'updated_at'
      AND UPPER(COALESCE(EXTRA, '')) LIKE '%ON UPDATE CURRENT_TIMESTAMP%'
);

SET @reviews_uq_count = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'staff_schedule_assignment_reviews'
      AND INDEX_NAME = 'uq_schedule_review'
      AND NON_UNIQUE = 0
      AND COLUMN_NAME = 'schedule_id'
);

SET @reviews_fk_count = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS
    WHERE CONSTRAINT_SCHEMA = DATABASE()
      AND TABLE_NAME = 'staff_schedule_assignment_reviews'
      AND CONSTRAINT_NAME IN ('fk_schedule_assignment_review_schedule', 'fk_schedule_assignment_review_assignment')
      AND UPDATE_RULE = 'RESTRICT'
      AND DELETE_RULE = 'RESTRICT'
);

SET @reviews_check_count = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.CHECK_CONSTRAINTS cc
    JOIN INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
      ON tc.CONSTRAINT_CATALOG = cc.CONSTRAINT_CATALOG
     AND tc.CONSTRAINT_SCHEMA = cc.CONSTRAINT_SCHEMA
     AND tc.CONSTRAINT_NAME = cc.CONSTRAINT_NAME
    WHERE tc.CONSTRAINT_SCHEMA = DATABASE()
      AND tc.TABLE_SCHEMA = DATABASE()
      AND tc.TABLE_NAME = 'staff_schedule_assignment_reviews'
      AND tc.CONSTRAINT_TYPE = 'CHECK'
      AND tc.ENFORCED = 'YES'
      AND cc.CONSTRAINT_NAME = 'chk_schedule_assignment_review_resolution'
      AND UPPER(cc.CHECK_CLAUSE) LIKE '%REVIEW_STATUS%'
      AND UPPER(cc.CHECK_CLAUSE) LIKE '%RESOLVED_ASSIGNMENT_ID%'
      AND UPPER(cc.CHECK_CLAUSE) LIKE '%RESOLVED_BY%'
      AND UPPER(cc.CHECK_CLAUSE) LIKE '%RESOLVED_AT%'
);

SET @reviews_valid = IF(
    @reviews_table_exists = 1
    AND @reviews_col_exact_count = 9
    AND @reviews_updated_at_on_update_count = 1
    AND @reviews_uq_count = 1
    AND @reviews_fk_count = 2
    AND @reviews_check_count = 1,
    1,
    0
);

SET @reviews_invalid_spec = IF(@reviews_table_exists = 1 AND @reviews_valid = 0, 1, 0);

SET @reviews_action_sql = IF(
    @reviews_invalid_spec = 1,
    'SELECT * FROM `FAIL_CLOSED_REVIEWS_TABLE_INVALID_SPEC_REVIEW_REQUIRED`',
    IF(
        @reviews_table_exists = 0,
        'CREATE TABLE staff_schedule_assignment_reviews (id BIGINT AUTO_INCREMENT PRIMARY KEY, schedule_id INT NOT NULL, review_reason VARCHAR(100) NOT NULL, review_status ENUM(\'review_required\', \'resolved\') NOT NULL DEFAULT \'review_required\', resolved_assignment_id BIGINT NULL, resolved_by VARCHAR(100) NULL, resolved_at TIMESTAMP NULL, created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP, UNIQUE KEY uq_schedule_review (schedule_id), INDEX idx_schedule_assignment_review_status (review_status, created_at), CONSTRAINT chk_schedule_assignment_review_resolution CHECK ((review_status = \'review_required\' AND resolved_assignment_id IS NULL AND resolved_by IS NULL AND resolved_at IS NULL) OR (review_status = \'resolved\' AND resolved_assignment_id IS NOT NULL AND resolved_by IS NOT NULL AND resolved_at IS NOT NULL)), CONSTRAINT fk_schedule_assignment_review_schedule FOREIGN KEY (schedule_id) REFERENCES staff_schedule(id) ON UPDATE RESTRICT ON DELETE RESTRICT, CONSTRAINT fk_schedule_assignment_review_assignment FOREIGN KEY (resolved_assignment_id) REFERENCES case_staff_assignments(id) ON UPDATE RESTRICT ON DELETE RESTRICT) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci',
        'SELECT 1'
    )
);

PREPARE stmt_reviews FROM @reviews_action_sql;
EXECUTE stmt_reviews;
DEALLOCATE PREPARE stmt_reviews;
-- END SOURCE: db/schema_parts/95_multi_caregiver_schedule.sql

-- BEGIN SOURCE: db/schema_parts/96_order_assignment_sync_audit.sql
-- 保存已成功套用的訂單服務變更與正式月嫂指派配置；不可作為薪資或時數覆寫來源。
CREATE TABLE IF NOT EXISTS order_assignment_change_audits (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    case_no VARCHAR(50) NOT NULL,
    order_after_snapshot JSON NOT NULL,
    assignment_plan_snapshot JSON NOT NULL,
    applied_by VARCHAR(100) NOT NULL,
    applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_order_assignment_change_audit_case_time (case_no, applied_at),
    CONSTRAINT chk_order_assignment_change_audit_applied_by
        CHECK (CHAR_LENGTH(TRIM(applied_by)) > 0),
    CONSTRAINT fk_order_assignment_change_audit_case
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
-- END SOURCE: db/schema_parts/96_order_assignment_sync_audit.sql

-- BEGIN SOURCE: db/schema_parts/97_client_payment_subsidy_return_review.sql
-- 既有客戶帳務表補上補助退款人工覆核欄位。
-- 使用 INFORMATION_SCHEMA 逐欄檢查，確保 migration 可安全重跑且不改寫歷史資料。
SET @subsidy_return_review_status_exists = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'client_payments'
      AND COLUMN_NAME = 'subsidy_return_review_status'
);
SET @subsidy_return_review_sql = IF(
    @subsidy_return_review_status_exists = 0,
    'ALTER TABLE `client_payments` ADD COLUMN `subsidy_return_review_status` ENUM(''review_required'') NULL COMMENT ''補助退還人工覆核狀態；NULL 表示未暫停自動核銷'' AFTER `subsidy_return_at`',
    'SELECT 1'
);
PREPARE subsidy_return_review_stmt FROM @subsidy_return_review_sql;
EXECUTE subsidy_return_review_stmt;
DEALLOCATE PREPARE subsidy_return_review_stmt;

SET @subsidy_return_review_reason_exists = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'client_payments'
      AND COLUMN_NAME = 'subsidy_return_review_reason'
);
SET @subsidy_return_review_sql = IF(
    @subsidy_return_review_reason_exists = 0,
    'ALTER TABLE `client_payments` ADD COLUMN `subsidy_return_review_reason` TEXT NULL COMMENT ''補助退還需人工覆核的原因'' AFTER `subsidy_return_review_status`',
    'SELECT 1'
);
PREPARE subsidy_return_review_stmt FROM @subsidy_return_review_sql;
EXECUTE subsidy_return_review_stmt;
DEALLOCATE PREPARE subsidy_return_review_stmt;
-- END SOURCE: db/schema_parts/97_client_payment_subsidy_return_review.sql

-- BEGIN SOURCE: db/schema_parts/97_line_confirmation_review.sql
-- 第五階段 5.6：人工審查處理者、原因與查詢索引。
-- 使用 INFORMATION_SCHEMA 守門，使既有開發資料庫可重複執行 init_db.py。
SET @line_review_admin_column_exists = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'line_confirmation_requests'
      AND COLUMN_NAME = 'reviewed_by_admin_user_id'
);
SET @line_review_schema_sql = IF(
    @line_review_admin_column_exists = 0,
    'ALTER TABLE `line_confirmation_requests` ADD COLUMN `reviewed_by_admin_user_id` BIGINT NULL COMMENT ''Web 管理中心處理者；開發終端處理時可為 NULL'' AFTER `status`',
    'SELECT 1'
);
PREPARE line_review_schema_stmt FROM @line_review_schema_sql;
EXECUTE line_review_schema_stmt;
DEALLOCATE PREPARE line_review_schema_stmt;

SET @line_review_reason_column_exists = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'line_confirmation_requests'
      AND COLUMN_NAME = 'decision_reason'
);
SET @line_review_schema_sql = IF(
    @line_review_reason_column_exists = 0,
    'ALTER TABLE `line_confirmation_requests` ADD COLUMN `decision_reason` TEXT NULL COMMENT ''核准備註或拒絕原因'' AFTER `reviewed_by_line_user_id`',
    'SELECT 1'
);
PREPARE line_review_schema_stmt FROM @line_review_schema_sql;
EXECUTE line_review_schema_stmt;
DEALLOCATE PREPARE line_review_schema_stmt;

SET @line_review_status_index_exists = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'line_confirmation_requests'
      AND INDEX_NAME = 'idx_confirmation_status_time'
);
SET @line_review_schema_sql = IF(
    @line_review_status_index_exists = 0,
    'ALTER TABLE `line_confirmation_requests` ADD INDEX `idx_confirmation_status_time` (`status`, `created_at`)',
    'SELECT 1'
);
PREPARE line_review_schema_stmt FROM @line_review_schema_sql;
EXECUTE line_review_schema_stmt;
DEALLOCATE PREPARE line_review_schema_stmt;

SET @line_review_admin_index_exists = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'line_confirmation_requests'
      AND INDEX_NAME = 'idx_confirmation_admin_reviewer'
);
SET @line_review_schema_sql = IF(
    @line_review_admin_index_exists = 0,
    'ALTER TABLE `line_confirmation_requests` ADD INDEX `idx_confirmation_admin_reviewer` (`reviewed_by_admin_user_id`, `reviewed_at`)',
    'SELECT 1'
);
PREPARE line_review_schema_stmt FROM @line_review_schema_sql;
EXECUTE line_review_schema_stmt;
DEALLOCATE PREPARE line_review_schema_stmt;

SET @line_review_admin_fk_exists = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
    WHERE CONSTRAINT_SCHEMA = DATABASE()
      AND TABLE_NAME = 'line_confirmation_requests'
      AND CONSTRAINT_NAME = 'fk_confirmation_admin_reviewer'
      AND CONSTRAINT_TYPE = 'FOREIGN KEY'
);
SET @line_review_schema_sql = IF(
    @line_review_admin_fk_exists = 0,
    'ALTER TABLE `line_confirmation_requests` ADD CONSTRAINT `fk_confirmation_admin_reviewer` FOREIGN KEY (`reviewed_by_admin_user_id`) REFERENCES `admin_users` (`id`) ON DELETE SET NULL',
    'SELECT 1'
);
PREPARE line_review_schema_stmt FROM @line_review_schema_sql;
EXECUTE line_review_schema_stmt;
DEALLOCATE PREPARE line_review_schema_stmt;
-- END SOURCE: db/schema_parts/97_line_confirmation_review.sql

-- BEGIN SOURCE: db/schema_parts/98_caregiver_matching_plans.sql
-- 98_caregiver_matching_plans.sql
-- 建立洽談中訂單案件的配對方案 Header 表與連續服務區段 Detail 表。
-- 支援版本控管、同一案件唯一有效版本、最多四個連續區段及同一月嫂在單一版本內唯一。
-- 外鍵刪除策略使用 RESTRICT，維護歷史配對紀錄不可連帶刪除。
-- 包含與 DatabaseSchemaLoader 相容的單一 Statement 4 個 BEFORE UPDATE/DELETE 機械阻斷 Triggers。

CREATE TABLE IF NOT EXISTS caregiver_matching_plans (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    case_no VARCHAR(50) NOT NULL COMMENT '洽談中訂單案件編號；對應 orders.case_no',
    version INT NOT NULL DEFAULT 1 COMMENT '配對方案版本號 (1, 2, ...)',
    status ENUM('draft', 'proposed', 'accepted', 'rejected', 'superseded', 'cancelled') NOT NULL DEFAULT 'draft' COMMENT '配對方案狀態',
    is_active TINYINT(1) NULL COMMENT '1表示該案件目前有效版本；歷史版本或無效版本為 NULL 以支援 UNIQUE(case_no, is_active)',
    start_date DATE NOT NULL COMMENT '本方案完整服務開始日',
    end_date DATE NOT NULL COMMENT '本方案完整服務結束日',
    created_by VARCHAR(100) NOT NULL COMMENT '建立方案版本的非空管理員識別',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_caregiver_matching_plan_case_version (case_no, version),
    UNIQUE KEY uq_caregiver_matching_plan_active (case_no, is_active),
    INDEX idx_caregiver_matching_plan_status (status, created_at),
    CONSTRAINT fk_caregiver_matching_plans_case_no
        FOREIGN KEY (case_no) REFERENCES orders (case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_caregiver_matching_plans_created_by
        CHECK (created_by IS NOT NULL AND CHAR_LENGTH(TRIM(created_by)) > 0),
    CONSTRAINT chk_caregiver_matching_plans_version
        CHECK (version >= 1),
    CONSTRAINT chk_caregiver_matching_plans_dates
        CHECK (start_date <= end_date),
    CONSTRAINT chk_caregiver_matching_plans_is_active
        CHECK (is_active IS NULL OR is_active = 1)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS caregiver_matching_plan_segments (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    plan_id BIGINT NOT NULL COMMENT '對應 caregiver_matching_plans.id',
    segment_order TINYINT NOT NULL COMMENT '服務區段順序 (1 至 4)',
    staff_id INT NOT NULL COMMENT '月嫂識別；對應 staff.id',
    assigned_start_date DATE NOT NULL COMMENT '該區段預計服務開始日',
    assigned_end_date DATE NOT NULL COMMENT '該區段預計服務結束日',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_matching_plan_segment_order (plan_id, segment_order),
    UNIQUE KEY uq_matching_plan_staff (plan_id, staff_id),
    INDEX idx_matching_plan_segment_staff (staff_id, assigned_start_date, assigned_end_date),
    CONSTRAINT fk_matching_plan_segments_plan
        FOREIGN KEY (plan_id) REFERENCES caregiver_matching_plans (id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_matching_plan_segments_staff
        FOREIGN KEY (staff_id) REFERENCES staff (id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_matching_plan_segments_order
        CHECK (segment_order BETWEEN 1 AND 4),
    CONSTRAINT chk_matching_plan_segments_dates
        CHECK (assigned_start_date <= assigned_end_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 舊環境的表可能早於起訖欄位；先補欄位、依既有區段回填，再收斂為 NOT NULL。
SET @matching_plan_start_exists = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'caregiver_matching_plans'
      AND COLUMN_NAME = 'start_date'
);
SET @matching_plan_boundary_sql = IF(
    @matching_plan_start_exists = 0,
    'ALTER TABLE `caregiver_matching_plans` ADD COLUMN `start_date` DATE NULL AFTER `is_active`',
    'SELECT 1'
);
PREPARE matching_plan_boundary_stmt FROM @matching_plan_boundary_sql;
EXECUTE matching_plan_boundary_stmt;
DEALLOCATE PREPARE matching_plan_boundary_stmt;

SET @matching_plan_end_exists = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'caregiver_matching_plans'
      AND COLUMN_NAME = 'end_date'
);
SET @matching_plan_boundary_sql = IF(
    @matching_plan_end_exists = 0,
    'ALTER TABLE `caregiver_matching_plans` ADD COLUMN `end_date` DATE NULL AFTER `start_date`',
    'SELECT 1'
);
PREPARE matching_plan_boundary_stmt FROM @matching_plan_boundary_sql;
EXECUTE matching_plan_boundary_stmt;
DEALLOCATE PREPARE matching_plan_boundary_stmt;

UPDATE caregiver_matching_plans p
JOIN (
    SELECT plan_id,
           MIN(assigned_start_date) AS start_date,
           MAX(assigned_end_date) AS end_date
    FROM caregiver_matching_plan_segments
    GROUP BY plan_id
) bounds ON bounds.plan_id = p.id
SET p.start_date = COALESCE(p.start_date, bounds.start_date),
    p.end_date = COALESCE(p.end_date, bounds.end_date)
WHERE p.start_date IS NULL OR p.end_date IS NULL;

ALTER TABLE caregiver_matching_plans
    MODIFY COLUMN start_date DATE NOT NULL COMMENT '本方案完整服務開始日',
    MODIFY COLUMN end_date DATE NOT NULL COMMENT '本方案完整服務結束日';

DROP TRIGGER IF EXISTS trg_caregiver_matching_plans_before_update;
CREATE TRIGGER trg_caregiver_matching_plans_before_update BEFORE UPDATE ON caregiver_matching_plans FOR EACH ROW SET NEW.created_by = IF(OLD.id <=> NEW.id AND OLD.case_no <=> NEW.case_no AND OLD.version <=> NEW.version AND OLD.start_date <=> NEW.start_date AND OLD.end_date <=> NEW.end_date AND OLD.created_by <=> NEW.created_by AND OLD.created_at <=> NEW.created_at, NEW.created_by, NULL);

DROP TRIGGER IF EXISTS trg_caregiver_matching_plans_before_delete;
CREATE TRIGGER trg_caregiver_matching_plans_before_delete BEFORE DELETE ON caregiver_matching_plans FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'caregiver_matching_plans records cannot be deleted';

DROP TRIGGER IF EXISTS trg_caregiver_matching_plan_segments_before_update;
CREATE TRIGGER trg_caregiver_matching_plan_segments_before_update BEFORE UPDATE ON caregiver_matching_plan_segments FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'caregiver_matching_plan_segments records cannot be updated';

DROP TRIGGER IF EXISTS trg_caregiver_matching_plan_segments_before_delete;
CREATE TRIGGER trg_caregiver_matching_plan_segments_before_delete BEFORE DELETE ON caregiver_matching_plan_segments FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'caregiver_matching_plan_segments records cannot be deleted';
-- END SOURCE: db/schema_parts/98_caregiver_matching_plans.sql

-- BEGIN SOURCE: db/schema_parts/98_customer_service_tickets.sql
CREATE TABLE IF NOT EXISTS customer_service_tickets (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    line_user_id VARCHAR(100) NOT NULL,
    client_id INT NULL,
    case_no VARCHAR(50) NULL,
    category ENUM('service_flow','payment_subsidy','service_progress','profile_update','contact_union','other') NOT NULL,
    status ENUM('waiting','handling','resolved') NOT NULL DEFAULT 'waiting',
    assigned_to_admin_user_id BIGINT NULL,
    internal_note TEXT NULL,
    version BIGINT NOT NULL DEFAULT 0,
    resolved_at_utc DATETIME NULL,
    created_at_utc DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at_utc DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    active_marker TINYINT GENERATED ALWAYS AS (
        CASE WHEN status IN ('waiting','handling') THEN 1 ELSE NULL END
    ) STORED,
    UNIQUE KEY uq_customer_service_active_category (line_user_id, category, active_marker),
    INDEX idx_customer_service_status_time (status, created_at_utc),
    INDEX idx_customer_service_client (client_id, created_at_utc),
    INDEX idx_customer_service_case (case_no, created_at_utc),
    CONSTRAINT fk_customer_service_client FOREIGN KEY (client_id)
        REFERENCES clients(id) ON UPDATE RESTRICT ON DELETE SET NULL,
    CONSTRAINT fk_customer_service_order FOREIGN KEY (case_no)
        REFERENCES orders(case_no) ON UPDATE CASCADE ON DELETE SET NULL,
    CONSTRAINT fk_customer_service_admin FOREIGN KEY (assigned_to_admin_user_id)
        REFERENCES admin_users(id) ON UPDATE RESTRICT ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS client_profile_change_requests (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    line_user_id VARCHAR(100) NOT NULL COMMENT '提出異動申請的 LINE 用戶',
    client_id INT NOT NULL COMMENT '欲異動的客戶資料',
    case_no VARCHAR(50) NULL COMMENT '申請當下的案件編號',
    ticket_id BIGINT NULL COMMENT '關聯客服單',
    status ENUM('pending','approved','partially_approved','rejected','reverted') NOT NULL DEFAULT 'pending',
    requested_changes_json JSON NOT NULL COMMENT '用戶送出的欄位異動內容',
    old_values_json JSON NOT NULL COMMENT '送出當下 DB 原始值快照',
    applied_values_json JSON NULL COMMENT '審核通過後實際套用的新值',
    rejection_reason TEXT NULL,
    reviewed_by_name VARCHAR(100) NULL COMMENT '審核人員姓名快照',
    reviewed_by_admin_user_id BIGINT NULL COMMENT '審核工會人員',
    reviewed_at DATETIME NULL COMMENT '審核時間',
    reverted_by_name VARCHAR(100) NULL COMMENT '回復人員姓名快照',
    reverted_by_admin_user_id BIGINT NULL COMMENT '回復工會人員',
    reverted_at DATETIME NULL COMMENT '回復時間',
    revert_reason TEXT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_client_profile_change_status_time (status, created_at),
    INDEX idx_client_profile_change_line_user (line_user_id, created_at),
    INDEX idx_client_profile_change_client (client_id, created_at),
    INDEX idx_client_profile_change_ticket (ticket_id),
    CONSTRAINT fk_client_profile_change_client
        FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE RESTRICT,
    CONSTRAINT fk_client_profile_change_ticket
        FOREIGN KEY (ticket_id) REFERENCES customer_service_tickets(id) ON DELETE SET NULL,
    CONSTRAINT fk_client_profile_change_reviewer
        FOREIGN KEY (reviewed_by_admin_user_id) REFERENCES admin_users(id) ON DELETE SET NULL,
    CONSTRAINT fk_client_profile_change_reverter
        FOREIGN KEY (reverted_by_admin_user_id) REFERENCES admin_users(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

SET @profile_change_reviewed_by_name_exists = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'client_profile_change_requests'
      AND COLUMN_NAME = 'reviewed_by_name'
);
SET @profile_change_reviewed_by_name_sql = IF(
    @profile_change_reviewed_by_name_exists = 0,
    'ALTER TABLE client_profile_change_requests ADD COLUMN reviewed_by_name VARCHAR(100) NULL COMMENT ''審核人員姓名快照'' AFTER rejection_reason',
    'SELECT 1'
);
PREPARE profile_change_reviewed_by_name_stmt FROM @profile_change_reviewed_by_name_sql;
EXECUTE profile_change_reviewed_by_name_stmt;
DEALLOCATE PREPARE profile_change_reviewed_by_name_stmt;

SET @profile_change_reverted_by_name_exists = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'client_profile_change_requests'
      AND COLUMN_NAME = 'reverted_by_name'
);
SET @profile_change_reverted_by_name_sql = IF(
    @profile_change_reverted_by_name_exists = 0,
    'ALTER TABLE client_profile_change_requests ADD COLUMN reverted_by_name VARCHAR(100) NULL COMMENT ''回復人員姓名快照'' AFTER reviewed_at',
    'SELECT 1'
);
PREPARE profile_change_reverted_by_name_stmt FROM @profile_change_reverted_by_name_sql;
EXECUTE profile_change_reverted_by_name_stmt;
DEALLOCATE PREPARE profile_change_reverted_by_name_stmt;

SET @profile_change_status_type = (
    SELECT COLUMN_TYPE
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'client_profile_change_requests'
      AND COLUMN_NAME = 'status'
);
SET @profile_change_status_sql = IF(
    @profile_change_status_type NOT LIKE '%partially_approved%',
    'ALTER TABLE client_profile_change_requests MODIFY COLUMN status ENUM(''pending'',''approved'',''partially_approved'',''rejected'',''reverted'') NOT NULL DEFAULT ''pending''',
    'SELECT 1'
);
PREPARE profile_change_status_stmt FROM @profile_change_status_sql;
EXECUTE profile_change_status_stmt;
DEALLOCATE PREPARE profile_change_status_stmt;
-- END SOURCE: db/schema_parts/98_customer_service_tickets.sql

-- BEGIN SOURCE: db/schema_parts/99_caregiver_matching_plan_events.sql
-- 99_caregiver_matching_plan_events.sql
-- 建立 append-only 配對方案與區段的操作、意願與發送事實事件表。
-- 包含事件型別與標的契約 CHECK 約束、payload JSON Object CHECK 約束、event_key 冪等全表唯一，
-- 及 2 個與 DatabaseSchemaLoader 相容的單一 Statement 機械阻斷 Triggers。

CREATE TABLE IF NOT EXISTS caregiver_matching_plan_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    plan_id BIGINT NOT NULL COMMENT '對應 caregiver_matching_plans.id',
    segment_id BIGINT NULL COMMENT '對應 caregiver_matching_plan_segments.id；方案層級事件為 NULL',
    event_type ENUM('info_1_sent', 'info_2_sent', 'willingness_changed', 'resume_sent', 'plan_cancelled') NOT NULL COMMENT '事件類型',
    event_key VARCHAR(100) NOT NULL COMMENT '呼叫端提供的全表唯一非空冪等鍵',
    actor VARCHAR(100) NOT NULL COMMENT '記錄事件的非空管理員識別',
    payload JSON NOT NULL COMMENT '事件型別限定的不可變 JSON 內容',
    occurred_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '事件發生時間',
    UNIQUE KEY uq_caregiver_matching_plan_event_key (event_key),
    INDEX idx_caregiver_matching_plan_events_plan (plan_id, occurred_at),
    INDEX idx_caregiver_matching_plan_events_segment (segment_id, occurred_at),
    INDEX idx_caregiver_matching_plan_events_type (event_type, occurred_at),
    CONSTRAINT fk_caregiver_matching_plan_events_plan
        FOREIGN KEY (plan_id) REFERENCES caregiver_matching_plans (id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_caregiver_matching_plan_events_segment
        FOREIGN KEY (segment_id) REFERENCES caregiver_matching_plan_segments (id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_caregiver_matching_plan_events_target
        CHECK (
            (event_type IN ('info_1_sent', 'info_2_sent', 'willingness_changed', 'resume_sent') AND segment_id IS NOT NULL)
            OR (event_type = 'plan_cancelled' AND segment_id IS NULL)
        ),
    CONSTRAINT chk_caregiver_matching_plan_events_payload_object
        CHECK (JSON_TYPE(payload) = 'OBJECT'),
    CONSTRAINT chk_caregiver_matching_plan_events_nonempty
        CHECK (CHAR_LENGTH(TRIM(event_key)) > 0 AND CHAR_LENGTH(TRIM(actor)) > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_caregiver_matching_plan_events_before_update;
CREATE TRIGGER trg_caregiver_matching_plan_events_before_update BEFORE UPDATE ON caregiver_matching_plan_events FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'caregiver_matching_plan_events records cannot be updated';

DROP TRIGGER IF EXISTS trg_caregiver_matching_plan_events_before_delete;
CREATE TRIGGER trg_caregiver_matching_plan_events_before_delete BEFORE DELETE ON caregiver_matching_plan_events FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'caregiver_matching_plan_events records cannot be deleted';
-- END SOURCE: db/schema_parts/99_caregiver_matching_plan_events.sql

-- BEGIN SOURCE: db/schema_parts/99a_caregiver_availability_locks.sql
-- 99a_caregiver_availability_locks.sql
-- 建立等待訂金階段的配對方案鎖定批次 Header 表與逐月嫂逐日占用 Detail 表。
-- 包含狀態生命週期 CHECK 約束 (要求 released_by trim 後非空)、TIMESTAMP 顯式 NOT NULL、
-- UNIQUE 鍵防同方案/同月嫂同日重複 active 鎖定，外鍵刪除策略一律為 RESTRICT，
-- 並含 4 個與 DatabaseSchemaLoader 相容的單一 Statement 機械阻斷 Triggers。

CREATE TABLE IF NOT EXISTS caregiver_availability_locks (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    plan_id BIGINT NOT NULL COMMENT '對應 caregiver_matching_plans.id',
    status ENUM('active', 'released', 'converted', 'cancelled') NOT NULL DEFAULT 'active' COMMENT '鎖定批次狀態',
    is_active TINYINT(1) NULL COMMENT '1表示該方案目前有效鎖定批次；歷史/無效為 NULL 以支援 UNIQUE(plan_id, is_active)',
    created_by VARCHAR(100) NOT NULL COMMENT '建立鎖定批次的非空管理員識別',
    released_by VARCHAR(100) NULL COMMENT '解除/轉換/取消鎖定批次的管理員識別',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '建立時間',
    released_at TIMESTAMP NULL COMMENT '解除/轉換/取消時間',
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新時間',
    UNIQUE KEY uq_availability_lock_plan_active (plan_id, is_active),
    INDEX idx_availability_locks_status (status, created_at),
    CONSTRAINT fk_availability_locks_plan
        FOREIGN KEY (plan_id) REFERENCES caregiver_matching_plans (id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_availability_locks_status_state
        CHECK (
            (status = 'active' AND is_active = 1 AND released_by IS NULL AND released_at IS NULL)
            OR (status IN ('released', 'converted', 'cancelled') AND is_active IS NULL AND CHAR_LENGTH(TRIM(released_by)) > 0 AND released_at IS NOT NULL)
        ),
    CONSTRAINT chk_availability_locks_created_by
        CHECK (CHAR_LENGTH(TRIM(created_by)) > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS caregiver_availability_lock_days (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    lock_id BIGINT NOT NULL COMMENT '對應 caregiver_availability_locks.id',
    segment_id BIGINT NOT NULL COMMENT '對應 caregiver_matching_plan_segments.id',
    staff_id INT NOT NULL COMMENT '月嫂識別；對應 staff.id',
    lock_date DATE NOT NULL COMMENT '等待訂金占用日期',
    active_marker TINYINT(1) NULL COMMENT '1表示該月嫂該日有效等待訂金鎖；已解除為 NULL 以支援 UNIQUE(staff_id, lock_date, active_marker)',
    released_by VARCHAR(100) NULL COMMENT '解除鎖定的管理員識別',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '建立時間',
    released_at TIMESTAMP NULL COMMENT '解除時間',
    UNIQUE KEY uq_availability_lock_staff_date_active (staff_id, lock_date, active_marker),
    UNIQUE KEY uq_availability_lock_segment_date (lock_id, segment_id, lock_date),
    INDEX idx_availability_lock_days_segment (segment_id, lock_date),
    CONSTRAINT fk_availability_lock_days_lock
        FOREIGN KEY (lock_id) REFERENCES caregiver_availability_locks (id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_availability_lock_days_segment
        FOREIGN KEY (segment_id) REFERENCES caregiver_matching_plan_segments (id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_availability_lock_days_staff
        FOREIGN KEY (staff_id) REFERENCES staff (id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_availability_lock_days_active_state
        CHECK (
            (active_marker = 1 AND released_by IS NULL AND released_at IS NULL)
            OR (active_marker IS NULL AND CHAR_LENGTH(TRIM(released_by)) > 0 AND released_at IS NOT NULL)
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_caregiver_availability_locks_before_update;
CREATE TRIGGER trg_caregiver_availability_locks_before_update BEFORE UPDATE ON caregiver_availability_locks FOR EACH ROW SET NEW.created_by = IF(OLD.id <=> NEW.id AND OLD.plan_id <=> NEW.plan_id AND OLD.created_by <=> NEW.created_by AND OLD.created_at <=> NEW.created_at, NEW.created_by, NULL);

DROP TRIGGER IF EXISTS trg_caregiver_availability_locks_before_delete;
CREATE TRIGGER trg_caregiver_availability_locks_before_delete BEFORE DELETE ON caregiver_availability_locks FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'caregiver_availability_locks records cannot be deleted';

DROP TRIGGER IF EXISTS trg_caregiver_availability_lock_days_before_update;
CREATE TRIGGER trg_caregiver_availability_lock_days_before_update BEFORE UPDATE ON caregiver_availability_lock_days FOR EACH ROW SET NEW.lock_id = IF(OLD.id <=> NEW.id AND OLD.lock_id <=> NEW.lock_id AND OLD.segment_id <=> NEW.segment_id AND OLD.staff_id <=> NEW.staff_id AND OLD.lock_date <=> NEW.lock_date AND OLD.created_at <=> NEW.created_at, NEW.lock_id, NULL);

DROP TRIGGER IF EXISTS trg_caregiver_availability_lock_days_before_delete;
CREATE TRIGGER trg_caregiver_availability_lock_days_before_delete BEFORE DELETE ON caregiver_availability_lock_days FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'caregiver_availability_lock_days records cannot be deleted';
-- END SOURCE: db/schema_parts/99a_caregiver_availability_locks.sql

-- BEGIN SOURCE: db/schema_parts/99b_caregiver_availability_lock_events.sql
-- 99b_caregiver_availability_lock_events.sql
-- 建立 append-only 鎖定生命週期稽核事件表。
-- 包含事件型別與原因契約 CHECK 約束、payload JSON Object CHECK 約束、
-- event_key 冪等全表唯一，外鍵刪除策略為 RESTRICT，
-- 及 2 個與 DatabaseSchemaLoader 相容的單一 Statement 機械阻斷 Triggers。

CREATE TABLE IF NOT EXISTS caregiver_availability_lock_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    lock_id BIGINT NOT NULL COMMENT '對應 caregiver_availability_locks.id',
    event_type ENUM('lock_acquired', 'lock_released', 'lock_converted', 'lock_cancelled') NOT NULL COMMENT '事件類型',
    event_key VARCHAR(100) NOT NULL COMMENT '呼叫端提供的全域唯一非空冪等鍵',
    actor VARCHAR(100) NOT NULL COMMENT '記錄事件的非空管理員識別',
    reason TEXT NULL COMMENT 'release/convert/cancel 的非空原因；acquired 為 NULL',
    payload JSON NOT NULL COMMENT '不可變 JSON Object 事件內容',
    occurred_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '事件發生時間',
    UNIQUE KEY uq_availability_lock_event_key (event_key),
    INDEX idx_availability_lock_events_lock (lock_id, occurred_at),
    INDEX idx_availability_lock_events_type (event_type, occurred_at),
    CONSTRAINT fk_availability_lock_events_lock
        FOREIGN KEY (lock_id) REFERENCES caregiver_availability_locks (id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_availability_lock_events_reason
        CHECK (
            (event_type = 'lock_acquired' AND reason IS NULL)
            OR (event_type IN ('lock_released', 'lock_converted', 'lock_cancelled') AND CHAR_LENGTH(TRIM(reason)) > 0)
        ),
    CONSTRAINT chk_availability_lock_events_payload_object
        CHECK (JSON_TYPE(payload) = 'OBJECT'),
    CONSTRAINT chk_availability_lock_events_nonempty
        CHECK (CHAR_LENGTH(TRIM(event_key)) > 0 AND CHAR_LENGTH(TRIM(actor)) > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_caregiver_availability_lock_events_before_update;
CREATE TRIGGER trg_caregiver_availability_lock_events_before_update BEFORE UPDATE ON caregiver_availability_lock_events FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'caregiver_availability_lock_events records cannot be updated';

DROP TRIGGER IF EXISTS trg_caregiver_availability_lock_events_before_delete;
CREATE TRIGGER trg_caregiver_availability_lock_events_before_delete BEFORE DELETE ON caregiver_availability_lock_events FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'caregiver_availability_lock_events records cannot be deleted';
-- END SOURCE: db/schema_parts/99b_caregiver_availability_lock_events.sql

-- BEGIN SOURCE: db/schema_parts/100_staff_schedule_allow_same_day_multiple_assignments.sql
-- 退休舊版放寬同一月嫂同日多個排班的 schema part。
-- 保留檔名 100_staff_schedule_allow_same_day_multiple_assignments.sql 以維護 lexical loader 相容性，
-- 但轉改為 fail-closed、可重跑 (idempotent) 的 canonical staff-date (staff_id, work_date) 唯一鍵守衛。
-- 嚴禁 DROP/RENAME/放寬唯一鍵；存在衝突、同名錯誤索引或等價異名索引時一律 fail-closed 並要求人工覆核。

SET @staff_schedule_table_exists = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'staff_schedule'
);

SET @canonical_any_cols = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'staff_schedule'
      AND INDEX_NAME = 'ukey_staff_date'
);

SET @canonical_exact_match = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'staff_schedule'
      AND INDEX_NAME = 'ukey_staff_date'
      AND NON_UNIQUE = 0
      AND (
          (COLUMN_NAME = 'staff_id' AND SEQ_IN_INDEX = 1)
       OR (COLUMN_NAME = 'work_date' AND SEQ_IN_INDEX = 2)
      )
);

SET @canonical_valid = IF(@canonical_any_cols = 2 AND @canonical_exact_match = 2, 1, 0);
SET @canonical_has_invalid_spec = IF(@canonical_any_cols > 0 AND @canonical_valid = 0, 1, 0);

SET @equivalent_index_count = (
    SELECT COUNT(DISTINCT INDEX_NAME)
    FROM (
        SELECT INDEX_NAME,
               COUNT(*) AS total_cols,
               SUM(IF((COLUMN_NAME = 'staff_id' AND SEQ_IN_INDEX = 1) OR (COLUMN_NAME = 'work_date' AND SEQ_IN_INDEX = 2), 1, 0)) AS match_cols,
               MIN(NON_UNIQUE) AS min_non_unique
        FROM INFORMATION_SCHEMA.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'staff_schedule'
          AND INDEX_NAME != 'ukey_staff_date'
        GROUP BY INDEX_NAME
    ) t
    WHERE min_non_unique = 0 AND total_cols = 2 AND match_cols = 2
);

SET @duplicate_rows_exist = IF(
    @staff_schedule_table_exists = 1 AND @canonical_any_cols = 0 AND @canonical_has_invalid_spec = 0 AND @equivalent_index_count = 0,
    (
        SELECT IF(COUNT(*) > 0, 1, 0)
        FROM (
            SELECT staff_id, work_date
            FROM staff_schedule
            GROUP BY staff_id, work_date
            HAVING COUNT(*) > 1
        ) dup_t
    ),
    0
);

SET @action_sql = IF(
    @staff_schedule_table_exists = 0,
    'SELECT * FROM `FAIL_CLOSED_STAFF_SCHEDULE_TABLE_NOT_FOUND`',
    IF(
        @canonical_has_invalid_spec = 1,
        'SELECT * FROM `FAIL_CLOSED_UKEY_STAFF_DATE_INVALID_SPEC_REVIEW_REQUIRED`',
        IF(
            @canonical_valid = 1,
            'SELECT 1',
            IF(
                @equivalent_index_count > 0,
                'SELECT * FROM `FAIL_CLOSED_EQUIVALENT_INDEX_REVIEW_REQUIRED`',
                IF(
                    @duplicate_rows_exist = 1,
                    'SELECT * FROM `FAIL_CLOSED_DUPLICATE_STAFF_DATE_ROWS_FOUND_REVIEW_REQUIRED`',
                    'ALTER TABLE `staff_schedule` ADD UNIQUE KEY `ukey_staff_date` (`staff_id`, `work_date`)'
                )
            )
        )
    )
);

PREPARE staff_schedule_guard_stmt FROM @action_sql;
EXECUTE staff_schedule_guard_stmt;
DEALLOCATE PREPARE staff_schedule_guard_stmt;
-- END SOURCE: db/schema_parts/100_staff_schedule_allow_same_day_multiple_assignments.sql

-- BEGIN SOURCE: db/schema_parts/101_assignment_schedule_leave_substitution_events.sql
-- 101_assignment_schedule_leave_substitution_events.sql
-- 記錄正式服務指派在單日休假/順延/代班流程中的事件事實。
-- 僅 append-only，無任何歷史修補與回填邏輯；欄位皆附上明確約束，
-- 供後續交易流程在單一交易中寫入核對快照。

CREATE TABLE IF NOT EXISTS assignment_schedule_leave_substitution_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    case_no VARCHAR(50) NOT NULL COMMENT '事件所屬案件（對應 orders.case_no）',
    original_assignment_id BIGINT NOT NULL COMMENT '請假日原始正式服務指派 id',
    original_schedule_id INT NOT NULL COMMENT '被處置之日排班 id',
    work_date DATE NOT NULL COMMENT '被處置之休假日期',
    resolution_type ENUM('leave_only', 'defer_following_assignments', 'substitute') NOT NULL COMMENT '處置類型',
    substitute_assignment_id BIGINT NULL COMMENT '只在 substitute 時為非空',
    event_key VARCHAR(100) NOT NULL COMMENT '呼叫端提供的全域唯一冪等鍵',
    actor VARCHAR(100) NOT NULL COMMENT '執行者管理員識別',
    reason VARCHAR(255) NOT NULL COMMENT '非空原因',
    schedule_snapshot JSON NOT NULL COMMENT '原排班/順延/代班日套用前後快照',
    payroll_snapshot JSON NOT NULL COMMENT '原 assignment 與代班 assignment 的核對快照',
    occurred_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '事件發生時間',
    UNIQUE KEY uq_assignment_schedule_leave_substitution_event_key (event_key),
    INDEX idx_assignment_schedule_leave_substitution_event_case_time (case_no, occurred_at),
    INDEX idx_assignment_schedule_leave_substitution_event_assignments (original_assignment_id, substitute_assignment_id, work_date),
    CONSTRAINT fk_assignment_schedule_leave_substitution_event_case_no
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_assignment_schedule_leave_substitution_original_assignment
        FOREIGN KEY (original_assignment_id) REFERENCES case_staff_assignments(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_assignment_schedule_leave_substitution_substitute_assignment
        FOREIGN KEY (substitute_assignment_id) REFERENCES case_staff_assignments(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_assignment_schedule_leave_substitution_original_schedule
        FOREIGN KEY (original_schedule_id) REFERENCES staff_schedule(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_assignment_schedule_leave_substitution_resolution
        CHECK (
            (resolution_type = 'substitute' AND substitute_assignment_id IS NOT NULL AND substitute_assignment_id <> original_assignment_id)
            OR (resolution_type IN ('leave_only', 'defer_following_assignments') AND substitute_assignment_id IS NULL)
        ),
    CONSTRAINT chk_leave_sub_actor_reason_key
        CHECK (CHAR_LENGTH(TRIM(event_key)) > 0 AND CHAR_LENGTH(TRIM(actor)) > 0 AND CHAR_LENGTH(TRIM(reason)) > 0),
    CONSTRAINT chk_leave_sub_schedule_snapshot
        CHECK (JSON_TYPE(schedule_snapshot) = 'OBJECT'),
    CONSTRAINT chk_leave_sub_payroll_snapshot
        CHECK (JSON_TYPE(payroll_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_assignment_schedule_leave_substitution_events_before_update;
CREATE TRIGGER trg_assignment_schedule_leave_substitution_events_before_update
BEFORE UPDATE ON assignment_schedule_leave_substitution_events
FOR EACH ROW
SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'assignment_schedule_leave_substitution_events records cannot be updated';

DROP TRIGGER IF EXISTS trg_assignment_schedule_leave_substitution_events_before_delete;
CREATE TRIGGER trg_assignment_schedule_leave_substitution_events_before_delete
BEFORE DELETE ON assignment_schedule_leave_substitution_events
FOR EACH ROW
SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'assignment_schedule_leave_substitution_events records cannot be deleted';
-- END SOURCE: db/schema_parts/101_assignment_schedule_leave_substitution_events.sql

-- BEGIN SOURCE: db/schema_parts/102_assignment_schedule_leave_substitution_batches.sql
-- 102_assignment_schedule_leave_substitution_batches.sql
-- 為同一案件多日休假／順延／代班 Apply 建立 batch 聚合根，並保留既有事件的
-- 可回填式欄位（預設 NULL，不做歷史回填或更新）。

CREATE TABLE IF NOT EXISTS assignment_schedule_leave_substitution_batches (
    batch_key VARCHAR(100) NOT NULL COMMENT '整批冪等鍵',
    case_no VARCHAR(50) NOT NULL COMMENT '事件所屬案件（對應 orders.case_no）',
    preview_fingerprint CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT 'canonical preview sha256 lowercase hex',
    item_count INT UNSIGNED NOT NULL COMMENT 'canonical items 數量',
    actor VARCHAR(100) NOT NULL COMMENT '執行者管理員識別',
    reason VARCHAR(255) NOT NULL COMMENT '統一 non-empty 原因',
    request_snapshot JSON NOT NULL COMMENT 'canonical request snapshot',
    occurred_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '批次建立時間',
    PRIMARY KEY (batch_key),
    INDEX idx_assignment_schedule_leave_substitution_batches_case_time (case_no, occurred_at),
    CONSTRAINT fk_assignment_schedule_leave_substitution_batches_case_no
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_assignment_schedule_leave_substitution_batches_identity
        CHECK (
            CHAR_LENGTH(TRIM(batch_key)) > 0
            AND CHAR_LENGTH(TRIM(case_no)) > 0
            AND CHAR_LENGTH(TRIM(actor)) > 0
            AND CHAR_LENGTH(TRIM(reason)) > 0
        ),
    CONSTRAINT chk_leave_batch_fingerprint
        CHECK (preview_fingerprint REGEXP '^[0-9a-f]{64}$'),
    CONSTRAINT chk_assignment_schedule_leave_substitution_batches_item_count
        CHECK (item_count >= 1),
    CONSTRAINT chk_leave_batch_request_snapshot
        CHECK (JSON_TYPE(request_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

SET @batch_header_exact = (
    SELECT IF(
        (SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES
         WHERE TABLE_SCHEMA = DATABASE()
           AND TABLE_NAME = 'assignment_schedule_leave_substitution_batches'
           AND ENGINE = 'InnoDB'
           AND TABLE_COLLATION = 'utf8mb4_unicode_ci') = 1
        AND
        (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
         WHERE TABLE_SCHEMA = DATABASE()
           AND TABLE_NAME = 'assignment_schedule_leave_substitution_batches') = 8
        AND
        (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
         WHERE TABLE_SCHEMA = DATABASE()
           AND TABLE_NAME = 'assignment_schedule_leave_substitution_batches'
           AND (
             (COLUMN_NAME = 'batch_key' AND DATA_TYPE = 'varchar' AND CHARACTER_MAXIMUM_LENGTH = 100 AND IS_NULLABLE = 'NO')
             OR (COLUMN_NAME = 'case_no' AND DATA_TYPE = 'varchar' AND CHARACTER_MAXIMUM_LENGTH = 50 AND IS_NULLABLE = 'NO')
             OR (COLUMN_NAME = 'preview_fingerprint' AND DATA_TYPE = 'char' AND CHARACTER_MAXIMUM_LENGTH = 64 AND CHARACTER_SET_NAME = 'ascii' AND COLLATION_NAME = 'ascii_bin' AND IS_NULLABLE = 'NO')
             OR (COLUMN_NAME = 'item_count' AND DATA_TYPE = 'int' AND COLUMN_TYPE = 'int unsigned' AND IS_NULLABLE = 'NO')
             OR (COLUMN_NAME = 'actor' AND DATA_TYPE = 'varchar' AND CHARACTER_MAXIMUM_LENGTH = 100 AND IS_NULLABLE = 'NO')
             OR (COLUMN_NAME = 'reason' AND DATA_TYPE = 'varchar' AND CHARACTER_MAXIMUM_LENGTH = 255 AND IS_NULLABLE = 'NO')
             OR (COLUMN_NAME = 'request_snapshot' AND DATA_TYPE = 'json' AND IS_NULLABLE = 'NO')
             OR (COLUMN_NAME = 'occurred_at' AND DATA_TYPE = 'timestamp' AND IS_NULLABLE = 'NO' AND UPPER(COLUMN_DEFAULT) = 'CURRENT_TIMESTAMP')
           )) = 8
        AND
        (SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS
         WHERE TABLE_SCHEMA = DATABASE()
           AND TABLE_NAME = 'assignment_schedule_leave_substitution_batches'
           AND INDEX_NAME = 'PRIMARY') = 1
        AND
        (SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS
         WHERE TABLE_SCHEMA = DATABASE()
           AND TABLE_NAME = 'assignment_schedule_leave_substitution_batches'
           AND INDEX_NAME = 'PRIMARY'
           AND NON_UNIQUE = 0
           AND SEQ_IN_INDEX = 1
           AND COLUMN_NAME = 'batch_key') = 1
        AND
        (SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS
         WHERE TABLE_SCHEMA = DATABASE()
           AND TABLE_NAME = 'assignment_schedule_leave_substitution_batches'
           AND INDEX_NAME = 'idx_assignment_schedule_leave_substitution_batches_case_time') = 2
        AND
        (SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS
         WHERE TABLE_SCHEMA = DATABASE()
           AND TABLE_NAME = 'assignment_schedule_leave_substitution_batches'
           AND INDEX_NAME = 'idx_assignment_schedule_leave_substitution_batches_case_time'
           AND NON_UNIQUE = 1
           AND ((SEQ_IN_INDEX = 1 AND COLUMN_NAME = 'case_no')
             OR (SEQ_IN_INDEX = 2 AND COLUMN_NAME = 'occurred_at'))) = 2
        AND
        (SELECT COUNT(*) FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE k
         JOIN INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS r
           ON k.CONSTRAINT_SCHEMA = r.CONSTRAINT_SCHEMA
          AND k.TABLE_NAME = r.TABLE_NAME
          AND k.CONSTRAINT_NAME = r.CONSTRAINT_NAME
         WHERE k.CONSTRAINT_SCHEMA = DATABASE()
           AND k.TABLE_NAME = 'assignment_schedule_leave_substitution_batches'
           AND k.CONSTRAINT_NAME = 'fk_assignment_schedule_leave_substitution_batches_case_no'
           AND k.COLUMN_NAME = 'case_no'
           AND k.REFERENCED_TABLE_NAME = 'orders'
           AND k.REFERENCED_COLUMN_NAME = 'case_no'
           AND r.UPDATE_RULE = 'RESTRICT'
           AND r.DELETE_RULE = 'RESTRICT') = 1
        AND
        (SELECT COUNT(*) FROM INFORMATION_SCHEMA.CHECK_CONSTRAINTS
         WHERE CONSTRAINT_SCHEMA = DATABASE()
           AND CONSTRAINT_NAME = 'chk_assignment_schedule_leave_substitution_batches_identity'
           AND UPPER(REPLACE(REPLACE(REPLACE(REPLACE(CHECK_CLAUSE, ' ', ''), CHAR(9), ''), CHAR(10), ''), '`', ''))
             = '((CHAR_LENGTH(TRIM(BATCH_KEY))>0)AND(CHAR_LENGTH(TRIM(CASE_NO))>0)AND(CHAR_LENGTH(TRIM(ACTOR))>0)AND(CHAR_LENGTH(TRIM(REASON))>0))') = 1
        AND
        (SELECT COUNT(*) FROM INFORMATION_SCHEMA.CHECK_CONSTRAINTS
         WHERE CONSTRAINT_SCHEMA = DATABASE()
           AND CONSTRAINT_NAME = 'chk_leave_batch_fingerprint'
           AND (
             BINARY REPLACE(REPLACE(REPLACE(REPLACE(CHECK_CLAUSE, ' ', ''), CHAR(9), ''), CHAR(10), ''), '`', '')
               = BINARY '(preview_fingerprintREGEXP''^[0-9a-f]{64}$'')'
             OR (
               LOWER(REPLACE(REPLACE(REPLACE(REPLACE(CHECK_CLAUSE, ' ', ''), CHAR(9), ''), CHAR(10), ''), '`', ''))
                 LIKE 'regexp_like(preview_fingerprint,%'
               AND BINARY REPLACE(REPLACE(REPLACE(REPLACE(CHECK_CLAUSE, ' ', ''), CHAR(9), ''), CHAR(10), ''), '`', '')
                 LIKE BINARY '%^[0-9a-f]{64}$%'
               AND BINARY REPLACE(REPLACE(REPLACE(REPLACE(CHECK_CLAUSE, ' ', ''), CHAR(9), ''), CHAR(10), ''), '`', '')
                 NOT LIKE BINARY '%[0-9A-F]{64}%'
             )
           )) = 1
        AND
        (SELECT COUNT(*) FROM INFORMATION_SCHEMA.CHECK_CONSTRAINTS
         WHERE CONSTRAINT_SCHEMA = DATABASE()
           AND CONSTRAINT_NAME = 'chk_assignment_schedule_leave_substitution_batches_item_count'
           AND UPPER(REPLACE(REPLACE(REPLACE(REPLACE(CHECK_CLAUSE, ' ', ''), CHAR(9), ''), CHAR(10), ''), '`', ''))
             = '(ITEM_COUNT>=1)') = 1
        AND
        (SELECT COUNT(*) FROM INFORMATION_SCHEMA.CHECK_CONSTRAINTS
         WHERE CONSTRAINT_SCHEMA = DATABASE()
           AND CONSTRAINT_NAME = 'chk_leave_batch_request_snapshot'
           AND (
             UPPER(REPLACE(REPLACE(REPLACE(REPLACE(CHECK_CLAUSE, ' ', ''), CHAR(9), ''), CHAR(10), ''), '`', ''))
               = '(JSON_TYPE(REQUEST_SNAPSHOT)=''OBJECT'')'
             OR UPPER(REPLACE(REPLACE(REPLACE(REPLACE(CHECK_CLAUSE, ' ', ''), CHAR(9), ''), CHAR(10), ''), '`', ''))
               LIKE '(JSON_TYPE(REQUEST_SNAPSHOT)=%OBJECT%)'
           )) = 1,
        1,
        0
    )
);

SET @batch_header_guard_action_sql = IF(
    @batch_header_exact = 1,
    'SELECT 1',
    'SELECT * FROM `FAIL_CLOSED_BATCH_HEADER_INVALID_SPEC_REVIEW_REQUIRED`'
);
PREPARE stmt_batch_header_guard FROM @batch_header_guard_action_sql;
EXECUTE stmt_batch_header_guard;
DEALLOCATE PREPARE stmt_batch_header_guard;

SET @batch_before_update_trigger_any = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.TRIGGERS
    WHERE TRIGGER_SCHEMA = DATABASE()
      AND EVENT_OBJECT_TABLE = 'assignment_schedule_leave_substitution_batches'
      AND TRIGGER_NAME = 'trg_assignment_schedule_leave_substitution_batches_before_update'
);

SET @batch_before_update_trigger_valid = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.TRIGGERS
    WHERE TRIGGER_SCHEMA = DATABASE()
      AND EVENT_OBJECT_TABLE = 'assignment_schedule_leave_substitution_batches'
      AND TRIGGER_NAME = 'trg_assignment_schedule_leave_substitution_batches_before_update'
      AND ACTION_TIMING = 'BEFORE'
      AND EVENT_MANIPULATION = 'UPDATE'
      AND UPPER(REPLACE(REPLACE(REPLACE(REPLACE(ACTION_STATEMENT, ' ', ''), CHAR(9), ''), CHAR(10), ''), '`', ''))
        = 'SIGNALSQLSTATE''45000''SETMESSAGE_TEXT=''ASSIGNMENT_SCHEDULE_LEAVE_SUBSTITUTION_BATCHESRECORDSCANNOTBEUPDATED'''
);

SET @batch_before_update_trigger_action_sql = IF(
    @batch_before_update_trigger_any > 0 AND @batch_before_update_trigger_valid = 0,
    'SELECT * FROM `FAIL_CLOSED_BATCH_BEFORE_UPDATE_TRIGGER_INVALID_SPEC_REVIEW_REQUIRED`',
    'SELECT 1'
);

PREPARE stmt_batch_before_update_trigger FROM @batch_before_update_trigger_action_sql;
EXECUTE stmt_batch_before_update_trigger;
DEALLOCATE PREPARE stmt_batch_before_update_trigger;

DROP TRIGGER IF EXISTS trg_assignment_schedule_leave_substitution_batches_before_update;
CREATE TRIGGER trg_assignment_schedule_leave_substitution_batches_before_update
BEFORE UPDATE ON assignment_schedule_leave_substitution_batches
FOR EACH ROW
SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'assignment_schedule_leave_substitution_batches records cannot be updated';

SET @batch_before_delete_trigger_any = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.TRIGGERS
    WHERE TRIGGER_SCHEMA = DATABASE()
      AND EVENT_OBJECT_TABLE = 'assignment_schedule_leave_substitution_batches'
      AND TRIGGER_NAME = 'trg_assignment_schedule_leave_substitution_batches_before_delete'
);

SET @batch_before_delete_trigger_valid = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.TRIGGERS
    WHERE TRIGGER_SCHEMA = DATABASE()
      AND EVENT_OBJECT_TABLE = 'assignment_schedule_leave_substitution_batches'
      AND TRIGGER_NAME = 'trg_assignment_schedule_leave_substitution_batches_before_delete'
      AND ACTION_TIMING = 'BEFORE'
      AND EVENT_MANIPULATION = 'DELETE'
      AND UPPER(REPLACE(REPLACE(REPLACE(REPLACE(ACTION_STATEMENT, ' ', ''), CHAR(9), ''), CHAR(10), ''), '`', ''))
        = 'SIGNALSQLSTATE''45000''SETMESSAGE_TEXT=''ASSIGNMENT_SCHEDULE_LEAVE_SUBSTITUTION_BATCHESRECORDSCANNOTBEDELETED'''
);

SET @batch_before_delete_trigger_action_sql = IF(
    @batch_before_delete_trigger_any > 0 AND @batch_before_delete_trigger_valid = 0,
    'SELECT * FROM `FAIL_CLOSED_BATCH_BEFORE_DELETE_TRIGGER_INVALID_SPEC_REVIEW_REQUIRED`',
    'SELECT 1'
);

PREPARE stmt_batch_before_delete_trigger FROM @batch_before_delete_trigger_action_sql;
EXECUTE stmt_batch_before_delete_trigger;
DEALLOCATE PREPARE stmt_batch_before_delete_trigger;

DROP TRIGGER IF EXISTS trg_assignment_schedule_leave_substitution_batches_before_delete;
CREATE TRIGGER trg_assignment_schedule_leave_substitution_batches_before_delete
BEFORE DELETE ON assignment_schedule_leave_substitution_batches
FOR EACH ROW
SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'assignment_schedule_leave_substitution_batches records cannot be deleted';

SET @events_table_exists = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'assignment_schedule_leave_substitution_events'
);

SET @event_batch_key_col_any = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'assignment_schedule_leave_substitution_events'
      AND COLUMN_NAME = 'batch_key'
);

SET @event_batch_key_col_exact = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'assignment_schedule_leave_substitution_events'
      AND COLUMN_NAME = 'batch_key'
      AND (DATA_TYPE = 'varchar' OR COLUMN_TYPE LIKE '%varchar%')
      AND CHARACTER_MAXIMUM_LENGTH = 100
      AND IS_NULLABLE = 'YES'
);

SET @event_batch_key_col_action_sql = IF(
    @events_table_exists = 0,
    'SELECT * FROM `FAIL_CLOSED_EVENTS_TABLE_NOT_FOUND`',
    IF(
        @event_batch_key_col_any > 0 AND @event_batch_key_col_exact = 0,
        'SELECT * FROM `FAIL_CLOSED_BATCH_KEY_COLUMN_INVALID_SPEC_REVIEW_REQUIRED`',
        IF(
            @event_batch_key_col_any = 0,
            'ALTER TABLE `assignment_schedule_leave_substitution_events` ADD COLUMN `batch_key` VARCHAR(100) NULL',
            'SELECT 1'
        )
    )
);

PREPARE stmt_event_batch_key_col FROM @event_batch_key_col_action_sql;
EXECUTE stmt_event_batch_key_col;
DEALLOCATE PREPARE stmt_event_batch_key_col;

SET @event_batch_item_index_col_any = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'assignment_schedule_leave_substitution_events'
      AND COLUMN_NAME = 'batch_item_index'
);

SET @event_batch_item_index_col_exact = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'assignment_schedule_leave_substitution_events'
      AND COLUMN_NAME = 'batch_item_index'
      AND DATA_TYPE = 'int'
      AND COLUMN_TYPE LIKE '%unsigned%'
      AND IS_NULLABLE = 'YES'
);

SET @event_batch_item_index_col_action_sql = IF(
    @events_table_exists = 0,
    'SELECT * FROM `FAIL_CLOSED_EVENTS_TABLE_NOT_FOUND`',
    IF(
        @event_batch_item_index_col_any > 0 AND @event_batch_item_index_col_exact = 0,
        'SELECT * FROM `FAIL_CLOSED_BATCH_ITEM_INDEX_COLUMN_INVALID_SPEC_REVIEW_REQUIRED`',
        IF(
            @event_batch_item_index_col_any = 0,
            'ALTER TABLE `assignment_schedule_leave_substitution_events` ADD COLUMN `batch_item_index` INT UNSIGNED NULL',
            'SELECT 1'
        )
    )
);

PREPARE stmt_event_batch_item_index_col FROM @event_batch_item_index_col_action_sql;
EXECUTE stmt_event_batch_item_index_col;
DEALLOCATE PREPARE stmt_event_batch_item_index_col;

SET @event_batch_linkage_index_any = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'assignment_schedule_leave_substitution_events'
      AND INDEX_NAME = 'uq_assignment_schedule_leave_substitution_events_batch_linkage'
);

SET @event_batch_linkage_index_seq1 = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'assignment_schedule_leave_substitution_events'
      AND INDEX_NAME = 'uq_assignment_schedule_leave_substitution_events_batch_linkage'
      AND NON_UNIQUE = 0
      AND COLUMN_NAME = 'batch_key'
      AND SEQ_IN_INDEX = 1
);

SET @event_batch_linkage_index_seq2 = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'assignment_schedule_leave_substitution_events'
      AND INDEX_NAME = 'uq_assignment_schedule_leave_substitution_events_batch_linkage'
      AND NON_UNIQUE = 0
      AND COLUMN_NAME = 'batch_item_index'
      AND SEQ_IN_INDEX = 2
);

SET @event_batch_linkage_index_exact = IF(
    @event_batch_linkage_index_any = 2
       AND @event_batch_linkage_index_seq1 = 1
       AND @event_batch_linkage_index_seq2 = 1,
    1,
    0
);

SET @event_batch_linkage_index_action_sql = IF(
    @events_table_exists = 0,
    'SELECT * FROM `FAIL_CLOSED_EVENTS_TABLE_NOT_FOUND`',
    IF(
        @event_batch_linkage_index_any > 0 AND @event_batch_linkage_index_exact = 0,
        'SELECT * FROM `FAIL_CLOSED_EVENT_BATCH_LINKAGE_INDEX_INVALID_SPEC_REVIEW_REQUIRED`',
        IF(
            @event_batch_linkage_index_any = 0,
            'ALTER TABLE `assignment_schedule_leave_substitution_events` ADD UNIQUE KEY '
            '`uq_assignment_schedule_leave_substitution_events_batch_linkage` (`batch_key`, `batch_item_index`)',
            'SELECT 1'
        )
    )
);

PREPARE stmt_event_batch_linkage_index FROM @event_batch_linkage_index_action_sql;
EXECUTE stmt_event_batch_linkage_index;
DEALLOCATE PREPARE stmt_event_batch_linkage_index;

SET @event_batch_work_date_index_any = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'assignment_schedule_leave_substitution_events'
      AND INDEX_NAME = 'idx_assignment_schedule_leave_substitution_events_batch_key'
);

SET @event_batch_work_date_index_seq1 = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'assignment_schedule_leave_substitution_events'
      AND INDEX_NAME = 'idx_assignment_schedule_leave_substitution_events_batch_key'
      AND NON_UNIQUE = 1
      AND COLUMN_NAME = 'batch_key'
      AND SEQ_IN_INDEX = 1
);

SET @event_batch_work_date_index_seq2 = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'assignment_schedule_leave_substitution_events'
      AND INDEX_NAME = 'idx_assignment_schedule_leave_substitution_events_batch_key'
      AND NON_UNIQUE = 1
      AND COLUMN_NAME = 'work_date'
      AND SEQ_IN_INDEX = 2
);

SET @event_batch_work_date_index_exact = IF(
    @event_batch_work_date_index_any = 2
       AND @event_batch_work_date_index_seq1 = 1
       AND @event_batch_work_date_index_seq2 = 1,
    1,
    0
);

SET @event_batch_work_date_index_action_sql = IF(
    @events_table_exists = 0,
    'SELECT * FROM `FAIL_CLOSED_EVENTS_TABLE_NOT_FOUND`',
    IF(
        @event_batch_work_date_index_any > 0 AND @event_batch_work_date_index_exact = 0,
        'SELECT * FROM `FAIL_CLOSED_EVENT_BATCH_KEY_WORK_DATE_INDEX_INVALID_SPEC_REVIEW_REQUIRED`',
        IF(
            @event_batch_work_date_index_any = 0,
            'ALTER TABLE `assignment_schedule_leave_substitution_events` ADD INDEX '
            '`idx_assignment_schedule_leave_substitution_events_batch_key` (`batch_key`, `work_date`)',
            'SELECT 1'
        )
    )
);

PREPARE stmt_event_batch_work_date_index FROM @event_batch_work_date_index_action_sql;
EXECUTE stmt_event_batch_work_date_index;
DEALLOCATE PREPARE stmt_event_batch_work_date_index;

SET @event_batch_fk_any = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
    WHERE CONSTRAINT_SCHEMA = DATABASE()
      AND TABLE_NAME = 'assignment_schedule_leave_substitution_events'
      AND CONSTRAINT_NAME = 'fk_assignment_schedule_leave_substitution_events_batch'
      AND CONSTRAINT_TYPE = 'FOREIGN KEY'
);

SET @event_batch_fk_exact = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE k
    JOIN INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS r
      ON k.CONSTRAINT_SCHEMA = r.CONSTRAINT_SCHEMA
     AND k.TABLE_NAME = r.TABLE_NAME
     AND k.CONSTRAINT_NAME = r.CONSTRAINT_NAME
    WHERE k.CONSTRAINT_SCHEMA = DATABASE()
      AND k.TABLE_NAME = 'assignment_schedule_leave_substitution_events'
      AND k.CONSTRAINT_NAME = 'fk_assignment_schedule_leave_substitution_events_batch'
      AND k.COLUMN_NAME = 'batch_key'
      AND k.REFERENCED_TABLE_NAME = 'assignment_schedule_leave_substitution_batches'
      AND k.REFERENCED_COLUMN_NAME = 'batch_key'
      AND r.UPDATE_RULE = 'RESTRICT'
      AND r.DELETE_RULE = 'RESTRICT'
);

SET @event_batch_fk_action_sql = IF(
    @events_table_exists = 0,
    'SELECT * FROM `FAIL_CLOSED_EVENTS_TABLE_NOT_FOUND`',
    IF(
        @event_batch_fk_any > 0 AND @event_batch_fk_exact = 0,
        'SELECT * FROM `FAIL_CLOSED_EVENT_BATCH_FK_INVALID_SPEC_REVIEW_REQUIRED`',
        IF(
            @event_batch_fk_any = 0,
            'ALTER TABLE `assignment_schedule_leave_substitution_events` ADD CONSTRAINT '
            '`fk_assignment_schedule_leave_substitution_events_batch` FOREIGN KEY (batch_key) '
            'REFERENCES assignment_schedule_leave_substitution_batches(batch_key) '
            'ON UPDATE RESTRICT ON DELETE RESTRICT',
            'SELECT 1'
        )
    )
);

PREPARE stmt_event_batch_fk FROM @event_batch_fk_action_sql;
EXECUTE stmt_event_batch_fk;
DEALLOCATE PREPARE stmt_event_batch_fk;

SET @event_batch_linkage_check_any = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.CHECK_CONSTRAINTS c
    JOIN INFORMATION_SCHEMA.TABLE_CONSTRAINTS t
      ON c.CONSTRAINT_SCHEMA = t.CONSTRAINT_SCHEMA
     AND c.CONSTRAINT_NAME = t.CONSTRAINT_NAME
    WHERE c.CONSTRAINT_SCHEMA = DATABASE()
      AND t.TABLE_NAME = 'assignment_schedule_leave_substitution_events'
      AND c.CONSTRAINT_NAME = 'chk_assignment_schedule_leave_substitution_events_batch_linkage'
);

SET @event_batch_linkage_check_exact = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.CHECK_CONSTRAINTS c
    JOIN INFORMATION_SCHEMA.TABLE_CONSTRAINTS t
      ON c.CONSTRAINT_SCHEMA = t.CONSTRAINT_SCHEMA
     AND c.CONSTRAINT_NAME = t.CONSTRAINT_NAME
    WHERE c.CONSTRAINT_SCHEMA = DATABASE()
      AND t.TABLE_NAME = 'assignment_schedule_leave_substitution_events'
      AND c.CONSTRAINT_NAME = 'chk_assignment_schedule_leave_substitution_events_batch_linkage'
      AND UPPER(REPLACE(REPLACE(REPLACE(REPLACE(c.CHECK_CLAUSE, ' ', ''), CHAR(9), ''), CHAR(10), ''), '`', ''))
        = '(((BATCH_KEYISNULL)AND(BATCH_ITEM_INDEXISNULL))OR((BATCH_KEYISNOTNULL)AND(BATCH_ITEM_INDEXISNOTNULL)AND(BATCH_ITEM_INDEX>=0)))'
);

SET @event_batch_linkage_check_action_sql = IF(
    @events_table_exists = 0,
    'SELECT * FROM `FAIL_CLOSED_EVENTS_TABLE_NOT_FOUND`',
    IF(
        @event_batch_linkage_check_any > 0 AND @event_batch_linkage_check_exact = 0,
        'SELECT * FROM `FAIL_CLOSED_EVENT_BATCH_LINKAGE_CHECK_INVALID_SPEC_REVIEW_REQUIRED`',
        IF(
            @event_batch_linkage_check_any = 0,
            'ALTER TABLE `assignment_schedule_leave_substitution_events` ADD CONSTRAINT '
            '`chk_assignment_schedule_leave_substitution_events_batch_linkage` CHECK ('
            '(batch_key IS NULL AND batch_item_index IS NULL)'
            ' OR (batch_key IS NOT NULL AND batch_item_index IS NOT NULL AND batch_item_index >= 0)'
            ')',
            'SELECT 1'
        )
    )
);

PREPARE stmt_event_batch_linkage_check FROM @event_batch_linkage_check_action_sql;
EXECUTE stmt_event_batch_linkage_check;
DEALLOCATE PREPARE stmt_event_batch_linkage_check;
-- END SOURCE: db/schema_parts/102_assignment_schedule_leave_substitution_batches.sql

-- BEGIN SOURCE: db/schema_parts/103_assignment_original_service_period.sql
-- 保存 assignment 初次建立的服務區段，讓調整前／調整後可被穩定查詢。
SET @assignment_original_start_exists = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'case_staff_assignments'
      AND COLUMN_NAME = 'original_assigned_start_date'
);
SET @assignment_original_period_sql = IF(
    @assignment_original_start_exists = 0,
    'ALTER TABLE `case_staff_assignments` ADD COLUMN `original_assigned_start_date` DATE NULL AFTER `assigned_end_date`',
    'SELECT 1'
);
PREPARE assignment_original_period_stmt FROM @assignment_original_period_sql;
EXECUTE assignment_original_period_stmt;
DEALLOCATE PREPARE assignment_original_period_stmt;

SET @assignment_original_end_exists = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'case_staff_assignments'
      AND COLUMN_NAME = 'original_assigned_end_date'
);
SET @assignment_original_period_sql = IF(
    @assignment_original_end_exists = 0,
    'ALTER TABLE `case_staff_assignments` ADD COLUMN `original_assigned_end_date` DATE NULL AFTER `original_assigned_start_date`',
    'SELECT 1'
);
PREPARE assignment_original_period_stmt FROM @assignment_original_period_sql;
EXECUTE assignment_original_period_stmt;
DEALLOCATE PREPARE assignment_original_period_stmt;

UPDATE case_staff_assignments
SET original_assigned_start_date = COALESCE(original_assigned_start_date, assigned_start_date),
    original_assigned_end_date = COALESCE(original_assigned_end_date, assigned_end_date)
WHERE original_assigned_start_date IS NULL OR original_assigned_end_date IS NULL;

DROP TRIGGER IF EXISTS trg_case_staff_assignments_original_period_insert;
CREATE TRIGGER trg_case_staff_assignments_original_period_insert
BEFORE INSERT ON case_staff_assignments
FOR EACH ROW
SET NEW.original_assigned_start_date = COALESCE(NEW.original_assigned_start_date, NEW.assigned_start_date),
    NEW.original_assigned_end_date = COALESCE(NEW.original_assigned_end_date, NEW.assigned_end_date);

DROP TRIGGER IF EXISTS trg_case_staff_assignments_original_period_update;
CREATE TRIGGER trg_case_staff_assignments_original_period_update
BEFORE UPDATE ON case_staff_assignments
FOR EACH ROW
SET NEW.original_assigned_start_date = OLD.original_assigned_start_date,
    NEW.original_assigned_end_date = OLD.original_assigned_end_date;
-- END SOURCE: db/schema_parts/103_assignment_original_service_period.sql

-- BEGIN SOURCE: db/schema_parts/104_order_lifecycle_state_history.sql
-- 104_order_lifecycle_state_history.sql
-- 記錄訂單生命週期的狀態轉移、明確維持或阻擋決策。
-- 本 schema 僅新增 append-only 歷史結構，不回填或修改任何既有正式資料。

CREATE TABLE IF NOT EXISTS order_lifecycle_state_events (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    case_no VARCHAR(50) NOT NULL COMMENT '事件所屬訂單（對應 orders.case_no）',
    trigger_event VARCHAR(100) NOT NULL COMMENT '觸發本次狀態評估的事件名稱',
    before_status VARCHAR(20) NOT NULL COMMENT '狀態評估前的 canonical 訂單狀態',
    after_status VARCHAR(20) NOT NULL COMMENT '狀態評估後的 canonical 訂單狀態；維持或阻擋時可與 before_status 相同',
    actor VARCHAR(255) NOT NULL COMMENT '觸發事件的操作者或系統身分',
    business_date DATE NOT NULL COMMENT '狀態評估採用的業務日期',
    expected_version BIGINT UNSIGNED NOT NULL COMMENT '呼叫端進行樂觀鎖定時讀取的訂單版本',
    idempotency_key VARCHAR(191) NOT NULL COMMENT '同一訂單內唯一的呼叫端冪等鍵',
    facts_snapshot JSON NOT NULL COMMENT '狀態評估當下的權威事實與決策摘要',
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '事件建立時間',
    PRIMARY KEY (id),
    UNIQUE KEY uq_order_lifecycle_state_event_idempotency (
        case_no,
        idempotency_key
    ),
    INDEX idx_order_lifecycle_state_event_case_time (
        case_no,
        created_at
    ),
    CONSTRAINT fk_order_lifecycle_state_event_case_no
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_order_lifecycle_state_event_before_status
        CHECK (
            before_status IN (
                '洽談中',
                '訂單成立',
                '服務中',
                '訂單完成',
                '訂單取消'
            )
        ),
    CONSTRAINT chk_order_lifecycle_state_event_after_status
        CHECK (
            after_status IN (
                '洽談中',
                '訂單成立',
                '服務中',
                '訂單完成',
                '訂單取消'
            )
        ),
    CONSTRAINT chk_order_lifecycle_state_event_required_text
        CHECK (
            CHAR_LENGTH(TRIM(trigger_event)) > 0
            AND CHAR_LENGTH(TRIM(actor)) > 0
            AND CHAR_LENGTH(TRIM(idempotency_key)) > 0
        ),
    CONSTRAINT chk_order_lifecycle_state_event_facts_snapshot
        CHECK (JSON_TYPE(facts_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_order_lifecycle_state_events_before_update;
CREATE TRIGGER trg_order_lifecycle_state_events_before_update
BEFORE UPDATE ON order_lifecycle_state_events
FOR EACH ROW
SIGNAL SQLSTATE '45000'
    SET MESSAGE_TEXT = 'order_lifecycle_state_events records cannot be updated';

DROP TRIGGER IF EXISTS trg_order_lifecycle_state_events_before_delete;
CREATE TRIGGER trg_order_lifecycle_state_events_before_delete
BEFORE DELETE ON order_lifecycle_state_events
FOR EACH ROW
SIGNAL SQLSTATE '45000'
    SET MESSAGE_TEXT = 'order_lifecycle_state_events records cannot be deleted';
-- END SOURCE: db/schema_parts/104_order_lifecycle_state_history.sql

-- BEGIN SOURCE: db/schema_parts/105_order_service_time_terms.sql
-- Add canonical per-order service-time terms without interpreting legacy free text.
-- Existing orders deliberately remain NULL and must be completed by an explicit command.

SET @order_service_terms_orders_exists = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'orders'
      AND TABLE_TYPE = 'BASE TABLE'
);
SET @order_service_terms_prereq_sql = IF(
    @order_service_terms_orders_exists = 1,
    'SELECT 1',
    'SELECT * FROM `FAIL_CLOSED_ORDERS_TABLE_NOT_FOUND`'
);
PREPARE order_service_terms_stmt FROM @order_service_terms_prereq_sql;
EXECUTE order_service_terms_stmt;
DEALLOCATE PREPARE order_service_terms_stmt;

SET @order_service_start_time_any = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'orders'
      AND COLUMN_NAME = 'service_start_time'
);
SET @order_service_start_time_exact = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'orders'
      AND COLUMN_NAME = 'service_start_time'
      AND DATA_TYPE = 'time'
      AND IS_NULLABLE = 'YES'
      AND COLUMN_DEFAULT IS NULL
);
SET @order_service_terms_sql = IF(
    @order_service_start_time_any = 0,
    'ALTER TABLE `orders` ADD COLUMN `service_start_time` TIME NULL COMMENT ''案件統一每日服務開始時間；既有案件待明確補登'' AFTER `actual_end_date`',
    IF(
        @order_service_start_time_any = 1
        AND @order_service_start_time_exact = 1,
        'SELECT 1',
        'SELECT * FROM `FAIL_CLOSED_SERVICE_START_TIME_INVALID_SPEC_REVIEW_REQUIRED`'
    )
);
PREPARE order_service_terms_stmt FROM @order_service_terms_sql;
EXECUTE order_service_terms_stmt;
DEALLOCATE PREPARE order_service_terms_stmt;

SET @order_service_end_time_any = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'orders'
      AND COLUMN_NAME = 'service_end_time'
);
SET @order_service_end_time_exact = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'orders'
      AND COLUMN_NAME = 'service_end_time'
      AND DATA_TYPE = 'time'
      AND IS_NULLABLE = 'YES'
      AND COLUMN_DEFAULT IS NULL
);
SET @order_service_terms_sql = IF(
    @order_service_end_time_any = 0,
    'ALTER TABLE `orders` ADD COLUMN `service_end_time` TIME NULL COMMENT ''案件統一每日服務結束時間；既有案件待明確補登'' AFTER `service_start_time`',
    IF(
        @order_service_end_time_any = 1
        AND @order_service_end_time_exact = 1,
        'SELECT 1',
        'SELECT * FROM `FAIL_CLOSED_SERVICE_END_TIME_INVALID_SPEC_REVIEW_REQUIRED`'
    )
);
PREPARE order_service_terms_stmt FROM @order_service_terms_sql;
EXECUTE order_service_terms_stmt;
DEALLOCATE PREPARE order_service_terms_stmt;

SET @order_service_end_offset_any = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'orders'
      AND COLUMN_NAME = 'service_end_day_offset'
);
SET @order_service_end_offset_exact = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'orders'
      AND COLUMN_NAME = 'service_end_day_offset'
      AND DATA_TYPE = 'tinyint'
      AND COLUMN_TYPE = 'tinyint unsigned'
      AND IS_NULLABLE = 'YES'
      AND COLUMN_DEFAULT IS NULL
);
SET @order_service_terms_sql = IF(
    @order_service_end_offset_any = 0,
    'ALTER TABLE `orders` ADD COLUMN `service_end_day_offset` TINYINT UNSIGNED NULL COMMENT ''0=服務日當日結束，1=次日結束；不得由時間大小推測'' AFTER `service_end_time`',
    IF(
        @order_service_end_offset_any = 1
        AND @order_service_end_offset_exact = 1,
        'SELECT 1',
        'SELECT * FROM `FAIL_CLOSED_SERVICE_END_DAY_OFFSET_INVALID_SPEC_REVIEW_REQUIRED`'
    )
);
PREPARE order_service_terms_stmt FROM @order_service_terms_sql;
EXECUTE order_service_terms_stmt;
DEALLOCATE PREPARE order_service_terms_stmt;

SET @order_service_terms_complete_check_any = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
    WHERE CONSTRAINT_SCHEMA = DATABASE()
      AND TABLE_NAME = 'orders'
      AND CONSTRAINT_NAME = 'chk_orders_service_time_terms_complete'
      AND CONSTRAINT_TYPE = 'CHECK'
);
SET @order_service_terms_complete_check_exact = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
    JOIN INFORMATION_SCHEMA.CHECK_CONSTRAINTS cc
      ON cc.CONSTRAINT_CATALOG = tc.CONSTRAINT_CATALOG
     AND cc.CONSTRAINT_SCHEMA = tc.CONSTRAINT_SCHEMA
     AND cc.CONSTRAINT_NAME = tc.CONSTRAINT_NAME
    WHERE tc.CONSTRAINT_SCHEMA = DATABASE()
      AND tc.TABLE_NAME = 'orders'
      AND tc.CONSTRAINT_NAME = 'chk_orders_service_time_terms_complete'
      AND tc.CONSTRAINT_TYPE = 'CHECK'
      AND tc.ENFORCED = 'YES'
      AND LOWER(
          REPLACE(
              REPLACE(
                  REPLACE(
                      REPLACE(
                          REPLACE(
                              REPLACE(
                                  REPLACE(cc.CHECK_CLAUSE, '`', ''),
                                  ' ',
                                  ''
                              ),
                              CHAR(9),
                              ''
                          ),
                          CHAR(10),
                          ''
                      ),
                      CHAR(13),
                      ''
                  ),
                  '(',
                  ''
              ),
              ')',
              ''
          )
      ) = 'service_start_timeisnullandservice_end_timeisnullandservice_end_day_offsetisnullorservice_start_timeisnotnullandservice_end_timeisnotnullandservice_end_day_offsetisnotnull'
);
SET @order_service_terms_sql = IF(
    @order_service_terms_complete_check_any = 0,
    'ALTER TABLE `orders` ADD CONSTRAINT `chk_orders_service_time_terms_complete` CHECK ((`service_start_time` IS NULL AND `service_end_time` IS NULL AND `service_end_day_offset` IS NULL) OR (`service_start_time` IS NOT NULL AND `service_end_time` IS NOT NULL AND `service_end_day_offset` IS NOT NULL))',
    IF(
        @order_service_terms_complete_check_any = 1
        AND @order_service_terms_complete_check_exact = 1,
        'SELECT 1',
        'SELECT * FROM `FAIL_CLOSED_SERVICE_TIME_TERMS_COMPLETE_CHECK_INVALID_SPEC_REVIEW_REQUIRED`'
    )
);
PREPARE order_service_terms_stmt FROM @order_service_terms_sql;
EXECUTE order_service_terms_stmt;
DEALLOCATE PREPARE order_service_terms_stmt;

SET @order_service_end_offset_check_any = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
    WHERE CONSTRAINT_SCHEMA = DATABASE()
      AND TABLE_NAME = 'orders'
      AND CONSTRAINT_NAME = 'chk_orders_service_end_day_offset'
      AND CONSTRAINT_TYPE = 'CHECK'
);
SET @order_service_end_offset_check_exact = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
    JOIN INFORMATION_SCHEMA.CHECK_CONSTRAINTS cc
      ON cc.CONSTRAINT_CATALOG = tc.CONSTRAINT_CATALOG
     AND cc.CONSTRAINT_SCHEMA = tc.CONSTRAINT_SCHEMA
     AND cc.CONSTRAINT_NAME = tc.CONSTRAINT_NAME
    WHERE tc.CONSTRAINT_SCHEMA = DATABASE()
      AND tc.TABLE_NAME = 'orders'
      AND tc.CONSTRAINT_NAME = 'chk_orders_service_end_day_offset'
      AND tc.CONSTRAINT_TYPE = 'CHECK'
      AND tc.ENFORCED = 'YES'
      AND LOWER(
          REPLACE(
              REPLACE(
                  REPLACE(
                      REPLACE(
                          REPLACE(
                              REPLACE(
                                  REPLACE(cc.CHECK_CLAUSE, '`', ''),
                                  ' ',
                                  ''
                              ),
                              CHAR(9),
                              ''
                          ),
                          CHAR(10),
                          ''
                      ),
                      CHAR(13),
                      ''
                  ),
                  '(',
                  ''
              ),
              ')',
              ''
          )
      ) = 'service_end_day_offsetisnullorservice_end_day_offsetin0,1'
);
SET @order_service_terms_sql = IF(
    @order_service_end_offset_check_any = 0,
    'ALTER TABLE `orders` ADD CONSTRAINT `chk_orders_service_end_day_offset` CHECK (`service_end_day_offset` IS NULL OR `service_end_day_offset` IN (0, 1))',
    IF(
        @order_service_end_offset_check_any = 1
        AND @order_service_end_offset_check_exact = 1,
        'SELECT 1',
        'SELECT * FROM `FAIL_CLOSED_SERVICE_END_DAY_OFFSET_CHECK_INVALID_SPEC_REVIEW_REQUIRED`'
    )
);
PREPARE order_service_terms_stmt FROM @order_service_terms_sql;
EXECUTE order_service_terms_stmt;
DEALLOCATE PREPARE order_service_terms_stmt;
-- END SOURCE: db/schema_parts/105_order_service_time_terms.sql

-- BEGIN SOURCE: db/schema_parts/106_order_lifecycle_control_facts.sql
-- Canonical ORD-01 aggregate revision, explicit control facts and alert outbox.
-- This migration is additive and never infers facts from existing order rows.

SET @olcf_orders_exists = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'orders'
      AND TABLE_TYPE = 'BASE TABLE'
);
SET @olcf_history_exists = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'order_lifecycle_state_events'
      AND TABLE_TYPE = 'BASE TABLE'
);
SET @olcf_service_terms_exact = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'orders'
      AND (
          (
              COLUMN_NAME IN ('service_start_time', 'service_end_time')
              AND DATA_TYPE = 'time'
              AND IS_NULLABLE = 'YES'
              AND COLUMN_DEFAULT IS NULL
          )
          OR
          (
              COLUMN_NAME = 'service_end_day_offset'
              AND DATA_TYPE = 'tinyint'
              AND COLUMN_TYPE = 'tinyint unsigned'
              AND IS_NULLABLE = 'YES'
              AND COLUMN_DEFAULT IS NULL
          )
      )
);
SET @olcf_prereq_sql = IF(
    @olcf_orders_exists != 1,
    'SELECT * FROM `FAIL_CLOSED_ORDERS_TABLE_NOT_FOUND`',
    IF(
        @olcf_history_exists != 1,
        'SELECT * FROM `FAIL_CLOSED_ORDER_LIFECYCLE_STATE_EVENTS_TABLE_NOT_FOUND`',
        IF(
            @olcf_service_terms_exact != 3,
            'SELECT * FROM `FAIL_CLOSED_ORDER_SERVICE_TIME_TERMS_INVALID_OR_MISSING`',
            'SELECT 1'
        )
    )
);
PREPARE olcf_stmt FROM @olcf_prereq_sql;
EXECUTE olcf_stmt;
DEALLOCATE PREPARE olcf_stmt;

SET @olcf_version_any = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'orders'
      AND COLUMN_NAME = 'lifecycle_version'
);
SET @olcf_version_exact = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'orders'
      AND COLUMN_NAME = 'lifecycle_version'
      AND DATA_TYPE = 'bigint'
      AND COLUMN_TYPE = 'bigint unsigned'
      AND IS_NULLABLE = 'NO'
      AND COLUMN_DEFAULT = '0'
);
SET @olcf_version_sql = IF(
    @olcf_version_any = 0,
    'ALTER TABLE `orders` ADD COLUMN `lifecycle_version` BIGINT UNSIGNED NOT NULL DEFAULT 0 COMMENT ''ORD-01 aggregate revision；每個非 replay command 恰遞增一次'' AFTER `status`',
    IF(
        @olcf_version_any = 1 AND @olcf_version_exact = 1,
        'SELECT 1',
        'SELECT * FROM `FAIL_CLOSED_ORDER_LIFECYCLE_VERSION_INVALID_SPEC_REVIEW_REQUIRED`'
    )
);
PREPARE olcf_stmt FROM @olcf_version_sql;
EXECUTE olcf_stmt;
DEALLOCATE PREPARE olcf_stmt;

SET @olcf_events_preexisting = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'order_lifecycle_control_events'
);

CREATE TABLE IF NOT EXISTS order_lifecycle_control_events (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    case_no VARCHAR(50) NOT NULL,
    control_type ENUM(
        'cancellation',
        'actual_start_reconfirmation',
        'human_hold'
    ) NOT NULL,
    control_key VARCHAR(100) NOT NULL,
    scope ENUM('order', 'enter_service', 'auto_complete') NOT NULL,
    action ENUM('activate', 'clear') NOT NULL,
    actor VARCHAR(100) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    expected_version BIGINT UNSIGNED NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    payload_hash CHAR(64)
        CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    payload_snapshot JSON NOT NULL,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    UNIQUE KEY uq_order_lifecycle_control_event_idempotency (
        case_no,
        idempotency_key
    ),
    UNIQUE KEY uq_order_lifecycle_control_event_identity (
        id,
        case_no,
        control_type,
        control_key
    ),
    INDEX idx_order_lifecycle_control_event_case_type_time (
        case_no,
        control_type,
        control_key,
        created_at
    ),
    CONSTRAINT fk_order_lifecycle_control_event_case
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_order_lifecycle_control_event_text
        CHECK (
            CHAR_LENGTH(TRIM(control_key)) > 0
            AND CHAR_LENGTH(TRIM(actor)) > 0
            AND CHAR_LENGTH(TRIM(reason)) > 0
            AND CHAR_LENGTH(TRIM(idempotency_key)) > 0
        ),
    CONSTRAINT chk_order_lifecycle_control_event_payload
        CHECK (
            payload_hash REGEXP '^[0-9a-f]{64}$'
            AND JSON_TYPE(payload_snapshot) = 'OBJECT'
        ),
    CONSTRAINT chk_order_lifecycle_control_event_shape
        CHECK (
            (
                control_type = 'cancellation'
                AND control_key = 'order_cancelled'
                AND scope = 'order'
            )
            OR
            (
                control_type = 'actual_start_reconfirmation'
                AND control_key = 'actual_start_reconfirmation'
                AND scope = 'enter_service'
            )
            OR
            (
                control_type = 'human_hold'
                AND scope IN ('enter_service', 'auto_complete')
            )
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

SET @olcf_events_column_count = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'order_lifecycle_control_events'
);
SET @olcf_events_columns_exact = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'order_lifecycle_control_events'
      AND (
          (
              COLUMN_NAME = 'id'
              AND COLUMN_TYPE = 'bigint unsigned'
              AND IS_NULLABLE = 'NO'
              AND EXTRA = 'auto_increment'
          )
          OR
          (
              COLUMN_NAME = 'case_no'
              AND COLUMN_TYPE = 'varchar(50)'
              AND IS_NULLABLE = 'NO'
          )
          OR
          (
              COLUMN_NAME = 'control_type'
              AND COLUMN_TYPE = 'enum(''cancellation'',''actual_start_reconfirmation'',''human_hold'')'
              AND IS_NULLABLE = 'NO'
          )
          OR
          (
              COLUMN_NAME = 'control_key'
              AND COLUMN_TYPE = 'varchar(100)'
              AND IS_NULLABLE = 'NO'
          )
          OR
          (
              COLUMN_NAME = 'scope'
              AND COLUMN_TYPE = 'enum(''order'',''enter_service'',''auto_complete'')'
              AND IS_NULLABLE = 'NO'
          )
          OR
          (
              COLUMN_NAME = 'action'
              AND COLUMN_TYPE = 'enum(''activate'',''clear'')'
              AND IS_NULLABLE = 'NO'
          )
          OR
          (
              COLUMN_NAME = 'actor'
              AND COLUMN_TYPE = 'varchar(100)'
              AND IS_NULLABLE = 'NO'
          )
          OR
          (
              COLUMN_NAME = 'reason'
              AND COLUMN_TYPE = 'varchar(500)'
              AND IS_NULLABLE = 'NO'
          )
          OR
          (
              COLUMN_NAME = 'expected_version'
              AND COLUMN_TYPE = 'bigint unsigned'
              AND IS_NULLABLE = 'NO'
          )
          OR
          (
              COLUMN_NAME = 'idempotency_key'
              AND COLUMN_TYPE = 'varchar(191)'
              AND IS_NULLABLE = 'NO'
          )
          OR
          (
              COLUMN_NAME = 'payload_hash'
              AND COLUMN_TYPE = 'char(64)'
              AND IS_NULLABLE = 'NO'
              AND CHARACTER_SET_NAME = 'ascii'
              AND COLLATION_NAME = 'ascii_bin'
          )
          OR
          (
              COLUMN_NAME = 'payload_snapshot'
              AND DATA_TYPE = 'json'
              AND IS_NULLABLE = 'NO'
          )
          OR
          (
              COLUMN_NAME = 'created_at'
              AND COLUMN_TYPE = 'timestamp(6)'
              AND IS_NULLABLE = 'NO'
              AND LOWER(COLUMN_DEFAULT) = 'current_timestamp(6)'
          )
      )
);
SET @olcf_events_index_parts_exact = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'order_lifecycle_control_events'
      AND (
          (
              INDEX_NAME = 'PRIMARY'
              AND NON_UNIQUE = 0
              AND SEQ_IN_INDEX = 1
              AND COLUMN_NAME = 'id'
          )
          OR
          (
              INDEX_NAME = 'uq_order_lifecycle_control_event_idempotency'
              AND NON_UNIQUE = 0
              AND (
                  (SEQ_IN_INDEX = 1 AND COLUMN_NAME = 'case_no')
                  OR
                  (SEQ_IN_INDEX = 2 AND COLUMN_NAME = 'idempotency_key')
              )
          )
          OR
          (
              INDEX_NAME = 'uq_order_lifecycle_control_event_identity'
              AND NON_UNIQUE = 0
              AND (
                  (SEQ_IN_INDEX = 1 AND COLUMN_NAME = 'id')
                  OR
                  (SEQ_IN_INDEX = 2 AND COLUMN_NAME = 'case_no')
                  OR
                  (SEQ_IN_INDEX = 3 AND COLUMN_NAME = 'control_type')
                  OR
                  (SEQ_IN_INDEX = 4 AND COLUMN_NAME = 'control_key')
              )
          )
          OR
          (
              INDEX_NAME = 'idx_order_lifecycle_control_event_case_type_time'
              AND NON_UNIQUE = 1
              AND (
                  (SEQ_IN_INDEX = 1 AND COLUMN_NAME = 'case_no')
                  OR
                  (SEQ_IN_INDEX = 2 AND COLUMN_NAME = 'control_type')
                  OR
                  (SEQ_IN_INDEX = 3 AND COLUMN_NAME = 'control_key')
                  OR
                  (SEQ_IN_INDEX = 4 AND COLUMN_NAME = 'created_at')
              )
          )
      )
);
SET @olcf_events_fk_exact = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE k
    JOIN INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS r
      ON r.CONSTRAINT_SCHEMA = k.CONSTRAINT_SCHEMA
     AND r.TABLE_NAME = k.TABLE_NAME
     AND r.CONSTRAINT_NAME = k.CONSTRAINT_NAME
    WHERE k.CONSTRAINT_SCHEMA = DATABASE()
      AND k.TABLE_NAME = 'order_lifecycle_control_events'
      AND k.CONSTRAINT_NAME = 'fk_order_lifecycle_control_event_case'
      AND k.COLUMN_NAME = 'case_no'
      AND k.REFERENCED_TABLE_NAME = 'orders'
      AND k.REFERENCED_COLUMN_NAME = 'case_no'
      AND r.UPDATE_RULE = 'RESTRICT'
      AND r.DELETE_RULE = 'RESTRICT'
);
SET @olcf_events_checks_exact = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
    JOIN INFORMATION_SCHEMA.CHECK_CONSTRAINTS cc
      ON cc.CONSTRAINT_CATALOG = tc.CONSTRAINT_CATALOG
     AND cc.CONSTRAINT_SCHEMA = tc.CONSTRAINT_SCHEMA
     AND cc.CONSTRAINT_NAME = tc.CONSTRAINT_NAME
    WHERE tc.CONSTRAINT_SCHEMA = DATABASE()
      AND tc.TABLE_NAME = 'order_lifecycle_control_events'
      AND tc.CONSTRAINT_TYPE = 'CHECK'
      AND tc.ENFORCED = 'YES'
      AND (
          (
              tc.CONSTRAINT_NAME = 'chk_order_lifecycle_control_event_text'
              AND cc.CHECK_CLAUSE LIKE '%control_key%'
              AND cc.CHECK_CLAUSE LIKE '%actor%'
              AND cc.CHECK_CLAUSE LIKE '%reason%'
              AND cc.CHECK_CLAUSE LIKE '%idempotency_key%'
          )
          OR
          (
              tc.CONSTRAINT_NAME = 'chk_order_lifecycle_control_event_payload'
              AND cc.CHECK_CLAUSE LIKE '%payload_hash%'
              AND cc.CHECK_CLAUSE LIKE '%payload_snapshot%'
          )
          OR
          (
              tc.CONSTRAINT_NAME = 'chk_order_lifecycle_control_event_shape'
              AND cc.CHECK_CLAUSE LIKE '%order_cancelled%'
              AND cc.CHECK_CLAUSE LIKE '%actual_start_reconfirmation%'
              AND cc.CHECK_CLAUSE LIKE '%human_hold%'
          )
      )
);
SET @olcf_events_table_exact = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'order_lifecycle_control_events'
      AND ENGINE = 'InnoDB'
      AND TABLE_COLLATION = 'utf8mb4_unicode_ci'
);
SET @olcf_events_metadata_sql = IF(
    @olcf_events_column_count = 13
    AND @olcf_events_columns_exact = 13
    AND @olcf_events_index_parts_exact = 11
    AND @olcf_events_fk_exact = 1
    AND @olcf_events_checks_exact = 3
    AND @olcf_events_table_exact = 1,
    'SELECT 1',
    'SELECT * FROM `FAIL_CLOSED_ORDER_LIFECYCLE_CONTROL_EVENTS_METADATA_DRIFT`'
);
PREPARE olcf_stmt FROM @olcf_events_metadata_sql;
EXECUTE olcf_stmt;
DEALLOCATE PREPARE olcf_stmt;

SET @olcf_events_update_trigger_exact = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.TRIGGERS
    WHERE TRIGGER_SCHEMA = DATABASE()
      AND TRIGGER_NAME = 'trg_order_lifecycle_control_events_before_update'
      AND EVENT_OBJECT_TABLE = 'order_lifecycle_control_events'
      AND ACTION_TIMING = 'BEFORE'
      AND EVENT_MANIPULATION = 'UPDATE'
      AND ACTION_STATEMENT LIKE 'SIGNAL SQLSTATE ''45000''%'
);
SET @olcf_events_delete_trigger_exact = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.TRIGGERS
    WHERE TRIGGER_SCHEMA = DATABASE()
      AND TRIGGER_NAME = 'trg_order_lifecycle_control_events_before_delete'
      AND EVENT_OBJECT_TABLE = 'order_lifecycle_control_events'
      AND ACTION_TIMING = 'BEFORE'
      AND EVENT_MANIPULATION = 'DELETE'
      AND ACTION_STATEMENT LIKE 'SIGNAL SQLSTATE ''45000''%'
);
SET @olcf_events_trigger_guard_sql = IF(
    @olcf_events_preexisting = 0
    OR (
        @olcf_events_update_trigger_exact = 1
        AND @olcf_events_delete_trigger_exact = 1
    ),
    'SELECT 1',
    'SELECT * FROM `FAIL_CLOSED_ORDER_LIFECYCLE_CONTROL_EVENTS_TRIGGER_DRIFT`'
);
PREPARE olcf_stmt FROM @olcf_events_trigger_guard_sql;
EXECUTE olcf_stmt;
DEALLOCATE PREPARE olcf_stmt;

DROP TRIGGER IF EXISTS trg_order_lifecycle_control_events_before_update;
CREATE TRIGGER trg_order_lifecycle_control_events_before_update
BEFORE UPDATE ON order_lifecycle_control_events
FOR EACH ROW
SIGNAL SQLSTATE '45000'
    SET MESSAGE_TEXT = 'order_lifecycle_control_events records cannot be updated';

DROP TRIGGER IF EXISTS trg_order_lifecycle_control_events_before_delete;
CREATE TRIGGER trg_order_lifecycle_control_events_before_delete
BEFORE DELETE ON order_lifecycle_control_events
FOR EACH ROW
SIGNAL SQLSTATE '45000'
    SET MESSAGE_TEXT = 'order_lifecycle_control_events records cannot be deleted';

SET @olcf_state_preexisting = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'order_lifecycle_control_state'
);

CREATE TABLE IF NOT EXISTS order_lifecycle_control_state (
    case_no VARCHAR(50) NOT NULL,
    control_type ENUM(
        'cancellation',
        'actual_start_reconfirmation',
        'human_hold'
    ) NOT NULL,
    control_key VARCHAR(100) NOT NULL,
    scope ENUM('order', 'enter_service', 'auto_complete') NOT NULL,
    state ENUM('active', 'cleared') NOT NULL,
    current_event_id BIGINT UNSIGNED NOT NULL,
    release_policy ENUM('manual', 'expires_at') NULL,
    expires_at_utc DATETIME(6) NULL,
    confirmed_start_date DATE NULL,
    deposit_settlement_identity_hash CHAR(64)
        CHARACTER SET ascii COLLATE ascii_bin NULL,
    reason VARCHAR(500) NOT NULL,
    changed_by VARCHAR(100) NOT NULL,
    changed_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (case_no, control_type, control_key),
    INDEX idx_order_lifecycle_control_state_case_status_type (
        case_no,
        state,
        control_type
    ),
    CONSTRAINT fk_order_lifecycle_control_state_case
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_order_lifecycle_control_state_event
        FOREIGN KEY (
            current_event_id,
            case_no,
            control_type,
            control_key
        )
        REFERENCES order_lifecycle_control_events (
            id,
            case_no,
            control_type,
            control_key
        )
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_order_lifecycle_control_state_text
        CHECK (
            CHAR_LENGTH(TRIM(control_key)) > 0
            AND CHAR_LENGTH(TRIM(reason)) > 0
            AND CHAR_LENGTH(TRIM(changed_by)) > 0
        ),
    CONSTRAINT chk_order_lifecycle_control_state_confirmation_hash
        CHECK (
            deposit_settlement_identity_hash IS NULL
            OR deposit_settlement_identity_hash REGEXP '^[0-9a-f]{64}$'
        ),
    CONSTRAINT chk_order_lifecycle_control_state_shape
        CHECK (
            (
                control_type = 'cancellation'
                AND control_key = 'order_cancelled'
                AND scope = 'order'
                AND release_policy IS NULL
                AND expires_at_utc IS NULL
                AND confirmed_start_date IS NULL
                AND deposit_settlement_identity_hash IS NULL
            )
            OR
            (
                control_type = 'actual_start_reconfirmation'
                AND control_key = 'actual_start_reconfirmation'
                AND scope = 'enter_service'
                AND release_policy IS NULL
                AND expires_at_utc IS NULL
                AND (
                    (
                        state = 'active'
                        AND confirmed_start_date IS NULL
                        AND deposit_settlement_identity_hash IS NULL
                    )
                    OR
                    (
                        state = 'cleared'
                        AND confirmed_start_date IS NOT NULL
                        AND deposit_settlement_identity_hash IS NOT NULL
                    )
                )
            )
            OR
            (
                control_type = 'human_hold'
                AND scope IN ('enter_service', 'auto_complete')
                AND confirmed_start_date IS NULL
                AND deposit_settlement_identity_hash IS NULL
                AND (
                    (
                        release_policy = 'manual'
                        AND expires_at_utc IS NULL
                    )
                    OR
                    (
                        release_policy = 'expires_at'
                        AND expires_at_utc IS NOT NULL
                    )
                )
            )
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

SET @olcf_state_column_count = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'order_lifecycle_control_state'
);
SET @olcf_state_columns_exact = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'order_lifecycle_control_state'
      AND (
          (
              COLUMN_NAME = 'case_no'
              AND COLUMN_TYPE = 'varchar(50)'
              AND IS_NULLABLE = 'NO'
          )
          OR
          (
              COLUMN_NAME = 'control_type'
              AND COLUMN_TYPE = 'enum(''cancellation'',''actual_start_reconfirmation'',''human_hold'')'
              AND IS_NULLABLE = 'NO'
          )
          OR
          (
              COLUMN_NAME = 'control_key'
              AND COLUMN_TYPE = 'varchar(100)'
              AND IS_NULLABLE = 'NO'
          )
          OR
          (
              COLUMN_NAME = 'scope'
              AND COLUMN_TYPE = 'enum(''order'',''enter_service'',''auto_complete'')'
              AND IS_NULLABLE = 'NO'
          )
          OR
          (
              COLUMN_NAME = 'state'
              AND COLUMN_TYPE = 'enum(''active'',''cleared'')'
              AND IS_NULLABLE = 'NO'
          )
          OR
          (
              COLUMN_NAME = 'current_event_id'
              AND COLUMN_TYPE = 'bigint unsigned'
              AND IS_NULLABLE = 'NO'
          )
          OR
          (
              COLUMN_NAME = 'release_policy'
              AND COLUMN_TYPE = 'enum(''manual'',''expires_at'')'
              AND IS_NULLABLE = 'YES'
          )
          OR
          (
              COLUMN_NAME IN ('expires_at_utc')
              AND COLUMN_TYPE = 'datetime(6)'
              AND IS_NULLABLE = 'YES'
          )
          OR
          (
              COLUMN_NAME = 'confirmed_start_date'
              AND DATA_TYPE = 'date'
              AND IS_NULLABLE = 'YES'
          )
          OR
          (
              COLUMN_NAME = 'deposit_settlement_identity_hash'
              AND COLUMN_TYPE = 'char(64)'
              AND IS_NULLABLE = 'YES'
              AND CHARACTER_SET_NAME = 'ascii'
              AND COLLATION_NAME = 'ascii_bin'
          )
          OR
          (
              COLUMN_NAME = 'reason'
              AND COLUMN_TYPE = 'varchar(500)'
              AND IS_NULLABLE = 'NO'
          )
          OR
          (
              COLUMN_NAME = 'changed_by'
              AND COLUMN_TYPE = 'varchar(100)'
              AND IS_NULLABLE = 'NO'
          )
          OR
          (
              COLUMN_NAME = 'changed_at'
              AND COLUMN_TYPE = 'timestamp(6)'
              AND IS_NULLABLE = 'NO'
              AND LOWER(COLUMN_DEFAULT) = 'current_timestamp(6)'
          )
      )
);
SET @olcf_state_index_parts_exact = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'order_lifecycle_control_state'
      AND (
          (
              INDEX_NAME = 'PRIMARY'
              AND NON_UNIQUE = 0
              AND (
                  (SEQ_IN_INDEX = 1 AND COLUMN_NAME = 'case_no')
                  OR
                  (SEQ_IN_INDEX = 2 AND COLUMN_NAME = 'control_type')
                  OR
                  (SEQ_IN_INDEX = 3 AND COLUMN_NAME = 'control_key')
              )
          )
          OR
          (
              INDEX_NAME = 'idx_order_lifecycle_control_state_case_status_type'
              AND NON_UNIQUE = 1
              AND (
                  (SEQ_IN_INDEX = 1 AND COLUMN_NAME = 'case_no')
                  OR
                  (SEQ_IN_INDEX = 2 AND COLUMN_NAME = 'state')
                  OR
                  (SEQ_IN_INDEX = 3 AND COLUMN_NAME = 'control_type')
              )
          )
          OR
          (
              INDEX_NAME = 'fk_order_lifecycle_control_state_event'
              AND NON_UNIQUE = 1
              AND (
                  (SEQ_IN_INDEX = 1 AND COLUMN_NAME = 'current_event_id')
                  OR
                  (SEQ_IN_INDEX = 2 AND COLUMN_NAME = 'case_no')
                  OR
                  (SEQ_IN_INDEX = 3 AND COLUMN_NAME = 'control_type')
                  OR
                  (SEQ_IN_INDEX = 4 AND COLUMN_NAME = 'control_key')
              )
          )
      )
);
SET @olcf_state_case_fk_exact = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE k
    JOIN INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS r
      ON r.CONSTRAINT_SCHEMA = k.CONSTRAINT_SCHEMA
     AND r.TABLE_NAME = k.TABLE_NAME
     AND r.CONSTRAINT_NAME = k.CONSTRAINT_NAME
    WHERE k.CONSTRAINT_SCHEMA = DATABASE()
      AND k.TABLE_NAME = 'order_lifecycle_control_state'
      AND k.CONSTRAINT_NAME = 'fk_order_lifecycle_control_state_case'
      AND k.COLUMN_NAME = 'case_no'
      AND k.REFERENCED_TABLE_NAME = 'orders'
      AND k.REFERENCED_COLUMN_NAME = 'case_no'
      AND r.UPDATE_RULE = 'RESTRICT'
      AND r.DELETE_RULE = 'RESTRICT'
);
SET @olcf_state_event_fk_parts_exact = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE k
    JOIN INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS r
      ON r.CONSTRAINT_SCHEMA = k.CONSTRAINT_SCHEMA
     AND r.TABLE_NAME = k.TABLE_NAME
     AND r.CONSTRAINT_NAME = k.CONSTRAINT_NAME
    WHERE k.CONSTRAINT_SCHEMA = DATABASE()
      AND k.TABLE_NAME = 'order_lifecycle_control_state'
      AND k.CONSTRAINT_NAME = 'fk_order_lifecycle_control_state_event'
      AND k.REFERENCED_TABLE_NAME = 'order_lifecycle_control_events'
      AND r.UPDATE_RULE = 'RESTRICT'
      AND r.DELETE_RULE = 'RESTRICT'
      AND (
          (
              k.ORDINAL_POSITION = 1
              AND k.COLUMN_NAME = 'current_event_id'
              AND k.REFERENCED_COLUMN_NAME = 'id'
          )
          OR
          (
              k.ORDINAL_POSITION = 2
              AND k.COLUMN_NAME = 'case_no'
              AND k.REFERENCED_COLUMN_NAME = 'case_no'
          )
          OR
          (
              k.ORDINAL_POSITION = 3
              AND k.COLUMN_NAME = 'control_type'
              AND k.REFERENCED_COLUMN_NAME = 'control_type'
          )
          OR
          (
              k.ORDINAL_POSITION = 4
              AND k.COLUMN_NAME = 'control_key'
              AND k.REFERENCED_COLUMN_NAME = 'control_key'
          )
      )
);
SET @olcf_state_checks_exact = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
    JOIN INFORMATION_SCHEMA.CHECK_CONSTRAINTS cc
      ON cc.CONSTRAINT_CATALOG = tc.CONSTRAINT_CATALOG
     AND cc.CONSTRAINT_SCHEMA = tc.CONSTRAINT_SCHEMA
     AND cc.CONSTRAINT_NAME = tc.CONSTRAINT_NAME
    WHERE tc.CONSTRAINT_SCHEMA = DATABASE()
      AND tc.TABLE_NAME = 'order_lifecycle_control_state'
      AND tc.CONSTRAINT_TYPE = 'CHECK'
      AND tc.ENFORCED = 'YES'
      AND (
          (
              tc.CONSTRAINT_NAME = 'chk_order_lifecycle_control_state_text'
              AND cc.CHECK_CLAUSE LIKE '%control_key%'
              AND cc.CHECK_CLAUSE LIKE '%changed_by%'
          )
          OR
          (
              tc.CONSTRAINT_NAME = 'chk_order_lifecycle_control_state_confirmation_hash'
              AND cc.CHECK_CLAUSE LIKE '%deposit_settlement_identity_hash%'
          )
          OR
          (
              tc.CONSTRAINT_NAME = 'chk_order_lifecycle_control_state_shape'
              AND cc.CHECK_CLAUSE LIKE '%confirmed_start_date%'
              AND cc.CHECK_CLAUSE LIKE '%expires_at_utc%'
              AND cc.CHECK_CLAUSE LIKE '%release_policy%'
          )
      )
);
SET @olcf_state_table_exact = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'order_lifecycle_control_state'
      AND ENGINE = 'InnoDB'
      AND TABLE_COLLATION = 'utf8mb4_unicode_ci'
);
SET @olcf_state_metadata_sql = IF(
    @olcf_state_column_count = 13
    AND @olcf_state_columns_exact = 13
    AND @olcf_state_index_parts_exact = 10
    AND @olcf_state_case_fk_exact = 1
    AND @olcf_state_event_fk_parts_exact = 4
    AND @olcf_state_checks_exact = 3
    AND @olcf_state_table_exact = 1,
    'SELECT 1',
    'SELECT * FROM `FAIL_CLOSED_ORDER_LIFECYCLE_CONTROL_STATE_METADATA_DRIFT`'
);
PREPARE olcf_stmt FROM @olcf_state_metadata_sql;
EXECUTE olcf_stmt;
DEALLOCATE PREPARE olcf_stmt;

SET @olcf_state_delete_trigger_exact = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.TRIGGERS
    WHERE TRIGGER_SCHEMA = DATABASE()
      AND TRIGGER_NAME = 'trg_order_lifecycle_control_state_before_delete'
      AND EVENT_OBJECT_TABLE = 'order_lifecycle_control_state'
      AND ACTION_TIMING = 'BEFORE'
      AND EVENT_MANIPULATION = 'DELETE'
      AND ACTION_STATEMENT LIKE 'SIGNAL SQLSTATE ''45000''%'
);
SET @olcf_state_trigger_guard_sql = IF(
    @olcf_state_preexisting = 0
    OR @olcf_state_delete_trigger_exact = 1,
    'SELECT 1',
    'SELECT * FROM `FAIL_CLOSED_ORDER_LIFECYCLE_CONTROL_STATE_TRIGGER_DRIFT`'
);
PREPARE olcf_stmt FROM @olcf_state_trigger_guard_sql;
EXECUTE olcf_stmt;
DEALLOCATE PREPARE olcf_stmt;

DROP TRIGGER IF EXISTS trg_order_lifecycle_control_state_before_delete;
CREATE TRIGGER trg_order_lifecycle_control_state_before_delete
BEFORE DELETE ON order_lifecycle_control_state
FOR EACH ROW
SIGNAL SQLSTATE '45000'
    SET MESSAGE_TEXT = 'order_lifecycle_control_state records cannot be deleted';

CREATE TABLE IF NOT EXISTS order_lifecycle_projection_outbox (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    case_no VARCHAR(50) NOT NULL,
    lifecycle_event_id BIGINT UNSIGNED NOT NULL,
    intent_key VARCHAR(191) NOT NULL,
    scope ENUM('enter_service', 'auto_complete') NOT NULL,
    alert_code VARCHAR(191) NOT NULL,
    action ENUM('open', 'resolve') NOT NULL,
    payload_hash CHAR(64)
        CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    payload_snapshot JSON NOT NULL,
    status ENUM(
        'pending',
        'processing',
        'projected',
        'failed'
    ) NOT NULL DEFAULT 'pending',
    attempt_count INT UNSIGNED NOT NULL DEFAULT 0,
    next_attempt_at_utc DATETIME(6) NULL,
    locked_at_utc DATETIME(6) NULL,
    projected_at_utc DATETIME(6) NULL,
    last_error VARCHAR(1000) NULL,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
        ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    UNIQUE KEY uq_order_lifecycle_projection_outbox_intent (
        case_no,
        intent_key
    ),
    INDEX idx_order_lifecycle_projection_outbox_retry (
        status,
        next_attempt_at_utc,
        id
    ),
    INDEX idx_order_lifecycle_projection_outbox_event (
        case_no,
        lifecycle_event_id
    ),
    CONSTRAINT fk_order_lifecycle_projection_outbox_case
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_order_lifecycle_projection_outbox_event
        FOREIGN KEY (lifecycle_event_id)
        REFERENCES order_lifecycle_state_events(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_order_lifecycle_projection_outbox_text
        CHECK (
            CHAR_LENGTH(TRIM(intent_key)) > 0
            AND CHAR_LENGTH(TRIM(alert_code)) > 0
        ),
    CONSTRAINT chk_order_lifecycle_projection_outbox_payload
        CHECK (
            payload_hash REGEXP '^[0-9a-f]{64}$'
            AND JSON_TYPE(payload_snapshot) = 'OBJECT'
        ),
    CONSTRAINT chk_order_lifecycle_projection_outbox_status
        CHECK (
            (
                status = 'pending'
                AND locked_at_utc IS NULL
                AND projected_at_utc IS NULL
                AND last_error IS NULL
            )
            OR
            (
                status = 'processing'
                AND locked_at_utc IS NOT NULL
                AND projected_at_utc IS NULL
            )
            OR
            (
                status = 'projected'
                AND projected_at_utc IS NOT NULL
                AND last_error IS NULL
            )
            OR
            (
                status = 'failed'
                AND projected_at_utc IS NULL
                AND last_error IS NOT NULL
            )
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

SET @olcf_outbox_column_count = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'order_lifecycle_projection_outbox'
);
SET @olcf_outbox_columns_exact = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'order_lifecycle_projection_outbox'
      AND (
          (
              COLUMN_NAME = 'id'
              AND COLUMN_TYPE = 'bigint unsigned'
              AND IS_NULLABLE = 'NO'
              AND EXTRA = 'auto_increment'
          )
          OR
          (
              COLUMN_NAME = 'case_no'
              AND COLUMN_TYPE = 'varchar(50)'
              AND IS_NULLABLE = 'NO'
          )
          OR
          (
              COLUMN_NAME = 'lifecycle_event_id'
              AND COLUMN_TYPE = 'bigint unsigned'
              AND IS_NULLABLE = 'NO'
          )
          OR
          (
              COLUMN_NAME = 'intent_key'
              AND COLUMN_TYPE = 'varchar(191)'
              AND IS_NULLABLE = 'NO'
          )
          OR
          (
              COLUMN_NAME = 'scope'
              AND COLUMN_TYPE = 'enum(''enter_service'',''auto_complete'')'
              AND IS_NULLABLE = 'NO'
          )
          OR
          (
              COLUMN_NAME = 'alert_code'
              AND COLUMN_TYPE = 'varchar(191)'
              AND IS_NULLABLE = 'NO'
          )
          OR
          (
              COLUMN_NAME = 'action'
              AND COLUMN_TYPE = 'enum(''open'',''resolve'')'
              AND IS_NULLABLE = 'NO'
          )
          OR
          (
              COLUMN_NAME = 'payload_hash'
              AND COLUMN_TYPE = 'char(64)'
              AND IS_NULLABLE = 'NO'
              AND CHARACTER_SET_NAME = 'ascii'
              AND COLLATION_NAME = 'ascii_bin'
          )
          OR
          (
              COLUMN_NAME = 'payload_snapshot'
              AND DATA_TYPE = 'json'
              AND IS_NULLABLE = 'NO'
          )
          OR
          (
              COLUMN_NAME = 'status'
              AND COLUMN_TYPE = 'enum(''pending'',''processing'',''projected'',''failed'')'
              AND IS_NULLABLE = 'NO'
              AND COLUMN_DEFAULT = 'pending'
          )
          OR
          (
              COLUMN_NAME = 'attempt_count'
              AND COLUMN_TYPE = 'int unsigned'
              AND IS_NULLABLE = 'NO'
              AND COLUMN_DEFAULT = '0'
          )
          OR
          (
              COLUMN_NAME IN (
                  'next_attempt_at_utc',
                  'locked_at_utc',
                  'projected_at_utc'
              )
              AND COLUMN_TYPE = 'datetime(6)'
              AND IS_NULLABLE = 'YES'
          )
          OR
          (
              COLUMN_NAME = 'last_error'
              AND COLUMN_TYPE = 'varchar(1000)'
              AND IS_NULLABLE = 'YES'
          )
          OR
          (
              COLUMN_NAME = 'created_at'
              AND COLUMN_TYPE = 'timestamp(6)'
              AND IS_NULLABLE = 'NO'
              AND LOWER(COLUMN_DEFAULT) = 'current_timestamp(6)'
              AND EXTRA NOT LIKE '%on update%'
          )
          OR
          (
              COLUMN_NAME = 'updated_at'
              AND COLUMN_TYPE = 'timestamp(6)'
              AND IS_NULLABLE = 'NO'
              AND LOWER(COLUMN_DEFAULT) = 'current_timestamp(6)'
              AND EXTRA = 'DEFAULT_GENERATED on update CURRENT_TIMESTAMP(6)'
          )
      )
);
SET @olcf_outbox_index_parts_exact = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'order_lifecycle_projection_outbox'
      AND (
          (
              INDEX_NAME = 'PRIMARY'
              AND NON_UNIQUE = 0
              AND SEQ_IN_INDEX = 1
              AND COLUMN_NAME = 'id'
          )
          OR
          (
              INDEX_NAME = 'uq_order_lifecycle_projection_outbox_intent'
              AND NON_UNIQUE = 0
              AND (
                  (SEQ_IN_INDEX = 1 AND COLUMN_NAME = 'case_no')
                  OR
                  (SEQ_IN_INDEX = 2 AND COLUMN_NAME = 'intent_key')
              )
          )
          OR
          (
              INDEX_NAME = 'idx_order_lifecycle_projection_outbox_retry'
              AND NON_UNIQUE = 1
              AND (
                  (SEQ_IN_INDEX = 1 AND COLUMN_NAME = 'status')
                  OR
                  (SEQ_IN_INDEX = 2 AND COLUMN_NAME = 'next_attempt_at_utc')
                  OR
                  (SEQ_IN_INDEX = 3 AND COLUMN_NAME = 'id')
              )
          )
          OR
          (
              INDEX_NAME = 'idx_order_lifecycle_projection_outbox_event'
              AND NON_UNIQUE = 1
              AND (
                  (SEQ_IN_INDEX = 1 AND COLUMN_NAME = 'case_no')
                  OR
                  (SEQ_IN_INDEX = 2 AND COLUMN_NAME = 'lifecycle_event_id')
              )
          )
          OR
          (
              INDEX_NAME = 'fk_order_lifecycle_projection_outbox_event'
              AND NON_UNIQUE = 1
              AND SEQ_IN_INDEX = 1
              AND COLUMN_NAME = 'lifecycle_event_id'
          )
      )
);
SET @olcf_outbox_case_fk_exact = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE k
    JOIN INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS r
      ON r.CONSTRAINT_SCHEMA = k.CONSTRAINT_SCHEMA
     AND r.TABLE_NAME = k.TABLE_NAME
     AND r.CONSTRAINT_NAME = k.CONSTRAINT_NAME
    WHERE k.CONSTRAINT_SCHEMA = DATABASE()
      AND k.TABLE_NAME = 'order_lifecycle_projection_outbox'
      AND k.CONSTRAINT_NAME = 'fk_order_lifecycle_projection_outbox_case'
      AND k.COLUMN_NAME = 'case_no'
      AND k.REFERENCED_TABLE_NAME = 'orders'
      AND k.REFERENCED_COLUMN_NAME = 'case_no'
      AND r.UPDATE_RULE = 'RESTRICT'
      AND r.DELETE_RULE = 'RESTRICT'
);
SET @olcf_outbox_event_fk_exact = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE k
    JOIN INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS r
      ON r.CONSTRAINT_SCHEMA = k.CONSTRAINT_SCHEMA
     AND r.TABLE_NAME = k.TABLE_NAME
     AND r.CONSTRAINT_NAME = k.CONSTRAINT_NAME
    WHERE k.CONSTRAINT_SCHEMA = DATABASE()
      AND k.TABLE_NAME = 'order_lifecycle_projection_outbox'
      AND k.CONSTRAINT_NAME = 'fk_order_lifecycle_projection_outbox_event'
      AND k.COLUMN_NAME = 'lifecycle_event_id'
      AND k.REFERENCED_TABLE_NAME = 'order_lifecycle_state_events'
      AND k.REFERENCED_COLUMN_NAME = 'id'
      AND r.UPDATE_RULE = 'RESTRICT'
      AND r.DELETE_RULE = 'RESTRICT'
);
SET @olcf_outbox_checks_exact = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
    JOIN INFORMATION_SCHEMA.CHECK_CONSTRAINTS cc
      ON cc.CONSTRAINT_CATALOG = tc.CONSTRAINT_CATALOG
     AND cc.CONSTRAINT_SCHEMA = tc.CONSTRAINT_SCHEMA
     AND cc.CONSTRAINT_NAME = tc.CONSTRAINT_NAME
    WHERE tc.CONSTRAINT_SCHEMA = DATABASE()
      AND tc.TABLE_NAME = 'order_lifecycle_projection_outbox'
      AND tc.CONSTRAINT_TYPE = 'CHECK'
      AND tc.ENFORCED = 'YES'
      AND (
          (
              tc.CONSTRAINT_NAME = 'chk_order_lifecycle_projection_outbox_text'
              AND cc.CHECK_CLAUSE LIKE '%intent_key%'
              AND cc.CHECK_CLAUSE LIKE '%alert_code%'
          )
          OR
          (
              tc.CONSTRAINT_NAME = 'chk_order_lifecycle_projection_outbox_payload'
              AND cc.CHECK_CLAUSE LIKE '%payload_hash%'
              AND cc.CHECK_CLAUSE LIKE '%payload_snapshot%'
          )
          OR
          (
              tc.CONSTRAINT_NAME = 'chk_order_lifecycle_projection_outbox_status'
              AND cc.CHECK_CLAUSE LIKE '%processing%'
              AND cc.CHECK_CLAUSE LIKE '%projected_at_utc%'
              AND cc.CHECK_CLAUSE LIKE '%last_error%'
          )
      )
);
SET @olcf_outbox_table_exact = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'order_lifecycle_projection_outbox'
      AND ENGINE = 'InnoDB'
      AND TABLE_COLLATION = 'utf8mb4_unicode_ci'
);
SET @olcf_outbox_metadata_sql = IF(
    @olcf_outbox_column_count = 17
    AND @olcf_outbox_columns_exact = 17
    AND @olcf_outbox_index_parts_exact = 9
    AND @olcf_outbox_case_fk_exact = 1
    AND @olcf_outbox_event_fk_exact = 1
    AND @olcf_outbox_checks_exact = 3
    AND @olcf_outbox_table_exact = 1,
    'SELECT 1',
    'SELECT * FROM `FAIL_CLOSED_ORDER_LIFECYCLE_PROJECTION_OUTBOX_METADATA_DRIFT`'
);
PREPARE olcf_stmt FROM @olcf_outbox_metadata_sql;
EXECUTE olcf_stmt;
DEALLOCATE PREPARE olcf_stmt;
-- END SOURCE: db/schema_parts/106_order_lifecycle_control_facts.sql

-- BEGIN SOURCE: db/schema_parts/107_system_alert_current_projection.sql
-- Preserve legacy system_alerts rows while installing the mutable current
-- projection required by SystemAlertService. This migration is candidate-only.

SET @system_alert_table_exists = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'system_alerts'
      AND TABLE_TYPE = 'BASE TABLE'
);
SET @system_alert_sql = IF(
    @system_alert_table_exists = 1,
    'SELECT 1',
    'SELECT * FROM `FAIL_CLOSED_SYSTEM_ALERTS_TABLE_NOT_FOUND`'
);
PREPARE system_alert_stmt FROM @system_alert_sql;
EXECUTE system_alert_stmt;
DEALLOCATE PREPARE system_alert_stmt;

SET @system_alert_new_column_count = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'system_alerts'
      AND COLUMN_NAME IN (
          'alert_code', 'source_domain', 'case_key', 'reason', 'details',
          'claimed_by', 'claimed_at', 'resolution_reason', 'updated_at'
      )
);
SET @system_alert_legacy_shape_count = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'system_alerts'
      AND (
          (COLUMN_NAME = 'id' AND COLUMN_TYPE = 'int'
              AND IS_NULLABLE = 'NO' AND EXTRA LIKE '%auto_increment%')
          OR (COLUMN_NAME = 'event_type' AND COLUMN_TYPE = 'varchar(50)'
              AND IS_NULLABLE = 'NO')
          OR (COLUMN_NAME = 'description' AND COLUMN_TYPE = 'text'
              AND IS_NULLABLE = 'NO')
          OR (COLUMN_NAME = 'status'
              AND COLUMN_TYPE = 'enum(''pending'',''resolved'')')
          OR (COLUMN_NAME = 'created_at' AND DATA_TYPE = 'timestamp')
          OR (COLUMN_NAME = 'resolved_at' AND DATA_TYPE = 'timestamp')
          OR (COLUMN_NAME = 'resolved_by' AND COLUMN_TYPE = 'varchar(50)')
      )
);
SET @system_alert_migrate_legacy = (
    @system_alert_new_column_count = 0
    AND @system_alert_legacy_shape_count = 7
);
SET @system_alert_sql = IF(
    @system_alert_migrate_legacy = 1
    OR @system_alert_new_column_count = 9,
    'SELECT 1',
    'SELECT * FROM `FAIL_CLOSED_SYSTEM_ALERTS_PARTIAL_OR_DRIFTED_SHAPE`'
);
PREPARE system_alert_stmt FROM @system_alert_sql;
EXECUTE system_alert_stmt;
DEALLOCATE PREPARE system_alert_stmt;

SET @system_alert_sql = IF(
    @system_alert_migrate_legacy = 1,
    'ALTER TABLE `system_alerts`
       ADD COLUMN `alert_code` VARCHAR(50) NULL AFTER `id`,
       ADD COLUMN `source_domain` VARCHAR(50) NULL AFTER `alert_code`,
       ADD COLUMN `case_key` VARCHAR(100) NULL AFTER `source_domain`,
       ADD COLUMN `reason` VARCHAR(500) NULL AFTER `case_key`,
       ADD COLUMN `details` JSON NULL AFTER `reason`,
       ADD COLUMN `claimed_by` VARCHAR(100) NULL AFTER `status`,
       ADD COLUMN `claimed_at` DATETIME NULL AFTER `claimed_by`,
       ADD COLUMN `resolution_reason` VARCHAR(500) NULL AFTER `resolved_by`,
       ADD COLUMN `updated_at` TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP
         ON UPDATE CURRENT_TIMESTAMP AFTER `created_at`',
    'SELECT 1'
);
PREPARE system_alert_stmt FROM @system_alert_sql;
EXECUTE system_alert_stmt;
DEALLOCATE PREPARE system_alert_stmt;

SET @system_alert_sql = IF(
    @system_alert_migrate_legacy = 1,
    'ALTER TABLE `system_alerts`
       MODIFY COLUMN `status`
         ENUM(''pending'',''open'',''claimed'',''resolved'')
         NULL DEFAULT ''pending''',
    'SELECT 1'
);
PREPARE system_alert_stmt FROM @system_alert_sql;
EXECUTE system_alert_stmt;
DEALLOCATE PREPARE system_alert_stmt;

SET @system_alert_sql = IF(
    @system_alert_migrate_legacy = 1,
    'UPDATE `system_alerts`
        SET `alert_code` = COALESCE(NULLIF(TRIM(`event_type`), ''''), ''LEGACY''),
            `source_domain` = ''LEGACY'',
            `case_key` = CONCAT(''legacy-alert:'', `id`),
            `reason` = COALESCE(
                NULLIF(LEFT(TRIM(`description`), 500), ''''),
                ''Legacy system alert''
            ),
            `details` = JSON_OBJECT(
                ''legacy_event_type'', COALESCE(NULLIF(TRIM(`event_type`), ''''), ''LEGACY''),
                ''migration'', ''system_alert_current_projection_v1''
            ),
            `status` = IF(`status` = ''pending'', ''open'', ''resolved'')',
    'SELECT 1'
);
PREPARE system_alert_stmt FROM @system_alert_sql;
EXECUTE system_alert_stmt;
DEALLOCATE PREPARE system_alert_stmt;

SET @system_alert_invalid_rows = (
    SELECT COUNT(*)
    FROM system_alerts
    WHERE alert_code IS NULL
       OR source_domain IS NULL
       OR case_key IS NULL
       OR reason IS NULL
       OR details IS NULL
       OR status NOT IN ('open', 'claimed', 'resolved')
);
SET @system_alert_duplicate_identity = (
    SELECT COUNT(*)
    FROM (
        SELECT alert_code, case_key
        FROM system_alerts
        GROUP BY alert_code, case_key
        HAVING COUNT(*) > 1
    ) AS duplicate_identity
);
SET @system_alert_sql = IF(
    @system_alert_invalid_rows = 0
    AND @system_alert_duplicate_identity = 0,
    'SELECT 1',
    'SELECT * FROM `FAIL_CLOSED_SYSTEM_ALERTS_BACKFILL_VALIDATION_FAILED`'
);
PREPARE system_alert_stmt FROM @system_alert_sql;
EXECUTE system_alert_stmt;
DEALLOCATE PREPARE system_alert_stmt;

SET @system_alert_sql = IF(
    @system_alert_migrate_legacy = 1,
    'ALTER TABLE `system_alerts`
       MODIFY COLUMN `alert_code` VARCHAR(50) NOT NULL,
       MODIFY COLUMN `source_domain` VARCHAR(50) NOT NULL,
       MODIFY COLUMN `case_key` VARCHAR(100) NOT NULL,
       MODIFY COLUMN `reason` VARCHAR(500) NOT NULL,
       MODIFY COLUMN `details` JSON NOT NULL,
       MODIFY COLUMN `status`
         ENUM(''open'',''claimed'',''resolved'') NOT NULL DEFAULT ''open'',
       MODIFY COLUMN `event_type` VARCHAR(50) NULL,
       MODIFY COLUMN `description` TEXT NULL,
       MODIFY COLUMN `resolved_by` VARCHAR(100) NULL,
       MODIFY COLUMN `resolved_at` DATETIME NULL,
       MODIFY COLUMN `created_at` TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
       MODIFY COLUMN `updated_at` TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP
         ON UPDATE CURRENT_TIMESTAMP',
    'SELECT 1'
);
PREPARE system_alert_stmt FROM @system_alert_sql;
EXECUTE system_alert_stmt;
DEALLOCATE PREPARE system_alert_stmt;

SET @system_alert_uq_any = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'system_alerts'
      AND INDEX_NAME = 'uq_alert_case'
);
SET @system_alert_uq_exact = (
    SELECT COUNT(*)
    FROM (
        SELECT INDEX_NAME, NON_UNIQUE
        FROM INFORMATION_SCHEMA.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'system_alerts'
          AND INDEX_NAME = 'uq_alert_case'
        GROUP BY INDEX_NAME, NON_UNIQUE
        HAVING NON_UNIQUE = 0
           AND GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX) =
               'alert_code,case_key'
    ) AS exact_index
);
SET @system_alert_sql = IF(
    @system_alert_uq_any = 0,
    'ALTER TABLE `system_alerts`
       ADD UNIQUE KEY `uq_alert_case` (`alert_code`, `case_key`)',
    IF(
        @system_alert_uq_exact = 1,
        'SELECT 1',
        'SELECT * FROM `FAIL_CLOSED_SYSTEM_ALERTS_UNIQUE_INDEX_DRIFT`'
    )
);
PREPARE system_alert_stmt FROM @system_alert_sql;
EXECUTE system_alert_stmt;
DEALLOCATE PREPARE system_alert_stmt;

SET @system_alert_status_index_any = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'system_alerts'
      AND INDEX_NAME = 'idx_system_alert_status'
);
SET @system_alert_status_index_exact = (
    SELECT COUNT(*)
    FROM (
        SELECT INDEX_NAME, NON_UNIQUE
        FROM INFORMATION_SCHEMA.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'system_alerts'
          AND INDEX_NAME = 'idx_system_alert_status'
        GROUP BY INDEX_NAME, NON_UNIQUE
        HAVING NON_UNIQUE = 1
           AND GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX) = 'status'
    ) AS exact_index
);
SET @system_alert_sql = IF(
    @system_alert_status_index_any = 0,
    'ALTER TABLE `system_alerts`
       ADD INDEX `idx_system_alert_status` (`status`)',
    IF(
        @system_alert_status_index_exact = 1,
        'SELECT 1',
        'SELECT * FROM `FAIL_CLOSED_SYSTEM_ALERTS_STATUS_INDEX_DRIFT`'
    )
);
PREPARE system_alert_stmt FROM @system_alert_sql;
EXECUTE system_alert_stmt;
DEALLOCATE PREPARE system_alert_stmt;

SET @system_alert_uq_exact = (
    SELECT COUNT(*)
    FROM (
        SELECT INDEX_NAME, NON_UNIQUE
        FROM INFORMATION_SCHEMA.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'system_alerts'
          AND INDEX_NAME = 'uq_alert_case'
        GROUP BY INDEX_NAME, NON_UNIQUE
        HAVING NON_UNIQUE = 0
           AND GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX) =
               'alert_code,case_key'
    ) AS exact_index
);
SET @system_alert_status_index_exact = (
    SELECT COUNT(*)
    FROM (
        SELECT INDEX_NAME, NON_UNIQUE
        FROM INFORMATION_SCHEMA.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'system_alerts'
          AND INDEX_NAME = 'idx_system_alert_status'
        GROUP BY INDEX_NAME, NON_UNIQUE
        HAVING NON_UNIQUE = 1
           AND GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX) = 'status'
    ) AS exact_index
);
SET @system_alert_current_shape_count = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'system_alerts'
      AND (
          (COLUMN_NAME = 'alert_code' AND COLUMN_TYPE = 'varchar(50)'
              AND IS_NULLABLE = 'NO')
          OR (COLUMN_NAME = 'source_domain' AND COLUMN_TYPE = 'varchar(50)'
              AND IS_NULLABLE = 'NO')
          OR (COLUMN_NAME = 'case_key' AND COLUMN_TYPE = 'varchar(100)'
              AND IS_NULLABLE = 'NO')
          OR (COLUMN_NAME = 'reason' AND COLUMN_TYPE = 'varchar(500)'
              AND IS_NULLABLE = 'NO')
          OR (COLUMN_NAME = 'details' AND DATA_TYPE = 'json'
              AND IS_NULLABLE = 'NO')
          OR (COLUMN_NAME = 'status'
              AND COLUMN_TYPE = 'enum(''open'',''claimed'',''resolved'')'
              AND IS_NULLABLE = 'NO' AND COLUMN_DEFAULT = 'open')
          OR (COLUMN_NAME = 'claimed_by' AND COLUMN_TYPE = 'varchar(100)'
              AND IS_NULLABLE = 'YES')
          OR (COLUMN_NAME = 'claimed_at' AND DATA_TYPE = 'datetime'
              AND IS_NULLABLE = 'YES')
          OR (COLUMN_NAME = 'resolved_by' AND COLUMN_TYPE = 'varchar(100)'
              AND IS_NULLABLE = 'YES')
          OR (COLUMN_NAME = 'resolved_at' AND DATA_TYPE = 'datetime'
              AND IS_NULLABLE = 'YES')
          OR (COLUMN_NAME = 'resolution_reason' AND COLUMN_TYPE = 'varchar(500)'
              AND IS_NULLABLE = 'YES')
          OR (COLUMN_NAME = 'created_at' AND DATA_TYPE = 'timestamp')
          OR (COLUMN_NAME = 'updated_at' AND DATA_TYPE = 'timestamp')
      )
);
SET @system_alert_sql = IF(
    @system_alert_current_shape_count = 13
    AND @system_alert_uq_exact = 1
    AND @system_alert_status_index_exact = 1,
    'SELECT 1',
    'SELECT * FROM `FAIL_CLOSED_SYSTEM_ALERTS_CURRENT_SHAPE_INVALID`'
);
PREPARE system_alert_stmt FROM @system_alert_sql;
EXECUTE system_alert_stmt;
DEALLOCATE PREPARE system_alert_stmt;
-- END SOURCE: db/schema_parts/107_system_alert_current_projection.sql

-- BEGIN SOURCE: db/schema_parts/108_matching_records_resume_delivery.sql
-- Add the explicit resume-delivery fact used by resume commands and DOC-SEND-001.
-- Existing matching rows deliberately remain NULL; no delivery is inferred.

SET @matching_resume_table_exists = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'matching_records'
      AND TABLE_TYPE = 'BASE TABLE'
);
SET @matching_resume_required_columns = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'matching_records'
      AND COLUMN_NAME IN (
          'id', 'case_no', 'staff_id', 'caregiver_accepted',
          'sent_at', 'replied_at', 'sent_info_1_at', 'sent_info_2_at'
      )
);
SET @matching_resume_sql = IF(
    @matching_resume_table_exists = 1
    AND @matching_resume_required_columns = 8,
    'SELECT 1',
    'SELECT * FROM `FAIL_CLOSED_MATCHING_RECORDS_PREREQUISITE_INVALID`'
);
PREPARE matching_resume_stmt FROM @matching_resume_sql;
EXECUTE matching_resume_stmt;
DEALLOCATE PREPARE matching_resume_stmt;

SET @matching_resume_column_any = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'matching_records'
      AND COLUMN_NAME = 'sent_resume_at'
);
SET @matching_resume_column_exact = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'matching_records'
      AND COLUMN_NAME = 'sent_resume_at'
      AND DATA_TYPE = 'datetime'
      AND COLUMN_TYPE = 'datetime'
      AND IS_NULLABLE = 'YES'
      AND COLUMN_DEFAULT IS NULL
      AND EXTRA = ''
      AND COALESCE(GENERATION_EXPRESSION, '') = ''
);
SET @matching_resume_sql = IF(
    @matching_resume_column_any = 0,
    'ALTER TABLE `matching_records`
       ADD COLUMN `sent_resume_at` DATETIME NULL
       COMMENT ''履歷發送給客戶的時間；NULL 表示無明確發送事實''
       AFTER `sent_info_2_at`',
    IF(
        @matching_resume_column_any = 1
        AND @matching_resume_column_exact = 1,
        'SELECT 1',
        'SELECT * FROM `FAIL_CLOSED_SENT_RESUME_AT_INVALID_SPEC`'
    )
);
PREPARE matching_resume_stmt FROM @matching_resume_sql;
EXECUTE matching_resume_stmt;
DEALLOCATE PREPARE matching_resume_stmt;

SET @matching_resume_column_exact = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'matching_records'
      AND COLUMN_NAME = 'sent_resume_at'
      AND DATA_TYPE = 'datetime'
      AND COLUMN_TYPE = 'datetime'
      AND IS_NULLABLE = 'YES'
      AND COLUMN_DEFAULT IS NULL
      AND EXTRA = ''
      AND COALESCE(GENERATION_EXPRESSION, '') = ''
);
SET @matching_resume_sql = IF(
    @matching_resume_column_exact = 1,
    'SELECT 1',
    'SELECT * FROM `FAIL_CLOSED_SENT_RESUME_AT_POSTCHECK_FAILED`'
);
PREPARE matching_resume_stmt FROM @matching_resume_sql;
EXECUTE matching_resume_stmt;
DEALLOCATE PREPARE matching_resume_stmt;
-- END SOURCE: db/schema_parts/108_matching_records_resume_delivery.sql

-- BEGIN SOURCE: db/schema_parts/109_scheduling_generations.sql
-- Additive Scheduling generation/effective metadata over the existing
-- case_staff_assignments and staff_schedule SSOT tables.

CREATE TABLE IF NOT EXISTS scheduling_aggregates (
    case_no VARCHAR(50) PRIMARY KEY,
    aggregate_version BIGINT UNSIGNED NOT NULL DEFAULT 0,
    generation_counter INT UNSIGNED NOT NULL DEFAULT 0,
    effective_generation_id BIGINT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_scheduling_aggregate_order
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS scheduling_generations (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    case_no VARCHAR(50) NOT NULL,
    generation_number INT UNSIGNED NOT NULL,
    resulting_aggregate_version BIGINT UNSIGNED NOT NULL,
    status ENUM('preparing', 'effective', 'cancelled') NOT NULL,
    effective_marker TINYINT(1) NULL,
    created_by VARCHAR(100) NOT NULL,
    change_reason VARCHAR(500) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    cancelled_at TIMESTAMP NULL,
    UNIQUE KEY uq_scheduling_generation_identity (id, case_no),
    UNIQUE KEY uq_scheduling_generation_number (case_no, generation_number),
    UNIQUE KEY uq_scheduling_generation_version (
        case_no,
        resulting_aggregate_version
    ),
    UNIQUE KEY uq_scheduling_generation_effective (case_no, effective_marker),
    CONSTRAINT fk_scheduling_generation_order
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_scheduling_generation_number
        CHECK (generation_number > 0),
    CONSTRAINT chk_scheduling_generation_version
        CHECK (resulting_aggregate_version > 0),
    CONSTRAINT chk_scheduling_generation_state
        CHECK (
            (
                status = 'effective'
                AND effective_marker = 1
                AND cancelled_at IS NULL
            )
            OR (
                status = 'preparing'
                AND effective_marker IS NULL
                AND cancelled_at IS NULL
            )
            OR (
                status = 'cancelled'
                AND effective_marker IS NULL
                AND cancelled_at IS NOT NULL
            )
        ),
    CONSTRAINT chk_scheduling_generation_actor
        CHECK (CHAR_LENGTH(TRIM(created_by)) > 0),
    CONSTRAINT chk_scheduling_generation_reason
        CHECK (CHAR_LENGTH(TRIM(change_reason)) > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

ALTER TABLE scheduling_aggregates
    ADD CONSTRAINT fk_scheduling_aggregate_effective_generation
        FOREIGN KEY (effective_generation_id, case_no)
        REFERENCES scheduling_generations(id, case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT;

ALTER TABLE case_staff_assignments
    DROP INDEX uq_case_assignment_sequence,
    ADD COLUMN generation_id BIGINT NULL AFTER case_no,
    ADD COLUMN candidate_key VARCHAR(191) NULL AFTER generation_id,
    ADD UNIQUE KEY uq_case_assignment_candidate (candidate_key),
    ADD UNIQUE KEY uq_case_assignment_generation_sequence (
        generation_id,
        assignment_sequence
    ),
    ADD UNIQUE KEY uq_case_assignment_generation (
        id,
        generation_id
    ),
    ADD UNIQUE KEY uq_case_assignment_generation_staff (
        id,
        generation_id,
        staff_id
    ),
    ADD UNIQUE KEY uq_case_assignment_case_staff (
        id,
        case_no,
        staff_id
    ),
    ADD INDEX idx_case_assignment_case_no (case_no),
    ADD CONSTRAINT fk_case_assignment_generation
        FOREIGN KEY (generation_id) REFERENCES scheduling_generations(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT;

ALTER TABLE staff_schedule
    DROP INDEX ukey_staff_date,
    ADD COLUMN generation_id BIGINT NULL AFTER assignment_id,
    ADD COLUMN effective_marker TINYINT(1) NULL DEFAULT 1 AFTER is_double_pay,
    ADD UNIQUE KEY uq_staff_schedule_effective_date (
        staff_id,
        work_date,
        effective_marker
    ),
    ADD UNIQUE KEY uq_staff_schedule_generation_owner (
        generation_id,
        work_date
    ),
    ADD CONSTRAINT fk_staff_schedule_generation
        FOREIGN KEY (generation_id) REFERENCES scheduling_generations(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT;

CREATE TABLE IF NOT EXISTS scheduling_buffer_days (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    generation_id BIGINT NOT NULL,
    assignment_id BIGINT NOT NULL,
    staff_id INT NOT NULL,
    buffer_date DATE NOT NULL,
    status ENUM('active', 'released', 'cancelled') NOT NULL DEFAULT 'active',
    active_marker TINYINT(1) NULL DEFAULT 1,
    released_by VARCHAR(100) NULL,
    released_at TIMESTAMP NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_scheduling_buffer_assignment_date (
        assignment_id,
        buffer_date
    ),
    UNIQUE KEY uq_scheduling_buffer_staff_date_active (
        staff_id,
        buffer_date,
        active_marker
    ),
    CONSTRAINT fk_scheduling_buffer_generation
        FOREIGN KEY (generation_id) REFERENCES scheduling_generations(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_scheduling_buffer_assignment
        FOREIGN KEY (assignment_id, generation_id, staff_id)
        REFERENCES case_staff_assignments(id, generation_id, staff_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_scheduling_buffer_state
        CHECK (
            (
                status = 'active'
                AND active_marker = 1
                AND released_by IS NULL
                AND released_at IS NULL
            )
            OR (
                status IN ('released', 'cancelled')
                AND active_marker IS NULL
                AND CHAR_LENGTH(TRIM(released_by)) > 0
                AND released_at IS NOT NULL
            )
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS scheduling_effective_occupancy (
    staff_id INT NOT NULL,
    occupancy_date DATE NOT NULL,
    generation_id BIGINT NOT NULL,
    assignment_id BIGINT NOT NULL,
    occupancy_type ENUM('assignment_interval', 'buffer') NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (staff_id, occupancy_date),
    INDEX idx_scheduling_effective_occupancy_generation (generation_id),
    CONSTRAINT fk_scheduling_occupancy_generation
        FOREIGN KEY (generation_id) REFERENCES scheduling_generations(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_scheduling_occupancy_assignment
        FOREIGN KEY (assignment_id, generation_id, staff_id)
        REFERENCES case_staff_assignments(id, generation_id, staff_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS scheduling_rebuild_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    case_no VARCHAR(50) NOT NULL,
    previous_generation_id BIGINT NULL,
    new_generation_id BIGINT NOT NULL,
    expected_order_version BIGINT UNSIGNED NOT NULL,
    expected_scheduling_version BIGINT UNSIGNED NOT NULL,
    resulting_scheduling_version BIGINT UNSIGNED NOT NULL,
    preview_fingerprint CHAR(64) NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    actor VARCHAR(100) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_scheduling_rebuild_idempotency (idempotency_key),
    UNIQUE KEY uq_scheduling_rebuild_generation (
        id,
        new_generation_id
    ),
    CONSTRAINT fk_scheduling_rebuild_order
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_scheduling_rebuild_previous_generation
        FOREIGN KEY (previous_generation_id, case_no)
        REFERENCES scheduling_generations(id, case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_scheduling_rebuild_new_generation
        FOREIGN KEY (new_generation_id, case_no)
        REFERENCES scheduling_generations(id, case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_scheduling_rebuild_version
        CHECK (
            resulting_scheduling_version = expected_scheduling_version + 1
        ),
    CONSTRAINT chk_scheduling_rebuild_fingerprint
        CHECK (preview_fingerprint REGEXP '^[0-9a-f]{64}$')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS scheduling_rebuild_lineage (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    rebuild_event_id BIGINT NOT NULL,
    old_assignment_identity VARCHAR(191) NOT NULL,
    new_assignment_id BIGINT NOT NULL,
    new_generation_id BIGINT NOT NULL,
    lineage_ordinal INT UNSIGNED NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_scheduling_rebuild_lineage (
        rebuild_event_id,
        old_assignment_identity,
        new_assignment_id
    ),
    UNIQUE KEY uq_scheduling_rebuild_lineage_ordinal (
        rebuild_event_id,
        lineage_ordinal
    ),
    CONSTRAINT fk_scheduling_rebuild_lineage_event
        FOREIGN KEY (rebuild_event_id, new_generation_id)
        REFERENCES scheduling_rebuild_events(id, new_generation_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_scheduling_rebuild_lineage_assignment
        FOREIGN KEY (new_assignment_id, new_generation_id)
        REFERENCES case_staff_assignments(id, generation_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS scheduling_command_receipts (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    idempotency_key VARCHAR(191) NOT NULL,
    command_family VARCHAR(100) NOT NULL,
    command_fingerprint CHAR(64) NOT NULL,
    preview_fingerprint CHAR(64) NOT NULL,
    case_no VARCHAR(50) NOT NULL,
    expected_scheduling_version BIGINT UNSIGNED NOT NULL,
    resulting_scheduling_version BIGINT UNSIGNED NOT NULL,
    resulting_generation_id BIGINT NOT NULL,
    rebuild_event_id BIGINT NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    result_snapshot JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_scheduling_command_receipt_key (idempotency_key),
    CONSTRAINT fk_scheduling_receipt_order
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_scheduling_receipt_generation
        FOREIGN KEY (resulting_generation_id, case_no)
        REFERENCES scheduling_generations(id, case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_scheduling_receipt_rebuild
        FOREIGN KEY (rebuild_event_id) REFERENCES scheduling_rebuild_events(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_scheduling_receipt_version
        CHECK (
            resulting_scheduling_version = expected_scheduling_version + 1
        ),
    CONSTRAINT chk_scheduling_receipt_fingerprints
        CHECK (
            command_fingerprint REGEXP '^[0-9a-f]{64}$'
            AND preview_fingerprint REGEXP '^[0-9a-f]{64}$'
        ),
    CONSTRAINT chk_scheduling_receipt_snapshot
        CHECK (JSON_TYPE(result_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS scheduling_bootstrap_review_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    case_no VARCHAR(50) NOT NULL,
    issue_code VARCHAR(32) NOT NULL,
    migration_identity VARCHAR(100) NOT NULL,
    evidence_snapshot JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_scheduling_bootstrap_review_issue (
        case_no,
        issue_code,
        migration_identity
    ),
    CONSTRAINT fk_scheduling_bootstrap_review_order
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_scheduling_bootstrap_review_code
        CHECK (issue_code REGEXP '^SCHED-BOOT-[0-9]{3}$'),
    CONSTRAINT chk_scheduling_bootstrap_review_migration
        CHECK (CHAR_LENGTH(TRIM(migration_identity)) > 0),
    CONSTRAINT chk_scheduling_bootstrap_review_evidence
        CHECK (JSON_TYPE(evidence_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_scheduling_rebuild_events_before_update;
CREATE TRIGGER trg_scheduling_rebuild_events_before_update
BEFORE UPDATE ON scheduling_rebuild_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'scheduling_rebuild_events records cannot be updated';

DROP TRIGGER IF EXISTS trg_scheduling_rebuild_events_before_delete;
CREATE TRIGGER trg_scheduling_rebuild_events_before_delete
BEFORE DELETE ON scheduling_rebuild_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'scheduling_rebuild_events records cannot be deleted';

DROP TRIGGER IF EXISTS trg_scheduling_rebuild_lineage_before_update;
CREATE TRIGGER trg_scheduling_rebuild_lineage_before_update
BEFORE UPDATE ON scheduling_rebuild_lineage
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'scheduling_rebuild_lineage records cannot be updated';

DROP TRIGGER IF EXISTS trg_scheduling_rebuild_lineage_before_delete;
CREATE TRIGGER trg_scheduling_rebuild_lineage_before_delete
BEFORE DELETE ON scheduling_rebuild_lineage
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'scheduling_rebuild_lineage records cannot be deleted';

DROP TRIGGER IF EXISTS trg_scheduling_command_receipts_before_update;
CREATE TRIGGER trg_scheduling_command_receipts_before_update
BEFORE UPDATE ON scheduling_command_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'scheduling_command_receipts records cannot be updated';

DROP TRIGGER IF EXISTS trg_scheduling_command_receipts_before_delete;
CREATE TRIGGER trg_scheduling_command_receipts_before_delete
BEFORE DELETE ON scheduling_command_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'scheduling_command_receipts records cannot be deleted';

DROP TRIGGER IF EXISTS trg_scheduling_bootstrap_review_events_before_update;
CREATE TRIGGER trg_scheduling_bootstrap_review_events_before_update
BEFORE UPDATE ON scheduling_bootstrap_review_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'scheduling_bootstrap_review_events records cannot be updated';

DROP TRIGGER IF EXISTS trg_scheduling_bootstrap_review_events_before_delete;
CREATE TRIGGER trg_scheduling_bootstrap_review_events_before_delete
BEFORE DELETE ON scheduling_bootstrap_review_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'scheduling_bootstrap_review_events records cannot be deleted';
-- END SOURCE: db/schema_parts/109_scheduling_generations.sql

-- BEGIN SOURCE: db/schema_parts/110_order_terms_workflow.sql
-- Additive Orders Terms, contract-flow, and irreversible service-lock facts.

ALTER TABLE orders
    ADD COLUMN staff_payment_due_date DATE NULL AFTER actual_end_date;

ALTER TABLE order_lifecycle_state_events
    ADD UNIQUE KEY uq_order_lifecycle_state_event_case_identity (
        id,
        case_no
    );

CREATE TABLE IF NOT EXISTS order_contract_flow_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    case_no VARCHAR(50) NOT NULL,
    contract_identity VARCHAR(191) NOT NULL,
    event_type ENUM('contract_completed') NOT NULL,
    actor VARCHAR(100) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_order_contract_completed_case (case_no, event_type),
    UNIQUE KEY uq_order_contract_event_idempotency (idempotency_key),
    CONSTRAINT fk_order_contract_event_order
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_order_contract_event_text
        CHECK (
            CHAR_LENGTH(TRIM(contract_identity)) > 0
            AND CHAR_LENGTH(TRIM(actor)) > 0
            AND CHAR_LENGTH(TRIM(reason)) > 0
            AND CHAR_LENGTH(TRIM(idempotency_key)) > 0
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS order_service_data_locks (
    case_no VARCHAR(50) PRIMARY KEY,
    lifecycle_event_id BIGINT UNSIGNED NOT NULL,
    client_settlement_fingerprint CHAR(64) NOT NULL,
    created_by VARCHAR(100) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_order_service_data_lock_order
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_order_service_data_lock_lifecycle_event
        FOREIGN KEY (lifecycle_event_id, case_no)
        REFERENCES order_lifecycle_state_events(id, case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_order_service_data_lock_fingerprint
        CHECK (client_settlement_fingerprint REGEXP '^[0-9a-f]{64}$'),
    CONSTRAINT chk_order_service_data_lock_actor
        CHECK (CHAR_LENGTH(TRIM(created_by)) > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS order_terms_change_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    case_no VARCHAR(50) NOT NULL,
    expected_order_version BIGINT UNSIGNED NOT NULL,
    resulting_order_version BIGINT UNSIGNED NOT NULL,
    preview_fingerprint CHAR(64) NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    actor VARCHAR(100) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    before_terms JSON NOT NULL,
    after_terms JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_order_terms_change_idempotency (idempotency_key),
    CONSTRAINT fk_order_terms_change_order
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_order_terms_change_version
        CHECK (resulting_order_version = expected_order_version + 1),
    CONSTRAINT chk_order_terms_change_fingerprint
        CHECK (preview_fingerprint REGEXP '^[0-9a-f]{64}$'),
    CONSTRAINT chk_order_terms_change_snapshots
        CHECK (
            JSON_TYPE(before_terms) = 'OBJECT'
            AND JSON_TYPE(after_terms) = 'OBJECT'
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS orders_domain_outbox (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    case_no VARCHAR(50) NOT NULL,
    lifecycle_event_id BIGINT UNSIGNED NOT NULL,
    intent_key VARCHAR(191) NOT NULL,
    intent_type ENUM(
        'lifecycle_projection_changed',
        'service_data_locked',
        'anomaly_root_changed'
    ) NOT NULL,
    payload_snapshot JSON NOT NULL,
    status ENUM('pending', 'processing', 'delivered', 'failed')
        NOT NULL DEFAULT 'pending',
    attempt_count INT UNSIGNED NOT NULL DEFAULT 0,
    next_attempt_at DATETIME NULL,
    delivered_at DATETIME NULL,
    last_error VARCHAR(1000) NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_orders_domain_outbox_intent (intent_key),
    INDEX idx_orders_domain_outbox_delivery (
        status,
        next_attempt_at,
        id
    ),
    CONSTRAINT fk_orders_domain_outbox_order
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_orders_domain_outbox_lifecycle
        FOREIGN KEY (lifecycle_event_id, case_no)
        REFERENCES order_lifecycle_state_events(id, case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_orders_domain_outbox_payload
        CHECK (JSON_TYPE(payload_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS order_terms_apply_receipts (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    idempotency_key VARCHAR(191) NOT NULL,
    command_fingerprint CHAR(64) NOT NULL,
    preview_fingerprint CHAR(64) NOT NULL,
    case_no VARCHAR(50) NOT NULL,
    order_terms_event_id BIGINT NOT NULL,
    scheduling_command_receipt_id BIGINT NOT NULL,
    lifecycle_event_id BIGINT UNSIGNED NOT NULL,
    order_version BIGINT UNSIGNED NOT NULL,
    scheduling_version BIGINT UNSIGNED NOT NULL,
    scheduling_generation INT UNSIGNED NOT NULL,
    client_finance_version BIGINT UNSIGNED NOT NULL,
    payroll_version BIGINT UNSIGNED NOT NULL,
    lifecycle_status ENUM(
        '洽談中',
        '訂單成立',
        '服務中',
        '訂單完成',
        '訂單取消'
    ) NOT NULL,
    service_data_lock_formed TINYINT(1) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    result_snapshot JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_order_terms_receipt_key (idempotency_key),
    CONSTRAINT fk_order_terms_receipt_order
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_order_terms_receipt_event
        FOREIGN KEY (order_terms_event_id)
        REFERENCES order_terms_change_events(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_order_terms_receipt_scheduling
        FOREIGN KEY (scheduling_command_receipt_id)
        REFERENCES scheduling_command_receipts(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_order_terms_receipt_lifecycle
        FOREIGN KEY (lifecycle_event_id, case_no)
        REFERENCES order_lifecycle_state_events(id, case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_order_terms_receipt_fingerprints
        CHECK (
            command_fingerprint REGEXP '^[0-9a-f]{64}$'
            AND preview_fingerprint REGEXP '^[0-9a-f]{64}$'
        ),
    CONSTRAINT chk_order_terms_receipt_snapshot
        CHECK (JSON_TYPE(result_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_order_contract_flow_events_before_update;
CREATE TRIGGER trg_order_contract_flow_events_before_update
BEFORE UPDATE ON order_contract_flow_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'order_contract_flow_events records cannot be updated';

DROP TRIGGER IF EXISTS trg_order_contract_flow_events_before_delete;
CREATE TRIGGER trg_order_contract_flow_events_before_delete
BEFORE DELETE ON order_contract_flow_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'order_contract_flow_events records cannot be deleted';

DROP TRIGGER IF EXISTS trg_order_service_data_locks_before_update;
CREATE TRIGGER trg_order_service_data_locks_before_update
BEFORE UPDATE ON order_service_data_locks
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'order_service_data_locks records cannot be updated';

DROP TRIGGER IF EXISTS trg_order_service_data_locks_before_delete;
CREATE TRIGGER trg_order_service_data_locks_before_delete
BEFORE DELETE ON order_service_data_locks
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'order_service_data_locks records cannot be deleted';

DROP TRIGGER IF EXISTS trg_order_terms_change_events_before_update;
CREATE TRIGGER trg_order_terms_change_events_before_update
BEFORE UPDATE ON order_terms_change_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'order_terms_change_events records cannot be updated';

DROP TRIGGER IF EXISTS trg_order_terms_change_events_before_delete;
CREATE TRIGGER trg_order_terms_change_events_before_delete
BEFORE DELETE ON order_terms_change_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'order_terms_change_events records cannot be deleted';

DROP TRIGGER IF EXISTS trg_order_terms_apply_receipts_before_update;
CREATE TRIGGER trg_order_terms_apply_receipts_before_update
BEFORE UPDATE ON order_terms_apply_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'order_terms_apply_receipts records cannot be updated';

DROP TRIGGER IF EXISTS trg_order_terms_apply_receipts_before_delete;
CREATE TRIGGER trg_order_terms_apply_receipts_before_delete
BEFORE DELETE ON order_terms_apply_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'order_terms_apply_receipts records cannot be deleted';
-- END SOURCE: db/schema_parts/110_order_terms_workflow.sql

-- BEGIN SOURCE: db/schema_parts/111_client_finance_ledger.sql
-- Additive Client Finance obligation, immutable ledger, and M:N allocation SSOT.

CREATE TABLE IF NOT EXISTS client_finance_accounts (
    case_no VARCHAR(50) PRIMARY KEY,
    aggregate_version BIGINT UNSIGNED NOT NULL DEFAULT 0,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_client_finance_account_order
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS client_payment_terms_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    case_no VARCHAR(50) NOT NULL,
    policy_version VARCHAR(100) NOT NULL,
    client_hourly_rate_ntd BIGINT NOT NULL,
    deposit_service_days INT UNSIGNED NOT NULL,
    deposit_due_date DATE NOT NULL,
    first_payment_due_date DATE NOT NULL,
    second_payment_due_date DATE NULL,
    expected_account_version BIGINT UNSIGNED NOT NULL,
    source_event_identity VARCHAR(191) NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    actor VARCHAR(100) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_client_payment_terms_source (
        case_no,
        source_event_identity
    ),
    UNIQUE KEY uq_client_payment_terms_idempotency (idempotency_key),
    CONSTRAINT fk_client_payment_terms_event_order
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_client_payment_terms_event_values
        CHECK (
            client_hourly_rate_ntd > 0
            AND CHAR_LENGTH(TRIM(policy_version)) > 0
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS client_payment_terms (
    case_no VARCHAR(50) PRIMARY KEY,
    policy_version VARCHAR(100) NOT NULL,
    client_hourly_rate_ntd BIGINT NOT NULL,
    deposit_service_days INT UNSIGNED NOT NULL,
    deposit_due_date DATE NOT NULL,
    first_payment_due_date DATE NOT NULL,
    second_payment_due_date DATE NULL,
    current_event_id BIGINT NOT NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_client_payment_terms_current_event (current_event_id),
    CONSTRAINT fk_client_payment_terms_order
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_client_payment_terms_current_event
        FOREIGN KEY (current_event_id) REFERENCES client_payment_terms_events(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_client_payment_terms_values
        CHECK (
            client_hourly_rate_ntd > 0
            AND CHAR_LENGTH(TRIM(policy_version)) > 0
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS client_obligation_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    obligation_identity VARCHAR(191) NOT NULL,
    case_no VARCHAR(50) NOT NULL,
    obligation_type ENUM(
        'deposit',
        'first',
        'second',
        'refund',
        'subsidy_return',
        'adjustment'
    ) NOT NULL,
    direction ENUM(
        'receivable_from_client',
        'payable_to_client'
    ) NOT NULL,
    event_type ENUM(
        'established',
        'recalculated',
        'adjusted',
        'reversed'
    ) NOT NULL,
    before_amount_ntd BIGINT NOT NULL,
    after_amount_ntd BIGINT NOT NULL,
    before_due_date DATE NULL,
    after_due_date DATE NULL,
    source_event_identity VARCHAR(191) NOT NULL,
    source_obligation_identity VARCHAR(191) NULL,
    expected_account_version BIGINT UNSIGNED NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    actor VARCHAR(100) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_client_obligation_event_idempotency (idempotency_key),
    UNIQUE KEY uq_client_obligation_source_event (
        obligation_identity,
        source_event_identity
    ),
    INDEX idx_client_obligation_event_case_type (
        case_no,
        obligation_type,
        created_at
    ),
    CONSTRAINT fk_client_obligation_event_order
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_client_obligation_event_amount
        CHECK (
            before_amount_ntd >= 0
            AND after_amount_ntd >= 0
            AND (
                before_amount_ntd <> after_amount_ntd
                OR NOT (before_due_date <=> after_due_date)
            )
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS client_obligations (
    obligation_identity VARCHAR(191) PRIMARY KEY,
    case_no VARCHAR(50) NOT NULL,
    obligation_type ENUM(
        'deposit',
        'first',
        'second',
        'refund',
        'subsidy_return',
        'adjustment'
    ) NOT NULL,
    direction ENUM(
        'receivable_from_client',
        'payable_to_client'
    ) NOT NULL,
    source_obligation_identity VARCHAR(191) NULL,
    amount_due_ntd BIGINT NOT NULL,
    due_date DATE NULL,
    status ENUM('open', 'settled', 'cancelled') NOT NULL,
    current_event_id BIGINT NOT NULL,
    projection_version BIGINT UNSIGNED NOT NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_client_obligation_case_identity (
        obligation_identity,
        case_no
    ),
    INDEX idx_client_obligation_case_status (
        case_no,
        status,
        obligation_type
    ),
    CONSTRAINT fk_client_obligation_order
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_client_obligation_current_event
        FOREIGN KEY (current_event_id) REFERENCES client_obligation_events(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_client_obligation_amount
        CHECK (amount_due_ntd >= 0),
    CONSTRAINT chk_client_obligation_state
        CHECK (
            (status = 'open' AND amount_due_ntd > 0)
            OR (status IN ('settled', 'cancelled') AND amount_due_ntd = 0)
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

ALTER TABLE client_obligation_events
    ADD CONSTRAINT fk_client_obligation_event_source
        FOREIGN KEY (source_obligation_identity, case_no)
        REFERENCES client_obligations(obligation_identity, case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT;

ALTER TABLE client_obligations
    ADD CONSTRAINT fk_client_obligation_source
        FOREIGN KEY (source_obligation_identity, case_no)
        REFERENCES client_obligations(obligation_identity, case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT;

CREATE TABLE IF NOT EXISTS client_ledger_entries (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    case_no VARCHAR(50) NOT NULL,
    finance_import_row_id BIGINT NULL,
    entry_type ENUM(
        'receipt',
        'refund',
        'adjustment',
        'reversal'
    ) NOT NULL,
    amount_ntd BIGINT NOT NULL,
    occurred_on DATE NOT NULL,
    reconciliation_reference VARCHAR(191) NOT NULL,
    reversal_of_entry_id BIGINT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    actor VARCHAR(100) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_client_ledger_import_row (finance_import_row_id),
    UNIQUE KEY uq_client_ledger_idempotency (idempotency_key),
    INDEX idx_client_ledger_case_date (case_no, occurred_on, id),
    CONSTRAINT fk_client_ledger_order
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_client_ledger_import_row
        FOREIGN KEY (finance_import_row_id) REFERENCES finance_import_rows(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_client_ledger_reversal
        FOREIGN KEY (reversal_of_entry_id) REFERENCES client_ledger_entries(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_client_ledger_amount
        CHECK (amount_ntd > 0),
    CONSTRAINT chk_client_ledger_reversal_shape
        CHECK (
            (entry_type = 'reversal' AND reversal_of_entry_id IS NOT NULL)
            OR (entry_type <> 'reversal' AND reversal_of_entry_id IS NULL)
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS client_ledger_obligation_allocations (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    ledger_entry_id BIGINT NOT NULL,
    obligation_identity VARCHAR(191) NOT NULL,
    amount_ntd BIGINT NOT NULL,
    allocation_ordinal INT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_client_ledger_obligation_allocation (
        ledger_entry_id,
        obligation_identity
    ),
    UNIQUE KEY uq_client_ledger_allocation_ordinal (
        ledger_entry_id,
        allocation_ordinal
    ),
    INDEX idx_client_allocation_obligation (
        obligation_identity,
        ledger_entry_id
    ),
    CONSTRAINT fk_client_allocation_ledger
        FOREIGN KEY (ledger_entry_id) REFERENCES client_ledger_entries(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_client_allocation_obligation
        FOREIGN KEY (obligation_identity)
        REFERENCES client_obligations(obligation_identity)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_client_allocation_amount
        CHECK (amount_ntd > 0),
    CONSTRAINT chk_client_allocation_ordinal
        CHECK (allocation_ordinal > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS client_finance_apply_receipts (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    idempotency_key VARCHAR(191) NOT NULL,
    command_fingerprint CHAR(64) NOT NULL,
    preview_fingerprint CHAR(64) NOT NULL,
    case_no VARCHAR(50) NOT NULL,
    resulting_account_version BIGINT UNSIGNED NOT NULL,
    result_snapshot JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_client_finance_receipt_key (idempotency_key),
    CONSTRAINT fk_client_finance_receipt_order
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_client_finance_receipt_fingerprints
        CHECK (
            command_fingerprint REGEXP '^[0-9a-f]{64}$'
            AND preview_fingerprint REGEXP '^[0-9a-f]{64}$'
        ),
    CONSTRAINT chk_client_finance_receipt_snapshot
        CHECK (JSON_TYPE(result_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS client_finance_outbox (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    case_no VARCHAR(50) NOT NULL,
    intent_type ENUM(
        'orders_deposit_reconciled',
        'orders_deposit_reversed',
        'anomaly_review_required',
        'projection_refresh'
    ) NOT NULL,
    intent_key VARCHAR(191) NOT NULL,
    payload_snapshot JSON NOT NULL,
    status ENUM('pending', 'processing', 'delivered', 'failed')
        NOT NULL DEFAULT 'pending',
    attempt_count INT UNSIGNED NOT NULL DEFAULT 0,
    next_attempt_at DATETIME NULL,
    delivered_at DATETIME NULL,
    last_error VARCHAR(1000) NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_client_finance_outbox_intent (intent_key),
    INDEX idx_client_finance_outbox_delivery (
        status,
        next_attempt_at,
        id
    ),
    CONSTRAINT fk_client_finance_outbox_order
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_client_finance_outbox_payload
        CHECK (JSON_TYPE(payload_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_client_obligation_events_before_update;
CREATE TRIGGER trg_client_obligation_events_before_update
BEFORE UPDATE ON client_obligation_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client_obligation_events records cannot be updated';

DROP TRIGGER IF EXISTS trg_client_obligation_events_before_delete;
CREATE TRIGGER trg_client_obligation_events_before_delete
BEFORE DELETE ON client_obligation_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client_obligation_events records cannot be deleted';

DROP TRIGGER IF EXISTS trg_client_payment_terms_events_before_update;
CREATE TRIGGER trg_client_payment_terms_events_before_update
BEFORE UPDATE ON client_payment_terms_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client_payment_terms_events records cannot be updated';

DROP TRIGGER IF EXISTS trg_client_payment_terms_events_before_delete;
CREATE TRIGGER trg_client_payment_terms_events_before_delete
BEFORE DELETE ON client_payment_terms_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client_payment_terms_events records cannot be deleted';

DROP TRIGGER IF EXISTS trg_client_ledger_entries_before_update;
CREATE TRIGGER trg_client_ledger_entries_before_update
BEFORE UPDATE ON client_ledger_entries
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client_ledger_entries records cannot be updated';

DROP TRIGGER IF EXISTS trg_client_ledger_entries_before_delete;
CREATE TRIGGER trg_client_ledger_entries_before_delete
BEFORE DELETE ON client_ledger_entries
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client_ledger_entries records cannot be deleted';

DROP TRIGGER IF EXISTS trg_client_ledger_allocations_before_update;
CREATE TRIGGER trg_client_ledger_allocations_before_update
BEFORE UPDATE ON client_ledger_obligation_allocations
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client ledger allocations cannot be updated';

DROP TRIGGER IF EXISTS trg_client_ledger_allocations_before_delete;
CREATE TRIGGER trg_client_ledger_allocations_before_delete
BEFORE DELETE ON client_ledger_obligation_allocations
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client ledger allocations cannot be deleted';

DROP TRIGGER IF EXISTS trg_client_finance_receipts_before_update;
CREATE TRIGGER trg_client_finance_receipts_before_update
BEFORE UPDATE ON client_finance_apply_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client_finance_apply_receipts records cannot be updated';

DROP TRIGGER IF EXISTS trg_client_finance_receipts_before_delete;
CREATE TRIGGER trg_client_finance_receipts_before_delete
BEFORE DELETE ON client_finance_apply_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client_finance_apply_receipts records cannot be deleted';
-- END SOURCE: db/schema_parts/111_client_finance_ledger.sql

-- BEGIN SOURCE: db/schema_parts/112_payroll_obligations.sql
-- Additive Payroll rate snapshots, special-pay, and staff obligation SSOT.

CREATE TABLE IF NOT EXISTS payroll_case_accounts (
    case_no VARCHAR(50) PRIMARY KEY,
    aggregate_version BIGINT UNSIGNED NOT NULL DEFAULT 0,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_payroll_case_account_order
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS payroll_rate_policies (
    policy_version VARCHAR(100) NOT NULL,
    policy_kind ENUM(
        'citizen',
        'subsidized_citizen',
        'non_citizen'
    ) NOT NULL,
    hourly_rate_ntd BIGINT NOT NULL,
    effective_from DATE NOT NULL,
    effective_until DATE NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (policy_version, policy_kind),
    CONSTRAINT chk_payroll_rate_policy_amount
        CHECK (hourly_rate_ntd > 0),
    CONSTRAINT chk_payroll_rate_policy_interval
        CHECK (
            effective_until IS NULL
            OR effective_until >= effective_from
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS assignment_payroll_rate_snapshots (
    assignment_id BIGINT PRIMARY KEY,
    policy_version VARCHAR(100) NOT NULL,
    policy_kind ENUM(
        'citizen',
        'subsidized_citizen',
        'non_citizen'
    ) NOT NULL,
    hourly_rate_ntd BIGINT NOT NULL,
    source_identity_status VARCHAR(100) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_assignment_payroll_rate_assignment
        FOREIGN KEY (assignment_id)
        REFERENCES case_staff_assignments(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_assignment_payroll_rate_policy
        FOREIGN KEY (policy_version, policy_kind)
        REFERENCES payroll_rate_policies(policy_version, policy_kind)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_assignment_payroll_rate_amount
        CHECK (hourly_rate_ntd > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS payroll_special_pay_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    assignment_id BIGINT NOT NULL,
    service_date DATE NOT NULL,
    event_type ENUM('double_pay') NOT NULL,
    source_event_identity VARCHAR(191) NOT NULL,
    actor VARCHAR(100) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_payroll_special_pay_assignment_date (
        assignment_id,
        service_date,
        event_type
    ),
    UNIQUE KEY uq_payroll_special_pay_idempotency (idempotency_key),
    CONSTRAINT fk_payroll_special_pay_assignment
        FOREIGN KEY (assignment_id)
        REFERENCES case_staff_assignments(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS payroll_adjustment_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    case_no VARCHAR(50) NOT NULL,
    adjustment_identity VARCHAR(191) NOT NULL,
    amount_ntd BIGINT NOT NULL,
    source_event_identity VARCHAR(191) NOT NULL,
    actor VARCHAR(100) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_payroll_adjustment_identity (adjustment_identity),
    UNIQUE KEY uq_payroll_adjustment_idempotency (idempotency_key),
    CONSTRAINT fk_payroll_adjustment_order
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_payroll_adjustment_nonzero
        CHECK (amount_ntd <> 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS payroll_adjustment_allocations (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    adjustment_event_id BIGINT NOT NULL,
    assignment_id BIGINT NOT NULL,
    amount_ntd BIGINT NOT NULL,
    allocation_ordinal INT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_payroll_adjustment_assignment (
        adjustment_event_id,
        assignment_id
    ),
    UNIQUE KEY uq_payroll_adjustment_ordinal (
        adjustment_event_id,
        allocation_ordinal
    ),
    CONSTRAINT fk_payroll_adjustment_allocation_event
        FOREIGN KEY (adjustment_event_id) REFERENCES payroll_adjustment_events(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_payroll_adjustment_allocation_assignment
        FOREIGN KEY (assignment_id)
        REFERENCES case_staff_assignments(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_payroll_adjustment_allocation_nonzero
        CHECK (amount_ntd <> 0),
    CONSTRAINT chk_payroll_adjustment_allocation_ordinal
        CHECK (allocation_ordinal > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS staff_obligation_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    obligation_identity VARCHAR(191) NOT NULL,
    assignment_id BIGINT NOT NULL,
    case_no VARCHAR(50) NOT NULL,
    staff_id INT NOT NULL,
    obligation_kind ENUM(
        'service_pay',
        'adjustment',
        'reversal'
    ) NOT NULL,
    direction ENUM(
        'payable_to_staff',
        'receivable_from_staff'
    ) NOT NULL,
    source_obligation_identity VARCHAR(191) NULL,
    event_type ENUM(
        'established',
        'rebuilt',
        'adjustment',
        'reversal'
    ) NOT NULL,
    before_amount_ntd BIGINT NOT NULL,
    after_amount_ntd BIGINT NOT NULL,
    due_date DATE NULL,
    payroll_fingerprint CHAR(64) NOT NULL,
    expected_payroll_version BIGINT UNSIGNED NOT NULL,
    resulting_payroll_version BIGINT UNSIGNED NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    actor VARCHAR(100) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_staff_obligation_event_idempotency (idempotency_key),
    INDEX idx_staff_obligation_event_identity (
        obligation_identity,
        created_at
    ),
    CONSTRAINT fk_staff_obligation_event_owner
        FOREIGN KEY (assignment_id, case_no, staff_id)
        REFERENCES case_staff_assignments(id, case_no, staff_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_staff_obligation_event_amount
        CHECK (
            before_amount_ntd >= 0
            AND after_amount_ntd >= 0
            AND before_amount_ntd <> after_amount_ntd
        ),
    CONSTRAINT chk_staff_obligation_event_fingerprint
        CHECK (payroll_fingerprint REGEXP '^[0-9a-f]{64}$'),
    CONSTRAINT chk_staff_obligation_event_version
        CHECK (resulting_payroll_version = expected_payroll_version + 1)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS staff_obligations (
    obligation_identity VARCHAR(191) PRIMARY KEY,
    assignment_id BIGINT NOT NULL,
    case_no VARCHAR(50) NOT NULL,
    staff_id INT NOT NULL,
    obligation_kind ENUM(
        'service_pay',
        'adjustment',
        'reversal'
    ) NOT NULL,
    direction ENUM(
        'payable_to_staff',
        'receivable_from_staff'
    ) NOT NULL,
    source_obligation_identity VARCHAR(191) NULL,
    amount_due_ntd BIGINT NOT NULL,
    due_date DATE NULL,
    status ENUM('open', 'settled', 'cancelled') NOT NULL,
    current_event_id BIGINT NOT NULL,
    payroll_version BIGINT UNSIGNED NOT NULL,
    payout_history_exists TINYINT(1) NOT NULL DEFAULT 0,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_staff_obligation_case_identity (
        obligation_identity,
        case_no
    ),
    INDEX idx_staff_obligation_assignment (assignment_id),
    INDEX idx_staff_obligation_staff_due (
        staff_id,
        due_date,
        obligation_identity
    ),
    CONSTRAINT fk_staff_obligation_owner
        FOREIGN KEY (assignment_id, case_no, staff_id)
        REFERENCES case_staff_assignments(id, case_no, staff_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_staff_obligation_current_event
        FOREIGN KEY (current_event_id) REFERENCES staff_obligation_events(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_staff_obligation_state
        CHECK (
            (status = 'open' AND amount_due_ntd > 0)
            OR (
                status IN ('settled', 'cancelled')
                AND amount_due_ntd = 0
            )
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

ALTER TABLE staff_obligation_events
    ADD CONSTRAINT fk_staff_obligation_event_source
        FOREIGN KEY (source_obligation_identity, case_no)
        REFERENCES staff_obligations(obligation_identity, case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT;

ALTER TABLE staff_obligations
    ADD CONSTRAINT fk_staff_obligation_source
        FOREIGN KEY (source_obligation_identity, case_no)
        REFERENCES staff_obligations(obligation_identity, case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT;

CREATE TABLE IF NOT EXISTS payroll_apply_receipts (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    idempotency_key VARCHAR(191) NOT NULL,
    command_fingerprint CHAR(64) NOT NULL,
    preview_fingerprint CHAR(64) NOT NULL,
    case_no VARCHAR(50) NOT NULL,
    resulting_payroll_version BIGINT UNSIGNED NOT NULL,
    result_snapshot JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_payroll_receipt_idempotency (idempotency_key),
    CONSTRAINT fk_payroll_receipt_order
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_payroll_receipt_fingerprint
        CHECK (
            command_fingerprint REGEXP '^[0-9a-f]{64}$'
            AND preview_fingerprint REGEXP '^[0-9a-f]{64}$'
        ),
    CONSTRAINT chk_payroll_receipt_snapshot
        CHECK (JSON_TYPE(result_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS payroll_outbox (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    case_no VARCHAR(50) NOT NULL,
    intent_key VARCHAR(191) NOT NULL,
    intent_type ENUM(
        'staff_obligation_changed',
        'payroll_anomaly_required'
    ) NOT NULL,
    payload_snapshot JSON NOT NULL,
    status ENUM('pending', 'processing', 'delivered', 'failed')
        NOT NULL DEFAULT 'pending',
    attempt_count INT UNSIGNED NOT NULL DEFAULT 0,
    next_attempt_at DATETIME NULL,
    delivered_at DATETIME NULL,
    last_error VARCHAR(1000) NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_payroll_outbox_intent (intent_key),
    INDEX idx_payroll_outbox_delivery (status, next_attempt_at, id),
    CONSTRAINT fk_payroll_outbox_order
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_payroll_outbox_payload
        CHECK (JSON_TYPE(payload_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_payroll_special_pay_events_before_update;
CREATE TRIGGER trg_payroll_special_pay_events_before_update
BEFORE UPDATE ON payroll_special_pay_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'payroll_special_pay_events records cannot be updated';

DROP TRIGGER IF EXISTS trg_payroll_special_pay_events_before_delete;
CREATE TRIGGER trg_payroll_special_pay_events_before_delete
BEFORE DELETE ON payroll_special_pay_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'payroll_special_pay_events records cannot be deleted';

DROP TRIGGER IF EXISTS trg_payroll_adjustment_events_before_update;
CREATE TRIGGER trg_payroll_adjustment_events_before_update
BEFORE UPDATE ON payroll_adjustment_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'payroll_adjustment_events records cannot be updated';

DROP TRIGGER IF EXISTS trg_payroll_adjustment_events_before_delete;
CREATE TRIGGER trg_payroll_adjustment_events_before_delete
BEFORE DELETE ON payroll_adjustment_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'payroll_adjustment_events records cannot be deleted';

DROP TRIGGER IF EXISTS trg_payroll_adjustment_allocations_before_update;
CREATE TRIGGER trg_payroll_adjustment_allocations_before_update
BEFORE UPDATE ON payroll_adjustment_allocations
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'payroll_adjustment_allocations records cannot be updated';

DROP TRIGGER IF EXISTS trg_payroll_adjustment_allocations_before_delete;
CREATE TRIGGER trg_payroll_adjustment_allocations_before_delete
BEFORE DELETE ON payroll_adjustment_allocations
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'payroll_adjustment_allocations records cannot be deleted';

DROP TRIGGER IF EXISTS trg_staff_obligation_events_before_update;
CREATE TRIGGER trg_staff_obligation_events_before_update
BEFORE UPDATE ON staff_obligation_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'staff_obligation_events records cannot be updated';

DROP TRIGGER IF EXISTS trg_staff_obligation_events_before_delete;
CREATE TRIGGER trg_staff_obligation_events_before_delete
BEFORE DELETE ON staff_obligation_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'staff_obligation_events records cannot be deleted';

DROP TRIGGER IF EXISTS trg_payroll_apply_receipts_before_update;
CREATE TRIGGER trg_payroll_apply_receipts_before_update
BEFORE UPDATE ON payroll_apply_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'payroll_apply_receipts records cannot be updated';

DROP TRIGGER IF EXISTS trg_payroll_apply_receipts_before_delete;
CREATE TRIGGER trg_payroll_apply_receipts_before_delete
BEFORE DELETE ON payroll_apply_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'payroll_apply_receipts records cannot be deleted';
-- END SOURCE: db/schema_parts/112_payroll_obligations.sql

-- BEGIN SOURCE: db/schema_parts/113_anomaly_registry_projection.sql
-- Additive Anomalies registry projection, immutable workflow, and checkpoints.

CREATE TABLE IF NOT EXISTS anomaly_current_alerts (
    fingerprint CHAR(64) PRIMARY KEY,
    definition_code VARCHAR(191) NOT NULL,
    definition_version INT UNSIGNED NOT NULL,
    source_domain VARCHAR(100) NOT NULL,
    source_identity VARCHAR(191) NOT NULL,
    source_version BIGINT UNSIGNED NOT NULL,
    predicate_active TINYINT(1) NOT NULL,
    workflow_status ENUM('open', 'claimed', 'resolved') NOT NULL,
    workflow_version BIGINT UNSIGNED NOT NULL,
    projection_version BIGINT UNSIGNED NOT NULL,
    claimed_by VARCHAR(100) NULL,
    claimed_at DATETIME NULL,
    resolved_by VARCHAR(100) NULL,
    resolved_at DATETIME NULL,
    display_snapshot JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_anomaly_current_source (
        definition_code,
        source_identity
    ),
    INDEX idx_anomaly_current_workflow (
        predicate_active,
        workflow_status,
        definition_code
    ),
    CONSTRAINT chk_anomaly_current_fingerprint
        CHECK (fingerprint REGEXP '^[0-9a-f]{64}$'),
    CONSTRAINT chk_anomaly_current_display
        CHECK (JSON_TYPE(display_snapshot) = 'OBJECT'),
    CONSTRAINT chk_anomaly_current_workflow
        CHECK (
            (
                workflow_status = 'open'
                AND claimed_by IS NULL
                AND claimed_at IS NULL
                AND resolved_by IS NULL
                AND resolved_at IS NULL
            )
            OR (
                workflow_status = 'claimed'
                AND CHAR_LENGTH(TRIM(claimed_by)) > 0
                AND claimed_at IS NOT NULL
                AND resolved_by IS NULL
                AND resolved_at IS NULL
            )
            OR (
                workflow_status = 'resolved'
                AND CHAR_LENGTH(TRIM(resolved_by)) > 0
                AND resolved_at IS NOT NULL
            )
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS anomaly_workflow_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    alert_fingerprint CHAR(64) NOT NULL,
    action ENUM('claim', 'resolve', 'reopen', 'auto_resolve') NOT NULL,
    expected_workflow_version BIGINT UNSIGNED NOT NULL,
    resulting_workflow_version BIGINT UNSIGNED NOT NULL,
    actor VARCHAR(100) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_anomaly_workflow_event_idempotency (idempotency_key),
    INDEX idx_anomaly_workflow_event_alert (
        alert_fingerprint,
        resulting_workflow_version
    ),
    CONSTRAINT fk_anomaly_workflow_event_alert
        FOREIGN KEY (alert_fingerprint)
        REFERENCES anomaly_current_alerts(fingerprint)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_anomaly_workflow_event_version
        CHECK (
            resulting_workflow_version = expected_workflow_version + 1
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS finance_anomaly_occurrences (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    occurrence_fingerprint CHAR(64) NOT NULL,
    definition_code VARCHAR(191) NOT NULL,
    source_event_identity VARCHAR(191) NOT NULL,
    finance_import_row_id BIGINT NULL,
    finance_import_batch_id BIGINT NULL,
    source_version BIGINT UNSIGNED NOT NULL,
    bounded_snapshot JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_finance_anomaly_occurrence_fingerprint (
        occurrence_fingerprint
    ),
    UNIQUE KEY uq_finance_anomaly_occurrence_source (
        definition_code,
        source_event_identity
    ),
    CONSTRAINT fk_finance_anomaly_occurrence_row
        FOREIGN KEY (finance_import_row_id) REFERENCES finance_import_rows(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_finance_anomaly_occurrence_batch
        FOREIGN KEY (finance_import_batch_id) REFERENCES finance_import_batches(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_finance_anomaly_occurrence_fingerprint
        CHECK (occurrence_fingerprint REGEXP '^[0-9a-f]{64}$'),
    CONSTRAINT chk_finance_anomaly_occurrence_snapshot
        CHECK (JSON_TYPE(bounded_snapshot) = 'OBJECT'),
    CONSTRAINT chk_finance_anomaly_occurrence_source
        CHECK (
            (finance_import_row_id IS NOT NULL)
            <> (finance_import_batch_id IS NOT NULL)
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS anomaly_consumer_checkpoints (
    consumer_identity VARCHAR(191) NOT NULL,
    partition_identity VARCHAR(191) NOT NULL,
    source_event_identity VARCHAR(191) NOT NULL,
    source_version BIGINT UNSIGNED NOT NULL,
    processed_at DATETIME NOT NULL,
    PRIMARY KEY (consumer_identity, partition_identity)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_anomaly_workflow_events_before_update;
CREATE TRIGGER trg_anomaly_workflow_events_before_update
BEFORE UPDATE ON anomaly_workflow_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'anomaly_workflow_events records cannot be updated';

DROP TRIGGER IF EXISTS trg_anomaly_workflow_events_before_delete;
CREATE TRIGGER trg_anomaly_workflow_events_before_delete
BEFORE DELETE ON anomaly_workflow_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'anomaly_workflow_events records cannot be deleted';

DROP TRIGGER IF EXISTS trg_finance_anomaly_occurrences_before_update;
CREATE TRIGGER trg_finance_anomaly_occurrences_before_update
BEFORE UPDATE ON finance_anomaly_occurrences
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'finance_anomaly_occurrences records cannot be updated';

DROP TRIGGER IF EXISTS trg_finance_anomaly_occurrences_before_delete;
CREATE TRIGGER trg_finance_anomaly_occurrences_before_delete
BEFORE DELETE ON finance_anomaly_occurrences
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'finance_anomaly_occurrences records cannot be deleted';
-- END SOURCE: db/schema_parts/113_anomaly_registry_projection.sql

-- BEGIN SOURCE: db/schema_parts/114_staff_payout_ledger.sql
-- Additive Staff Payables immutable payout/return/reversal ledger.

CREATE TABLE IF NOT EXISTS staff_payout_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    staff_id INT NOT NULL,
    finance_import_row_id BIGINT NULL,
    event_type ENUM('payout', 'return', 'reversal') NOT NULL,
    amount_ntd BIGINT NOT NULL,
    occurred_on DATE NOT NULL,
    bank_account_identity_hash CHAR(64) NOT NULL,
    reversal_of_event_id BIGINT NULL,
    reconciliation_reference VARCHAR(191) NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    actor VARCHAR(100) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_staff_payout_import_row (finance_import_row_id),
    UNIQUE KEY uq_staff_payout_idempotency (idempotency_key),
    INDEX idx_staff_payout_staff_date (staff_id, occurred_on, id),
    CONSTRAINT fk_staff_payout_staff
        FOREIGN KEY (staff_id) REFERENCES staff(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_staff_payout_import_row
        FOREIGN KEY (finance_import_row_id) REFERENCES finance_import_rows(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_staff_payout_reversal
        FOREIGN KEY (reversal_of_event_id) REFERENCES staff_payout_events(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_staff_payout_amount
        CHECK (amount_ntd > 0),
    CONSTRAINT chk_staff_payout_account_hash
        CHECK (bank_account_identity_hash REGEXP '^[0-9a-f]{64}$'),
    CONSTRAINT chk_staff_payout_reversal_shape
        CHECK (
            (event_type = 'payout' AND reversal_of_event_id IS NULL)
            OR (
                event_type IN ('return', 'reversal')
                AND reversal_of_event_id IS NOT NULL
            )
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS staff_payout_obligation_links (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    payout_event_id BIGINT NOT NULL,
    obligation_identity VARCHAR(191) NOT NULL,
    allocated_amount_ntd BIGINT NOT NULL,
    allocation_ordinal INT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_staff_payout_obligation_link (
        payout_event_id,
        obligation_identity
    ),
    UNIQUE KEY uq_staff_payout_link_ordinal (
        payout_event_id,
        allocation_ordinal
    ),
    INDEX idx_staff_payout_link_obligation (
        obligation_identity,
        payout_event_id
    ),
    CONSTRAINT fk_staff_payout_link_event
        FOREIGN KEY (payout_event_id) REFERENCES staff_payout_events(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_staff_payout_link_obligation
        FOREIGN KEY (obligation_identity)
        REFERENCES staff_obligations(obligation_identity)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_staff_payout_link_amount
        CHECK (allocated_amount_ntd > 0),
    CONSTRAINT chk_staff_payout_link_ordinal
        CHECK (allocation_ordinal > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS staff_payable_accounts (
    staff_id INT PRIMARY KEY,
    aggregate_version BIGINT UNSIGNED NOT NULL DEFAULT 0,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_staff_payable_account_staff
        FOREIGN KEY (staff_id) REFERENCES staff(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS staff_payable_projections (
    obligation_identity VARCHAR(191) PRIMARY KEY,
    staff_id INT NOT NULL,
    obligation_amount_ntd BIGINT NOT NULL,
    net_paid_ntd BIGINT NOT NULL,
    balance_ntd BIGINT NOT NULL,
    status ENUM('payable', 'completed', 'anomaly') NOT NULL,
    aggregate_version BIGINT UNSIGNED NOT NULL,
    current_event_id BIGINT NOT NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_staff_payable_projection_status (
        staff_id,
        status,
        obligation_identity
    ),
    CONSTRAINT fk_staff_payable_projection_obligation
        FOREIGN KEY (obligation_identity)
        REFERENCES staff_obligations(obligation_identity)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_staff_payable_projection_staff
        FOREIGN KEY (staff_id) REFERENCES staff(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_staff_payable_projection_event
        FOREIGN KEY (current_event_id) REFERENCES staff_payout_events(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_staff_payable_projection_money
        CHECK (
            obligation_amount_ntd > 0
            AND net_paid_ntd >= 0
            AND balance_ntd = obligation_amount_ntd - net_paid_ntd
        ),
    CONSTRAINT chk_staff_payable_projection_status
        CHECK (
            (
                status = 'payable'
                AND net_paid_ntd = 0
                AND balance_ntd = obligation_amount_ntd
            )
            OR (
                status = 'completed'
                AND net_paid_ntd = obligation_amount_ntd
                AND balance_ntd = 0
            )
            OR (
                status = 'anomaly'
                AND net_paid_ntd <> 0
                AND balance_ntd <> 0
            )
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS staff_payables_apply_receipts (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    idempotency_key VARCHAR(191) NOT NULL,
    command_fingerprint CHAR(64) NOT NULL,
    preview_fingerprint CHAR(64) NOT NULL,
    staff_id INT NOT NULL,
    result_snapshot JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_staff_payables_receipt_idempotency (idempotency_key),
    CONSTRAINT fk_staff_payables_receipt_staff
        FOREIGN KEY (staff_id) REFERENCES staff(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_staff_payables_receipt_fingerprint
        CHECK (
            command_fingerprint REGEXP '^[0-9a-f]{64}$'
            AND preview_fingerprint REGEXP '^[0-9a-f]{64}$'
        ),
    CONSTRAINT chk_staff_payables_receipt_snapshot
        CHECK (JSON_TYPE(result_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS staff_payables_outbox (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    staff_id INT NOT NULL,
    intent_key VARCHAR(191) NOT NULL,
    intent_type ENUM(
        'payable_projection_refresh',
        'payout_anomaly_required'
    ) NOT NULL,
    payload_snapshot JSON NOT NULL,
    status ENUM('pending', 'processing', 'delivered', 'failed')
        NOT NULL DEFAULT 'pending',
    attempt_count INT UNSIGNED NOT NULL DEFAULT 0,
    next_attempt_at DATETIME NULL,
    delivered_at DATETIME NULL,
    last_error VARCHAR(1000) NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_staff_payables_outbox_intent (intent_key),
    INDEX idx_staff_payables_outbox_delivery (
        status,
        next_attempt_at,
        id
    ),
    CONSTRAINT fk_staff_payables_outbox_staff
        FOREIGN KEY (staff_id) REFERENCES staff(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_staff_payables_outbox_payload
        CHECK (JSON_TYPE(payload_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_staff_payout_events_before_update;
CREATE TRIGGER trg_staff_payout_events_before_update
BEFORE UPDATE ON staff_payout_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'staff_payout_events records cannot be updated';

DROP TRIGGER IF EXISTS trg_staff_payout_events_before_delete;
CREATE TRIGGER trg_staff_payout_events_before_delete
BEFORE DELETE ON staff_payout_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'staff_payout_events records cannot be deleted';

DROP TRIGGER IF EXISTS trg_staff_payout_links_before_update;
CREATE TRIGGER trg_staff_payout_links_before_update
BEFORE UPDATE ON staff_payout_obligation_links
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'staff_payout_obligation_links records cannot be updated';

DROP TRIGGER IF EXISTS trg_staff_payout_links_before_delete;
CREATE TRIGGER trg_staff_payout_links_before_delete
BEFORE DELETE ON staff_payout_obligation_links
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'staff_payout_obligation_links records cannot be deleted';

DROP TRIGGER IF EXISTS trg_staff_payables_receipts_before_update;
CREATE TRIGGER trg_staff_payables_receipts_before_update
BEFORE UPDATE ON staff_payables_apply_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'staff_payables_apply_receipts records cannot be updated';

DROP TRIGGER IF EXISTS trg_staff_payables_receipts_before_delete;
CREATE TRIGGER trg_staff_payables_receipts_before_delete
BEFORE DELETE ON staff_payables_apply_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'staff_payables_apply_receipts records cannot be deleted';
-- END SOURCE: db/schema_parts/114_staff_payout_ledger.sql

-- BEGIN SOURCE: db/schema_parts/115_global_command_claims.sql
-- Global transactional mutex for idempotent application commands.

CREATE TABLE IF NOT EXISTS application_command_claims (
    idempotency_key VARCHAR(191) PRIMARY KEY,
    command_family VARCHAR(100) NOT NULL,
    aggregate_identity VARCHAR(191) NOT NULL,
    command_fingerprint CHAR(64) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_application_command_claim_text
        CHECK (
            CHAR_LENGTH(TRIM(command_family)) > 0
            AND CHAR_LENGTH(TRIM(aggregate_identity)) > 0
            AND CHAR_LENGTH(TRIM(correlation_id)) > 0
        ),
    CONSTRAINT chk_application_command_claim_fingerprint
        CHECK (command_fingerprint REGEXP '^[0-9a-f]{64}$')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_application_command_claims_before_update;
CREATE TRIGGER trg_application_command_claims_before_update
BEFORE UPDATE ON application_command_claims
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'application_command_claims records cannot be updated';

DROP TRIGGER IF EXISTS trg_application_command_claims_before_delete;
CREATE TRIGGER trg_application_command_claims_before_delete
BEFORE DELETE ON application_command_claims
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'application_command_claims records cannot be deleted';
-- END SOURCE: db/schema_parts/115_global_command_claims.sql

-- BEGIN SOURCE: db/schema_parts/116_order_actual_start_workflow.sql
-- Additive Actual Start root events and outer transaction receipts.

CREATE TABLE IF NOT EXISTS order_actual_start_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    case_no VARCHAR(50) NOT NULL,
    event_type ENUM(
        'confirmed',
        'corrected',
        'reconfirmed_after_delayed_settlement'
    ) NOT NULL,
    before_actual_start_date DATE NULL,
    after_actual_start_date DATE NOT NULL,
    deposit_settlement_identity CHAR(64) NULL,
    expected_order_version BIGINT UNSIGNED NOT NULL,
    resulting_order_version BIGINT UNSIGNED NOT NULL,
    preview_fingerprint CHAR(64) NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    actor VARCHAR(100) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_order_actual_start_event_idempotency (idempotency_key),
    UNIQUE KEY uq_order_actual_start_event_case_identity (id, case_no),
    CONSTRAINT fk_order_actual_start_event_order
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_order_actual_start_event_version
        CHECK (resulting_order_version = expected_order_version + 1),
    CONSTRAINT chk_order_actual_start_event_fingerprint
        CHECK (preview_fingerprint REGEXP '^[0-9a-f]{64}$'),
    CONSTRAINT chk_order_actual_start_event_settlement
        CHECK (
            deposit_settlement_identity IS NULL
            OR deposit_settlement_identity REGEXP '^[0-9a-f]{64}$'
        ),
    CONSTRAINT chk_order_actual_start_event_shape
        CHECK (
            (
                event_type = 'confirmed'
                AND before_actual_start_date IS NULL
                AND deposit_settlement_identity IS NULL
            )
            OR
            (
                event_type = 'corrected'
                AND before_actual_start_date IS NOT NULL
                AND deposit_settlement_identity IS NULL
            )
            OR
            (
                event_type = 'reconfirmed_after_delayed_settlement'
                AND before_actual_start_date IS NOT NULL
                AND deposit_settlement_identity IS NOT NULL
            )
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS order_actual_start_apply_receipts (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    idempotency_key VARCHAR(191) NOT NULL,
    command_fingerprint CHAR(64) NOT NULL,
    preview_fingerprint CHAR(64) NOT NULL,
    case_no VARCHAR(50) NOT NULL,
    actual_start_event_id BIGINT NOT NULL,
    scheduling_command_receipt_id BIGINT NOT NULL,
    lifecycle_event_id BIGINT UNSIGNED NOT NULL,
    reconfirmation_control_event_id BIGINT UNSIGNED NULL,
    order_version BIGINT UNSIGNED NOT NULL,
    scheduling_version BIGINT UNSIGNED NOT NULL,
    scheduling_generation INT UNSIGNED NOT NULL,
    client_finance_version BIGINT UNSIGNED NOT NULL,
    payroll_version BIGINT UNSIGNED NOT NULL,
    lifecycle_status ENUM(
        '洽談中',
        '訂單成立',
        '服務中',
        '訂單完成',
        '訂單取消'
    ) NOT NULL,
    actual_start_date DATE NOT NULL,
    actual_end_date DATE NOT NULL,
    service_data_lock_formed TINYINT(1) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    result_snapshot JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_order_actual_start_receipt_key (idempotency_key),
    CONSTRAINT fk_order_actual_start_receipt_order
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_order_actual_start_receipt_event
        FOREIGN KEY (actual_start_event_id, case_no)
        REFERENCES order_actual_start_events(id, case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_order_actual_start_receipt_scheduling
        FOREIGN KEY (scheduling_command_receipt_id)
        REFERENCES scheduling_command_receipts(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_order_actual_start_receipt_lifecycle
        FOREIGN KEY (lifecycle_event_id, case_no)
        REFERENCES order_lifecycle_state_events(id, case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_order_actual_start_receipt_control
        FOREIGN KEY (reconfirmation_control_event_id)
        REFERENCES order_lifecycle_control_events(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_order_actual_start_receipt_fingerprints
        CHECK (
            command_fingerprint REGEXP '^[0-9a-f]{64}$'
            AND preview_fingerprint REGEXP '^[0-9a-f]{64}$'
        ),
    CONSTRAINT chk_order_actual_start_receipt_dates
        CHECK (actual_end_date >= actual_start_date),
    CONSTRAINT chk_order_actual_start_receipt_snapshot
        CHECK (JSON_TYPE(result_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_order_actual_start_events_before_update;
CREATE TRIGGER trg_order_actual_start_events_before_update
BEFORE UPDATE ON order_actual_start_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'order_actual_start_events records cannot be updated';

DROP TRIGGER IF EXISTS trg_order_actual_start_events_before_delete;
CREATE TRIGGER trg_order_actual_start_events_before_delete
BEFORE DELETE ON order_actual_start_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'order_actual_start_events records cannot be deleted';

DROP TRIGGER IF EXISTS trg_order_actual_start_receipts_before_update;
CREATE TRIGGER trg_order_actual_start_receipts_before_update
BEFORE UPDATE ON order_actual_start_apply_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'order_actual_start_apply_receipts records cannot be updated';

DROP TRIGGER IF EXISTS trg_order_actual_start_receipts_before_delete;
CREATE TRIGGER trg_order_actual_start_receipts_before_delete
BEFORE DELETE ON order_actual_start_apply_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'order_actual_start_apply_receipts records cannot be deleted';
-- END SOURCE: db/schema_parts/116_order_actual_start_workflow.sql

-- BEGIN SOURCE: db/schema_parts/117_client_deposit_settlement_projection.sql
-- Additive Client Finance-owned current deposit settlement projection.

CREATE TABLE IF NOT EXISTS client_deposit_settlement_projection (
    case_no VARCHAR(50) PRIMARY KEY,
    deposit_obligation_identity VARCHAR(191) NOT NULL,
    settlement_state ENUM('unsettled', 'settled') NOT NULL,
    contracted_amount_ntd BIGINT UNSIGNED NOT NULL,
    allocated_net_amount_ntd BIGINT NOT NULL,
    settlement_identity CHAR(64) NULL,
    source_fingerprint CHAR(64) NOT NULL,
    projection_version BIGINT UNSIGNED NOT NULL,
    latest_ledger_entry_id BIGINT NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_client_deposit_projection_obligation (
        deposit_obligation_identity,
        case_no
    ),
    INDEX idx_client_deposit_projection_state (
        settlement_state,
        case_no
    ),
    CONSTRAINT fk_client_deposit_projection_account
        FOREIGN KEY (case_no) REFERENCES client_finance_accounts(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_client_deposit_projection_obligation
        FOREIGN KEY (deposit_obligation_identity, case_no)
        REFERENCES client_obligations(obligation_identity, case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_client_deposit_projection_latest_ledger
        FOREIGN KEY (latest_ledger_entry_id) REFERENCES client_ledger_entries(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_client_deposit_projection_version
        CHECK (projection_version > 0),
    CONSTRAINT chk_client_deposit_projection_amount
        CHECK (contracted_amount_ntd > 0),
    CONSTRAINT chk_client_deposit_projection_fingerprints
        CHECK (
            source_fingerprint REGEXP '^[0-9a-f]{64}$'
            AND (
                settlement_identity IS NULL
                OR settlement_identity REGEXP '^[0-9a-f]{64}$'
            )
        ),
    CONSTRAINT chk_client_deposit_projection_state
        CHECK (
            (
                settlement_state = 'settled'
                AND allocated_net_amount_ntd = contracted_amount_ntd
                AND settlement_identity IS NOT NULL
                AND latest_ledger_entry_id IS NOT NULL
            )
            OR
            (
                settlement_state = 'unsettled'
                AND allocated_net_amount_ntd <> contracted_amount_ntd
                AND settlement_identity IS NULL
            )
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
-- END SOURCE: db/schema_parts/117_client_deposit_settlement_projection.sql

-- BEGIN SOURCE: db/schema_parts/118_order_cancellation_workflow.sql
-- Additive Orders Cancellation root events and outer transaction receipts.

CREATE TABLE IF NOT EXISTS order_cancellation_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    case_no VARCHAR(50) NOT NULL,
    cancellation_date DATE NOT NULL,
    actual_end_date DATE NULL,
    official_service_day_count INT UNSIGNED NOT NULL,
    official_service_hours INT UNSIGNED NOT NULL,
    confirmed_service_days JSON NOT NULL,
    expected_order_version BIGINT UNSIGNED NOT NULL,
    resulting_order_version BIGINT UNSIGNED NOT NULL,
    preview_fingerprint CHAR(64) NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    actor VARCHAR(100) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_order_cancellation_event_key (idempotency_key),
    UNIQUE KEY uq_order_cancellation_event_owner (id, case_no),
    CONSTRAINT fk_order_cancellation_event_order
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_order_cancellation_event_version
        CHECK (resulting_order_version = expected_order_version + 1),
    CONSTRAINT chk_order_cancellation_event_fingerprint
        CHECK (preview_fingerprint REGEXP '^[0-9a-f]{64}$'),
    CONSTRAINT chk_order_cancellation_event_snapshot
        CHECK (JSON_TYPE(confirmed_service_days) = 'ARRAY'),
    CONSTRAINT chk_order_cancellation_event_service
        CHECK (
            (
                official_service_day_count = 0
                AND official_service_hours = 0
                AND actual_end_date IS NULL
            )
            OR
            (
                official_service_day_count > 0
                AND official_service_hours > 0
                AND actual_end_date IS NOT NULL
            )
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS order_cancellation_apply_receipts (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    idempotency_key VARCHAR(191) NOT NULL,
    command_fingerprint CHAR(64) NOT NULL,
    preview_fingerprint CHAR(64) NOT NULL,
    case_no VARCHAR(50) NOT NULL,
    cancellation_event_id BIGINT NOT NULL,
    scheduling_command_receipt_id BIGINT NOT NULL,
    cancellation_control_event_id BIGINT UNSIGNED NOT NULL,
    lifecycle_event_id BIGINT UNSIGNED NOT NULL,
    order_version BIGINT UNSIGNED NOT NULL,
    scheduling_version BIGINT UNSIGNED NOT NULL,
    scheduling_generation INT UNSIGNED NOT NULL,
    client_finance_version BIGINT UNSIGNED NOT NULL,
    payroll_version BIGINT UNSIGNED NOT NULL,
    lifecycle_status ENUM(
        '洽談中',
        '訂單成立',
        '服務中',
        '訂單完成',
        '訂單取消'
    ) NOT NULL,
    actual_end_date DATE NULL,
    official_service_day_count INT UNSIGNED NOT NULL,
    official_service_hours INT UNSIGNED NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    result_snapshot JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_order_cancellation_receipt_key (idempotency_key),
    CONSTRAINT fk_order_cancellation_receipt_order
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_order_cancellation_receipt_event
        FOREIGN KEY (cancellation_event_id, case_no)
        REFERENCES order_cancellation_events(id, case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_order_cancellation_receipt_scheduling
        FOREIGN KEY (scheduling_command_receipt_id)
        REFERENCES scheduling_command_receipts(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_order_cancellation_receipt_control
        FOREIGN KEY (cancellation_control_event_id)
        REFERENCES order_lifecycle_control_events(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_order_cancellation_receipt_lifecycle
        FOREIGN KEY (lifecycle_event_id, case_no)
        REFERENCES order_lifecycle_state_events(id, case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_order_cancellation_receipt_fingerprints
        CHECK (
            command_fingerprint REGEXP '^[0-9a-f]{64}$'
            AND preview_fingerprint REGEXP '^[0-9a-f]{64}$'
        ),
    CONSTRAINT chk_order_cancellation_receipt_service
        CHECK (
            (
                official_service_day_count = 0
                AND official_service_hours = 0
                AND actual_end_date IS NULL
            )
            OR
            (
                official_service_day_count > 0
                AND official_service_hours > 0
                AND actual_end_date IS NOT NULL
            )
        ),
    CONSTRAINT chk_order_cancellation_receipt_snapshot
        CHECK (JSON_TYPE(result_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_order_cancellation_events_before_update;
CREATE TRIGGER trg_order_cancellation_events_before_update
BEFORE UPDATE ON order_cancellation_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'order_cancellation_events records cannot be updated';

DROP TRIGGER IF EXISTS trg_order_cancellation_events_before_delete;
CREATE TRIGGER trg_order_cancellation_events_before_delete
BEFORE DELETE ON order_cancellation_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'order_cancellation_events records cannot be deleted';

DROP TRIGGER IF EXISTS trg_order_cancellation_receipts_before_update;
CREATE TRIGGER trg_order_cancellation_receipts_before_update
BEFORE UPDATE ON order_cancellation_apply_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'order_cancellation_apply_receipts records cannot be updated';

DROP TRIGGER IF EXISTS trg_order_cancellation_receipts_before_delete;
CREATE TRIGGER trg_order_cancellation_receipts_before_delete
BEFORE DELETE ON order_cancellation_apply_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'order_cancellation_apply_receipts records cannot be deleted';
-- END SOURCE: db/schema_parts/118_order_cancellation_workflow.sql

-- BEGIN SOURCE: db/schema_parts/119_assignment_plan_workflow.sql
-- Append-only receipt for one cross-Domain Assignment Plan Apply.

CREATE TABLE IF NOT EXISTS assignment_plan_apply_receipts (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    idempotency_key VARCHAR(191) NOT NULL,
    command_fingerprint CHAR(64) NOT NULL,
    preview_fingerprint CHAR(64) NOT NULL,
    case_no VARCHAR(50) NOT NULL,
    expected_order_version BIGINT UNSIGNED NOT NULL,
    resulting_order_version BIGINT UNSIGNED NOT NULL,
    expected_scheduling_version BIGINT UNSIGNED NOT NULL,
    resulting_scheduling_version BIGINT UNSIGNED NOT NULL,
    resulting_generation_number INT UNSIGNED NOT NULL,
    expected_client_finance_version BIGINT UNSIGNED NOT NULL,
    resulting_client_finance_version BIGINT UNSIGNED NOT NULL,
    expected_payroll_version BIGINT UNSIGNED NOT NULL,
    resulting_payroll_version BIGINT UNSIGNED NOT NULL,
    scheduling_receipt_id BIGINT NOT NULL,
    cancelled_assignment_ids JSON NOT NULL,
    created_assignment_keys JSON NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_assignment_plan_receipt_key (idempotency_key),
    CONSTRAINT fk_assignment_plan_receipt_order
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_assignment_plan_scheduling_receipt
        FOREIGN KEY (scheduling_receipt_id)
        REFERENCES scheduling_command_receipts(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_assignment_plan_receipt_fingerprints
        CHECK (
            command_fingerprint REGEXP '^[0-9a-f]{64}$'
            AND preview_fingerprint REGEXP '^[0-9a-f]{64}$'
        ),
    CONSTRAINT chk_assignment_plan_receipt_versions
        CHECK (
            resulting_order_version = expected_order_version + 1
            AND resulting_scheduling_version =
                expected_scheduling_version + 1
            AND resulting_client_finance_version =
                expected_client_finance_version + 1
            AND resulting_payroll_version = expected_payroll_version + 1
        ),
    CONSTRAINT chk_assignment_plan_receipt_arrays
        CHECK (
            JSON_TYPE(cancelled_assignment_ids) = 'ARRAY'
            AND JSON_TYPE(created_assignment_keys) = 'ARRAY'
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_assignment_plan_receipts_before_update;
CREATE TRIGGER trg_assignment_plan_receipts_before_update
BEFORE UPDATE ON assignment_plan_apply_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'assignment_plan_apply_receipts cannot be updated';

DROP TRIGGER IF EXISTS trg_assignment_plan_receipts_before_delete;
CREATE TRIGGER trg_assignment_plan_receipts_before_delete
BEFORE DELETE ON assignment_plan_apply_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'assignment_plan_apply_receipts cannot be deleted';
-- END SOURCE: db/schema_parts/119_assignment_plan_workflow.sql

-- BEGIN SOURCE: db/schema_parts/120_leave_substitution_workflow.sql
-- Typed leave/substitution batch, immutable outcomes, occupancy, and receipt.

CREATE TABLE IF NOT EXISTS scheduling_leave_substitution_batches (
    batch_key VARCHAR(191) NOT NULL,
    case_no VARCHAR(50) NOT NULL,
    original_assignment_id BIGINT NOT NULL,
    command_fingerprint CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    preview_fingerprint CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    request_fingerprint CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    item_count INT UNSIGNED NOT NULL,
    actor VARCHAR(100) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    request_snapshot JSON NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (batch_key),
    INDEX idx_scheduling_leave_batch_case_time (case_no, created_at),
    CONSTRAINT fk_scheduling_leave_batch_case
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_scheduling_leave_batch_original_assignment
        FOREIGN KEY (original_assignment_id) REFERENCES case_staff_assignments(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_scheduling_leave_batch_fingerprints
        CHECK (
            command_fingerprint REGEXP '^[0-9a-f]{64}$'
            AND preview_fingerprint REGEXP '^[0-9a-f]{64}$'
            AND request_fingerprint REGEXP '^[0-9a-f]{64}$'
        ),
    CONSTRAINT chk_scheduling_leave_batch_identity
        CHECK (
            item_count > 0
            AND CHAR_LENGTH(TRIM(batch_key)) > 0
            AND CHAR_LENGTH(TRIM(actor)) > 0
            AND CHAR_LENGTH(TRIM(reason)) > 0
            AND CHAR_LENGTH(TRIM(correlation_id)) > 0
            AND JSON_TYPE(request_snapshot) = 'OBJECT'
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS scheduling_leave_substitution_outcomes (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    batch_key VARCHAR(191) NOT NULL,
    item_index INT UNSIGNED NOT NULL,
    event_key VARCHAR(191) NOT NULL,
    original_assignment_id BIGINT NOT NULL,
    original_schedule_id INT NOT NULL,
    original_staff_id INT NOT NULL,
    original_work_date DATE NOT NULL,
    resolution_type ENUM(
        'defer_following_assignments',
        'substitute'
    ) NOT NULL,
    leave_occupancy_date DATE NOT NULL,
    resulting_assignment_id BIGINT NOT NULL,
    resulting_staff_id INT NOT NULL,
    resulting_service_date DATE NOT NULL,
    is_double_pay BOOLEAN NOT NULL DEFAULT FALSE,
    result_fingerprint CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    outcome_snapshot JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_scheduling_leave_outcome_ordinal (batch_key, item_index),
    UNIQUE KEY uq_scheduling_leave_outcome_event_key (event_key),
    UNIQUE KEY uq_scheduling_leave_outcome_identity (id, batch_key),
    CONSTRAINT fk_scheduling_leave_outcome_batch
        FOREIGN KEY (batch_key)
        REFERENCES scheduling_leave_substitution_batches(batch_key)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_scheduling_leave_outcome_original_assignment
        FOREIGN KEY (original_assignment_id) REFERENCES case_staff_assignments(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_scheduling_leave_outcome_original_schedule
        FOREIGN KEY (original_schedule_id) REFERENCES staff_schedule(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_scheduling_leave_outcome_resulting_assignment
        FOREIGN KEY (resulting_assignment_id) REFERENCES case_staff_assignments(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_scheduling_leave_outcome_result
        CHECK (
            result_fingerprint REGEXP '^[0-9a-f]{64}$'
            AND CHAR_LENGTH(TRIM(event_key)) > 0
            AND JSON_TYPE(outcome_snapshot) = 'OBJECT'
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS scheduling_leave_occupancy_days (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    batch_key VARCHAR(191) NOT NULL,
    item_index INT UNSIGNED NOT NULL,
    outcome_id BIGINT NOT NULL,
    generation_id BIGINT NOT NULL,
    staff_id INT NOT NULL,
    occupancy_date DATE NOT NULL,
    status ENUM('active', 'cancelled') NOT NULL DEFAULT 'active',
    active_marker TINYINT(1) NULL DEFAULT 1,
    cancelled_by VARCHAR(100) NULL,
    cancelled_at TIMESTAMP NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_scheduling_leave_occupancy_outcome (outcome_id),
    UNIQUE KEY uq_scheduling_leave_occupancy_staff_date (
        staff_id,
        occupancy_date,
        active_marker
    ),
    INDEX idx_scheduling_leave_occupancy_generation (
        generation_id,
        active_marker
    ),
    CONSTRAINT fk_scheduling_leave_occupancy_outcome
        FOREIGN KEY (outcome_id, batch_key)
        REFERENCES scheduling_leave_substitution_outcomes(id, batch_key)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_scheduling_leave_occupancy_generation
        FOREIGN KEY (generation_id) REFERENCES scheduling_generations(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_scheduling_leave_occupancy_staff
        FOREIGN KEY (staff_id) REFERENCES staff(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_scheduling_leave_occupancy_state
        CHECK (
            (
                status = 'active'
                AND active_marker = 1
                AND cancelled_by IS NULL
                AND cancelled_at IS NULL
            )
            OR (
                status = 'cancelled'
                AND active_marker IS NULL
                AND CHAR_LENGTH(TRIM(cancelled_by)) > 0
                AND cancelled_at IS NOT NULL
            )
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS scheduling_leave_substitution_receipts (
    batch_key VARCHAR(191) NOT NULL,
    command_fingerprint CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    preview_fingerprint CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    case_no VARCHAR(50) NOT NULL,
    expected_order_version BIGINT UNSIGNED NOT NULL,
    resulting_order_version BIGINT UNSIGNED NOT NULL,
    expected_scheduling_version BIGINT UNSIGNED NOT NULL,
    resulting_scheduling_version BIGINT UNSIGNED NOT NULL,
    resulting_generation_number INT UNSIGNED NOT NULL,
    expected_client_finance_version BIGINT UNSIGNED NOT NULL,
    resulting_client_finance_version BIGINT UNSIGNED NOT NULL,
    expected_payroll_version BIGINT UNSIGNED NOT NULL,
    resulting_payroll_version BIGINT UNSIGNED NOT NULL,
    scheduling_receipt_id BIGINT NOT NULL,
    outcome_event_ids JSON NOT NULL,
    result_snapshot JSON NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (batch_key),
    CONSTRAINT fk_scheduling_leave_receipt_batch
        FOREIGN KEY (batch_key)
        REFERENCES scheduling_leave_substitution_batches(batch_key)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_scheduling_leave_receipt_case
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_scheduling_leave_receipt_scheduling
        FOREIGN KEY (scheduling_receipt_id)
        REFERENCES scheduling_command_receipts(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_scheduling_leave_receipt_fingerprints
        CHECK (
            command_fingerprint REGEXP '^[0-9a-f]{64}$'
            AND preview_fingerprint REGEXP '^[0-9a-f]{64}$'
        ),
    CONSTRAINT chk_scheduling_leave_receipt_versions
        CHECK (
            resulting_order_version = expected_order_version + 1
            AND resulting_scheduling_version =
                expected_scheduling_version + 1
            AND resulting_client_finance_version =
                expected_client_finance_version + 1
            AND resulting_payroll_version = expected_payroll_version + 1
        ),
    CONSTRAINT chk_scheduling_leave_receipt_snapshots
        CHECK (
            JSON_TYPE(outcome_event_ids) = 'ARRAY'
            AND JSON_TYPE(result_snapshot) = 'OBJECT'
            AND CHAR_LENGTH(TRIM(correlation_id)) > 0
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_scheduling_leave_batches_before_update;
CREATE TRIGGER trg_scheduling_leave_batches_before_update
BEFORE UPDATE ON scheduling_leave_substitution_batches
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'scheduling_leave_substitution_batches cannot be updated';

DROP TRIGGER IF EXISTS trg_scheduling_leave_batches_before_delete;
CREATE TRIGGER trg_scheduling_leave_batches_before_delete
BEFORE DELETE ON scheduling_leave_substitution_batches
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'scheduling_leave_substitution_batches cannot be deleted';

DROP TRIGGER IF EXISTS trg_scheduling_leave_outcomes_before_update;
CREATE TRIGGER trg_scheduling_leave_outcomes_before_update
BEFORE UPDATE ON scheduling_leave_substitution_outcomes
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'scheduling_leave_substitution_outcomes cannot be updated';

DROP TRIGGER IF EXISTS trg_scheduling_leave_outcomes_before_delete;
CREATE TRIGGER trg_scheduling_leave_outcomes_before_delete
BEFORE DELETE ON scheduling_leave_substitution_outcomes
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'scheduling_leave_substitution_outcomes cannot be deleted';

DROP TRIGGER IF EXISTS trg_scheduling_leave_receipts_before_update;
CREATE TRIGGER trg_scheduling_leave_receipts_before_update
BEFORE UPDATE ON scheduling_leave_substitution_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'scheduling_leave_substitution_receipts cannot be updated';

DROP TRIGGER IF EXISTS trg_scheduling_leave_receipts_before_delete;
CREATE TRIGGER trg_scheduling_leave_receipts_before_delete
BEFORE DELETE ON scheduling_leave_substitution_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'scheduling_leave_substitution_receipts cannot be deleted';
-- END SOURCE: db/schema_parts/120_leave_substitution_workflow.sql

-- BEGIN SOURCE: db/schema_parts/121_finance_import_preview_apply.sql
-- Finance Import Preview/Apply control state and immutable audit.

CREATE TABLE IF NOT EXISTS finance_import_batch_contracts (
    batch_id BIGINT PRIMARY KEY,
    batch_identity VARCHAR(191) NOT NULL,
    source_content_digest CHAR(64) NOT NULL,
    classifier_version VARCHAR(191) NOT NULL,
    fingerprint_version VARCHAR(191) NOT NULL,
    batch_version BIGINT UNSIGNED NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_finance_import_batch_contract_identity (batch_identity),
    CONSTRAINT fk_finance_import_batch_contract_batch
        FOREIGN KEY (batch_id) REFERENCES finance_import_batches(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_finance_import_batch_contract_digest
        CHECK (source_content_digest REGEXP '^[0-9a-f]{64}$'),
    CONSTRAINT chk_finance_import_batch_contract_text
        CHECK (
            CHAR_LENGTH(TRIM(batch_identity)) > 0
            AND CHAR_LENGTH(TRIM(classifier_version)) > 0
            AND CHAR_LENGTH(TRIM(fingerprint_version)) > 0
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS finance_import_classification_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    batch_id BIGINT NOT NULL,
    finance_import_row_id BIGINT NOT NULL,
    classification_version BIGINT UNSIGNED NOT NULL,
    canonical_fact_version BIGINT UNSIGNED NOT NULL,
    classification_type ENUM(
        'client_receipt',
        'client_subsidy_return',
        'government_subsidy',
        'staff_payout',
        'non_business_review'
    ) NOT NULL,
    disposition ENUM(
        'create',
        'existing',
        'manual_review',
        'business_pending',
        'blocked'
    ) NOT NULL,
    decision_facts_fingerprint CHAR(64) NOT NULL,
    target_identities JSON NOT NULL,
    evidence JSON NOT NULL,
    available_actions JSON NOT NULL,
    actor VARCHAR(100) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_finance_import_classification_version (
        finance_import_row_id,
        classification_version
    ),
    INDEX idx_finance_import_classification_batch (
        batch_id,
        finance_import_row_id,
        id
    ),
    CONSTRAINT fk_finance_import_classification_batch
        FOREIGN KEY (batch_id) REFERENCES finance_import_batches(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_finance_import_classification_row
        FOREIGN KEY (finance_import_row_id) REFERENCES finance_import_rows(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_finance_import_classification_fingerprint
        CHECK (decision_facts_fingerprint REGEXP '^[0-9a-f]{64}$'),
    CONSTRAINT chk_finance_import_classification_json
        CHECK (
            JSON_TYPE(target_identities) = 'ARRAY'
            AND JSON_TYPE(evidence) = 'ARRAY'
            AND JSON_TYPE(available_actions) = 'ARRAY'
        ),
    CONSTRAINT chk_finance_import_classification_text
        CHECK (
            CHAR_LENGTH(TRIM(actor)) > 0
            AND CHAR_LENGTH(TRIM(reason)) > 0
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS finance_import_integrity_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    batch_id BIGINT NOT NULL,
    finance_import_row_id BIGINT NULL,
    issue_code VARCHAR(191) NOT NULL,
    active TINYINT(1) NOT NULL,
    evidence_snapshot JSON NOT NULL,
    source_event_identity VARCHAR(191) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_finance_import_integrity_source (source_event_identity),
    INDEX idx_finance_import_integrity_current (
        batch_id,
        finance_import_row_id,
        issue_code,
        id
    ),
    CONSTRAINT fk_finance_import_integrity_batch
        FOREIGN KEY (batch_id) REFERENCES finance_import_batches(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_finance_import_integrity_row
        FOREIGN KEY (finance_import_row_id) REFERENCES finance_import_rows(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_finance_import_integrity_active
        CHECK (active IN (0, 1)),
    CONSTRAINT chk_finance_import_integrity_snapshot
        CHECK (JSON_TYPE(evidence_snapshot) = 'OBJECT'),
    CONSTRAINT chk_finance_import_integrity_text
        CHECK (
            CHAR_LENGTH(TRIM(issue_code)) > 0
            AND CHAR_LENGTH(TRIM(source_event_identity)) > 0
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS finance_import_dispatch_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    batch_id BIGINT NOT NULL,
    finance_import_row_id BIGINT NOT NULL,
    plan_fingerprint CHAR(64) NOT NULL,
    outcome ENUM(
        'reconciled',
        'existing',
        'pending',
        'rejected',
        'conflict'
    ) NOT NULL,
    result_reference VARCHAR(191) NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_finance_import_dispatch_plan_row (
        plan_fingerprint,
        finance_import_row_id
    ),
    INDEX idx_finance_import_dispatch_batch (batch_id, id),
    CONSTRAINT fk_finance_import_dispatch_batch
        FOREIGN KEY (batch_id) REFERENCES finance_import_batches(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_finance_import_dispatch_row
        FOREIGN KEY (finance_import_row_id) REFERENCES finance_import_rows(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_finance_import_dispatch_fingerprint
        CHECK (plan_fingerprint REGEXP '^[0-9a-f]{64}$'),
    CONSTRAINT chk_finance_import_dispatch_reference
        CHECK (
            (
                outcome IN ('reconciled', 'existing')
                AND result_reference IS NOT NULL
                AND CHAR_LENGTH(TRIM(result_reference)) > 0
            )
            OR (
                outcome IN ('pending', 'rejected', 'conflict')
                AND result_reference IS NULL
            )
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS finance_import_reconciliation_receipts (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    finance_import_row_id BIGINT NOT NULL,
    candidate_fingerprint CHAR(64) NOT NULL,
    owning_domain ENUM('client_finance', 'staff_payables') NOT NULL,
    allocation_count INT UNSIGNED NOT NULL,
    amount_ntd BIGINT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_finance_import_reconciliation_candidate (
        candidate_fingerprint
    ),
    CONSTRAINT fk_finance_import_reconciliation_row
        FOREIGN KEY (finance_import_row_id) REFERENCES finance_import_rows(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_finance_import_reconciliation_fingerprint
        CHECK (candidate_fingerprint REGEXP '^[0-9a-f]{64}$'),
    CONSTRAINT chk_finance_import_reconciliation_values
        CHECK (allocation_count > 0 AND amount_ntd > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS finance_import_apply_receipts (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    idempotency_key VARCHAR(191) NOT NULL,
    command_fingerprint CHAR(64) NOT NULL,
    preview_fingerprint CHAR(64) NOT NULL,
    batch_id BIGINT NOT NULL,
    result_snapshot JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_finance_import_apply_receipt_key (idempotency_key),
    CONSTRAINT fk_finance_import_apply_receipt_batch
        FOREIGN KEY (batch_id) REFERENCES finance_import_batches(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_finance_import_apply_receipt_fingerprints
        CHECK (
            command_fingerprint REGEXP '^[0-9a-f]{64}$'
            AND preview_fingerprint REGEXP '^[0-9a-f]{64}$'
        ),
    CONSTRAINT chk_finance_import_apply_receipt_snapshot
        CHECK (JSON_TYPE(result_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS finance_import_correction_receipts (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    idempotency_key VARCHAR(191) NOT NULL,
    command_fingerprint CHAR(64) NOT NULL,
    preview_fingerprint CHAR(64) NOT NULL,
    finance_import_row_id BIGINT NOT NULL,
    result_snapshot JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_finance_import_correction_receipt_key (idempotency_key),
    CONSTRAINT fk_finance_import_correction_receipt_row
        FOREIGN KEY (finance_import_row_id) REFERENCES finance_import_rows(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_finance_import_correction_receipt_fingerprints
        CHECK (
            command_fingerprint REGEXP '^[0-9a-f]{64}$'
            AND preview_fingerprint REGEXP '^[0-9a-f]{64}$'
        ),
    CONSTRAINT chk_finance_import_correction_receipt_snapshot
        CHECK (JSON_TYPE(result_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS finance_import_outbox (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    batch_id BIGINT NOT NULL,
    intent_key VARCHAR(191) NOT NULL,
    intent_type ENUM(
        'dispatch_completed',
        'manual_correction_completed',
        'initial_classification_recorded'
    ) NOT NULL,
    payload_snapshot JSON NOT NULL,
    status ENUM('pending', 'processing', 'delivered', 'failed')
        NOT NULL DEFAULT 'pending',
    attempt_count INT UNSIGNED NOT NULL DEFAULT 0,
    next_attempt_at DATETIME NULL,
    delivered_at DATETIME NULL,
    last_error VARCHAR(1000) NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_finance_import_outbox_intent (intent_key),
    INDEX idx_finance_import_outbox_delivery (
        status,
        next_attempt_at,
        id
    ),
    CONSTRAINT fk_finance_import_outbox_batch
        FOREIGN KEY (batch_id) REFERENCES finance_import_batches(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_finance_import_outbox_payload
        CHECK (JSON_TYPE(payload_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_finance_import_classification_before_update;
CREATE TRIGGER trg_finance_import_classification_before_update
BEFORE UPDATE ON finance_import_classification_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'finance_import_classification_events cannot be updated';

DROP TRIGGER IF EXISTS trg_finance_import_classification_before_delete;
CREATE TRIGGER trg_finance_import_classification_before_delete
BEFORE DELETE ON finance_import_classification_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'finance_import_classification_events cannot be deleted';

DROP TRIGGER IF EXISTS trg_finance_import_integrity_before_update;
CREATE TRIGGER trg_finance_import_integrity_before_update
BEFORE UPDATE ON finance_import_integrity_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'finance_import_integrity_events cannot be updated';

DROP TRIGGER IF EXISTS trg_finance_import_integrity_before_delete;
CREATE TRIGGER trg_finance_import_integrity_before_delete
BEFORE DELETE ON finance_import_integrity_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'finance_import_integrity_events cannot be deleted';

DROP TRIGGER IF EXISTS trg_finance_import_dispatch_before_update;
CREATE TRIGGER trg_finance_import_dispatch_before_update
BEFORE UPDATE ON finance_import_dispatch_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'finance_import_dispatch_events cannot be updated';

DROP TRIGGER IF EXISTS trg_finance_import_dispatch_before_delete;
CREATE TRIGGER trg_finance_import_dispatch_before_delete
BEFORE DELETE ON finance_import_dispatch_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'finance_import_dispatch_events cannot be deleted';

DROP TRIGGER IF EXISTS trg_finance_import_reconciliation_before_update;
CREATE TRIGGER trg_finance_import_reconciliation_before_update
BEFORE UPDATE ON finance_import_reconciliation_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'finance_import_reconciliation_receipts cannot be updated';

DROP TRIGGER IF EXISTS trg_finance_import_reconciliation_before_delete;
CREATE TRIGGER trg_finance_import_reconciliation_before_delete
BEFORE DELETE ON finance_import_reconciliation_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'finance_import_reconciliation_receipts cannot be deleted';

DROP TRIGGER IF EXISTS trg_finance_import_apply_receipt_before_update;
CREATE TRIGGER trg_finance_import_apply_receipt_before_update
BEFORE UPDATE ON finance_import_apply_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'finance_import_apply_receipts cannot be updated';

DROP TRIGGER IF EXISTS trg_finance_import_apply_receipt_before_delete;
CREATE TRIGGER trg_finance_import_apply_receipt_before_delete
BEFORE DELETE ON finance_import_apply_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'finance_import_apply_receipts cannot be deleted';

DROP TRIGGER IF EXISTS trg_finance_import_correction_receipt_before_update;
CREATE TRIGGER trg_finance_import_correction_receipt_before_update
BEFORE UPDATE ON finance_import_correction_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'finance_import_correction_receipts cannot be updated';

DROP TRIGGER IF EXISTS trg_finance_import_correction_receipt_before_delete;
CREATE TRIGGER trg_finance_import_correction_receipt_before_delete
BEFORE DELETE ON finance_import_correction_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'finance_import_correction_receipts cannot be deleted';
-- END SOURCE: db/schema_parts/121_finance_import_preview_apply.sql

-- BEGIN SOURCE: db/schema_parts/122_order_contract_completion_workflow.sql
-- Additive immutable receipt for the Orders contract-completion workflow.

CREATE TABLE IF NOT EXISTS order_contract_completion_apply_receipts (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    idempotency_key VARCHAR(191) NOT NULL,
    command_fingerprint CHAR(64) NOT NULL,
    preview_fingerprint CHAR(64) NOT NULL,
    case_no VARCHAR(50) NOT NULL,
    contract_event_id BIGINT NOT NULL,
    lifecycle_event_id BIGINT UNSIGNED NOT NULL,
    order_version BIGINT UNSIGNED NOT NULL,
    lifecycle_status ENUM(
        '洽談中',
        '訂單成立',
        '服務中',
        '訂單完成',
        '訂單取消'
    ) NOT NULL,
    contract_identity VARCHAR(191) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    result_snapshot JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_order_contract_completion_receipt_key (idempotency_key),
    CONSTRAINT fk_order_contract_completion_receipt_order
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_order_contract_completion_receipt_contract_event
        FOREIGN KEY (contract_event_id)
        REFERENCES order_contract_flow_events(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_order_contract_completion_receipt_lifecycle
        FOREIGN KEY (lifecycle_event_id, case_no)
        REFERENCES order_lifecycle_state_events(id, case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_order_contract_completion_receipt_fingerprints
        CHECK (
            command_fingerprint REGEXP '^[0-9a-f]{64}$'
            AND preview_fingerprint REGEXP '^[0-9a-f]{64}$'
        ),
    CONSTRAINT chk_order_contract_completion_receipt_text
        CHECK (
            CHAR_LENGTH(TRIM(contract_identity)) > 0
            AND CHAR_LENGTH(TRIM(correlation_id)) > 0
        ),
    CONSTRAINT chk_order_contract_completion_receipt_snapshot
        CHECK (JSON_TYPE(result_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_order_contract_completion_receipts_before_update;
CREATE TRIGGER trg_order_contract_completion_receipts_before_update
BEFORE UPDATE ON order_contract_completion_apply_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'order_contract_completion_apply_receipts cannot be updated';

DROP TRIGGER IF EXISTS trg_order_contract_completion_receipts_before_delete;
CREATE TRIGGER trg_order_contract_completion_receipts_before_delete
BEFORE DELETE ON order_contract_completion_apply_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'order_contract_completion_apply_receipts cannot be deleted';
-- END SOURCE: db/schema_parts/122_order_contract_completion_workflow.sql

-- BEGIN SOURCE: db/schema_parts/123_order_reopen_workflow.sql
-- Additive immutable events and receipts for controlled order reopening.

CREATE TABLE IF NOT EXISTS order_reopen_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    case_no VARCHAR(50) NOT NULL,
    cancellation_event_id BIGINT NOT NULL,
    before_status ENUM(
        '洽談中',
        '訂單成立',
        '服務中',
        '訂單完成',
        '訂單取消'
    ) NOT NULL,
    after_status ENUM(
        '洽談中',
        '訂單成立',
        '服務中',
        '訂單完成',
        '訂單取消'
    ) NOT NULL,
    expected_order_version BIGINT UNSIGNED NOT NULL,
    resulting_order_version BIGINT UNSIGNED NOT NULL,
    preview_fingerprint CHAR(64) NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    actor VARCHAR(100) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_order_reopen_event_key (idempotency_key),
    UNIQUE KEY uq_order_reopen_event_owner (id, case_no),
    INDEX idx_order_reopen_cancellation (
        cancellation_event_id,
        case_no
    ),
    CONSTRAINT fk_order_reopen_event_order
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_order_reopen_event_cancellation
        FOREIGN KEY (cancellation_event_id, case_no)
        REFERENCES order_cancellation_events(id, case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_order_reopen_event_version
        CHECK (resulting_order_version = expected_order_version + 1),
    CONSTRAINT chk_order_reopen_event_status
        CHECK (
            before_status = '訂單取消'
            AND after_status IN ('洽談中', '訂單成立', '服務中')
        ),
    CONSTRAINT chk_order_reopen_event_fingerprint
        CHECK (preview_fingerprint REGEXP '^[0-9a-f]{64}$'),
    CONSTRAINT chk_order_reopen_event_text
        CHECK (
            CHAR_LENGTH(TRIM(idempotency_key)) > 0
            AND CHAR_LENGTH(TRIM(actor)) > 0
            AND CHAR_LENGTH(TRIM(reason)) > 0
            AND CHAR_LENGTH(TRIM(correlation_id)) > 0
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS order_reopen_apply_receipts (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    idempotency_key VARCHAR(191) NOT NULL,
    command_fingerprint CHAR(64) NOT NULL,
    preview_fingerprint CHAR(64) NOT NULL,
    case_no VARCHAR(50) NOT NULL,
    reopen_event_id BIGINT NOT NULL,
    cancellation_control_event_id BIGINT UNSIGNED NOT NULL,
    lifecycle_event_id BIGINT UNSIGNED NOT NULL,
    cancellation_event_id BIGINT NOT NULL,
    order_version BIGINT UNSIGNED NOT NULL,
    lifecycle_status ENUM(
        '洽談中',
        '訂單成立',
        '服務中',
        '訂單完成',
        '訂單取消'
    ) NOT NULL,
    requires_fresh_scheduling_preview TINYINT(1) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    result_snapshot JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_order_reopen_receipt_key (idempotency_key),
    CONSTRAINT fk_order_reopen_receipt_order
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_order_reopen_receipt_event
        FOREIGN KEY (reopen_event_id, case_no)
        REFERENCES order_reopen_events(id, case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_order_reopen_receipt_control
        FOREIGN KEY (cancellation_control_event_id)
        REFERENCES order_lifecycle_control_events(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_order_reopen_receipt_lifecycle
        FOREIGN KEY (lifecycle_event_id, case_no)
        REFERENCES order_lifecycle_state_events(id, case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_order_reopen_receipt_cancellation
        FOREIGN KEY (cancellation_event_id, case_no)
        REFERENCES order_cancellation_events(id, case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_order_reopen_receipt_fingerprints
        CHECK (
            command_fingerprint REGEXP '^[0-9a-f]{64}$'
            AND preview_fingerprint REGEXP '^[0-9a-f]{64}$'
        ),
    CONSTRAINT chk_order_reopen_receipt_result
        CHECK (
            lifecycle_status IN ('洽談中', '訂單成立', '服務中')
            AND requires_fresh_scheduling_preview = 1
            AND JSON_TYPE(result_snapshot) = 'OBJECT'
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_order_reopen_events_before_update;
CREATE TRIGGER trg_order_reopen_events_before_update
BEFORE UPDATE ON order_reopen_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'order_reopen_events records cannot be updated';

DROP TRIGGER IF EXISTS trg_order_reopen_events_before_delete;
CREATE TRIGGER trg_order_reopen_events_before_delete
BEFORE DELETE ON order_reopen_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'order_reopen_events records cannot be deleted';

DROP TRIGGER IF EXISTS trg_order_reopen_receipts_before_update;
CREATE TRIGGER trg_order_reopen_receipts_before_update
BEFORE UPDATE ON order_reopen_apply_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'order_reopen_apply_receipts records cannot be updated';

DROP TRIGGER IF EXISTS trg_order_reopen_receipts_before_delete;
CREATE TRIGGER trg_order_reopen_receipts_before_delete
BEFORE DELETE ON order_reopen_apply_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'order_reopen_apply_receipts records cannot be deleted';
-- END SOURCE: db/schema_parts/123_order_reopen_workflow.sql

-- BEGIN SOURCE: db/schema_parts/124_case_architecture_bootstrap.sql
-- Canonical first-use bootstrap for Client Finance, Payroll, and Scheduling.

-- The version is immutable so later rate changes create a new policy identity.
INSERT INTO payroll_rate_policies (
    policy_version,
    policy_kind,
    hourly_rate_ntd,
    effective_from,
    effective_until
)
SELECT 'approved-rates-v1', 'citizen', 300, '1900-01-01', NULL
WHERE NOT EXISTS (
    SELECT 1 FROM payroll_rate_policies
    WHERE policy_version = 'approved-rates-v1'
      AND policy_kind = 'citizen'
);

INSERT INTO payroll_rate_policies (
    policy_version,
    policy_kind,
    hourly_rate_ntd,
    effective_from,
    effective_until
)
SELECT 'approved-rates-v1', 'subsidized_citizen', 350, '1900-01-01', NULL
WHERE NOT EXISTS (
    SELECT 1 FROM payroll_rate_policies
    WHERE policy_version = 'approved-rates-v1'
      AND policy_kind = 'subsidized_citizen'
);

INSERT INTO payroll_rate_policies (
    policy_version,
    policy_kind,
    hourly_rate_ntd,
    effective_from,
    effective_until
)
SELECT 'approved-rates-v1', 'non_citizen', 320, '1900-01-01', NULL
WHERE NOT EXISTS (
    SELECT 1 FROM payroll_rate_policies
    WHERE policy_version = 'approved-rates-v1'
      AND policy_kind = 'non_citizen'
);

CREATE TABLE IF NOT EXISTS case_architecture_bootstrap_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    case_no VARCHAR(50) NOT NULL,
    order_version BIGINT UNSIGNED NOT NULL,
    client_payment_terms_event_id BIGINT NOT NULL,
    client_policy_version VARCHAR(100) NOT NULL,
    client_hourly_rate_ntd BIGINT NOT NULL,
    payroll_policy_version VARCHAR(100) NOT NULL,
    payroll_policy_kind ENUM(
        'citizen',
        'subsidized_citizen',
        'non_citizen'
    ) NOT NULL,
    payroll_hourly_rate_ntd BIGINT NOT NULL,
    source_identity_status VARCHAR(100) NOT NULL,
    candidate_fingerprint CHAR(64) NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    actor VARCHAR(100) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_case_architecture_bootstrap_case (case_no),
    UNIQUE KEY uq_case_architecture_bootstrap_idempotency (idempotency_key),
    UNIQUE KEY uq_case_architecture_bootstrap_terms_event (
        client_payment_terms_event_id
    ),
    CONSTRAINT fk_case_architecture_bootstrap_order
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_case_architecture_bootstrap_terms_event
        FOREIGN KEY (client_payment_terms_event_id)
        REFERENCES client_payment_terms_events(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_case_architecture_bootstrap_payroll_policy
        FOREIGN KEY (payroll_policy_version, payroll_policy_kind)
        REFERENCES payroll_rate_policies(policy_version, policy_kind)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_case_architecture_bootstrap_amounts
        CHECK (
            client_hourly_rate_ntd > 0
            AND payroll_hourly_rate_ntd > 0
        ),
    CONSTRAINT chk_case_architecture_bootstrap_fingerprint
        CHECK (candidate_fingerprint REGEXP '^[0-9a-f]{64}$'),
    CONSTRAINT chk_case_architecture_bootstrap_text
        CHECK (
            CHAR_LENGTH(TRIM(source_identity_status)) > 0
            AND CHAR_LENGTH(TRIM(actor)) > 0
            AND CHAR_LENGTH(TRIM(reason)) > 0
            AND CHAR_LENGTH(TRIM(correlation_id)) > 0
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS case_payroll_rate_policy_snapshots (
    case_no VARCHAR(50) PRIMARY KEY,
    policy_version VARCHAR(100) NOT NULL,
    policy_kind ENUM(
        'citizen',
        'subsidized_citizen',
        'non_citizen'
    ) NOT NULL,
    hourly_rate_ntd BIGINT NOT NULL,
    source_identity_status VARCHAR(100) NOT NULL,
    source_event_id BIGINT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_case_payroll_policy_source_event (source_event_id),
    CONSTRAINT fk_case_payroll_policy_order
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_case_payroll_policy_definition
        FOREIGN KEY (policy_version, policy_kind)
        REFERENCES payroll_rate_policies(policy_version, policy_kind)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_case_payroll_policy_source_event
        FOREIGN KEY (source_event_id)
        REFERENCES case_architecture_bootstrap_events(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_case_payroll_policy_amount
        CHECK (hourly_rate_ntd > 0),
    CONSTRAINT chk_case_payroll_policy_identity
        CHECK (CHAR_LENGTH(TRIM(source_identity_status)) > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS case_architecture_bootstrap_receipts (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    idempotency_key VARCHAR(191) NOT NULL,
    command_fingerprint CHAR(64) NOT NULL,
    preview_fingerprint CHAR(64) NOT NULL,
    case_no VARCHAR(50) NOT NULL,
    bootstrap_event_id BIGINT NOT NULL,
    order_version BIGINT UNSIGNED NOT NULL,
    client_finance_version BIGINT UNSIGNED NOT NULL,
    payroll_version BIGINT UNSIGNED NOT NULL,
    scheduling_version BIGINT UNSIGNED NOT NULL,
    scheduling_generation INT UNSIGNED NOT NULL,
    bootstrap_created TINYINT(1) NOT NULL,
    result_snapshot JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_case_architecture_bootstrap_receipt_key (idempotency_key),
    CONSTRAINT fk_case_architecture_bootstrap_receipt_order
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_case_architecture_bootstrap_receipt_event
        FOREIGN KEY (bootstrap_event_id)
        REFERENCES case_architecture_bootstrap_events(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_case_architecture_receipt_fingerprints
        CHECK (
            command_fingerprint REGEXP '^[0-9a-f]{64}$'
            AND preview_fingerprint REGEXP '^[0-9a-f]{64}$'
        ),
    CONSTRAINT chk_case_architecture_receipt_initial_versions
        CHECK (
            client_finance_version = 0
            AND payroll_version = 0
            AND scheduling_version = 0
            AND scheduling_generation = 0
        ),
    CONSTRAINT chk_case_architecture_receipt_created
        CHECK (bootstrap_created IN (0, 1)),
    CONSTRAINT chk_case_architecture_receipt_snapshot
        CHECK (JSON_TYPE(result_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_case_architecture_bootstrap_events_before_update;
CREATE TRIGGER trg_case_architecture_bootstrap_events_before_update
BEFORE UPDATE ON case_architecture_bootstrap_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'case_architecture_bootstrap_events records cannot be updated';

DROP TRIGGER IF EXISTS trg_case_architecture_bootstrap_events_before_delete;
CREATE TRIGGER trg_case_architecture_bootstrap_events_before_delete
BEFORE DELETE ON case_architecture_bootstrap_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'case_architecture_bootstrap_events records cannot be deleted';

DROP TRIGGER IF EXISTS trg_case_payroll_policy_snapshots_before_update;
CREATE TRIGGER trg_case_payroll_policy_snapshots_before_update
BEFORE UPDATE ON case_payroll_rate_policy_snapshots
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'case_payroll_rate_policy_snapshots records cannot be updated';

DROP TRIGGER IF EXISTS trg_case_payroll_policy_snapshots_before_delete;
CREATE TRIGGER trg_case_payroll_policy_snapshots_before_delete
BEFORE DELETE ON case_payroll_rate_policy_snapshots
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'case_payroll_rate_policy_snapshots records cannot be deleted';

DROP TRIGGER IF EXISTS trg_case_architecture_bootstrap_receipts_before_update;
CREATE TRIGGER trg_case_architecture_bootstrap_receipts_before_update
BEFORE UPDATE ON case_architecture_bootstrap_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'case_architecture_bootstrap_receipts records cannot be updated';

DROP TRIGGER IF EXISTS trg_case_architecture_bootstrap_receipts_before_delete;
CREATE TRIGGER trg_case_architecture_bootstrap_receipts_before_delete
BEFORE DELETE ON case_architecture_bootstrap_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'case_architecture_bootstrap_receipts records cannot be deleted';
-- END SOURCE: db/schema_parts/124_case_architecture_bootstrap.sql

-- BEGIN SOURCE: db/schema_parts/125_government_subsidy_domain.sql
-- Additive Government Subsidy owner, immutable audit, and Apply receipts.

CREATE TABLE IF NOT EXISTS government_subsidy_batch_accounts (
    batch_id BIGINT PRIMARY KEY,
    aggregate_version BIGINT UNSIGNED NOT NULL,
    requested_total_ntd BIGINT UNSIGNED NOT NULL,
    approved_total_ntd BIGINT UNSIGNED NOT NULL,
    net_allocated_ntd BIGINT UNSIGNED NOT NULL,
    outstanding_ntd BIGINT UNSIGNED NOT NULL,
    status ENUM(
        'draft',
        'submitted',
        'approved',
        'partially_paid',
        'paid'
    ) NOT NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_government_subsidy_account_batch
        FOREIGN KEY (batch_id) REFERENCES subsidy_claim_batches(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_government_subsidy_account_version
        CHECK (aggregate_version > 0),
    CONSTRAINT chk_government_subsidy_account_totals
        CHECK (
            approved_total_ntd <= requested_total_ntd
            AND net_allocated_ntd <= approved_total_ntd
            AND outstanding_ntd = approved_total_ntd - net_allocated_ntd
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

ALTER TABLE government_subsidy_transactions
    ADD COLUMN expected_batch_version BIGINT UNSIGNED NULL
        AFTER reversal_target_type,
    ADD COLUMN resulting_batch_version BIGINT UNSIGNED NULL
        AFTER expected_batch_version,
    ADD COLUMN preview_fingerprint CHAR(64) NULL
        AFTER resulting_batch_version,
    ADD COLUMN idempotency_key VARCHAR(191) NULL
        AFTER preview_fingerprint,
    ADD COLUMN actor VARCHAR(100) NULL
        AFTER idempotency_key,
    ADD COLUMN reason VARCHAR(500) NULL
        AFTER actor,
    ADD COLUMN correlation_id VARCHAR(191) NULL
        AFTER reason,
    ADD UNIQUE KEY uq_government_subsidy_transaction_idempotency (
        idempotency_key
    ),
    ADD CONSTRAINT chk_government_subsidy_transaction_new_version
        CHECK (
            expected_batch_version IS NULL
            OR resulting_batch_version = expected_batch_version + 1
        ),
    ADD CONSTRAINT chk_government_subsidy_transaction_new_fingerprint
        CHECK (
            preview_fingerprint IS NULL
            OR preview_fingerprint REGEXP '^[0-9a-f]{64}$'
        );

CREATE TABLE IF NOT EXISTS government_subsidy_projection_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    batch_id BIGINT NOT NULL,
    transaction_id BIGINT NOT NULL,
    before_status ENUM(
        'draft',
        'submitted',
        'approved',
        'partially_paid',
        'paid'
    ) NOT NULL,
    after_status ENUM(
        'draft',
        'submitted',
        'approved',
        'partially_paid',
        'paid'
    ) NOT NULL,
    before_net_allocated_ntd BIGINT UNSIGNED NOT NULL,
    after_net_allocated_ntd BIGINT UNSIGNED NOT NULL,
    outstanding_ntd BIGINT UNSIGNED NOT NULL,
    expected_batch_version BIGINT UNSIGNED NOT NULL,
    resulting_batch_version BIGINT UNSIGNED NOT NULL,
    preview_fingerprint CHAR(64) NOT NULL,
    actor VARCHAR(100) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_government_subsidy_projection_event_key (
        idempotency_key
    ),
    UNIQUE KEY uq_government_subsidy_projection_event_identity (
        id,
        batch_id
    ),
    CONSTRAINT fk_government_subsidy_projection_event_account
        FOREIGN KEY (batch_id)
        REFERENCES government_subsidy_batch_accounts(batch_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_government_subsidy_projection_event_transaction
        FOREIGN KEY (transaction_id, batch_id)
        REFERENCES government_subsidy_transactions(id, claim_batch_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_government_subsidy_projection_event_version
        CHECK (resulting_batch_version = expected_batch_version + 1),
    CONSTRAINT chk_government_subsidy_projection_event_fingerprint
        CHECK (preview_fingerprint REGEXP '^[0-9a-f]{64}$')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS government_subsidy_apply_receipts (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    idempotency_key VARCHAR(191) NOT NULL,
    command_fingerprint CHAR(64) NOT NULL,
    preview_fingerprint CHAR(64) NOT NULL,
    command_kind ENUM('receipt', 'reversal') NOT NULL,
    transaction_id BIGINT NOT NULL,
    batch_id BIGINT NOT NULL,
    batch_version BIGINT UNSIGNED NOT NULL,
    bank_fact_identity VARCHAR(191) NOT NULL,
    amount_ntd BIGINT UNSIGNED NOT NULL,
    allocation_count INT UNSIGNED NOT NULL,
    status ENUM(
        'draft',
        'submitted',
        'approved',
        'partially_paid',
        'paid'
    ) NOT NULL,
    outstanding_ntd BIGINT UNSIGNED NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    result_snapshot JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_government_subsidy_receipt_key (idempotency_key),
    CONSTRAINT fk_government_subsidy_receipt_transaction
        FOREIGN KEY (transaction_id, batch_id)
        REFERENCES government_subsidy_transactions(id, claim_batch_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_government_subsidy_receipt_fingerprints
        CHECK (
            command_fingerprint REGEXP '^[0-9a-f]{64}$'
            AND preview_fingerprint REGEXP '^[0-9a-f]{64}$'
        ),
    CONSTRAINT chk_government_subsidy_receipt_amount
        CHECK (amount_ntd > 0 AND allocation_count > 0),
    CONSTRAINT chk_government_subsidy_receipt_snapshot
        CHECK (JSON_TYPE(result_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS government_subsidy_outbox (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    batch_id BIGINT NOT NULL,
    transaction_id BIGINT NOT NULL,
    projection_event_id BIGINT NOT NULL,
    intent_key VARCHAR(191) NOT NULL,
    intent_type ENUM(
        'government_subsidy_receipt_applied',
        'government_subsidy_reversal_applied',
        'government_subsidy_anomaly_root_changed'
    ) NOT NULL,
    payload_snapshot JSON NOT NULL,
    status ENUM('pending', 'processing', 'delivered', 'failed')
        NOT NULL DEFAULT 'pending',
    attempt_count INT UNSIGNED NOT NULL DEFAULT 0,
    next_attempt_at DATETIME NULL,
    delivered_at DATETIME NULL,
    last_error VARCHAR(1000) NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_government_subsidy_outbox_intent (intent_key),
    INDEX idx_government_subsidy_outbox_delivery (
        status,
        next_attempt_at,
        id
    ),
    CONSTRAINT fk_government_subsidy_outbox_transaction
        FOREIGN KEY (transaction_id, batch_id)
        REFERENCES government_subsidy_transactions(id, claim_batch_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_government_subsidy_outbox_projection
        FOREIGN KEY (projection_event_id, batch_id)
        REFERENCES government_subsidy_projection_events(id, batch_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_government_subsidy_outbox_payload
        CHECK (JSON_TYPE(payload_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_government_subsidy_transactions_before_update;
CREATE TRIGGER trg_government_subsidy_transactions_before_update
BEFORE UPDATE ON government_subsidy_transactions
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'government_subsidy_transactions cannot be updated';

DROP TRIGGER IF EXISTS trg_government_subsidy_transactions_before_delete;
CREATE TRIGGER trg_government_subsidy_transactions_before_delete
BEFORE DELETE ON government_subsidy_transactions
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'government_subsidy_transactions cannot be deleted';

DROP TRIGGER IF EXISTS trg_government_subsidy_allocations_before_update;
CREATE TRIGGER trg_government_subsidy_allocations_before_update
BEFORE UPDATE ON government_subsidy_allocations
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'government_subsidy_allocations cannot be updated';

DROP TRIGGER IF EXISTS trg_government_subsidy_allocations_before_delete;
CREATE TRIGGER trg_government_subsidy_allocations_before_delete
BEFORE DELETE ON government_subsidy_allocations
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'government_subsidy_allocations cannot be deleted';

DROP TRIGGER IF EXISTS trg_government_subsidy_projection_events_before_update;
CREATE TRIGGER trg_government_subsidy_projection_events_before_update
BEFORE UPDATE ON government_subsidy_projection_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'government_subsidy_projection_events cannot be updated';

DROP TRIGGER IF EXISTS trg_government_subsidy_projection_events_before_delete;
CREATE TRIGGER trg_government_subsidy_projection_events_before_delete
BEFORE DELETE ON government_subsidy_projection_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'government_subsidy_projection_events cannot be deleted';

DROP TRIGGER IF EXISTS trg_government_subsidy_receipts_before_update;
CREATE TRIGGER trg_government_subsidy_receipts_before_update
BEFORE UPDATE ON government_subsidy_apply_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'government_subsidy_apply_receipts cannot be updated';

DROP TRIGGER IF EXISTS trg_government_subsidy_receipts_before_delete;
CREATE TRIGGER trg_government_subsidy_receipts_before_delete
BEFORE DELETE ON government_subsidy_apply_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'government_subsidy_apply_receipts cannot be deleted';
-- END SOURCE: db/schema_parts/125_government_subsidy_domain.sql

-- BEGIN SOURCE: db/schema_parts/126_client_refund_reversal.sql
-- Additive idempotency receipt SSOT for Client Refund and Client Reversal.

CREATE TABLE IF NOT EXISTS client_refund_reversal_apply_receipts (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    idempotency_key VARCHAR(191) NOT NULL,
    correction_type ENUM('refund', 'reversal') NOT NULL,
    command_fingerprint CHAR(64) NOT NULL,
    preview_fingerprint CHAR(64) NOT NULL,
    case_no VARCHAR(50) NOT NULL,
    resulting_account_version BIGINT UNSIGNED NOT NULL,
    result_snapshot JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_client_refund_reversal_receipt_key (idempotency_key),
    INDEX idx_client_refund_reversal_case (
        case_no,
        correction_type,
        created_at
    ),
    CONSTRAINT fk_client_refund_reversal_receipt_order
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_client_refund_reversal_fingerprints
        CHECK (
            command_fingerprint REGEXP '^[0-9a-f]{64}$'
            AND preview_fingerprint REGEXP '^[0-9a-f]{64}$'
        ),
    CONSTRAINT chk_client_refund_reversal_snapshot
        CHECK (JSON_TYPE(result_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_client_refund_reversal_receipt_before_update;
CREATE TRIGGER trg_client_refund_reversal_receipt_before_update
BEFORE UPDATE ON client_refund_reversal_apply_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client refund reversal receipts cannot be updated';

DROP TRIGGER IF EXISTS trg_client_refund_reversal_receipt_before_delete;
CREATE TRIGGER trg_client_refund_reversal_receipt_before_delete
BEFORE DELETE ON client_refund_reversal_apply_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client refund reversal receipts cannot be deleted';
-- END SOURCE: db/schema_parts/126_client_refund_reversal.sql

-- BEGIN SOURCE: db/schema_parts/127_anomaly_root_fact_projector.sql
-- Additive root-fact projector receipts and recovery snapshots.

CREATE TABLE IF NOT EXISTS anomaly_root_fact_projection_receipts (
    source_event_identity VARCHAR(191) PRIMARY KEY,
    event_payload_fingerprint CHAR(64) NOT NULL,
    alert_fingerprint CHAR(64) NOT NULL,
    source_version BIGINT UNSIGNED NOT NULL,
    predicate_active TINYINT(1) NOT NULL,
    workflow_version BIGINT UNSIGNED NULL,
    occurrence_recorded TINYINT(1) NOT NULL,
    processed_at DATETIME NOT NULL,
    CONSTRAINT chk_anomaly_root_receipt_event_fingerprint
        CHECK (event_payload_fingerprint REGEXP '^[0-9a-f]{64}$'),
    CONSTRAINT chk_anomaly_root_receipt_alert_fingerprint
        CHECK (alert_fingerprint REGEXP '^[0-9a-f]{64}$')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS anomaly_root_fact_snapshots (
    alert_fingerprint CHAR(64) PRIMARY KEY,
    source_event_identity VARCHAR(191) NOT NULL,
    source_version BIGINT UNSIGNED NOT NULL,
    source_occurred_at DATETIME NOT NULL,
    root_condition_active TINYINT(1) NOT NULL,
    integrity_blocker_active TINYINT(1) NOT NULL,
    amount_delta_ntd BIGINT NOT NULL,
    finance_import_row_id BIGINT NOT NULL,
    finance_import_batch_id BIGINT NOT NULL,
    affected_order_identities JSON NOT NULL,
    affected_obligation_identities JSON NOT NULL,
    domain_blockers JSON NOT NULL,
    reason_codes JSON NOT NULL,
    projection_freshness ENUM('current', 'stale') NOT NULL DEFAULT 'current',
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_anomaly_root_snapshot_alert
        FOREIGN KEY (alert_fingerprint)
        REFERENCES anomaly_current_alerts(fingerprint)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_anomaly_root_snapshot_row
        FOREIGN KEY (finance_import_row_id)
        REFERENCES finance_import_rows(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_anomaly_root_snapshot_batch
        FOREIGN KEY (finance_import_batch_id)
        REFERENCES finance_import_batches(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_anomaly_root_snapshot_orders
        CHECK (JSON_TYPE(affected_order_identities) = 'ARRAY'),
    CONSTRAINT chk_anomaly_root_snapshot_obligations
        CHECK (JSON_TYPE(affected_obligation_identities) = 'ARRAY'),
    CONSTRAINT chk_anomaly_root_snapshot_blockers
        CHECK (JSON_TYPE(domain_blockers) = 'ARRAY'),
    CONSTRAINT chk_anomaly_root_snapshot_reasons
        CHECK (JSON_TYPE(reason_codes) = 'ARRAY')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_anomaly_root_receipts_before_update;
CREATE TRIGGER trg_anomaly_root_receipts_before_update
BEFORE UPDATE ON anomaly_root_fact_projection_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'anomaly root fact projection receipts cannot be updated';

DROP TRIGGER IF EXISTS trg_anomaly_root_receipts_before_delete;
CREATE TRIGGER trg_anomaly_root_receipts_before_delete
BEFORE DELETE ON anomaly_root_fact_projection_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'anomaly root fact projection receipts cannot be deleted';
-- END SOURCE: db/schema_parts/127_anomaly_root_fact_projector.sql

-- BEGIN SOURCE: db/schema_parts/128_finance_import_ingestion.sql
-- Atomic workbook ingestion receipts. Formal accounting remains Preview/Apply owned.

CREATE TABLE IF NOT EXISTS finance_import_ingestion_receipts (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    idempotency_key VARCHAR(191) NOT NULL,
    command_fingerprint CHAR(64) NOT NULL,
    source_content_digest CHAR(64) NOT NULL,
    batch_id BIGINT NOT NULL,
    result_snapshot JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_finance_import_ingestion_receipt_key (idempotency_key),
    CONSTRAINT fk_finance_import_ingestion_receipt_batch
        FOREIGN KEY (batch_id) REFERENCES finance_import_batches(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_finance_import_ingestion_receipt_fingerprints
        CHECK (
            command_fingerprint REGEXP '^[0-9a-f]{64}$'
            AND source_content_digest REGEXP '^[0-9a-f]{64}$'
        ),
    CONSTRAINT chk_finance_import_ingestion_receipt_snapshot
        CHECK (JSON_TYPE(result_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_finance_import_ingestion_receipt_before_update;
CREATE TRIGGER trg_finance_import_ingestion_receipt_before_update
BEFORE UPDATE ON finance_import_ingestion_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'finance_import_ingestion_receipts cannot be updated';

DROP TRIGGER IF EXISTS trg_finance_import_ingestion_receipt_before_delete;
CREATE TRIGGER trg_finance_import_ingestion_receipt_before_delete
BEFORE DELETE ON finance_import_ingestion_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'finance_import_ingestion_receipts cannot be deleted';
-- END SOURCE: db/schema_parts/128_finance_import_ingestion.sql

-- BEGIN SOURCE: db/schema_parts/129_case_import.sql
-- Immutable evidence and replay receipts for atomic negotiated-case import.

CREATE TABLE IF NOT EXISTS case_import_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    case_no VARCHAR(50) NOT NULL,
    client_id INT NOT NULL,
    bootstrap_event_id BIGINT NOT NULL,
    source_fingerprint CHAR(64) NOT NULL,
    candidate_fingerprint CHAR(64) NOT NULL,
    source_snapshot JSON NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    actor VARCHAR(100) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_case_import_case (case_no),
    UNIQUE KEY uq_case_import_idempotency (idempotency_key),
    UNIQUE KEY uq_case_import_source (source_fingerprint),
    CONSTRAINT fk_case_import_order
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_case_import_client
        FOREIGN KEY (client_id) REFERENCES clients(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_case_import_bootstrap
        FOREIGN KEY (bootstrap_event_id)
        REFERENCES case_architecture_bootstrap_events(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_case_import_fingerprints
        CHECK (
            source_fingerprint REGEXP '^[0-9a-f]{64}$'
            AND candidate_fingerprint REGEXP '^[0-9a-f]{64}$'
        ),
    CONSTRAINT chk_case_import_snapshot
        CHECK (JSON_TYPE(source_snapshot) = 'OBJECT'),
    CONSTRAINT chk_case_import_text
        CHECK (
            CHAR_LENGTH(TRIM(actor)) > 0
            AND CHAR_LENGTH(TRIM(reason)) > 0
            AND CHAR_LENGTH(TRIM(correlation_id)) > 0
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS case_import_receipts (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    idempotency_key VARCHAR(191) NOT NULL,
    command_fingerprint CHAR(64) NOT NULL,
    source_fingerprint CHAR(64) NOT NULL,
    preview_fingerprint CHAR(64) NOT NULL,
    case_no VARCHAR(50) NOT NULL,
    client_id INT NOT NULL,
    import_event_id BIGINT NOT NULL,
    bootstrap_event_id BIGINT NOT NULL,
    order_version BIGINT UNSIGNED NOT NULL,
    client_finance_version BIGINT UNSIGNED NOT NULL,
    payroll_version BIGINT UNSIGNED NOT NULL,
    scheduling_version BIGINT UNSIGNED NOT NULL,
    scheduling_generation INT UNSIGNED NOT NULL,
    result_snapshot JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_case_import_receipt_key (idempotency_key),
    UNIQUE KEY uq_case_import_receipt_event (import_event_id),
    CONSTRAINT fk_case_import_receipt_order
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_case_import_receipt_client
        FOREIGN KEY (client_id) REFERENCES clients(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_case_import_receipt_import_event
        FOREIGN KEY (import_event_id) REFERENCES case_import_events(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_case_import_receipt_bootstrap_event
        FOREIGN KEY (bootstrap_event_id)
        REFERENCES case_architecture_bootstrap_events(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_case_import_receipt_fingerprints
        CHECK (
            command_fingerprint REGEXP '^[0-9a-f]{64}$'
            AND source_fingerprint REGEXP '^[0-9a-f]{64}$'
            AND preview_fingerprint REGEXP '^[0-9a-f]{64}$'
        ),
    CONSTRAINT chk_case_import_receipt_versions
        CHECK (
            order_version = 0
            AND client_finance_version = 0
            AND payroll_version = 0
            AND scheduling_version = 0
            AND scheduling_generation = 0
        ),
    CONSTRAINT chk_case_import_receipt_snapshot
        CHECK (JSON_TYPE(result_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_case_import_events_before_update;
CREATE TRIGGER trg_case_import_events_before_update
BEFORE UPDATE ON case_import_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'case_import_events records cannot be updated';

DROP TRIGGER IF EXISTS trg_case_import_events_before_delete;
CREATE TRIGGER trg_case_import_events_before_delete
BEFORE DELETE ON case_import_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'case_import_events records cannot be deleted';

DROP TRIGGER IF EXISTS trg_case_import_receipts_before_update;
CREATE TRIGGER trg_case_import_receipts_before_update
BEFORE UPDATE ON case_import_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'case_import_receipts records cannot be updated';

DROP TRIGGER IF EXISTS trg_case_import_receipts_before_delete;
CREATE TRIGGER trg_case_import_receipts_before_delete
BEFORE DELETE ON case_import_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'case_import_receipts records cannot be deleted';
-- END SOURCE: db/schema_parts/129_case_import.sql

-- BEGIN SOURCE: db/schema_parts/133_financial_adjustments.sql
-- Additive cross-domain financial adjustment SSOT and idempotency receipts.

CREATE TABLE IF NOT EXISTS financial_adjustments (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    adjustment_identity VARCHAR(191) NOT NULL,
    case_no VARCHAR(50) NOT NULL,
    adjustment_source_type ENUM(
        'preview_recalculation',
        'manual_extra'
    ) NOT NULL,
    source_event_identity VARCHAR(191) NOT NULL,
    amount_delta_ntd BIGINT NOT NULL,
    reason VARCHAR(255) NULL,
    reversal_of_adjustment_id BIGINT NULL,
    cancelled_at TIMESTAMP NULL,
    apply_idempotency_key VARCHAR(191) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_financial_adjustment_identity (adjustment_identity),
    UNIQUE KEY uq_financial_adjustment_apply_key (apply_idempotency_key),
    UNIQUE KEY uq_financial_adjustment_source (
        case_no,
        source_event_identity
    ),
    INDEX idx_financial_adjustment_case_created (
        case_no,
        created_at,
        id
    ),
    CONSTRAINT fk_financial_adjustment_order
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_financial_adjustment_reversal
        FOREIGN KEY (reversal_of_adjustment_id)
        REFERENCES financial_adjustments(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_financial_adjustment_amount
        CHECK (amount_delta_ntd <> 0),
    CONSTRAINT chk_financial_adjustment_reason
        CHECK (
            (
                adjustment_source_type = 'manual_extra'
                AND reason IS NOT NULL
                AND CHAR_LENGTH(TRIM(reason)) > 0
            )
            OR (
                adjustment_source_type = 'preview_recalculation'
                AND reason IS NULL
            )
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS financial_adjustment_staff_allocations (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    financial_adjustment_id BIGINT NOT NULL,
    assignment_id BIGINT NOT NULL,
    amount_delta_ntd BIGINT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_financial_adjustment_staff_assignment (
        financial_adjustment_id,
        assignment_id
    ),
    INDEX idx_financial_adjustment_staff_assignment (
        assignment_id,
        financial_adjustment_id
    ),
    CONSTRAINT fk_financial_adjustment_staff_parent
        FOREIGN KEY (financial_adjustment_id)
        REFERENCES financial_adjustments(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_financial_adjustment_staff_assignment
        FOREIGN KEY (assignment_id)
        REFERENCES case_staff_assignments(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_financial_adjustment_staff_amount
        CHECK (amount_delta_ntd <> 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS financial_adjustment_apply_receipts (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    idempotency_key VARCHAR(191) NOT NULL,
    command_fingerprint CHAR(64) NOT NULL,
    preview_fingerprint CHAR(64) NOT NULL,
    case_no VARCHAR(50) NOT NULL,
    resulting_client_account_version BIGINT UNSIGNED NOT NULL,
    resulting_payroll_version BIGINT UNSIGNED NOT NULL,
    result_snapshot JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_financial_adjustment_receipt_key (idempotency_key),
    CONSTRAINT fk_financial_adjustment_receipt_order
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_financial_adjustment_receipt_fingerprints
        CHECK (
            command_fingerprint REGEXP '^[0-9a-f]{64}$'
            AND preview_fingerprint REGEXP '^[0-9a-f]{64}$'
        ),
    CONSTRAINT chk_financial_adjustment_receipt_snapshot
        CHECK (JSON_TYPE(result_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_financial_adjustments_before_update;
CREATE TRIGGER trg_financial_adjustments_before_update
BEFORE UPDATE ON financial_adjustments
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'financial adjustments cannot be updated';

DROP TRIGGER IF EXISTS trg_financial_adjustments_before_delete;
CREATE TRIGGER trg_financial_adjustments_before_delete
BEFORE DELETE ON financial_adjustments
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'financial adjustments cannot be deleted';

DROP TRIGGER IF EXISTS trg_financial_adjustment_staff_before_update;
CREATE TRIGGER trg_financial_adjustment_staff_before_update
BEFORE UPDATE ON financial_adjustment_staff_allocations
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'financial adjustment staff allocations cannot be updated';

DROP TRIGGER IF EXISTS trg_financial_adjustment_staff_before_delete;
CREATE TRIGGER trg_financial_adjustment_staff_before_delete
BEFORE DELETE ON financial_adjustment_staff_allocations
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'financial adjustment staff allocations cannot be deleted';

DROP TRIGGER IF EXISTS trg_financial_adjustment_receipt_before_update;
CREATE TRIGGER trg_financial_adjustment_receipt_before_update
BEFORE UPDATE ON financial_adjustment_apply_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'financial adjustment receipts cannot be updated';

DROP TRIGGER IF EXISTS trg_financial_adjustment_receipt_before_delete;
CREATE TRIGGER trg_financial_adjustment_receipt_before_delete
BEFORE DELETE ON financial_adjustment_apply_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'financial adjustment receipts cannot be deleted';
-- END SOURCE: db/schema_parts/133_financial_adjustments.sql

-- BEGIN SOURCE: db/schema_parts/134_government_subsidy_claim_workflow.sql
-- Additive Government Subsidy claim planning, submission, and approval owner.

CREATE TABLE IF NOT EXISTS government_subsidy_claim_submission_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    batch_id BIGINT NOT NULL,
    expected_batch_version BIGINT UNSIGNED NOT NULL,
    resulting_batch_version BIGINT UNSIGNED NOT NULL,
    preview_fingerprint CHAR(64) NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    actor VARCHAR(100) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    submitted_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_government_subsidy_submission_key (idempotency_key),
    UNIQUE KEY uq_government_subsidy_submission_batch (batch_id),
    CONSTRAINT fk_government_subsidy_submission_batch
        FOREIGN KEY (batch_id) REFERENCES subsidy_claim_batches(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_government_subsidy_submission_version
        CHECK (resulting_batch_version = expected_batch_version + 1),
    CONSTRAINT chk_government_subsidy_submission_fingerprint
        CHECK (preview_fingerprint REGEXP '^[0-9a-f]{64}$'),
    CONSTRAINT chk_government_subsidy_submission_actor
        CHECK (CHAR_LENGTH(TRIM(actor)) > 0),
    CONSTRAINT chk_government_subsidy_submission_reason
        CHECK (CHAR_LENGTH(TRIM(reason)) > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS government_subsidy_claim_approval_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    batch_id BIGINT NOT NULL,
    approved_total_ntd BIGINT UNSIGNED NOT NULL,
    expected_batch_version BIGINT UNSIGNED NOT NULL,
    resulting_batch_version BIGINT UNSIGNED NOT NULL,
    preview_fingerprint CHAR(64) NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    actor VARCHAR(100) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    approved_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_government_subsidy_approval_key (idempotency_key),
    UNIQUE KEY uq_government_subsidy_approval_batch (batch_id),
    UNIQUE KEY uq_government_subsidy_approval_identity (id, batch_id),
    CONSTRAINT fk_government_subsidy_approval_batch
        FOREIGN KEY (batch_id) REFERENCES subsidy_claim_batches(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_government_subsidy_approval_version
        CHECK (resulting_batch_version = expected_batch_version + 1),
    CONSTRAINT chk_government_subsidy_approval_fingerprint
        CHECK (preview_fingerprint REGEXP '^[0-9a-f]{64}$'),
    CONSTRAINT chk_government_subsidy_approval_actor
        CHECK (CHAR_LENGTH(TRIM(actor)) > 0),
    CONSTRAINT chk_government_subsidy_approval_reason
        CHECK (CHAR_LENGTH(TRIM(reason)) > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS government_subsidy_claim_approval_items (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    approval_event_id BIGINT NOT NULL,
    batch_id BIGINT NOT NULL,
    claim_item_id BIGINT NOT NULL,
    approved_amount_ntd BIGINT UNSIGNED NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_government_subsidy_approval_item (
        approval_event_id,
        claim_item_id
    ),
    CONSTRAINT fk_government_subsidy_approval_item_event
        FOREIGN KEY (approval_event_id, batch_id)
        REFERENCES government_subsidy_claim_approval_events(id, batch_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_government_subsidy_approval_item_claim
        FOREIGN KEY (claim_item_id, batch_id)
        REFERENCES subsidy_claim_batch_items(id, batch_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS government_subsidy_claim_outbox (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    batch_id BIGINT NOT NULL,
    intent_key VARCHAR(191) NOT NULL,
    intent_type ENUM('plan', 'submit', 'approval') NOT NULL,
    payload_snapshot JSON NOT NULL,
    status ENUM('pending', 'processing', 'delivered', 'failed')
        NOT NULL DEFAULT 'pending',
    attempt_count INT UNSIGNED NOT NULL DEFAULT 0,
    next_attempt_at DATETIME NULL,
    delivered_at DATETIME NULL,
    last_error VARCHAR(1000) NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_government_subsidy_claim_outbox_intent (intent_key),
    INDEX idx_government_subsidy_claim_outbox_delivery (
        status,
        next_attempt_at,
        id
    ),
    CONSTRAINT fk_government_subsidy_claim_outbox_batch
        FOREIGN KEY (batch_id) REFERENCES subsidy_claim_batches(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_government_subsidy_claim_outbox_payload
        CHECK (JSON_TYPE(payload_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS government_subsidy_claim_apply_receipts (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    idempotency_key VARCHAR(191) NOT NULL,
    command_fingerprint CHAR(64) NOT NULL,
    preview_fingerprint CHAR(64) NOT NULL,
    command_kind ENUM('plan', 'submit', 'approval') NOT NULL,
    batch_id BIGINT NOT NULL,
    batch_version BIGINT UNSIGNED NOT NULL,
    status ENUM(
        'draft',
        'submitted',
        'approved',
        'partially_paid',
        'paid'
    ) NOT NULL,
    item_count INT UNSIGNED NOT NULL,
    total_ntd BIGINT UNSIGNED NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    result_snapshot JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_government_subsidy_claim_receipt_key (idempotency_key),
    CONSTRAINT fk_government_subsidy_claim_receipt_batch
        FOREIGN KEY (batch_id) REFERENCES subsidy_claim_batches(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_government_subsidy_claim_receipt_fingerprints
        CHECK (
            command_fingerprint REGEXP '^[0-9a-f]{64}$'
            AND preview_fingerprint REGEXP '^[0-9a-f]{64}$'
        ),
    CONSTRAINT chk_government_subsidy_claim_receipt_items
        CHECK (item_count > 0),
    CONSTRAINT chk_government_subsidy_claim_receipt_snapshot
        CHECK (JSON_TYPE(result_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_government_subsidy_submission_before_update;
CREATE TRIGGER trg_government_subsidy_submission_before_update
BEFORE UPDATE ON government_subsidy_claim_submission_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'government subsidy submission cannot be updated';

DROP TRIGGER IF EXISTS trg_government_subsidy_submission_before_delete;
CREATE TRIGGER trg_government_subsidy_submission_before_delete
BEFORE DELETE ON government_subsidy_claim_submission_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'government subsidy submission cannot be deleted';

DROP TRIGGER IF EXISTS trg_government_subsidy_approval_before_update;
CREATE TRIGGER trg_government_subsidy_approval_before_update
BEFORE UPDATE ON government_subsidy_claim_approval_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'government subsidy approval cannot be updated';

DROP TRIGGER IF EXISTS trg_government_subsidy_approval_before_delete;
CREATE TRIGGER trg_government_subsidy_approval_before_delete
BEFORE DELETE ON government_subsidy_claim_approval_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'government subsidy approval cannot be deleted';

DROP TRIGGER IF EXISTS trg_government_subsidy_approval_item_before_update;
CREATE TRIGGER trg_government_subsidy_approval_item_before_update
BEFORE UPDATE ON government_subsidy_claim_approval_items
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'government subsidy approval item cannot be updated';

DROP TRIGGER IF EXISTS trg_government_subsidy_approval_item_before_delete;
CREATE TRIGGER trg_government_subsidy_approval_item_before_delete
BEFORE DELETE ON government_subsidy_claim_approval_items
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'government subsidy approval item cannot be deleted';

DROP TRIGGER IF EXISTS trg_government_subsidy_claim_receipt_before_update;
CREATE TRIGGER trg_government_subsidy_claim_receipt_before_update
BEFORE UPDATE ON government_subsidy_claim_apply_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'government subsidy claim receipt cannot be updated';

DROP TRIGGER IF EXISTS trg_government_subsidy_claim_receipt_before_delete;
CREATE TRIGGER trg_government_subsidy_claim_receipt_before_delete
BEFORE DELETE ON government_subsidy_claim_apply_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'government subsidy claim receipt cannot be deleted';
-- END SOURCE: db/schema_parts/134_government_subsidy_claim_workflow.sql

-- BEGIN SOURCE: db/schema_parts/135_client_only_financial_adjustments.sql
-- Add explicit client-only financial adjustments without payroll side effects.

SET @financial_adjustment_scope_exists = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'financial_adjustments'
      AND COLUMN_NAME = 'adjustment_scope'
);
SET @financial_adjustment_scope_sql = IF(
    @financial_adjustment_scope_exists = 0,
    'ALTER TABLE financial_adjustments ADD COLUMN adjustment_scope ENUM(''client_only'',''client_and_staff'') NOT NULL DEFAULT ''client_and_staff'' AFTER adjustment_source_type',
    'SELECT 1'
);
PREPARE financial_adjustment_scope_statement
    FROM @financial_adjustment_scope_sql;
EXECUTE financial_adjustment_scope_statement;
DEALLOCATE PREPARE financial_adjustment_scope_statement;

ALTER TABLE financial_adjustment_apply_receipts
    MODIFY COLUMN resulting_payroll_version BIGINT UNSIGNED NULL;
-- END SOURCE: db/schema_parts/135_client_only_financial_adjustments.sql

-- BEGIN SOURCE: db/schema_parts/136_beclass_import_review.sql
-- Append-only invalid-row evidence and correction workflow for BeClass imports.

CREATE TABLE IF NOT EXISTS beclass_import_review_rows (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    review_identity VARCHAR(191) NOT NULL,
    source_kind ENUM('client', 'staff') NOT NULL,
    source_event_identity VARCHAR(191) NOT NULL,
    source_sheet VARCHAR(191) NOT NULL,
    source_row INT UNSIGNED NOT NULL,
    masked_identifier VARCHAR(191) NOT NULL,
    source_fingerprint CHAR(64) NOT NULL,
    source_payload JSON NOT NULL,
    issue_codes JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_beclass_review_identity (review_identity),
    UNIQUE KEY uq_beclass_review_source_event (
        source_kind,
        source_event_identity
    ),
    CONSTRAINT chk_beclass_review_fingerprint
        CHECK (source_fingerprint REGEXP '^[0-9a-f]{64}$'),
    CONSTRAINT chk_beclass_review_payload
        CHECK (JSON_TYPE(source_payload) = 'OBJECT'),
    CONSTRAINT chk_beclass_review_issues
        CHECK (
            JSON_TYPE(issue_codes) = 'ARRAY'
            AND JSON_LENGTH(issue_codes) > 0
        ),
    CONSTRAINT chk_beclass_review_source_location
        CHECK (
            CHAR_LENGTH(TRIM(source_sheet)) > 0
            AND source_row > 0
            AND CHAR_LENGTH(TRIM(masked_identifier)) > 0
            AND LOCATE('*', masked_identifier) > 0
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS beclass_import_review_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    review_row_id BIGINT NOT NULL,
    event_type ENUM('resolved') NOT NULL,
    expected_version BIGINT UNSIGNED NOT NULL,
    resulting_version BIGINT UNSIGNED NOT NULL,
    candidate_fingerprint CHAR(64) NOT NULL,
    owning_record_identity VARCHAR(191) NOT NULL,
    corrected_payload JSON NOT NULL,
    resolved_issue_codes JSON NOT NULL,
    actor VARCHAR(100) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_beclass_review_event_version (
        review_row_id,
        resulting_version
    ),
    UNIQUE KEY uq_beclass_review_event_idempotency (idempotency_key),
    CONSTRAINT fk_beclass_review_event_row
        FOREIGN KEY (review_row_id) REFERENCES beclass_import_review_rows(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_beclass_review_event_version
        CHECK (resulting_version = expected_version + 1),
    CONSTRAINT chk_beclass_review_event_fingerprint
        CHECK (candidate_fingerprint REGEXP '^[0-9a-f]{64}$'),
    CONSTRAINT chk_beclass_review_event_payload
        CHECK (JSON_TYPE(corrected_payload) = 'OBJECT'),
    CONSTRAINT chk_beclass_review_event_issues
        CHECK (JSON_TYPE(resolved_issue_codes) = 'ARRAY'),
    CONSTRAINT chk_beclass_review_event_text
        CHECK (
            CHAR_LENGTH(TRIM(actor)) > 0
            AND CHAR_LENGTH(TRIM(reason)) > 0
            AND CHAR_LENGTH(TRIM(correlation_id)) > 0
            AND CHAR_LENGTH(TRIM(idempotency_key)) > 0
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS beclass_import_review_outbox (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    review_row_id BIGINT NOT NULL,
    review_event_id BIGINT NULL,
    intent_key VARCHAR(191) NOT NULL,
    intent_type ENUM('review_opened', 'review_resolved') NOT NULL,
    bounded_snapshot JSON NOT NULL,
    published_at DATETIME NULL,
    attempts INT UNSIGNED NOT NULL DEFAULT 0,
    last_error VARCHAR(500) NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_beclass_review_outbox_intent (intent_key),
    INDEX idx_beclass_review_outbox_pending (published_at, id),
    CONSTRAINT fk_beclass_review_outbox_row
        FOREIGN KEY (review_row_id) REFERENCES beclass_import_review_rows(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_beclass_review_outbox_event
        FOREIGN KEY (review_event_id) REFERENCES beclass_import_review_events(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_beclass_review_outbox_snapshot
        CHECK (JSON_TYPE(bounded_snapshot) = 'OBJECT'),
    CONSTRAINT chk_beclass_review_outbox_event_shape
        CHECK (
            (intent_type = 'review_opened' AND review_event_id IS NULL)
            OR (intent_type = 'review_resolved' AND review_event_id IS NOT NULL)
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS beclass_import_review_receipts (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    idempotency_key VARCHAR(191) NOT NULL,
    command_fingerprint CHAR(64) NOT NULL,
    preview_fingerprint CHAR(64) NOT NULL,
    review_row_id BIGINT NOT NULL,
    owning_record_identity VARCHAR(191) NOT NULL,
    review_event_id BIGINT NOT NULL,
    outbox_id BIGINT NOT NULL,
    resulting_version BIGINT UNSIGNED NOT NULL,
    result_snapshot JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_beclass_review_receipt_key (idempotency_key),
    UNIQUE KEY uq_beclass_review_receipt_event (review_event_id),
    CONSTRAINT fk_beclass_review_receipt_row
        FOREIGN KEY (review_row_id) REFERENCES beclass_import_review_rows(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_beclass_review_receipt_event
        FOREIGN KEY (review_event_id) REFERENCES beclass_import_review_events(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_beclass_review_receipt_outbox
        FOREIGN KEY (outbox_id) REFERENCES beclass_import_review_outbox(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_beclass_review_receipt_fingerprints
        CHECK (
            command_fingerprint REGEXP '^[0-9a-f]{64}$'
            AND preview_fingerprint REGEXP '^[0-9a-f]{64}$'
        ),
    CONSTRAINT chk_beclass_review_receipt_snapshot
        CHECK (JSON_TYPE(result_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_beclass_review_rows_before_update;
CREATE TRIGGER trg_beclass_review_rows_before_update
BEFORE UPDATE ON beclass_import_review_rows
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'beclass_import_review_rows records cannot be updated';

DROP TRIGGER IF EXISTS trg_beclass_review_rows_before_delete;
CREATE TRIGGER trg_beclass_review_rows_before_delete
BEFORE DELETE ON beclass_import_review_rows
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'beclass_import_review_rows records cannot be deleted';

DROP TRIGGER IF EXISTS trg_beclass_review_events_before_update;
CREATE TRIGGER trg_beclass_review_events_before_update
BEFORE UPDATE ON beclass_import_review_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'beclass_import_review_events records cannot be updated';

DROP TRIGGER IF EXISTS trg_beclass_review_events_before_delete;
CREATE TRIGGER trg_beclass_review_events_before_delete
BEFORE DELETE ON beclass_import_review_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'beclass_import_review_events records cannot be deleted';

DROP TRIGGER IF EXISTS trg_beclass_review_receipts_before_update;
CREATE TRIGGER trg_beclass_review_receipts_before_update
BEFORE UPDATE ON beclass_import_review_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'beclass_import_review_receipts records cannot be updated';

DROP TRIGGER IF EXISTS trg_beclass_review_receipts_before_delete;
CREATE TRIGGER trg_beclass_review_receipts_before_delete
BEFORE DELETE ON beclass_import_review_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'beclass_import_review_receipts records cannot be deleted';
-- END SOURCE: db/schema_parts/136_beclass_import_review.sql

-- BEGIN SOURCE: db/schema_parts/137_background_jobs.sql
CREATE TABLE `background_jobs` (
    `job_id` VARCHAR(191) NOT NULL,
    `command_identity` VARCHAR(191) NOT NULL,
    `status` ENUM('queued', 'running', 'succeeded', 'failed', 'cancelled') NOT NULL DEFAULT 'queued',
    `receipt_payload` JSON DEFAULT NULL,
    `error_payload` JSON DEFAULT NULL,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (`job_id`),
    UNIQUE KEY `uk_command_identity` (`command_identity`),
    INDEX `idx_status` (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
-- END SOURCE: db/schema_parts/137_background_jobs.sql

-- BEGIN SOURCE: db/schema_parts/138_client_subsidy_advance_settlement.sql
-- Additive settlement facts for a union-funded client subsidy advance.

ALTER TABLE client_ledger_entries
    MODIFY COLUMN entry_type ENUM(
        'receipt',
        'refund',
        'subsidy_return',
        'subsidy_advance',
        'adjustment',
        'reversal',
        'refund_reversal',
        'subsidy_return_reversal',
        'subsidy_advance_reversal'
    ) NOT NULL;

ALTER TABLE government_subsidy_outbox
    MODIFY COLUMN intent_type ENUM(
        'government_subsidy_receipt_applied',
        'government_subsidy_receipt_allocated',
        'government_subsidy_reversal_applied',
        'government_subsidy_anomaly_root_changed'
    ) NOT NULL;

CREATE TABLE IF NOT EXISTS client_subsidy_return_claim_item_links (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    obligation_identity VARCHAR(191) NOT NULL,
    claim_item_id BIGINT NOT NULL,
    entitled_amount_ntd BIGINT UNSIGNED NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_client_subsidy_return_claim_item (
        obligation_identity,
        claim_item_id
    ),
    INDEX idx_client_subsidy_return_claim_item (claim_item_id),
    CONSTRAINT fk_client_subsidy_return_link_obligation
        FOREIGN KEY (obligation_identity)
        REFERENCES client_obligations(obligation_identity)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_client_subsidy_return_link_claim_item
        FOREIGN KEY (claim_item_id)
        REFERENCES subsidy_claim_batch_items(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_client_subsidy_return_link_amount
        CHECK (entitled_amount_ntd > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS client_subsidy_advance_recoveries (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    case_no VARCHAR(50) NOT NULL,
    advance_ledger_entry_id BIGINT NOT NULL,
    government_allocation_id BIGINT NOT NULL,
    recovered_amount_ntd BIGINT UNSIGNED NOT NULL,
    source_outbox_id BIGINT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_client_subsidy_advance_recovery (
        advance_ledger_entry_id,
        government_allocation_id
    ),
    UNIQUE KEY uq_client_subsidy_advance_once (
        advance_ledger_entry_id
    ),
    UNIQUE KEY uq_client_subsidy_recovery_outbox_advance (
        source_outbox_id,
        advance_ledger_entry_id
    ),
    INDEX idx_client_subsidy_recovery_case (case_no, created_at),
    CONSTRAINT fk_client_subsidy_recovery_order
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_client_subsidy_recovery_advance
        FOREIGN KEY (advance_ledger_entry_id)
        REFERENCES client_ledger_entries(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_client_subsidy_recovery_allocation
        FOREIGN KEY (government_allocation_id)
        REFERENCES government_subsidy_allocations(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_client_subsidy_recovery_outbox
        FOREIGN KEY (source_outbox_id)
        REFERENCES government_subsidy_outbox(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_client_subsidy_recovery_amount
        CHECK (recovered_amount_ntd > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_client_subsidy_advance_recovery_before_update;
CREATE TRIGGER trg_client_subsidy_advance_recovery_before_update
BEFORE UPDATE ON client_subsidy_advance_recoveries
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client_subsidy_advance_recoveries cannot be updated';

DROP TRIGGER IF EXISTS trg_client_subsidy_advance_recovery_before_delete;
CREATE TRIGGER trg_client_subsidy_advance_recovery_before_delete
BEFORE DELETE ON client_subsidy_advance_recoveries
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client_subsidy_advance_recoveries cannot be deleted';

DROP TRIGGER IF EXISTS trg_client_subsidy_return_claim_item_link_before_update;
CREATE TRIGGER trg_client_subsidy_return_claim_item_link_before_update
BEFORE UPDATE ON client_subsidy_return_claim_item_links
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client_subsidy_return_claim_item_links cannot be updated';

DROP TRIGGER IF EXISTS trg_client_subsidy_return_claim_item_link_before_delete;
CREATE TRIGGER trg_client_subsidy_return_claim_item_link_before_delete
BEFORE DELETE ON client_subsidy_return_claim_item_links
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client_subsidy_return_claim_item_links cannot be deleted';
-- END SOURCE: db/schema_parts/138_client_subsidy_advance_settlement.sql

-- BEGIN SOURCE: db/schema_parts/139_finance_import_historical_reprocess.sql
-- Additive contracts for typed historical Finance Import reprocess Apply.

ALTER TABLE finance_import_classification_events
    MODIFY COLUMN classification_type ENUM(
        'client_receipt',
        'client_refund',
        'client_subsidy_return',
        'government_subsidy',
        'staff_payout',
        'non_business_review'
    ) NOT NULL;

ALTER TABLE finance_import_outbox
    MODIFY COLUMN intent_type ENUM(
        'dispatch_completed',
        'manual_correction_completed',
        'initial_classification_recorded',
        'historical_reprocess_completed'
    ) NOT NULL;

CREATE TABLE IF NOT EXISTS finance_import_historical_reprocess_receipts (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    idempotency_key VARCHAR(191) NOT NULL,
    command_fingerprint CHAR(64) NOT NULL,
    preview_fingerprint CHAR(64) NOT NULL,
    batch_id BIGINT NOT NULL,
    reprocess_run_id BIGINT NOT NULL,
    result_snapshot JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_finance_import_historical_reprocess_receipt_key (idempotency_key),
    UNIQUE KEY uq_finance_import_historical_reprocess_receipt_run (reprocess_run_id),
    CONSTRAINT fk_finance_import_historical_reprocess_receipt_batch
        FOREIGN KEY (batch_id) REFERENCES finance_import_batches(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_finance_import_historical_reprocess_receipt_run
        FOREIGN KEY (reprocess_run_id) REFERENCES finance_import_reprocess_runs(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_finance_import_historical_reprocess_receipt_fingerprint
        CHECK (
            command_fingerprint REGEXP '^[0-9a-f]{64}$'
            AND preview_fingerprint REGEXP '^[0-9a-f]{64}$'
        ),
    CONSTRAINT chk_finance_import_historical_reprocess_receipt_snapshot
        CHECK (JSON_TYPE(result_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Manual evidence is a separate immutable fact.  It must never be written
-- back to finance_import_rows or its bank_references JSON root fact.
CREATE TABLE IF NOT EXISTS historical_owner_selection_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    finance_import_row_id BIGINT NOT NULL,
    batch_id BIGINT NOT NULL,
    case_no VARCHAR(50) NOT NULL,
    obligation_identity VARCHAR(191) NOT NULL,
    actor VARCHAR(255) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    evidence_references JSON NOT NULL,
    source_canonical_fact_version BIGINT UNSIGNED NOT NULL,
    resulting_canonical_fact_version BIGINT UNSIGNED NOT NULL,
    batch_version BIGINT UNSIGNED NOT NULL,
    obligation_projection_version BIGINT UNSIGNED NOT NULL,
    preview_fingerprint CHAR(64) NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_historical_owner_selection_idempotency (idempotency_key, finance_import_row_id),
    INDEX idx_historical_owner_selection_row (finance_import_row_id, created_at),
    CONSTRAINT fk_historical_owner_selection_row FOREIGN KEY (finance_import_row_id)
        REFERENCES finance_import_rows(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_historical_owner_selection_batch FOREIGN KEY (batch_id)
        REFERENCES finance_import_batches(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_historical_owner_selection_obligation FOREIGN KEY (obligation_identity, case_no)
        REFERENCES client_obligations(obligation_identity, case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_historical_owner_selection_versions CHECK (
        resulting_canonical_fact_version = source_canonical_fact_version + 1
        AND obligation_projection_version >= 0
    ),
    CONSTRAINT chk_historical_owner_selection_evidence CHECK (
        JSON_TYPE(evidence_references) = 'ARRAY' AND JSON_LENGTH(evidence_references) > 0
    ),
    CONSTRAINT chk_historical_owner_selection_fingerprint CHECK (
        preview_fingerprint REGEXP '^[0-9a-f]{64}$'
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_historical_owner_selection_before_update;
CREATE TRIGGER trg_historical_owner_selection_before_update
BEFORE UPDATE ON historical_owner_selection_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'historical_owner_selection_events cannot be updated';

DROP TRIGGER IF EXISTS trg_historical_owner_selection_before_delete;
CREATE TRIGGER trg_historical_owner_selection_before_delete
BEFORE DELETE ON historical_owner_selection_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'historical_owner_selection_events cannot be deleted';

DROP TRIGGER IF EXISTS trg_finance_import_historical_reprocess_receipt_before_update;
CREATE TRIGGER trg_finance_import_historical_reprocess_receipt_before_update
BEFORE UPDATE ON finance_import_historical_reprocess_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'finance_import_historical_reprocess_receipts cannot be updated';

DROP TRIGGER IF EXISTS trg_finance_import_historical_reprocess_receipt_before_delete;
CREATE TRIGGER trg_finance_import_historical_reprocess_receipt_before_delete
BEFORE DELETE ON finance_import_historical_reprocess_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'finance_import_historical_reprocess_receipts cannot be deleted';
-- END SOURCE: db/schema_parts/139_finance_import_historical_reprocess.sql

-- BEGIN SOURCE: db/schema_parts/140_client_refund_return.sql
-- Add the distinct idempotency receipt kind for a bank-backed client refund return.

ALTER TABLE client_refund_reversal_apply_receipts
    MODIFY COLUMN correction_type ENUM('refund', 'refund_return', 'reversal') NOT NULL;

ALTER TABLE client_ledger_entries
    DROP CHECK chk_client_ledger_reversal_shape,
    ADD CONSTRAINT chk_client_ledger_reversal_shape CHECK (
        (entry_type IN (
            'reversal',
            'refund_reversal',
            'subsidy_return_reversal',
            'subsidy_advance_reversal'
        ) AND reversal_of_entry_id IS NOT NULL)
        OR (entry_type NOT IN (
            'reversal',
            'refund_reversal',
            'subsidy_return_reversal',
            'subsidy_advance_reversal'
        ) AND reversal_of_entry_id IS NULL)
    );

ALTER TABLE finance_import_classification_events
    MODIFY COLUMN classification_type ENUM(
        'client_receipt',
        'client_refund',
        'client_refund_return',
        'client_subsidy_return',
        'government_subsidy',
        'staff_payout',
        'non_business_review'
    ) NOT NULL;
-- END SOURCE: db/schema_parts/140_client_refund_return.sql

-- BEGIN SOURCE: db/schema_parts/141_durable_background_job_queue.sql
-- Additive queue metadata.  Existing in-process jobs remain readable while
-- newly submitted durable commands carry a complete replayable envelope.
ALTER TABLE background_jobs
    ADD COLUMN command_type VARCHAR(191) NULL AFTER command_identity,
    ADD COLUMN command_version SMALLINT UNSIGNED NULL AFTER command_type,
    ADD COLUMN command_payload JSON NULL AFTER command_version,
    ADD COLUMN submitted_by VARCHAR(191) NULL AFTER command_payload,
    ADD COLUMN correlation_id VARCHAR(191) NULL AFTER submitted_by,
    ADD COLUMN available_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) AFTER error_payload,
    ADD COLUMN attempt_count SMALLINT UNSIGNED NOT NULL DEFAULT 0 AFTER available_at,
    ADD COLUMN max_attempts SMALLINT UNSIGNED NOT NULL DEFAULT 3 AFTER attempt_count,
    ADD COLUMN lease_token VARCHAR(191) NULL AFTER max_attempts,
    ADD COLUMN lease_owner VARCHAR(191) NULL AFTER lease_token,
    ADD COLUMN lease_expires_at DATETIME(6) NULL AFTER lease_owner,
    ADD COLUMN result_reference VARCHAR(191) NULL AFTER lease_expires_at,
    ADD COLUMN completed_at DATETIME(6) NULL AFTER result_reference;

CREATE INDEX idx_background_jobs_queue
    ON background_jobs (status, available_at, created_at);

CREATE INDEX idx_background_jobs_lease
    ON background_jobs (status, lease_expires_at);
-- END SOURCE: db/schema_parts/141_durable_background_job_queue.sql

-- BEGIN SOURCE: db/schema_parts/142_client_deposit_reversal.sql
-- Append-only idempotency receipt for the canonical deposit reversal command.

CREATE TABLE IF NOT EXISTS client_deposit_reversal_apply_receipts (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    idempotency_key VARCHAR(191) NOT NULL,
    command_fingerprint CHAR(64) NOT NULL,
    preview_fingerprint CHAR(64) NOT NULL,
    case_no VARCHAR(50) NOT NULL,
    resulting_account_version BIGINT UNSIGNED NOT NULL,
    result_snapshot JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_client_deposit_reversal_receipt_key (idempotency_key),
    CONSTRAINT fk_client_deposit_reversal_receipt_order
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_client_deposit_reversal_receipt_fingerprint
        CHECK (
            command_fingerprint REGEXP '^[0-9a-f]{64}$'
            AND preview_fingerprint REGEXP '^[0-9a-f]{64}$'
        ),
    CONSTRAINT chk_client_deposit_reversal_receipt_snapshot
        CHECK (JSON_TYPE(result_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_client_deposit_reversal_receipts_before_update;
CREATE TRIGGER trg_client_deposit_reversal_receipts_before_update
BEFORE UPDATE ON client_deposit_reversal_apply_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client_deposit_reversal_apply_receipts records cannot be updated';

DROP TRIGGER IF EXISTS trg_client_deposit_reversal_receipts_before_delete;
CREATE TRIGGER trg_client_deposit_reversal_receipts_before_delete
BEFORE DELETE ON client_deposit_reversal_apply_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client_deposit_reversal_apply_receipts records cannot be deleted';
-- END SOURCE: db/schema_parts/142_client_deposit_reversal.sql

-- BEGIN SOURCE: db/schema_parts/143_client_refund_return_review.sql
-- Immutable operator-confirmed review facts for an ambiguous returned client refund.
-- Recognition is intentionally not inferred from bank memo, name, account, or amount.

ALTER TABLE finance_import_outbox
    MODIFY COLUMN intent_type ENUM(
        'dispatch_completed',
        'manual_correction_completed',
        'initial_classification_recorded',
        'historical_reprocess_completed',
        'refund_return_review_recorded'
    ) NOT NULL;

CREATE TABLE IF NOT EXISTS client_refund_return_review_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    finance_import_row_id BIGINT NOT NULL,
    original_refund_ledger_entry_id BIGINT NOT NULL,
    case_no VARCHAR(50) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    evidence JSON NOT NULL,
    actor VARCHAR(100) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_client_refund_return_review_bank_refund (
        finance_import_row_id,
        original_refund_ledger_entry_id
    ),
    UNIQUE KEY uq_client_refund_return_review_idempotency (idempotency_key),
    INDEX idx_client_refund_return_review_case (case_no, created_at, id),
    CONSTRAINT fk_client_refund_return_review_row
        FOREIGN KEY (finance_import_row_id) REFERENCES finance_import_rows(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_client_refund_return_review_ledger
        FOREIGN KEY (original_refund_ledger_entry_id)
        REFERENCES client_ledger_entries(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_client_refund_return_review_order
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_client_refund_return_review_evidence
        CHECK (JSON_TYPE(evidence) = 'ARRAY'),
    CONSTRAINT chk_client_refund_return_review_text
        CHECK (
            CHAR_LENGTH(TRIM(reason)) > 0
            AND CHAR_LENGTH(TRIM(actor)) > 0
            AND CHAR_LENGTH(TRIM(correlation_id)) > 0
            AND CHAR_LENGTH(TRIM(idempotency_key)) > 0
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS client_refund_return_review_receipts (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    idempotency_key VARCHAR(191) NOT NULL,
    command_fingerprint CHAR(64) NOT NULL,
    finance_import_row_id BIGINT NOT NULL,
    review_event_id BIGINT NOT NULL,
    result_snapshot JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_client_refund_return_review_receipt_key (idempotency_key),
    UNIQUE KEY uq_client_refund_return_review_receipt_event (review_event_id),
    CONSTRAINT fk_client_refund_return_review_receipt_row
        FOREIGN KEY (finance_import_row_id) REFERENCES finance_import_rows(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_client_refund_return_review_receipt_event
        FOREIGN KEY (review_event_id) REFERENCES client_refund_return_review_events(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_client_refund_return_review_receipt_fingerprint
        CHECK (command_fingerprint REGEXP '^[0-9a-f]{64}$'),
    CONSTRAINT chk_client_refund_return_review_receipt_snapshot
        CHECK (JSON_TYPE(result_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_client_refund_return_review_event_before_update;
CREATE TRIGGER trg_client_refund_return_review_event_before_update
BEFORE UPDATE ON client_refund_return_review_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client refund return review events cannot be updated';

DROP TRIGGER IF EXISTS trg_client_refund_return_review_event_before_delete;
CREATE TRIGGER trg_client_refund_return_review_event_before_delete
BEFORE DELETE ON client_refund_return_review_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client refund return review events cannot be deleted';

DROP TRIGGER IF EXISTS trg_client_refund_return_review_receipt_before_update;
CREATE TRIGGER trg_client_refund_return_review_receipt_before_update
BEFORE UPDATE ON client_refund_return_review_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client refund return review receipts cannot be updated';

DROP TRIGGER IF EXISTS trg_client_refund_return_review_receipt_before_delete;
CREATE TRIGGER trg_client_refund_return_review_receipt_before_delete
BEFORE DELETE ON client_refund_return_review_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client refund return review receipts cannot be deleted';
-- END SOURCE: db/schema_parts/143_client_refund_return_review.sql

-- BEGIN SOURCE: db/schema_parts/144_order_auto_completion_workflow.sql
-- Append-only receipt for the canonical Orders service auto-completion command.

CREATE TABLE IF NOT EXISTS order_auto_completion_apply_receipts (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    idempotency_key VARCHAR(191) NOT NULL,
    command_fingerprint CHAR(64) NOT NULL,
    case_no VARCHAR(50) NOT NULL,
    lifecycle_event_id BIGINT UNSIGNED NOT NULL,
    order_version BIGINT UNSIGNED NOT NULL,
    completion_instant DATETIME NOT NULL,
    evaluation_at DATETIME NOT NULL,
    result_snapshot JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_order_auto_completion_receipt_key (idempotency_key),
    UNIQUE KEY uq_order_auto_completion_lifecycle_event (lifecycle_event_id),
    CONSTRAINT fk_order_auto_completion_receipt_order
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_order_auto_completion_receipt_lifecycle_event
        FOREIGN KEY (lifecycle_event_id, case_no)
        REFERENCES order_lifecycle_state_events(id, case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_order_auto_completion_receipt_fingerprint
        CHECK (command_fingerprint REGEXP '^[0-9a-f]{64}$'),
    CONSTRAINT chk_order_auto_completion_receipt_snapshot
        CHECK (JSON_TYPE(result_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_order_auto_completion_receipts_before_update;
CREATE TRIGGER trg_order_auto_completion_receipts_before_update
BEFORE UPDATE ON order_auto_completion_apply_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'order_auto_completion_apply_receipts records cannot be updated';

DROP TRIGGER IF EXISTS trg_order_auto_completion_receipts_before_delete;
CREATE TRIGGER trg_order_auto_completion_receipts_before_delete
BEFORE DELETE ON order_auto_completion_apply_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'order_auto_completion_apply_receipts records cannot be deleted';
-- END SOURCE: db/schema_parts/144_order_auto_completion_workflow.sql

-- BEGIN SOURCE: db/schema_parts/145_admin_command_receipts.sql
CREATE TABLE IF NOT EXISTS admin_command_receipts (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    command_family VARCHAR(100) NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    request_fingerprint CHAR(64) NOT NULL,
    preview_fingerprint CHAR(64) NOT NULL,
    actor VARCHAR(100) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    result_snapshot JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_admin_command_receipt (command_family, idempotency_key),
    CONSTRAINT chk_admin_command_receipt_fingerprints CHECK (
        request_fingerprint REGEXP '^[0-9a-f]{64}$'
        AND preview_fingerprint REGEXP '^[0-9a-f]{64}$'
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
-- END SOURCE: db/schema_parts/145_admin_command_receipts.sql

-- BEGIN SOURCE: db/schema_parts/146_provisional_client_registrations.sql
CREATE TABLE IF NOT EXISTS provisional_client_registrations (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    line_user_id VARCHAR(100) NOT NULL,
    active_line_user_id VARCHAR(100) NULL,
    payload_fingerprint CHAR(64) NOT NULL,
    status ENUM('submitted','case_issued') NOT NULL DEFAULT 'submitted',
    client_id INT NULL,
    beclass_record_id INT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_provisional_registration_active_line_user (active_line_user_id),
    INDEX idx_provisional_registration_line_status (line_user_id, status),
    CONSTRAINT chk_provisional_registration_fingerprint CHECK (
        payload_fingerprint REGEXP '^[0-9a-f]{64}$'
    ),
    CONSTRAINT fk_provisional_registration_client
        FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE RESTRICT,
    CONSTRAINT fk_provisional_registration_beclass
        FOREIGN KEY (beclass_record_id) REFERENCES beclass_records(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS provisional_registration_conflicts (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    registration_id BIGINT NOT NULL,
    proposed_payload_fingerprint CHAR(64) NOT NULL,
    proposed_payload JSON NOT NULL,
    status ENUM('open','resolved') NOT NULL DEFAULT 'open',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_provisional_registration_conflict (
        registration_id, proposed_payload_fingerprint
    ),
    INDEX idx_provisional_registration_conflict_status (status, created_at),
    CONSTRAINT chk_provisional_registration_conflict_fingerprint CHECK (
        proposed_payload_fingerprint REGEXP '^[0-9a-f]{64}$'
    ),
    CONSTRAINT fk_provisional_registration_conflict_registration
        FOREIGN KEY (registration_id) REFERENCES provisional_client_registrations(id)
        ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
-- END SOURCE: db/schema_parts/146_provisional_client_registrations.sql

-- BEGIN SOURCE: db/schema_parts/147_access_capability_grants.sql
-- Versioned per-admin capability grants; role bundles remain the baseline policy.

CREATE TABLE IF NOT EXISTS admin_capability_grants (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    admin_user_id BIGINT NOT NULL,
    capability VARCHAR(100) NOT NULL,
    granted_by_admin_user_id BIGINT NOT NULL,
    reason VARCHAR(500) NOT NULL,
    effective_from DATETIME NOT NULL,
    expires_at DATETIME NULL,
    revoked_at DATETIME NULL,
    revoked_by_admin_user_id BIGINT NULL,
    revoked_reason VARCHAR(500) NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_admin_capability_grant (admin_user_id, capability),
    INDEX idx_admin_capability_effective (admin_user_id, revoked_at, effective_from, expires_at),
    CONSTRAINT fk_capability_grant_admin FOREIGN KEY (admin_user_id)
        REFERENCES admin_users(id) ON DELETE RESTRICT,
    CONSTRAINT fk_capability_grant_actor FOREIGN KEY (granted_by_admin_user_id)
        REFERENCES admin_users(id) ON DELETE RESTRICT,
    CONSTRAINT fk_capability_grant_revoke_actor FOREIGN KEY (revoked_by_admin_user_id)
        REFERENCES admin_users(id) ON DELETE SET NULL,
    CONSTRAINT chk_capability_grant_period
        CHECK (expires_at IS NULL OR expires_at > effective_from)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS access_control_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    admin_user_id BIGINT NOT NULL,
    actor_admin_user_id BIGINT NOT NULL,
    event_type ENUM('capability_granted','capability_revoked') NOT NULL,
    capability VARCHAR(100) NOT NULL,
    before_authorization_version BIGINT UNSIGNED NOT NULL,
    after_authorization_version BIGINT UNSIGNED NOT NULL,
    reason VARCHAR(500) NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_access_control_event_idempotency (idempotency_key),
    INDEX idx_access_control_event_target (admin_user_id, created_at),
    CONSTRAINT fk_access_event_admin FOREIGN KEY (admin_user_id)
        REFERENCES admin_users(id) ON DELETE RESTRICT,
    CONSTRAINT fk_access_event_actor FOREIGN KEY (actor_admin_user_id)
        REFERENCES admin_users(id) ON DELETE RESTRICT,
    CONSTRAINT chk_access_control_event_version
        CHECK (after_authorization_version = before_authorization_version + 1)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS access_control_apply_receipts (
    idempotency_key VARCHAR(191) PRIMARY KEY,
    command_fingerprint CHAR(64) NOT NULL,
    receipt_json JSON NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
-- END SOURCE: db/schema_parts/147_access_capability_grants.sql

-- BEGIN SOURCE: db/schema_parts/148_knowledge_retrieval.sql
-- Reviewed, published knowledge is independent from the retired legacy FAQ table.
CREATE TABLE IF NOT EXISTS knowledge_items (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    source_uri VARCHAR(500) NOT NULL,
    source_trust_tier ENUM('internal_policy','government_source','approved_partner') NOT NULL,
    title VARCHAR(300) NOT NULL,
    content TEXT NOT NULL,
    content_digest CHAR(64) NOT NULL,
    state ENUM('draft','reviewed','published','retired') NOT NULL DEFAULT 'draft',
    version BIGINT UNSIGNED NOT NULL DEFAULT 0,
    created_by_admin_user_id BIGINT NOT NULL,
    reviewed_by_admin_user_id BIGINT NULL,
    published_by_admin_user_id BIGINT NULL,
    retired_by_admin_user_id BIGINT NULL,
    review_reason VARCHAR(500) NULL,
    publication_reason VARCHAR(500) NULL,
    retired_reason VARCHAR(500) NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    published_at DATETIME NULL,
    retired_at DATETIME NULL,
    UNIQUE KEY uk_knowledge_source_digest (source_uri, content_digest),
    INDEX idx_knowledge_answer (state, source_trust_tier, published_at),
    CONSTRAINT fk_knowledge_creator FOREIGN KEY (created_by_admin_user_id)
        REFERENCES admin_users(id) ON DELETE RESTRICT,
    CONSTRAINT fk_knowledge_reviewer FOREIGN KEY (reviewed_by_admin_user_id)
        REFERENCES admin_users(id) ON DELETE RESTRICT,
    CONSTRAINT fk_knowledge_publisher FOREIGN KEY (published_by_admin_user_id)
        REFERENCES admin_users(id) ON DELETE RESTRICT,
    CONSTRAINT fk_knowledge_retirer FOREIGN KEY (retired_by_admin_user_id)
        REFERENCES admin_users(id) ON DELETE RESTRICT,
    CONSTRAINT chk_knowledge_published_actor
        CHECK (state <> 'published' OR published_by_admin_user_id IS NOT NULL)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS knowledge_item_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    knowledge_item_id BIGINT NOT NULL,
    actor_admin_user_id BIGINT NOT NULL,
    event_type ENUM('ingested','reviewed','published','retired') NOT NULL,
    before_version BIGINT UNSIGNED NOT NULL,
    after_version BIGINT UNSIGNED NOT NULL,
    reason VARCHAR(500) NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    snapshot_json JSON NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_knowledge_event_idempotency (idempotency_key),
    INDEX idx_knowledge_event_item (knowledge_item_id, created_at),
    CONSTRAINT fk_knowledge_event_item FOREIGN KEY (knowledge_item_id)
        REFERENCES knowledge_items(id) ON DELETE RESTRICT,
    CONSTRAINT fk_knowledge_event_actor FOREIGN KEY (actor_admin_user_id)
        REFERENCES admin_users(id) ON DELETE RESTRICT,
    CONSTRAINT chk_knowledge_event_version
        CHECK (after_version = before_version + 1)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS knowledge_apply_receipts (
    idempotency_key VARCHAR(191) PRIMARY KEY,
    command_fingerprint CHAR(64) NOT NULL,
    receipt_json JSON NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
-- END SOURCE: db/schema_parts/148_knowledge_retrieval.sql

-- BEGIN SOURCE: db/schema_parts/149_admin_authorization_version.sql
-- Additive authorization revision for release-managed dynamic capability grants.
ALTER TABLE admin_users
    ADD COLUMN authorization_version BIGINT UNSIGNED NOT NULL DEFAULT 0
    COMMENT 'effective capability grant revision' AFTER enabled;
-- END SOURCE: db/schema_parts/149_admin_authorization_version.sql

-- BEGIN SOURCE: db/schema_parts/150_line_publication_confirmation_and_session_expiry.sql
-- A session has a sliding idle window but can never outlive its original login.
SET @admin_session_absolute_expiry_exists = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'admin_sessions'
      AND COLUMN_NAME = 'absolute_expires_at'
);
SET @admin_session_schema_sql = IF(
    @admin_session_absolute_expiry_exists = 0,
    'ALTER TABLE `admin_sessions` ADD COLUMN `absolute_expires_at` DATETIME NULL COMMENT ''hard re-authentication deadline'' AFTER `expires_at`',
    'SELECT 1'
);
PREPARE admin_session_schema_stmt FROM @admin_session_schema_sql;
EXECUTE admin_session_schema_stmt;
DEALLOCATE PREPARE admin_session_schema_stmt;

-- A publication may be applied only after the same administrator previewed the
-- current immutable configuration revision.  A later configuration save makes
-- the old preview unusable instead of publishing an unseen menu.
CREATE TABLE IF NOT EXISTS line_rich_menu_publish_previews (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    menu_config_id VARCHAR(100) NOT NULL,
    config_revision CHAR(64) NOT NULL,
    config_fingerprint CHAR(64) NOT NULL,
    previewed_by_admin_user_id BIGINT NOT NULL,
    publication_id BIGINT NULL,
    previewed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    confirmed_at DATETIME NULL,
    UNIQUE KEY uk_line_menu_preview_snapshot (
        menu_config_id, config_revision, config_fingerprint, previewed_by_admin_user_id
    ),
    INDEX idx_line_menu_preview_apply (menu_config_id, previewed_by_admin_user_id, publication_id),
    CONSTRAINT fk_line_menu_preview_admin FOREIGN KEY (previewed_by_admin_user_id)
        REFERENCES admin_users(id) ON DELETE RESTRICT,
    CONSTRAINT fk_line_menu_preview_publication FOREIGN KEY (publication_id)
        REFERENCES line_rich_menu_publications(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
-- END SOURCE: db/schema_parts/150_line_publication_confirmation_and_session_expiry.sql

-- BEGIN SOURCE: db/schema_parts/151_admin_security_audit_retention.sql
CREATE TABLE IF NOT EXISTS admin_audit_log_archive (
    source_audit_id BIGINT NOT NULL PRIMARY KEY,
    admin_user_id BIGINT NULL,
    action VARCHAR(100) NOT NULL,
    resource_type VARCHAR(100) NULL,
    resource_id VARCHAR(255) NULL,
    request_path VARCHAR(500) NULL,
    http_method VARCHAR(10) NULL,
    result_status INT NULL,
    ip_address VARCHAR(64) NULL,
    details_json JSON NULL,
    created_at DATETIME NOT NULL,
    archived_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_admin_audit_archive_created_at (created_at),
    INDEX idx_admin_audit_archive_actor_time (admin_user_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
-- END SOURCE: db/schema_parts/151_admin_security_audit_retention.sql

-- BEGIN SOURCE: db/schema_parts/152_finance_import_ingestion_attempts.sql
-- Append-only outcome ledger for every durable Finance Import ingestion command.

CREATE TABLE IF NOT EXISTS finance_import_ingestion_attempts (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    idempotency_key VARCHAR(191) NOT NULL,
    command_fingerprint CHAR(64) NOT NULL,
    source_content_digest CHAR(64) NOT NULL,
    phase VARCHAR(64) NOT NULL,
    error_code VARCHAR(96) NULL,
    transaction_outcome ENUM('committed', 'rolled_back') NOT NULL,
    batch_id BIGINT NULL,
    started_at DATETIME(6) NOT NULL,
    completed_at DATETIME(6) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_finance_import_attempt_command (idempotency_key),
    KEY ix_finance_import_attempt_digest (source_content_digest),
    CONSTRAINT fk_finance_import_attempt_batch
        FOREIGN KEY (batch_id) REFERENCES finance_import_batches(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_finance_import_attempt_fingerprints
        CHECK (
            command_fingerprint REGEXP '^[0-9a-f]{64}$'
            AND source_content_digest REGEXP '^[0-9a-f]{64}$'
        ),
    CONSTRAINT chk_finance_import_attempt_outcome
        CHECK (
            (transaction_outcome = 'committed' AND error_code IS NULL AND batch_id IS NOT NULL)
            OR (transaction_outcome = 'rolled_back' AND error_code IS NOT NULL AND batch_id IS NULL)
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_finance_import_ingestion_attempt_before_update;
CREATE TRIGGER trg_finance_import_ingestion_attempt_before_update
BEFORE UPDATE ON finance_import_ingestion_attempts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'finance_import_ingestion_attempts cannot be updated';

DROP TRIGGER IF EXISTS trg_finance_import_ingestion_attempt_before_delete;
CREATE TRIGGER trg_finance_import_ingestion_attempt_before_delete
BEFORE DELETE ON finance_import_ingestion_attempts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'finance_import_ingestion_attempts cannot be deleted';
-- END SOURCE: db/schema_parts/152_finance_import_ingestion_attempts.sql

-- BEGIN SOURCE: db/schema_parts/154_line_integration_inbox_delivery.sql
-- Canonical LINE webhook inbox, delivery queue, receipts, outbox, and audit facts.
-- Legacy LINE tables remain untouched until the runtime cutover stage.

CREATE TABLE IF NOT EXISTS line_inbox_events (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    event_identity VARCHAR(191) NOT NULL,
    provider_event_id VARCHAR(191) NULL,
    destination_id VARCHAR(191) NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    source_type ENUM('user','group','room') NOT NULL,
    source_identity VARCHAR(191) NOT NULL,
    source_user_id VARCHAR(191) NULL,
    occurred_at_utc DATETIME(6) NOT NULL,
    payload_fingerprint CHAR(64) NOT NULL,
    payload_snapshot JSON NOT NULL,
    identity_source ENUM('provider','fingerprint','legacy') NOT NULL,
    is_redelivery BOOLEAN NOT NULL DEFAULT FALSE,
    processing_status ENUM(
        'pending','processing','processed','retryable_failed','terminal_failed'
    ) NOT NULL DEFAULT 'pending',
    aggregate_version BIGINT UNSIGNED NOT NULL DEFAULT 0,
    attempt_count INT UNSIGNED NOT NULL DEFAULT 0,
    max_attempts INT UNSIGNED NOT NULL DEFAULT 5,
    next_attempt_at_utc DATETIME(6) NULL,
    lease_owner VARCHAR(191) NULL,
    lease_acquired_at_utc DATETIME(6) NULL,
    lease_expires_at_utc DATETIME(6) NULL,
    error_code VARCHAR(191) NULL,
    error_message VARCHAR(1000) NULL,
    received_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    processed_at_utc DATETIME(6) NULL,
    updated_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
        ON UPDATE CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_line_inbox_event_identity (event_identity),
    INDEX idx_line_inbox_due (
        processing_status, next_attempt_at_utc, received_at_utc, id
    ),
    INDEX idx_line_inbox_lease (processing_status, lease_expires_at_utc),
    CONSTRAINT chk_line_inbox_payload_fingerprint
        CHECK (payload_fingerprint REGEXP '^[0-9a-f]{64}$'),
    CONSTRAINT chk_line_inbox_payload_object
        CHECK (JSON_TYPE(payload_snapshot) = 'OBJECT'),
    CONSTRAINT chk_line_inbox_lease_pair CHECK (
        (lease_owner IS NULL AND lease_acquired_at_utc IS NULL AND lease_expires_at_utc IS NULL)
        OR
        (lease_owner IS NOT NULL AND lease_acquired_at_utc IS NOT NULL
            AND lease_expires_at_utc > lease_acquired_at_utc)
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT IGNORE INTO line_inbox_events (
    id, event_identity, provider_event_id, destination_id, event_type,
    source_type, source_identity, source_user_id, occurred_at_utc,
    payload_fingerprint, payload_snapshot, identity_source, is_redelivery,
    processing_status, aggregate_version, error_message, received_at_utc,
    processed_at_utc
)
SELECT
    id,
    webhook_event_id,
    webhook_event_id,
    'legacy:unknown',
    event_type,
    CASE WHEN source_type IN ('group','room') THEN source_type ELSE 'user' END,
    COALESCE(source_group_id, source_user_id, 'legacy:unknown'),
    source_user_id,
    COALESCE(FROM_UNIXTIME(event_timestamp / 1000.0), received_at),
    SHA2(CAST(payload_json AS CHAR CHARACTER SET utf8mb4), 256),
    payload_json,
    'legacy',
    is_redelivery,
    CASE processing_status
        WHEN 'received' THEN 'pending'
        WHEN 'processing' THEN 'processing'
        WHEN 'completed' THEN 'processed'
        WHEN 'ignored' THEN 'processed'
        ELSE 'terminal_failed'
    END,
    0,
    error_message,
    received_at,
    processed_at
FROM line_webhook_events;

CREATE TABLE IF NOT EXISTS line_delivery_tasks (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    recipient_type ENUM('user','group','room') NOT NULL,
    recipient_identity VARCHAR(191) NOT NULL,
    message_kind ENUM('text','flex') NOT NULL,
    payload_snapshot JSON NOT NULL,
    payload_fingerprint CHAR(64) NOT NULL,
    scheduled_at_utc DATETIME(6) NOT NULL,
    source_aggregate_type VARCHAR(191) NOT NULL,
    source_aggregate_identity VARCHAR(191) NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    processing_status ENUM(
        'pending','processing','sent','retryable_failed','failed','cancelled'
    ) NOT NULL DEFAULT 'pending',
    completed_attempts INT UNSIGNED NOT NULL DEFAULT 0,
    max_attempts INT UNSIGNED NOT NULL DEFAULT 3,
    next_attempt_at_utc DATETIME(6) NULL,
    lease_owner VARCHAR(191) NULL,
    lease_acquired_at_utc DATETIME(6) NULL,
    lease_expires_at_utc DATETIME(6) NULL,
    provider_message_id VARCHAR(191) NULL,
    error_code VARCHAR(191) NULL,
    error_message VARCHAR(1000) NULL,
    sent_at_utc DATETIME(6) NULL,
    failed_at_utc DATETIME(6) NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
        ON UPDATE CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_line_delivery_idempotency (idempotency_key),
    INDEX idx_line_delivery_due (
        processing_status, scheduled_at_utc, next_attempt_at_utc, id
    ),
    INDEX idx_line_delivery_lease (processing_status, lease_expires_at_utc),
    INDEX idx_line_delivery_source (
        source_aggregate_type, source_aggregate_identity, id
    ),
    CONSTRAINT chk_line_delivery_payload_fingerprint
        CHECK (payload_fingerprint REGEXP '^[0-9a-f]{64}$'),
    CONSTRAINT chk_line_delivery_payload_object
        CHECK (JSON_TYPE(payload_snapshot) = 'OBJECT'),
    CONSTRAINT chk_line_delivery_lease_pair CHECK (
        (lease_owner IS NULL AND lease_acquired_at_utc IS NULL AND lease_expires_at_utc IS NULL)
        OR
        (lease_owner IS NOT NULL AND lease_acquired_at_utc IS NOT NULL
            AND lease_expires_at_utc > lease_acquired_at_utc)
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT IGNORE INTO line_delivery_tasks (
    id, recipient_type, recipient_identity, message_kind, payload_snapshot,
    payload_fingerprint, scheduled_at_utc, source_aggregate_type,
    source_aggregate_identity, idempotency_key, correlation_id,
    processing_status, completed_attempts, max_attempts, next_attempt_at_utc,
    provider_message_id, error_code, error_message, sent_at_utc,
    failed_at_utc, created_at_utc, updated_at_utc
)
SELECT
    id,
    'user',
    to_user_id,
    CASE
        WHEN payload_json IS NOT NULL
          AND JSON_UNQUOTE(JSON_EXTRACT(payload_json, '$.type')) = 'flex'
        THEN 'flex'
        ELSE 'text'
    END,
    CASE
        WHEN payload_json IS NOT NULL AND JSON_TYPE(payload_json) = 'OBJECT'
        THEN payload_json
        ELSE JSON_OBJECT('text', COALESCE(message_content, ''), 'type', 'text')
    END,
    SHA2(CONCAT_WS('|', to_user_id, task_type, COALESCE(message_content, ''),
        COALESCE(CAST(payload_json AS CHAR CHARACTER SET utf8mb4), ''), scheduled_at), 256),
    scheduled_at,
    'legacy_line_task',
    CAST(id AS CHAR),
    COALESCE(idempotency_key, CONCAT('legacy-line-task:', id)),
    CONCAT('legacy-line-task:', id),
    CASE status
        WHEN 'pending' THEN 'pending'
        WHEN 'processing' THEN 'processing'
        WHEN 'sent' THEN 'sent'
        WHEN 'cancelled' THEN 'cancelled'
        ELSE 'failed'
    END,
    retry_count,
    max_retries,
    next_retry_at,
    NULL,
    error_code,
    error_message,
    sent_at,
    failed_at,
    created_at,
    updated_at
FROM line_tasks;

CREATE TABLE IF NOT EXISTS line_delivery_attempt_events (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    task_id BIGINT UNSIGNED NOT NULL,
    attempt_number INT UNSIGNED NOT NULL,
    outcome ENUM(
        'success','retryable_failure','terminal_failure','legacy_incomplete'
    ) NOT NULL,
    provider_outcome_type ENUM(
        'success','rate_limited','rejected','unavailable','timeout','legacy'
    ) NOT NULL,
    provider_message_id VARCHAR(191) NULL,
    error_code VARCHAR(191) NULL,
    error_message VARCHAR(1000) NULL,
    retry_after_seconds INT UNSIGNED NULL,
    started_at_utc DATETIME(6) NOT NULL,
    completed_at_utc DATETIME(6) NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_line_delivery_attempt_number (task_id, attempt_number),
    UNIQUE KEY uq_line_delivery_attempt_idempotency (idempotency_key),
    INDEX idx_line_delivery_attempt_time (outcome, completed_at_utc),
    CONSTRAINT fk_line_delivery_attempt_task
        FOREIGN KEY (task_id) REFERENCES line_delivery_tasks(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT IGNORE INTO line_delivery_attempt_events (
    id, task_id, attempt_number, outcome, provider_outcome_type,
    error_code, error_message, started_at_utc, completed_at_utc,
    idempotency_key, correlation_id
)
SELECT
    id,
    task_id,
    attempt_no,
    CASE outcome
        WHEN 'sent' THEN 'success'
        WHEN 'retry_scheduled' THEN 'retryable_failure'
        WHEN 'failed' THEN 'terminal_failure'
        ELSE 'legacy_incomplete'
    END,
    CASE outcome WHEN 'sent' THEN 'success' ELSE 'legacy' END,
    error_code,
    error_message,
    started_at,
    COALESCE(finished_at, started_at),
    CONCAT('legacy-line-attempt:', id),
    CONCAT('legacy-line-attempt:', id)
FROM line_task_attempts;

CREATE TABLE IF NOT EXISTS line_command_receipts (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    idempotency_key VARCHAR(191) NOT NULL,
    command_family VARCHAR(100) NOT NULL,
    payload_fingerprint CHAR(64) NOT NULL,
    result_reference VARCHAR(191) NOT NULL,
    result_snapshot JSON NULL,
    correlation_id VARCHAR(191) NOT NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_line_command_receipt_key (idempotency_key),
    INDEX idx_line_command_receipt_family (command_family, created_at_utc),
    CONSTRAINT chk_line_command_receipt_fingerprint
        CHECK (payload_fingerprint REGEXP '^[0-9a-f]{64}$'),
    CONSTRAINT chk_line_command_receipt_snapshot
        CHECK (result_snapshot IS NULL OR JSON_TYPE(result_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS line_domain_outbox (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    aggregate_type VARCHAR(100) NOT NULL,
    aggregate_identity VARCHAR(191) NOT NULL,
    intent_type VARCHAR(191) NOT NULL,
    payload_snapshot JSON NOT NULL,
    idempotency_identity VARCHAR(191) NOT NULL,
    processing_status ENUM('pending','processing','completed','dead')
        NOT NULL DEFAULT 'pending',
    attempt_count INT UNSIGNED NOT NULL DEFAULT 0,
    next_attempt_at_utc DATETIME(6) NULL,
    lease_owner VARCHAR(191) NULL,
    lease_expires_at_utc DATETIME(6) NULL,
    error_code VARCHAR(191) NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    completed_at_utc DATETIME(6) NULL,
    UNIQUE KEY uq_line_domain_outbox_identity (idempotency_identity),
    INDEX idx_line_domain_outbox_due (
        processing_status, next_attempt_at_utc, created_at_utc, id
    ),
    CONSTRAINT chk_line_domain_outbox_payload
        CHECK (JSON_TYPE(payload_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS line_domain_audit_events (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    action VARCHAR(191) NOT NULL,
    actor_id VARCHAR(191) NOT NULL,
    aggregate_type VARCHAR(191) NOT NULL,
    aggregate_identity VARCHAR(191) NOT NULL,
    occurred_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    INDEX idx_line_domain_audit_aggregate (
        aggregate_type, aggregate_identity, occurred_at_utc, id
    ),
    INDEX idx_line_domain_audit_actor (actor_id, occurred_at_utc, id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_line_delivery_attempt_events_before_update;
CREATE TRIGGER trg_line_delivery_attempt_events_before_update
BEFORE UPDATE ON line_delivery_attempt_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_delivery_attempt_events records cannot be updated';

DROP TRIGGER IF EXISTS trg_line_delivery_attempt_events_before_delete;
CREATE TRIGGER trg_line_delivery_attempt_events_before_delete
BEFORE DELETE ON line_delivery_attempt_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_delivery_attempt_events records cannot be deleted';

DROP TRIGGER IF EXISTS trg_line_command_receipts_before_update;
CREATE TRIGGER trg_line_command_receipts_before_update
BEFORE UPDATE ON line_command_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_command_receipts records cannot be updated';

DROP TRIGGER IF EXISTS trg_line_command_receipts_before_delete;
CREATE TRIGGER trg_line_command_receipts_before_delete
BEFORE DELETE ON line_command_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_command_receipts records cannot be deleted';

DROP TRIGGER IF EXISTS trg_line_domain_audit_events_before_update;
CREATE TRIGGER trg_line_domain_audit_events_before_update
BEFORE UPDATE ON line_domain_audit_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_domain_audit_events records cannot be updated';

DROP TRIGGER IF EXISTS trg_line_domain_audit_events_before_delete;
CREATE TRIGGER trg_line_domain_audit_events_before_delete
BEFORE DELETE ON line_domain_audit_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_domain_audit_events records cannot be deleted';
-- END SOURCE: db/schema_parts/154_line_integration_inbox_delivery.sql

-- BEGIN SOURCE: db/schema_parts/155_line_identity_review_configuration.sql
-- Canonical LINE identity bindings, review facts, and versioned configuration.

CREATE TABLE IF NOT EXISTS line_identity_bindings (
    line_user_id VARCHAR(191) PRIMARY KEY,
    binding_status ENUM('unbound','pending_review','bound','revoked')
        NOT NULL DEFAULT 'unbound',
    subject_type ENUM('customer','staff','admin') NULL,
    subject_reference VARCHAR(191) NULL,
    aggregate_version BIGINT UNSIGNED NOT NULL DEFAULT 0,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
        ON UPDATE CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_line_identity_subject (subject_type, subject_reference),
    INDEX idx_line_identity_status (binding_status, updated_at_utc),
    CONSTRAINT chk_line_identity_subject_pair CHECK (
        (binding_status = 'unbound' AND subject_type IS NULL AND subject_reference IS NULL)
        OR
        (binding_status <> 'unbound' AND subject_type IS NOT NULL
            AND subject_reference IS NOT NULL)
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS line_identity_binding_events (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    line_user_id VARCHAR(191) NOT NULL,
    action ENUM('claim_submitted','bound','revoked','rebound','legacy_imported')
        NOT NULL,
    subject_type ENUM('customer','staff','admin') NULL,
    subject_reference VARCHAR(191) NULL,
    expected_version BIGINT UNSIGNED NOT NULL,
    resulting_version BIGINT UNSIGNED NOT NULL,
    actor_id VARCHAR(191) NOT NULL,
    payload_fingerprint CHAR(64) NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    occurred_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_line_identity_event_idempotency (idempotency_key),
    INDEX idx_line_identity_event_user (line_user_id, id),
    CONSTRAINT fk_line_identity_event_binding
        FOREIGN KEY (line_user_id) REFERENCES line_identity_bindings(line_user_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_line_identity_event_fingerprint
        CHECK (payload_fingerprint REGEXP '^[0-9a-f]{64}$'),
    CONSTRAINT chk_line_identity_event_version
        CHECK (resulting_version = expected_version + 1)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS line_identity_migration_anomalies (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    line_user_id VARCHAR(191) NOT NULL,
    candidate_count INT UNSIGNED NOT NULL,
    candidate_snapshot JSON NOT NULL,
    detected_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_line_identity_migration_anomaly (line_user_id),
    CONSTRAINT chk_line_identity_anomaly_snapshot
        CHECK (JSON_TYPE(candidate_snapshot) = 'ARRAY')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT IGNORE INTO line_identity_bindings (
    line_user_id, binding_status, subject_type, subject_reference,
    aggregate_version, created_at_utc, updated_at_utc
)
SELECT
    candidate.line_user_id,
    'bound',
    MIN(candidate.subject_type),
    MIN(candidate.subject_reference),
    1,
    CURRENT_TIMESTAMP(6),
    CURRENT_TIMESTAMP(6)
FROM (
    SELECT line_user_id, 'customer' AS subject_type, CAST(id AS CHAR) AS subject_reference
    FROM clients WHERE line_user_id IS NOT NULL AND line_user_id <> ''
    UNION ALL
    SELECT line_user_id, 'staff', CAST(id AS CHAR)
    FROM staff WHERE line_user_id IS NOT NULL AND line_user_id <> ''
    UNION ALL
    SELECT linked_line_user_id, 'admin', CAST(id AS CHAR)
    FROM admin_users
    WHERE linked_line_user_id IS NOT NULL AND linked_line_user_id <> ''
) AS candidate
GROUP BY candidate.line_user_id
HAVING COUNT(*) = 1;

INSERT IGNORE INTO line_identity_bindings (
    line_user_id, binding_status, aggregate_version, created_at_utc, updated_at_utc
)
SELECT line_user_id, 'unbound', 0, created_at, updated_at
FROM line_users;

INSERT IGNORE INTO line_identity_migration_anomalies (
    line_user_id, candidate_count, candidate_snapshot
)
SELECT
    candidate.line_user_id,
    COUNT(*),
    JSON_ARRAYAGG(JSON_OBJECT(
        'subject_reference', candidate.subject_reference,
        'subject_type', candidate.subject_type
    ))
FROM (
    SELECT line_user_id, 'customer' AS subject_type, CAST(id AS CHAR) AS subject_reference
    FROM clients WHERE line_user_id IS NOT NULL AND line_user_id <> ''
    UNION ALL
    SELECT line_user_id, 'staff', CAST(id AS CHAR)
    FROM staff WHERE line_user_id IS NOT NULL AND line_user_id <> ''
    UNION ALL
    SELECT linked_line_user_id, 'admin', CAST(id AS CHAR)
    FROM admin_users
    WHERE linked_line_user_id IS NOT NULL AND linked_line_user_id <> ''
) AS candidate
GROUP BY candidate.line_user_id
HAVING COUNT(*) > 1;

INSERT IGNORE INTO line_identity_binding_events (
    line_user_id, action, subject_type, subject_reference,
    expected_version, resulting_version, actor_id, payload_fingerprint,
    idempotency_key, correlation_id
)
SELECT
    line_user_id,
    'legacy_imported',
    subject_type,
    subject_reference,
    0,
    1,
    'migration:line-stage-2',
    SHA2(CONCAT_WS('|', line_user_id, subject_type, subject_reference), 256),
    CONCAT('legacy-line-binding:', line_user_id),
    CONCAT('legacy-line-binding:', line_user_id)
FROM line_identity_bindings
WHERE binding_status = 'bound';

CREATE TABLE IF NOT EXISTS line_review_requests (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    review_type ENUM('client_rebind','staff_verification','admin_binding') NOT NULL,
    line_user_id VARCHAR(191) NOT NULL,
    subject_type ENUM('customer','staff','admin') NOT NULL,
    subject_reference VARCHAR(191) NOT NULL,
    review_status ENUM('pending','approved','rejected','cancelled','expired')
        NOT NULL DEFAULT 'pending',
    aggregate_version BIGINT UNSIGNED NOT NULL DEFAULT 0,
    request_fingerprint CHAR(64) NOT NULL,
    evidence_snapshot JSON NOT NULL,
    assigned_admin_id BIGINT NULL,
    assigned_at_utc DATETIME(6) NULL,
    due_at_utc DATETIME(6) NULL,
    reassignment_count INT UNSIGNED NOT NULL DEFAULT 0,
    reviewed_by_actor_id VARCHAR(191) NULL,
    decision_reason VARCHAR(1000) NULL,
    reviewed_at_utc DATETIME(6) NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
        ON UPDATE CURRENT_TIMESTAMP(6),
    INDEX idx_line_review_queue (review_status, review_type, created_at_utc, id),
    INDEX idx_line_review_assignee (assigned_admin_id, review_status, due_at_utc),
    CONSTRAINT fk_line_review_assignee
        FOREIGN KEY (assigned_admin_id) REFERENCES admin_users(id)
        ON UPDATE RESTRICT ON DELETE SET NULL,
    CONSTRAINT chk_line_review_fingerprint
        CHECK (request_fingerprint REGEXP '^[0-9a-f]{64}$'),
    CONSTRAINT chk_line_review_evidence
        CHECK (JSON_TYPE(evidence_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT IGNORE INTO line_review_requests (
    id, review_type, line_user_id, subject_type, subject_reference,
    review_status, aggregate_version, request_fingerprint, evidence_snapshot,
    assigned_admin_id, reviewed_by_actor_id, decision_reason, reviewed_at_utc,
    created_at_utc, updated_at_utc
)
SELECT
    id,
    request_type,
    line_user_id,
    CASE request_type WHEN 'staff_verification' THEN 'staff' ELSE 'customer' END,
    COALESCE(CAST(client_id AS CHAR), client_name, line_user_id),
    status,
    CASE WHEN status = 'pending' THEN 0 ELSE 1 END,
    SHA2(CONCAT_WS('|', request_type, line_user_id, COALESCE(client_id, ''),
        COALESCE(old_line_user_id, ''), COALESCE(new_line_user_id, '')), 256),
    JSON_OBJECT(
        'client_id', client_id,
        'client_name', client_name,
        'new_line_user_id', new_line_user_id,
        'old_line_user_id', old_line_user_id
    ),
    reviewed_by_admin_user_id,
    COALESCE(CAST(reviewed_by_admin_user_id AS CHAR), reviewed_by_line_user_id),
    decision_reason,
    COALESCE(reviewed_at, resolved_at),
    created_at,
    updated_at
FROM line_confirmation_requests;

CREATE TABLE IF NOT EXISTS line_review_decision_events (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    review_request_id BIGINT UNSIGNED NOT NULL,
    before_status ENUM('pending','approved','rejected','cancelled','expired') NOT NULL,
    after_status ENUM('approved','rejected','cancelled','expired') NOT NULL,
    expected_version BIGINT UNSIGNED NOT NULL,
    resulting_version BIGINT UNSIGNED NOT NULL,
    actor_id VARCHAR(191) NOT NULL,
    reason VARCHAR(1000) NOT NULL,
    decision_fingerprint CHAR(64) NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    occurred_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_line_review_decision_idempotency (idempotency_key),
    INDEX idx_line_review_decision_request (review_request_id, id),
    CONSTRAINT fk_line_review_decision_request
        FOREIGN KEY (review_request_id) REFERENCES line_review_requests(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_line_review_decision_fingerprint
        CHECK (decision_fingerprint REGEXP '^[0-9a-f]{64}$'),
    CONSTRAINT chk_line_review_decision_version
        CHECK (resulting_version = expected_version + 1)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT IGNORE INTO line_review_decision_events (
    review_request_id, before_status, after_status, expected_version,
    resulting_version, actor_id, reason, decision_fingerprint,
    idempotency_key, correlation_id, occurred_at_utc
)
SELECT
    id,
    'pending',
    status,
    0,
    1,
    COALESCE(CAST(reviewed_by_admin_user_id AS CHAR), reviewed_by_line_user_id,
        'migration:line-stage-2'),
    COALESCE(decision_reason, 'legacy decision import'),
    SHA2(CONCAT_WS('|', id, status, COALESCE(decision_reason, '')), 256),
    CONCAT('legacy-line-review-decision:', id),
    CONCAT('legacy-line-review-decision:', id),
    COALESCE(reviewed_at, resolved_at, updated_at)
FROM line_confirmation_requests
WHERE status IN ('approved','rejected','cancelled');

CREATE TABLE IF NOT EXISTS line_configuration_revisions (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    configuration_kind ENUM(
        'message_templates','message_schedules','rich_menus','liff','customer_service'
    ) NOT NULL,
    revision BIGINT UNSIGNED NOT NULL,
    definition_snapshot JSON NOT NULL,
    definition_fingerprint CHAR(64) NOT NULL,
    actor_id VARCHAR(191) NOT NULL,
    reason VARCHAR(1000) NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_line_configuration_revision (configuration_kind, revision),
    UNIQUE KEY uq_line_configuration_idempotency (idempotency_key),
    CONSTRAINT chk_line_configuration_snapshot
        CHECK (JSON_TYPE(definition_snapshot) = 'OBJECT'),
    CONSTRAINT chk_line_configuration_fingerprint
        CHECK (definition_fingerprint REGEXP '^[0-9a-f]{64}$')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS line_configuration_current (
    configuration_kind ENUM(
        'message_templates','message_schedules','rich_menus','liff','customer_service'
    ) PRIMARY KEY,
    revision BIGINT UNSIGNED NOT NULL,
    revision_id BIGINT UNSIGNED NOT NULL,
    updated_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
        ON UPDATE CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_line_configuration_current_revision (revision_id),
    CONSTRAINT fk_line_configuration_current_revision
        FOREIGN KEY (revision_id) REFERENCES line_configuration_revisions(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_line_identity_binding_events_before_update;
CREATE TRIGGER trg_line_identity_binding_events_before_update
BEFORE UPDATE ON line_identity_binding_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_identity_binding_events records cannot be updated';

DROP TRIGGER IF EXISTS trg_line_identity_binding_events_before_delete;
CREATE TRIGGER trg_line_identity_binding_events_before_delete
BEFORE DELETE ON line_identity_binding_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_identity_binding_events records cannot be deleted';

DROP TRIGGER IF EXISTS trg_line_review_decision_events_before_update;
CREATE TRIGGER trg_line_review_decision_events_before_update
BEFORE UPDATE ON line_review_decision_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_review_decision_events records cannot be updated';

DROP TRIGGER IF EXISTS trg_line_review_decision_events_before_delete;
CREATE TRIGGER trg_line_review_decision_events_before_delete
BEFORE DELETE ON line_review_decision_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_review_decision_events records cannot be deleted';

DROP TRIGGER IF EXISTS trg_line_configuration_revisions_before_update;
CREATE TRIGGER trg_line_configuration_revisions_before_update
BEFORE UPDATE ON line_configuration_revisions
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_configuration_revisions records cannot be updated';

DROP TRIGGER IF EXISTS trg_line_configuration_revisions_before_delete;
CREATE TRIGGER trg_line_configuration_revisions_before_delete
BEFORE DELETE ON line_configuration_revisions
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_configuration_revisions records cannot be deleted';
-- END SOURCE: db/schema_parts/155_line_identity_review_configuration.sql

-- BEGIN SOURCE: db/schema_parts/203_line_notification_rule_catalog.sql
-- File: 203_line_notification_rule_catalog.sql
-- Description: 新增 LINE 可配置通知規則的來源事件、決策與意圖稽核資料模型。

ALTER TABLE line_configuration_revisions
    MODIFY COLUMN configuration_kind ENUM(
        'message_templates','message_schedules','rich_menus','liff','customer_service','notification_rules'
    ) NOT NULL;

ALTER TABLE line_configuration_current
    MODIFY COLUMN configuration_kind ENUM(
        'message_templates','message_schedules','rich_menus','liff','customer_service','notification_rules'
    ) NOT NULL;

CREATE TABLE IF NOT EXISTS line_notification_source_events (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    source_domain VARCHAR(64) NOT NULL,
    event_code VARCHAR(64) NOT NULL,
    source_event_identity VARCHAR(191) NOT NULL,
    source_aggregate_type VARCHAR(191) NOT NULL,
    source_aggregate_identity VARCHAR(191) NOT NULL,
    source_version BIGINT UNSIGNED NOT NULL,
    historical_silent BOOLEAN NOT NULL DEFAULT FALSE,
    facts_snapshot JSON NOT NULL,
    occurred_at_utc DATETIME(6) NOT NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_line_notification_source_identity (source_domain,event_code,source_event_identity),
    INDEX idx_line_notification_source_due (event_code,historical_silent,occurred_at_utc,id),
    CONSTRAINT chk_line_notification_source_facts CHECK (JSON_TYPE(facts_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS line_notification_decisions (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    source_event_id BIGINT UNSIGNED NOT NULL,
    rule_revision_id BIGINT UNSIGNED NOT NULL,
    rule_id VARCHAR(64) NOT NULL,
    recipient_selector VARCHAR(64) NOT NULL,
    recipient_type ENUM('user','group','room') NULL,
    recipient_identity VARCHAR(191) NOT NULL DEFAULT '',
    decision_status ENUM('suppressed','intent_created','cancelled_stale') NOT NULL,
    reason_code VARCHAR(64) NOT NULL,
    decision_snapshot JSON NOT NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_line_notification_decision (source_event_id,rule_revision_id,rule_id,recipient_selector,recipient_identity),
    INDEX idx_line_notification_decision_source (source_event_id,id),
    CONSTRAINT fk_line_notification_decision_source FOREIGN KEY (source_event_id) REFERENCES line_notification_source_events(id),
    CONSTRAINT fk_line_notification_decision_revision FOREIGN KEY (rule_revision_id) REFERENCES line_configuration_revisions(id),
    CONSTRAINT chk_line_notification_decision_snapshot CHECK (JSON_TYPE(decision_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS line_notification_intents (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    decision_id BIGINT UNSIGNED NOT NULL,
    delivery_task_id BIGINT UNSIGNED NULL,
    template_revision_id BIGINT UNSIGNED NOT NULL,
    template_id VARCHAR(64) NOT NULL,
    payload_snapshot JSON NOT NULL,
    payload_fingerprint CHAR(64) NOT NULL,
    scheduled_at_utc DATETIME(6) NOT NULL,
    intent_status ENUM('scheduled','cancelled','provider_accepted') NOT NULL DEFAULT 'scheduled',
    cancellation_reason VARCHAR(64) NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    cancelled_at_utc DATETIME(6) NULL,
    UNIQUE KEY uq_line_notification_intent_decision (decision_id),
    UNIQUE KEY uq_line_notification_intent_delivery (delivery_task_id),
    INDEX idx_line_notification_intent_status (intent_status,scheduled_at_utc,id),
    CONSTRAINT fk_line_notification_intent_decision FOREIGN KEY (decision_id) REFERENCES line_notification_decisions(id),
    CONSTRAINT fk_line_notification_intent_delivery FOREIGN KEY (delivery_task_id) REFERENCES line_delivery_tasks(id),
    CONSTRAINT fk_line_notification_intent_template FOREIGN KEY (template_revision_id) REFERENCES line_configuration_revisions(id),
    CONSTRAINT chk_line_notification_intent_payload CHECK (JSON_TYPE(payload_snapshot) = 'OBJECT'),
    CONSTRAINT chk_line_notification_intent_fingerprint CHECK (payload_fingerprint REGEXP '^[0-9a-f]{64}$')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TRIGGER trg_line_notification_source_events_before_update
BEFORE UPDATE ON line_notification_source_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_notification_source_events records cannot be updated';

CREATE TRIGGER trg_line_notification_source_events_before_delete
BEFORE DELETE ON line_notification_source_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_notification_source_events records cannot be deleted';

CREATE TRIGGER trg_line_notification_decisions_before_update
BEFORE UPDATE ON line_notification_decisions
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_notification_decisions records cannot be updated';

CREATE TRIGGER trg_line_notification_decisions_before_delete
BEFORE DELETE ON line_notification_decisions
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_notification_decisions records cannot be deleted';
-- END SOURCE: db/schema_parts/203_line_notification_rule_catalog.sql

-- BEGIN SOURCE: db/schema_parts/156_line_publication_media_order_group.sql
-- Canonical LINE Rich Menu publication, media metadata, and order-group binding.

CREATE TABLE IF NOT EXISTS line_rich_menu_publication_tasks (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    menu_definition_id VARCHAR(191) NOT NULL,
    configuration_revision BIGINT UNSIGNED NOT NULL,
    operation ENUM('publish','rollback','delete') NOT NULL DEFAULT 'publish',
    publication_status ENUM(
        'draft','queued','publishing','published','publish_retryable_failed',
        'failed','rollback_queued','delete_queued','rollback_retryable_failed',
        'delete_retryable_failed','rolled_back','deleted'
    ) NOT NULL,
    definition_snapshot JSON NOT NULL,
    image_object_reference VARCHAR(500) NULL,
    provider_menu_id VARCHAR(191) NULL,
    previous_provider_menu_id VARCHAR(191) NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    requested_by_actor_id VARCHAR(191) NOT NULL,
    attempt_count INT UNSIGNED NOT NULL DEFAULT 0,
    max_attempts INT UNSIGNED NOT NULL DEFAULT 3,
    next_attempt_at_utc DATETIME(6) NULL,
    lease_owner VARCHAR(191) NULL,
    lease_expires_at_utc DATETIME(6) NULL,
    error_code VARCHAR(191) NULL,
    error_message VARCHAR(1000) NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
        ON UPDATE CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_line_rich_menu_publication_idempotency (idempotency_key),
    INDEX idx_line_rich_menu_publication_due (
        publication_status, next_attempt_at_utc, id
    ),
    INDEX idx_line_rich_menu_definition (
        menu_definition_id, configuration_revision, id
    ),
    CONSTRAINT chk_line_rich_menu_definition
        CHECK (JSON_TYPE(definition_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT IGNORE INTO line_rich_menu_publication_tasks (
    id, menu_definition_id, configuration_revision, operation,
    publication_status, definition_snapshot, image_object_reference,
    provider_menu_id, previous_provider_menu_id, idempotency_key,
    correlation_id, requested_by_actor_id, attempt_count, max_attempts,
    next_attempt_at_utc, error_code, error_message, created_at_utc, updated_at_utc
)
SELECT
    publication.id,
    publication.menu_config_id,
    0,
    'publish',
    CASE publication.status
        WHEN 'pending' THEN 'queued'
        WHEN 'processing' THEN 'publishing'
        WHEN 'published' THEN 'published'
        ELSE 'failed'
    END,
    publication.config_snapshot,
    asset.storage_key,
    publication.line_rich_menu_id,
    publication.previous_line_rich_menu_id,
    CONCAT('legacy-line-rich-menu:', publication.id),
    CONCAT('legacy-line-rich-menu:', publication.id),
    COALESCE(CAST(publication.requested_by_admin_user_id AS CHAR),
        'migration:line-stage-2'),
    publication.retry_count,
    publication.max_retries,
    publication.next_retry_at,
    publication.error_code,
    publication.error_message,
    publication.created_at,
    publication.updated_at
FROM line_rich_menu_publications AS publication
LEFT JOIN media_assets AS asset ON asset.id = publication.image_asset_id;

CREATE TABLE IF NOT EXISTS line_media_records (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    provider_media_id VARCHAR(191) NOT NULL,
    source_type ENUM('user','group','room') NOT NULL,
    source_identity VARCHAR(191) NOT NULL,
    source_user_id VARCHAR(191) NULL,
    content_type VARCHAR(100) NOT NULL,
    size_bytes BIGINT UNSIGNED NOT NULL,
    content_sha256 CHAR(64) NOT NULL,
    received_at_utc DATETIME(6) NOT NULL,
    media_category ENUM(
        'user_upload','identity_evidence','order_attachment','rich_menu_image',
        'customer_service_attachment','unclassified'
    ) NOT NULL,
    owner_type VARCHAR(100) NULL,
    owner_reference VARCHAR(191) NULL,
    object_reference VARCHAR(500) NOT NULL,
    legacy_media_asset_id BIGINT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_line_media_provider_id (provider_media_id),
    UNIQUE KEY uq_line_media_idempotency (idempotency_key),
    INDEX idx_line_media_owner (
        media_category, owner_type, owner_reference, received_at_utc
    ),
    CONSTRAINT fk_line_media_legacy_asset
        FOREIGN KEY (legacy_media_asset_id) REFERENCES media_assets(id)
        ON UPDATE RESTRICT ON DELETE SET NULL,
    CONSTRAINT chk_line_media_sha256
        CHECK (content_sha256 REGEXP '^[0-9a-f]{64}$')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT IGNORE INTO line_media_records (
    provider_media_id, source_type, source_identity, content_type,
    size_bytes, content_sha256, received_at_utc, media_category,
    owner_type, owner_reference, object_reference, legacy_media_asset_id,
    idempotency_key
)
SELECT
    CONCAT('legacy-media:', id),
    'user',
    'legacy:unknown',
    mime_type,
    file_size,
    sha256,
    created_at,
    CASE category
        WHEN 'rich_menu' THEN 'rich_menu_image'
        WHEN 'line_user_upload' THEN 'user_upload'
        WHEN 'contract' THEN 'order_attachment'
        ELSE 'unclassified'
    END,
    owner_type,
    owner_id,
    storage_key,
    id,
    CONCAT('legacy-line-media:', id)
FROM media_assets
WHERE deleted_at IS NULL;

CREATE TABLE IF NOT EXISTS line_order_group_bindings (
    case_no VARCHAR(50) PRIMARY KEY,
    group_id VARCHAR(191) NULL,
    binding_status ENUM('unbound','bound','replaced','released')
        NOT NULL DEFAULT 'unbound',
    aggregate_version BIGINT UNSIGNED NOT NULL DEFAULT 0,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
        ON UPDATE CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_line_order_group_id (group_id),
    CONSTRAINT fk_line_order_group_order
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_line_order_group_status CHECK (
        (binding_status = 'unbound' AND group_id IS NULL)
        OR
        (binding_status <> 'unbound' AND group_id IS NOT NULL)
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS line_order_group_binding_events (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    case_no VARCHAR(50) NOT NULL,
    action ENUM('bound','replaced','released','legacy_imported') NOT NULL,
    before_group_id VARCHAR(191) NULL,
    resulting_group_id VARCHAR(191) NULL,
    expected_version BIGINT UNSIGNED NOT NULL,
    resulting_version BIGINT UNSIGNED NOT NULL,
    actor_id VARCHAR(191) NOT NULL,
    binding_fingerprint CHAR(64) NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    occurred_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_line_order_group_event_idempotency (idempotency_key),
    INDEX idx_line_order_group_event_case (case_no, id),
    CONSTRAINT fk_line_order_group_event_binding
        FOREIGN KEY (case_no) REFERENCES line_order_group_bindings(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_line_order_group_event_fingerprint
        CHECK (binding_fingerprint REGEXP '^[0-9a-f]{64}$'),
    CONSTRAINT chk_line_order_group_event_version
        CHECK (resulting_version = expected_version + 1)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS line_order_group_migration_anomalies (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    case_no VARCHAR(50) NOT NULL,
    legacy_group_id VARCHAR(191) NOT NULL,
    anomaly_code VARCHAR(100) NOT NULL,
    details_snapshot JSON NOT NULL,
    detected_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_line_order_group_migration_anomaly (
        case_no, anomaly_code
    ),
    INDEX idx_line_order_group_migration_group (legacy_group_id, id),
    CONSTRAINT fk_line_order_group_migration_order
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_line_order_group_migration_details
        CHECK (JSON_TYPE(details_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT IGNORE INTO line_order_group_bindings (
    case_no, group_id, binding_status, aggregate_version,
    created_at_utc, updated_at_utc
)
SELECT
    case_no,
    NULL,
    'unbound',
    0,
    CURRENT_TIMESTAMP(6),
    CURRENT_TIMESTAMP(6)
FROM orders;

INSERT IGNORE INTO line_order_group_migration_anomalies (
    case_no, legacy_group_id, anomaly_code, details_snapshot
)
SELECT
    source_order.case_no,
    TRIM(source_order.line_group_id),
    'duplicate_legacy_group_id',
    JSON_OBJECT(
        'legacy_group_id', TRIM(source_order.line_group_id),
        'duplicate_count', duplicate_group.duplicate_count
    )
FROM orders AS source_order
INNER JOIN (
    SELECT TRIM(line_group_id) AS group_id, COUNT(*) AS duplicate_count
    FROM orders
    WHERE line_group_id IS NOT NULL AND TRIM(line_group_id) <> ''
    GROUP BY TRIM(line_group_id)
    HAVING COUNT(*) > 1
) AS duplicate_group
    ON duplicate_group.group_id = TRIM(source_order.line_group_id);

UPDATE line_order_group_bindings AS binding
INNER JOIN orders AS source_order ON source_order.case_no = binding.case_no
INNER JOIN (
    SELECT TRIM(line_group_id) AS group_id
    FROM orders
    WHERE line_group_id IS NOT NULL AND TRIM(line_group_id) <> ''
    GROUP BY TRIM(line_group_id)
    HAVING COUNT(*) = 1
) AS unique_group ON unique_group.group_id = TRIM(source_order.line_group_id)
SET
    binding.group_id = unique_group.group_id,
    binding.binding_status = 'bound',
    binding.aggregate_version = 1;

INSERT IGNORE INTO line_order_group_binding_events (
    case_no, action, resulting_group_id, expected_version, resulting_version,
    actor_id, binding_fingerprint, idempotency_key, correlation_id
)
SELECT
    binding.case_no,
    'legacy_imported',
    binding.group_id,
    0,
    1,
    'migration:line-stage-2',
    SHA2(CONCAT_WS('|', binding.case_no, binding.group_id), 256),
    CONCAT('legacy-line-order-group:', binding.case_no),
    CONCAT('legacy-line-order-group:', binding.case_no)
FROM line_order_group_bindings AS binding
WHERE binding.binding_status = 'bound';

DROP TRIGGER IF EXISTS trg_line_order_group_binding_events_before_update;
CREATE TRIGGER trg_line_order_group_binding_events_before_update
BEFORE UPDATE ON line_order_group_binding_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_order_group_binding_events records cannot be updated';

DROP TRIGGER IF EXISTS trg_line_order_group_binding_events_before_delete;
CREATE TRIGGER trg_line_order_group_binding_events_before_delete
BEFORE DELETE ON line_order_group_binding_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_order_group_binding_events records cannot be deleted';
-- END SOURCE: db/schema_parts/156_line_publication_media_order_group.sql

-- BEGIN SOURCE: db/schema_parts/204_scheduling_service_day_logs.sql
-- File: 204_scheduling_service_day_logs.sql
-- Description: 新增月嫂服務日寶寶日誌、餐食照片關聯、完成事件與通知用 Scheduling outbox。

CREATE TABLE IF NOT EXISTS scheduling_service_day_logs (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    case_no VARCHAR(50) NOT NULL,
    assignment_id BIGINT NOT NULL,
    staff_id INT NOT NULL,
    staff_line_user_id VARCHAR(191) NOT NULL,
    service_date DATE NOT NULL,
    baby_log_text TEXT NOT NULL,
    requires_cooking BOOLEAN NOT NULL,
    content_fingerprint CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_scheduling_service_day_log_assignment_date (assignment_id, service_date),
    UNIQUE KEY uq_scheduling_service_day_log_idempotency (idempotency_key),
    INDEX idx_scheduling_service_day_log_case_date (case_no, service_date, id),
    CONSTRAINT fk_scheduling_service_day_log_case FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_scheduling_service_day_log_assignment FOREIGN KEY (assignment_id) REFERENCES case_staff_assignments(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_scheduling_service_day_log_staff FOREIGN KEY (staff_id) REFERENCES staff(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_scheduling_service_day_log_text CHECK (CHAR_LENGTH(TRIM(baby_log_text)) > 0),
    CONSTRAINT chk_scheduling_service_day_log_fingerprint CHECK (content_fingerprint REGEXP '^[0-9a-f]{64}$')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS scheduling_service_day_log_attachments (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    service_day_log_id BIGINT UNSIGNED NOT NULL,
    provider_media_id VARCHAR(191) NOT NULL,
    attachment_kind ENUM('meal_photo') NOT NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_scheduling_service_day_log_attachment (service_day_log_id, provider_media_id),
    CONSTRAINT fk_scheduling_service_day_log_attachment_root FOREIGN KEY (service_day_log_id) REFERENCES scheduling_service_day_logs(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_scheduling_service_day_log_attachment_media FOREIGN KEY (provider_media_id) REFERENCES line_media_records(provider_media_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS scheduling_service_day_log_events (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    service_day_log_id BIGINT UNSIGNED NOT NULL,
    assignment_id BIGINT NOT NULL,
    staff_id INT NOT NULL,
    service_date DATE NOT NULL,
    event_type ENUM('submitted') NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_scheduling_service_day_log_event_root (service_day_log_id, event_type),
    UNIQUE KEY uq_scheduling_service_day_log_event_idempotency (idempotency_key),
    INDEX idx_scheduling_service_day_log_event_assignment_date (assignment_id, service_date, id),
    CONSTRAINT fk_scheduling_service_day_log_event_root FOREIGN KEY (service_day_log_id) REFERENCES scheduling_service_day_logs(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_scheduling_service_day_log_event_assignment FOREIGN KEY (assignment_id) REFERENCES case_staff_assignments(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_scheduling_service_day_log_event_staff FOREIGN KEY (staff_id) REFERENCES staff(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS scheduling_service_day_log_outbox (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    event_id BIGINT UNSIGNED NOT NULL,
    intent_key VARCHAR(191) NOT NULL,
    payload_snapshot JSON NOT NULL,
    delivery_status ENUM('pending','processing','published','failed') NOT NULL DEFAULT 'pending',
    attempt_count INT UNSIGNED NOT NULL DEFAULT 0,
    published_at_utc DATETIME(6) NULL,
    last_error_code VARCHAR(128) NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_scheduling_service_day_log_outbox_event (event_id),
    UNIQUE KEY uq_scheduling_service_day_log_outbox_intent (intent_key),
    INDEX idx_scheduling_service_day_log_outbox_delivery (delivery_status, created_at_utc, id),
    CONSTRAINT fk_scheduling_service_day_log_outbox_event FOREIGN KEY (event_id) REFERENCES scheduling_service_day_log_events(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_scheduling_service_day_log_outbox_payload CHECK (JSON_TYPE(payload_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TRIGGER trg_scheduling_service_day_log_attachments_before_update
BEFORE UPDATE ON scheduling_service_day_log_attachments
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'scheduling_service_day_log_attachments cannot be updated';

CREATE TRIGGER trg_scheduling_service_day_log_attachments_before_delete
BEFORE DELETE ON scheduling_service_day_log_attachments
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'scheduling_service_day_log_attachments cannot be deleted';

CREATE TRIGGER trg_scheduling_service_day_log_events_before_update
BEFORE UPDATE ON scheduling_service_day_log_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'scheduling_service_day_log_events cannot be updated';

CREATE TRIGGER trg_scheduling_service_day_log_events_before_delete
BEFORE DELETE ON scheduling_service_day_log_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'scheduling_service_day_log_events cannot be deleted';
-- END SOURCE: db/schema_parts/204_scheduling_service_day_logs.sql

-- BEGIN SOURCE: db/schema_parts/205_scheduling_service_day_checkpoints.sql
-- File: 205_scheduling_service_day_checkpoints.sql
-- Description: 為已結束的正式服務日保存不可變 checkpoint 與 outbox，供 LINE 規則安全判斷寶寶日誌是否逾期。

CREATE TABLE IF NOT EXISTS scheduling_service_day_checkpoints (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    case_no VARCHAR(50) NOT NULL,
    assignment_id BIGINT NOT NULL,
    schedule_id BIGINT NOT NULL,
    staff_id INT NOT NULL,
    service_date DATE NOT NULL,
    service_ends_at_utc DATETIME(6) NOT NULL,
    requires_cooking BOOLEAN NOT NULL,
    baby_log_completed BOOLEAN NOT NULL DEFAULT FALSE,
    checkpoint_key VARCHAR(191) NOT NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_scheduling_service_day_checkpoint_assignment_date (assignment_id, service_date),
    UNIQUE KEY uq_scheduling_service_day_checkpoint_key (checkpoint_key),
    INDEX idx_scheduling_service_day_checkpoint_due (service_ends_at_utc, id),
    CONSTRAINT fk_scheduling_service_day_checkpoint_case FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_scheduling_service_day_checkpoint_assignment FOREIGN KEY (assignment_id) REFERENCES case_staff_assignments(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_scheduling_service_day_checkpoint_staff FOREIGN KEY (staff_id) REFERENCES staff(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_scheduling_service_day_checkpoint_key CHECK (CHAR_LENGTH(TRIM(checkpoint_key)) > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS scheduling_service_day_checkpoint_events (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    checkpoint_id BIGINT UNSIGNED NOT NULL,
    event_type ENUM('service_ended') NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_scheduling_service_day_checkpoint_event_root (checkpoint_id, event_type),
    UNIQUE KEY uq_scheduling_service_day_checkpoint_event_idempotency (idempotency_key),
    CONSTRAINT fk_scheduling_service_day_checkpoint_event_root FOREIGN KEY (checkpoint_id) REFERENCES scheduling_service_day_checkpoints(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS scheduling_service_day_checkpoint_outbox (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    event_id BIGINT UNSIGNED NOT NULL,
    intent_key VARCHAR(191) NOT NULL,
    payload_snapshot JSON NOT NULL,
    delivery_status ENUM('pending','processing','published','failed') NOT NULL DEFAULT 'pending',
    attempt_count INT UNSIGNED NOT NULL DEFAULT 0,
    next_attempt_at_utc DATETIME(6) NULL,
    published_at_utc DATETIME(6) NULL,
    last_error_code VARCHAR(128) NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_scheduling_service_day_checkpoint_outbox_event (event_id),
    UNIQUE KEY uq_scheduling_service_day_checkpoint_outbox_intent (intent_key),
    INDEX idx_scheduling_service_day_checkpoint_outbox_delivery (delivery_status, next_attempt_at_utc, id),
    CONSTRAINT fk_scheduling_service_day_checkpoint_outbox_event FOREIGN KEY (event_id) REFERENCES scheduling_service_day_checkpoint_events(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_scheduling_service_day_checkpoint_outbox_payload CHECK (JSON_TYPE(payload_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TRIGGER trg_scheduling_service_day_checkpoints_before_update
BEFORE UPDATE ON scheduling_service_day_checkpoints
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'scheduling_service_day_checkpoints cannot be updated';

CREATE TRIGGER trg_scheduling_service_day_checkpoints_before_delete
BEFORE DELETE ON scheduling_service_day_checkpoints
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'scheduling_service_day_checkpoints cannot be deleted';

CREATE TRIGGER trg_scheduling_service_day_checkpoint_events_before_update
BEFORE UPDATE ON scheduling_service_day_checkpoint_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'scheduling_service_day_checkpoint_events cannot be updated';

CREATE TRIGGER trg_scheduling_service_day_checkpoint_events_before_delete
BEFORE DELETE ON scheduling_service_day_checkpoint_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'scheduling_service_day_checkpoint_events cannot be deleted';
-- END SOURCE: db/schema_parts/205_scheduling_service_day_checkpoints.sql

-- BEGIN SOURCE: db/schema_parts/206_line_notification_recurring_intents.sql
-- File: 206_line_notification_recurring_intents.sql
-- Description: 讓同一通知決策可保存受規則上限約束的多次每日提醒意圖。

ALTER TABLE line_notification_intents
    ADD COLUMN occurrence_number INT UNSIGNED NOT NULL DEFAULT 1 AFTER decision_id,
    DROP INDEX uq_line_notification_intent_decision,
    ADD UNIQUE KEY uq_line_notification_intent_decision_occurrence (decision_id, occurrence_number);
-- END SOURCE: db/schema_parts/206_line_notification_recurring_intents.sql

-- BEGIN SOURCE: db/schema_parts/207_scheduling_service_day_log_outbox_retry.sql
-- File: 207_scheduling_service_day_log_outbox_retry.sql
-- Description: 為服務日日誌完成 outbox 加入一秒間隔、最多三次的可恢復投影時點。

ALTER TABLE scheduling_service_day_log_outbox
    ADD COLUMN next_attempt_at_utc DATETIME(6) NULL AFTER attempt_count,
    ADD INDEX idx_scheduling_service_day_log_outbox_retry (delivery_status, next_attempt_at_utc, id);
-- END SOURCE: db/schema_parts/207_scheduling_service_day_log_outbox_retry.sql

-- BEGIN SOURCE: db/schema_parts/208_scheduling_rebuild_notification_invalidation.sql
-- File: 208_scheduling_rebuild_notification_invalidation.sql
-- Description: 將排班重建的已取消指派以不可變 outbox 提供 LINE 取消尚未送出的舊提醒。

CREATE TABLE IF NOT EXISTS scheduling_rebuild_notification_outbox (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    rebuild_event_id BIGINT NOT NULL,
    intent_key VARCHAR(191) NOT NULL,
    payload_snapshot JSON NOT NULL,
    delivery_status ENUM('pending','processing','published','failed') NOT NULL DEFAULT 'pending',
    attempt_count INT UNSIGNED NOT NULL DEFAULT 0,
    next_attempt_at_utc DATETIME(6) NULL,
    published_at_utc DATETIME(6) NULL,
    last_error_code VARCHAR(128) NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_scheduling_rebuild_notification_outbox_event (rebuild_event_id),
    UNIQUE KEY uq_scheduling_rebuild_notification_outbox_intent (intent_key),
    INDEX idx_scheduling_rebuild_notification_outbox_delivery (delivery_status,next_attempt_at_utc,id),
    CONSTRAINT fk_scheduling_rebuild_notification_outbox_event FOREIGN KEY (rebuild_event_id)
        REFERENCES scheduling_rebuild_events(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_scheduling_rebuild_notification_outbox_payload CHECK (JSON_TYPE(payload_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
-- END SOURCE: db/schema_parts/208_scheduling_rebuild_notification_invalidation.sql

-- BEGIN SOURCE: db/schema_parts/209_access_control_totp_root.sql
-- File: 209_access_control_totp_root.sql
-- Description: 新增 root、TOTP、recovery code、enrollment 與登入嘗試的 Access Control 事實表。

ALTER TABLE admin_users
    ADD COLUMN access_control_version BIGINT UNSIGNED NOT NULL DEFAULT 1
    COMMENT '帳號中心 optimistic-lock version' AFTER role;

CREATE TABLE IF NOT EXISTS admin_root_account (
    singleton_key TINYINT NOT NULL DEFAULT 1,
    admin_user_id BIGINT NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (singleton_key),
    UNIQUE KEY uk_admin_root_account_user (admin_user_id),
    CONSTRAINT chk_admin_root_account_singleton CHECK (singleton_key = 1),
    CONSTRAINT fk_admin_root_account_user FOREIGN KEY (admin_user_id)
        REFERENCES admin_users(id) ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS admin_totp_factors (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    admin_user_id BIGINT NOT NULL,
    factor_state ENUM('enrollment_pending','active','revoked') NOT NULL,
    seed_ciphertext TEXT NOT NULL,
    encryption_key_version VARCHAR(64) NOT NULL,
    enrollment_challenge_hash CHAR(64) NOT NULL,
    enrollment_expires_at DATETIME(6) NOT NULL,
    last_successful_step BIGINT NULL,
    activated_at DATETIME(6) NULL,
    revoked_at DATETIME(6) NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    UNIQUE KEY uk_admin_totp_factor_user (admin_user_id),
    INDEX idx_admin_totp_factor_enrollment (factor_state,enrollment_expires_at),
    CONSTRAINT fk_admin_totp_factor_user FOREIGN KEY (admin_user_id)
        REFERENCES admin_users(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_admin_totp_factor_activation CHECK (
        (factor_state = 'active' AND activated_at IS NOT NULL AND revoked_at IS NULL)
        OR (factor_state = 'enrollment_pending' AND activated_at IS NULL AND revoked_at IS NULL)
        OR (factor_state = 'revoked' AND revoked_at IS NOT NULL)
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS admin_mfa_enrollment_challenges (
    id CHAR(36) PRIMARY KEY,
    admin_user_id BIGINT NOT NULL,
    challenge_hash CHAR(64) NOT NULL,
    expires_at DATETIME(6) NOT NULL,
    consumed_at DATETIME(6) NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uk_admin_mfa_challenge_hash (challenge_hash),
    INDEX idx_admin_mfa_challenge_user_expiry (admin_user_id,expires_at,consumed_at),
    CONSTRAINT fk_admin_mfa_challenge_user FOREIGN KEY (admin_user_id)
        REFERENCES admin_users(id) ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS admin_totp_recovery_codes (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    factor_id BIGINT UNSIGNED NOT NULL,
    code_hash VARCHAR(512) NOT NULL,
    consumed_at DATETIME(6) NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uk_admin_totp_recovery_code_hash (code_hash),
    INDEX idx_admin_totp_recovery_factor (factor_id,consumed_at),
    CONSTRAINT fk_admin_totp_recovery_factor FOREIGN KEY (factor_id)
        REFERENCES admin_totp_factors(id) ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS admin_login_attempts (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    username_hash CHAR(64) NOT NULL,
    source_hash CHAR(64) NOT NULL,
    outcome ENUM('failed','succeeded','rate_limited','mfa_replay') NOT NULL,
    occurred_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    INDEX idx_admin_login_attempt_subject (username_hash,source_hash,occurred_at),
    INDEX idx_admin_login_attempt_time (occurred_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
-- END SOURCE: db/schema_parts/209_access_control_totp_root.sql

-- BEGIN SOURCE: db/schema_parts/210_access_control_password_challenges.sql
-- File: 210_access_control_password_challenges.sql
-- Description: 保存兩段式登入的短效 password challenge，綁定 credential、active factor identity 與帳號 access-control version。

CREATE TABLE IF NOT EXISTS admin_password_login_challenges (
    id CHAR(36) PRIMARY KEY,
    admin_user_id BIGINT NOT NULL,
    credential_version BIGINT UNSIGNED NOT NULL,
    factor_id BIGINT UNSIGNED NOT NULL,
    challenge_hash CHAR(64) NOT NULL,
    source_hash CHAR(64) NOT NULL,
    expires_at DATETIME(6) NOT NULL,
    consumed_at DATETIME(6) NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uk_admin_password_login_challenge_hash (challenge_hash),
    INDEX idx_admin_password_login_challenge_expiry (admin_user_id, expires_at, consumed_at),
    CONSTRAINT fk_admin_password_login_challenge_user FOREIGN KEY (admin_user_id)
        REFERENCES admin_users(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_admin_password_login_challenge_factor FOREIGN KEY (factor_id)
        REFERENCES admin_totp_factors(id) ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
-- END SOURCE: db/schema_parts/210_access_control_password_challenges.sql

-- BEGIN SOURCE: db/schema_parts/211_access_control_security_alert_outbox.sql
-- File: 211_access_control_security_alert_outbox.sql
-- Description: 保存 Access Control security audit 的耐久告警投影 intent，供 Incident Worker 非同步重試。

CREATE TABLE IF NOT EXISTS admin_security_alert_outbox (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    source_audit_id BIGINT NOT NULL,
    alert_code VARCHAR(64) NOT NULL,
    alert_identity CHAR(64) NOT NULL,
    payload_snapshot JSON NOT NULL,
    processing_status ENUM('pending','processing','completed','dead') NOT NULL DEFAULT 'pending',
    attempt_count INT UNSIGNED NOT NULL DEFAULT 0,
    max_attempts INT UNSIGNED NOT NULL DEFAULT 5,
    next_attempt_at DATETIME(6) NULL,
    lease_owner VARCHAR(191) NULL,
    lease_expires_at DATETIME(6) NULL,
    last_error_code VARCHAR(64) NULL,
    completed_at DATETIME(6) NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    UNIQUE KEY uk_admin_security_alert_outbox_audit (source_audit_id),
    INDEX idx_admin_security_alert_outbox_due (processing_status,next_attempt_at,lease_expires_at,id),
    CONSTRAINT fk_admin_security_alert_outbox_audit FOREIGN KEY (source_audit_id)
        REFERENCES admin_audit_logs(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_admin_security_alert_outbox_payload CHECK (JSON_TYPE(payload_snapshot) = 'OBJECT'),
    CONSTRAINT chk_admin_security_alert_outbox_attempts CHECK (
        attempt_count <= max_attempts AND max_attempts > 0
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
-- END SOURCE: db/schema_parts/211_access_control_security_alert_outbox.sql

-- BEGIN SOURCE: db/schema_parts/157_line_runtime_control.sql
-- Canonical LINE runtime leases, worker heartbeat, and webhook security facts.
-- This migration is additive and preserves every Stage 2 and legacy row.

ALTER TABLE line_inbox_events
    MODIFY processing_status ENUM(
        'pending','processing','processed','ignored',
        'retryable_failed','terminal_failed'
    ) NOT NULL DEFAULT 'pending';

CREATE TABLE IF NOT EXISTS line_worker_heartbeats (
    worker_identity VARCHAR(191) PRIMARY KEY,
    process_id INT UNSIGNED NOT NULL,
    host_name VARCHAR(191) NOT NULL,
    runtime_mode ENUM('legacy','canonical','compatibility') NOT NULL,
    component_status_snapshot JSON NOT NULL,
    last_cycle_at_utc DATETIME(6) NULL,
    heartbeat_at_utc DATETIME(6) NOT NULL,
    stopped_at_utc DATETIME(6) NULL,
    last_error_code VARCHAR(191) NULL,
    last_error_message VARCHAR(1000) NULL,
    updated_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
        ON UPDATE CURRENT_TIMESTAMP(6),
    INDEX idx_line_worker_heartbeat (heartbeat_at_utc, stopped_at_utc),
    CONSTRAINT chk_line_worker_components
        CHECK (JSON_TYPE(component_status_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS line_webhook_security_receipts (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    request_fingerprint CHAR(64) NOT NULL,
    signature_present BOOLEAN NOT NULL,
    verification_outcome ENUM(
        'verified','invalid_signature','invalid_payload','storage_failed'
    ) NOT NULL,
    event_count INT UNSIGNED NOT NULL DEFAULT 0,
    correlation_id VARCHAR(191) NOT NULL,
    occurred_at_utc DATETIME(6) NOT NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    INDEX idx_line_webhook_security_outcome (
        verification_outcome, occurred_at_utc, id
    ),
    INDEX idx_line_webhook_security_fingerprint (request_fingerprint, id),
    CONSTRAINT chk_line_webhook_security_fingerprint
        CHECK (request_fingerprint REGEXP '^[0-9a-f]{64}$')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_line_webhook_security_receipts_before_update;
CREATE TRIGGER trg_line_webhook_security_receipts_before_update
BEFORE UPDATE ON line_webhook_security_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_webhook_security_receipts records cannot be updated';

DROP TRIGGER IF EXISTS trg_line_webhook_security_receipts_before_delete;
CREATE TRIGGER trg_line_webhook_security_receipts_before_delete
BEFORE DELETE ON line_webhook_security_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_webhook_security_receipts records cannot be deleted';
-- END SOURCE: db/schema_parts/157_line_runtime_control.sql

-- BEGIN SOURCE: db/schema_parts/158_line_identity_runtime.sql
-- Canonical LINE platform friend state, LIFF identity flow, and review creation facts.
-- Additive Stage 4 migration; legacy projections remain available until Stage 10.

CREATE TABLE IF NOT EXISTS line_platform_users (
    line_user_id VARCHAR(191) PRIMARY KEY,
    friend_status ENUM('unknown','active','blocked') NOT NULL DEFAULT 'unknown',
    first_followed_at_utc DATETIME(6) NULL,
    last_followed_at_utc DATETIME(6) NULL,
    blocked_at_utc DATETIME(6) NULL,
    last_event_at_utc DATETIME(6) NULL,
    aggregate_version BIGINT UNSIGNED NOT NULL DEFAULT 0,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
        ON UPDATE CURRENT_TIMESTAMP(6),
    INDEX idx_line_platform_friend_state (friend_status, last_event_at_utc)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT IGNORE INTO line_platform_users (
    line_user_id, friend_status, first_followed_at_utc, last_followed_at_utc,
    blocked_at_utc, last_event_at_utc, aggregate_version, created_at_utc, updated_at_utc
)
SELECT
    line_user_id,
    CASE status WHEN 'active' THEN 'active' WHEN 'blocked' THEN 'blocked' ELSE 'unknown' END,
    followed_at,
    followed_at,
    blocked_at,
    last_event_at,
    0,
    created_at,
    updated_at
FROM line_users;

CREATE TABLE IF NOT EXISTS line_friend_state_events (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    event_identity VARCHAR(191) NOT NULL,
    line_user_id VARCHAR(191) NOT NULL,
    event_type ENUM('follow','unfollow','activity') NOT NULL,
    before_status ENUM('unknown','active','blocked') NOT NULL,
    after_status ENUM('active','blocked') NOT NULL,
    expected_version BIGINT UNSIGNED NOT NULL,
    resulting_version BIGINT UNSIGNED NOT NULL,
    occurred_at_utc DATETIME(6) NOT NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_line_friend_event_identity (event_identity),
    INDEX idx_line_friend_event_user (line_user_id, id),
    CONSTRAINT fk_line_friend_event_user FOREIGN KEY (line_user_id)
        REFERENCES line_platform_users(line_user_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_line_friend_event_version
        CHECK (resulting_version = expected_version + 1)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS line_identity_flows (
    flow_id CHAR(36) PRIMARY KEY,
    flow_purpose ENUM('customer_binding','staff_verification','admin_binding') NOT NULL,
    line_user_id VARCHAR(191) NOT NULL,
    flow_status ENUM('active','used','expired','cancelled') NOT NULL DEFAULT 'active',
    expires_at_utc DATETIME(6) NOT NULL,
    used_at_utc DATETIME(6) NULL,
    attempt_count INT UNSIGNED NOT NULL DEFAULT 0,
    idempotency_key VARCHAR(191) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
        ON UPDATE CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_line_identity_flow_idempotency (idempotency_key),
    INDEX idx_line_identity_flow_user (line_user_id, flow_status, expires_at_utc),
    CONSTRAINT fk_line_identity_flow_user FOREIGN KEY (line_user_id)
        REFERENCES line_platform_users(line_user_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- MySQL versions used by this project do not consistently support conditional
-- column-add syntax. Use metadata-gated DDL so this release is replayable.
SET @line_review_flow_column_exists := (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='line_review_requests'
      AND COLUMN_NAME='identity_flow_id'
);
SET @line_review_flow_column_sql := IF(
    @line_review_flow_column_exists=0,
    'ALTER TABLE line_review_requests ADD COLUMN identity_flow_id CHAR(36) NULL AFTER evidence_snapshot',
    'SELECT 1'
);
PREPARE line_review_flow_column_stmt FROM @line_review_flow_column_sql;
EXECUTE line_review_flow_column_stmt;
DEALLOCATE PREPARE line_review_flow_column_stmt;

SET @line_review_request_key_column_exists := (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='line_review_requests'
      AND COLUMN_NAME='request_idempotency_key'
);
SET @line_review_request_key_column_sql := IF(
    @line_review_request_key_column_exists=0,
    'ALTER TABLE line_review_requests ADD COLUMN request_idempotency_key VARCHAR(191) NULL AFTER identity_flow_id',
    'SELECT 1'
);
PREPARE line_review_request_key_column_stmt FROM @line_review_request_key_column_sql;
EXECUTE line_review_request_key_column_stmt;
DEALLOCATE PREPARE line_review_request_key_column_stmt;

SET @line_review_correlation_column_exists := (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='line_review_requests'
      AND COLUMN_NAME='request_correlation_id'
);
SET @line_review_correlation_column_sql := IF(
    @line_review_correlation_column_exists=0,
    'ALTER TABLE line_review_requests ADD COLUMN request_correlation_id VARCHAR(191) NULL AFTER request_idempotency_key',
    'SELECT 1'
);
PREPARE line_review_correlation_column_stmt FROM @line_review_correlation_column_sql;
EXECUTE line_review_correlation_column_stmt;
DEALLOCATE PREPARE line_review_correlation_column_stmt;

SET @line_review_flow_index_exists := (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS
    WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='line_review_requests'
      AND INDEX_NAME='uq_line_review_identity_flow'
);
SET @line_review_flow_index_sql := IF(
    @line_review_flow_index_exists=0,
    'ALTER TABLE line_review_requests ADD UNIQUE KEY uq_line_review_identity_flow (identity_flow_id)',
    'SELECT 1'
);
PREPARE line_review_flow_index_stmt FROM @line_review_flow_index_sql;
EXECUTE line_review_flow_index_stmt;
DEALLOCATE PREPARE line_review_flow_index_stmt;

SET @line_review_request_key_exists := (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS
    WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='line_review_requests'
      AND INDEX_NAME='uq_line_review_request_idempotency'
);
SET @line_review_request_key_sql := IF(
    @line_review_request_key_exists=0,
    'ALTER TABLE line_review_requests ADD UNIQUE KEY uq_line_review_request_idempotency (request_idempotency_key)',
    'SELECT 1'
);
PREPARE line_review_request_key_stmt FROM @line_review_request_key_sql;
EXECUTE line_review_request_key_stmt;
DEALLOCATE PREPARE line_review_request_key_stmt;

SET @line_review_flow_fk_exists := (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
    WHERE CONSTRAINT_SCHEMA=DATABASE() AND TABLE_NAME='line_review_requests'
      AND CONSTRAINT_NAME='fk_line_review_identity_flow'
);
SET @line_review_flow_fk_sql := IF(
    @line_review_flow_fk_exists=0,
    'ALTER TABLE line_review_requests ADD CONSTRAINT fk_line_review_identity_flow FOREIGN KEY (identity_flow_id) REFERENCES line_identity_flows(flow_id) ON UPDATE RESTRICT ON DELETE RESTRICT',
    'SELECT 1'
);
PREPARE line_review_flow_fk_stmt FROM @line_review_flow_fk_sql;
EXECUTE line_review_flow_fk_stmt;
DEALLOCATE PREPARE line_review_flow_fk_stmt;

SET @line_identity_subject_index_exists := (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS
    WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='line_identity_bindings'
      AND INDEX_NAME='uq_line_identity_subject'
);
SET @line_identity_subject_drop_sql := IF(
    @line_identity_subject_index_exists>0,
    'ALTER TABLE line_identity_bindings DROP INDEX uq_line_identity_subject',
    'SELECT 1'
);
PREPARE line_identity_subject_drop_stmt FROM @line_identity_subject_drop_sql;
EXECUTE line_identity_subject_drop_stmt;
DEALLOCATE PREPARE line_identity_subject_drop_stmt;

SET @line_identity_active_subject_column_exists := (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='line_identity_bindings'
      AND COLUMN_NAME='active_subject_key'
);
SET @line_identity_active_subject_column_sql := IF(
    @line_identity_active_subject_column_exists=0,
    'ALTER TABLE line_identity_bindings ADD COLUMN active_subject_key VARCHAR(400) GENERATED ALWAYS AS (CASE WHEN binding_status IN (''pending_review'',''bound'') THEN CONCAT(subject_type, '':'', subject_reference) ELSE NULL END) STORED',
    'SELECT 1'
);
PREPARE line_identity_active_subject_column_stmt
    FROM @line_identity_active_subject_column_sql;
EXECUTE line_identity_active_subject_column_stmt;
DEALLOCATE PREPARE line_identity_active_subject_column_stmt;

SET @line_identity_active_subject_exists := (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS
    WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='line_identity_bindings'
      AND INDEX_NAME='uq_line_identity_active_subject'
);
SET @line_identity_active_subject_sql := IF(
    @line_identity_active_subject_exists=0,
    'ALTER TABLE line_identity_bindings ADD UNIQUE KEY uq_line_identity_active_subject (active_subject_key)',
    'SELECT 1'
);
PREPARE line_identity_active_subject_stmt FROM @line_identity_active_subject_sql;
EXECUTE line_identity_active_subject_stmt;
DEALLOCATE PREPARE line_identity_active_subject_stmt;

DROP TRIGGER IF EXISTS trg_line_friend_state_events_before_update;
CREATE TRIGGER trg_line_friend_state_events_before_update
BEFORE UPDATE ON line_friend_state_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_friend_state_events records cannot be updated';

DROP TRIGGER IF EXISTS trg_line_friend_state_events_before_delete;
CREATE TRIGGER trg_line_friend_state_events_before_delete
BEFORE DELETE ON line_friend_state_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_friend_state_events records cannot be deleted';
-- END SOURCE: db/schema_parts/158_line_identity_runtime.sql

-- BEGIN SOURCE: db/schema_parts/159_line_messaging_publication_runtime.sql
-- Stage 5 reliable LINE configuration, media-outbox, and Rich Menu publication runtime.

SET @line_outbox_max_attempts_column_exists := (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='line_domain_outbox'
      AND COLUMN_NAME='max_attempts'
);
SET @line_outbox_max_attempts_column_sql := IF(
    @line_outbox_max_attempts_column_exists=0,
    'ALTER TABLE line_domain_outbox ADD COLUMN max_attempts INT UNSIGNED NOT NULL DEFAULT 3 AFTER attempt_count',
    'SELECT 1'
);
PREPARE line_outbox_max_attempts_column_stmt FROM @line_outbox_max_attempts_column_sql;
EXECUTE line_outbox_max_attempts_column_stmt;
DEALLOCATE PREPARE line_outbox_max_attempts_column_stmt;

SET @line_outbox_error_message_column_exists := (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='line_domain_outbox'
      AND COLUMN_NAME='error_message'
);
SET @line_outbox_error_message_column_sql := IF(
    @line_outbox_error_message_column_exists=0,
    'ALTER TABLE line_domain_outbox ADD COLUMN error_message VARCHAR(1000) NULL AFTER error_code',
    'SELECT 1'
);
PREPARE line_outbox_error_message_column_stmt FROM @line_outbox_error_message_column_sql;
EXECUTE line_outbox_error_message_column_stmt;
DEALLOCATE PREPARE line_outbox_error_message_column_stmt;

CREATE TABLE IF NOT EXISTS line_rich_menu_publication_step_receipts (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    publication_id BIGINT UNSIGNED NOT NULL,
    step_name ENUM('create','upload','switch','cleanup') NOT NULL,
    provider_menu_id VARCHAR(191) NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    completed_at_utc DATETIME(6) NOT NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_line_rich_menu_step (publication_id, step_name),
    UNIQUE KEY uq_line_rich_menu_step_idempotency (idempotency_key),
    CONSTRAINT fk_line_rich_menu_step_publication
        FOREIGN KEY (publication_id) REFERENCES line_rich_menu_publication_tasks(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_line_rich_menu_step_receipts_before_update;
CREATE TRIGGER trg_line_rich_menu_step_receipts_before_update
BEFORE UPDATE ON line_rich_menu_publication_step_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_rich_menu_publication_step_receipts records cannot be updated';

DROP TRIGGER IF EXISTS trg_line_rich_menu_step_receipts_before_delete;
CREATE TRIGGER trg_line_rich_menu_step_receipts_before_delete
BEFORE DELETE ON line_rich_menu_publication_step_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_rich_menu_publication_step_receipts records cannot be deleted';
-- END SOURCE: db/schema_parts/159_line_messaging_publication_runtime.sql

-- BEGIN SOURCE: db/schema_parts/160_line_order_group_runtime.sql
-- Canonical LINE order-group command, participant, and invitation runtime.

ALTER TABLE line_order_group_bindings
    MODIFY COLUMN binding_status ENUM(
        'unbound','bound','inviting','active','attention','replaced','released'
    ) NOT NULL DEFAULT 'unbound',
    ADD COLUMN last_invitation_at_utc DATETIME(6) NULL AFTER aggregate_version,
    ADD COLUMN activated_at_utc DATETIME(6) NULL AFTER last_invitation_at_utc;

CREATE TABLE IF NOT EXISTS line_order_group_participants (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    case_no VARCHAR(50) NOT NULL,
    participant_type ENUM('customer','staff') NOT NULL,
    line_user_id VARCHAR(191) NOT NULL,
    invitation_status ENUM(
        'pending','sent','joined','left','failed'
    ) NOT NULL DEFAULT 'pending',
    joined_at_utc DATETIME(6) NULL,
    left_at_utc DATETIME(6) NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
        ON UPDATE CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_line_order_group_participant (
        case_no, participant_type, line_user_id
    ),
    INDEX idx_line_order_group_participant_user (line_user_id, case_no),
    CONSTRAINT fk_line_order_group_participant_binding
        FOREIGN KEY (case_no) REFERENCES line_order_group_bindings(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS line_order_group_runtime_events (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    case_no VARCHAR(50) NOT NULL,
    event_type ENUM(
        'invitation_relayed','member_joined','member_left',
        'group_left','attention_required'
    ) NOT NULL,
    line_user_id VARCHAR(191) NULL,
    invitation_fingerprint CHAR(64) NULL,
    actor_id VARCHAR(191) NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    occurred_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_line_order_group_runtime_idempotency (idempotency_key),
    INDEX idx_line_order_group_runtime_case (case_no, occurred_at_utc, id),
    CONSTRAINT fk_line_order_group_runtime_binding
        FOREIGN KEY (case_no) REFERENCES line_order_group_bindings(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_line_order_group_invitation_fingerprint CHECK (
        invitation_fingerprint IS NULL
        OR invitation_fingerprint REGEXP '^[0-9a-f]{64}$'
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_line_order_group_runtime_events_before_update;
CREATE TRIGGER trg_line_order_group_runtime_events_before_update
BEFORE UPDATE ON line_order_group_runtime_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_order_group_runtime_events records cannot be updated';

DROP TRIGGER IF EXISTS trg_line_order_group_runtime_events_before_delete;
CREATE TRIGGER trg_line_order_group_runtime_events_before_delete
BEFORE DELETE ON line_order_group_runtime_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_order_group_runtime_events records cannot be deleted';
-- END SOURCE: db/schema_parts/160_line_order_group_runtime.sql

-- BEGIN SOURCE: db/schema_parts/161_runtime_monitoring_line_alerts.sql
-- Runtime monitoring projections and canonical LINE alert notification targets.

CREATE TABLE IF NOT EXISTS runtime_service_heartbeats (
    service_name VARCHAR(100) NOT NULL,
    instance_id VARCHAR(191) NOT NULL,
    process_id BIGINT NULL,
    host_name VARCHAR(191) NOT NULL,
    service_status ENUM('starting','running','degraded','stopped') NOT NULL,
    details_snapshot JSON NOT NULL,
    started_at_utc DATETIME(6) NOT NULL,
    last_seen_at_utc DATETIME(6) NOT NULL,
    stopped_at_utc DATETIME(6) NULL,
    PRIMARY KEY (service_name, instance_id),
    INDEX idx_runtime_service_latest (service_name, last_seen_at_utc),
    CONSTRAINT chk_runtime_service_details
        CHECK (JSON_TYPE(details_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS runtime_health_status (
    check_name VARCHAR(100) PRIMARY KEY,
    component VARCHAR(100) NOT NULL,
    health_status ENUM(
        'healthy','warning','critical','unknown','maintenance'
    ) NOT NULL,
    raw_status ENUM(
        'healthy','warning','critical','unknown','maintenance'
    ) NOT NULL,
    message VARCHAR(1000) NOT NULL,
    details_snapshot JSON NOT NULL,
    response_ms INT UNSIGNED NULL,
    consecutive_failures INT UNSIGNED NOT NULL DEFAULT 0,
    consecutive_successes INT UNSIGNED NOT NULL DEFAULT 0,
    checked_at_utc DATETIME(6) NOT NULL,
    last_success_at_utc DATETIME(6) NULL,
    status_changed_at_utc DATETIME(6) NOT NULL,
    CONSTRAINT chk_runtime_health_details
        CHECK (JSON_TYPE(details_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS runtime_health_events (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    check_name VARCHAR(100) NOT NULL,
    component VARCHAR(100) NOT NULL,
    transition_type ENUM(
        'opened','escalated','reminder','recovered','test'
    ) NOT NULL,
    before_status ENUM(
        'healthy','warning','critical','unknown','maintenance'
    ) NULL,
    resulting_status ENUM(
        'healthy','warning','critical','unknown','maintenance'
    ) NOT NULL,
    message VARCHAR(1000) NOT NULL,
    details_snapshot JSON NOT NULL,
    event_fingerprint CHAR(64) NOT NULL,
    occurred_at_utc DATETIME(6) NOT NULL,
    UNIQUE KEY uq_runtime_health_event_fingerprint (event_fingerprint),
    INDEX idx_runtime_health_event_check (check_name, occurred_at_utc, id),
    CONSTRAINT chk_runtime_health_event_details
        CHECK (JSON_TYPE(details_snapshot) = 'OBJECT'),
    CONSTRAINT chk_runtime_health_event_fingerprint
        CHECK (event_fingerprint REGEXP '^[0-9a-f]{64}$')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS line_alert_notification_targets (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    target_type ENUM('admin_user','group') NOT NULL,
    admin_user_id BIGINT NULL,
    group_id VARCHAR(191) NULL,
    display_name VARCHAR(191) NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    minimum_status ENUM('warning','critical') NOT NULL DEFAULT 'warning',
    created_by_actor_id VARCHAR(191) NOT NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
        ON UPDATE CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_line_alert_admin_target (admin_user_id),
    UNIQUE KEY uq_line_alert_group_target (group_id),
    CONSTRAINT fk_line_alert_admin_target
        FOREIGN KEY (admin_user_id) REFERENCES admin_users(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_line_alert_target_identity CHECK (
        (target_type='admin_user' AND admin_user_id IS NOT NULL AND group_id IS NULL)
        OR
        (target_type='group' AND admin_user_id IS NULL AND group_id IS NOT NULL)
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS line_alert_delivery_intents (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    health_event_id BIGINT UNSIGNED NOT NULL,
    target_id BIGINT UNSIGNED NOT NULL,
    delivery_task_id BIGINT UNSIGNED NULL,
    projection_status ENUM('queued','skipped','failed') NOT NULL,
    resolved_line_target_type ENUM('user','group') NULL,
    resolved_line_target_id VARCHAR(191) NULL,
    error_code VARCHAR(191) NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_line_alert_delivery_intent (health_event_id, target_id),
    INDEX idx_line_alert_delivery_task (delivery_task_id),
    CONSTRAINT fk_line_alert_intent_event
        FOREIGN KEY (health_event_id) REFERENCES runtime_health_events(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_line_alert_intent_target
        FOREIGN KEY (target_id) REFERENCES line_alert_notification_targets(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_line_alert_intent_delivery
        FOREIGN KEY (delivery_task_id) REFERENCES line_delivery_tasks(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_runtime_health_events_before_update;
CREATE TRIGGER trg_runtime_health_events_before_update
BEFORE UPDATE ON runtime_health_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'runtime_health_events records cannot be updated';

DROP TRIGGER IF EXISTS trg_runtime_health_events_before_delete;
CREATE TRIGGER trg_runtime_health_events_before_delete
BEFORE DELETE ON runtime_health_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'runtime_health_events records cannot be deleted';

DROP TRIGGER IF EXISTS trg_line_alert_delivery_intents_before_update;
CREATE TRIGGER trg_line_alert_delivery_intents_before_update
BEFORE UPDATE ON line_alert_delivery_intents
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_alert_delivery_intents records cannot be updated';

DROP TRIGGER IF EXISTS trg_line_alert_delivery_intents_before_delete;
CREATE TRIGGER trg_line_alert_delivery_intents_before_delete
BEFORE DELETE ON line_alert_delivery_intents
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_alert_delivery_intents records cannot be deleted';
-- END SOURCE: db/schema_parts/161_runtime_monitoring_line_alerts.sql

-- BEGIN SOURCE: db/schema_parts/162_matching_line_communication.sql
-- Canonical matching notification intents, one-time LINE actions, and responses.

SET @matching_communication_version_exists = (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'caregiver_matching_plans'
      AND COLUMN_NAME = 'communication_version'
);
SET @matching_communication_version_sql = IF(
    @matching_communication_version_exists = 0,
    'ALTER TABLE `caregiver_matching_plans` ADD COLUMN `communication_version` INT UNSIGNED NOT NULL DEFAULT 0 COMMENT ''配對通知與回覆的 optimistic version'' AFTER `version`',
    'SELECT 1'
);
PREPARE matching_communication_version_stmt FROM @matching_communication_version_sql;
EXECUTE matching_communication_version_stmt;
DEALLOCATE PREPARE matching_communication_version_stmt;

CREATE TABLE IF NOT EXISTS matching_notification_intents (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    plan_id BIGINT NOT NULL,
    segment_id BIGINT NULL,
    notification_kind ENUM(
        'caregiver_info_1','caregiver_info_2','customer_profiles'
    ) NOT NULL,
    recipient_line_user_id VARCHAR(191) NOT NULL,
    payload_snapshot JSON NOT NULL,
    projection_status ENUM('pending','projected','failed','cancelled')
        NOT NULL DEFAULT 'pending',
    delivery_task_id BIGINT UNSIGNED NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    payload_fingerprint CHAR(64) NOT NULL,
    created_by_actor_id VARCHAR(191) NOT NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    projected_at_utc DATETIME(6) NULL,
    UNIQUE KEY uq_matching_notification_idempotency (idempotency_key),
    INDEX idx_matching_notification_plan (plan_id, created_at_utc, id),
    INDEX idx_matching_notification_segment (segment_id, created_at_utc, id),
    INDEX idx_matching_notification_delivery (delivery_task_id),
    CONSTRAINT fk_matching_notification_plan FOREIGN KEY (plan_id)
        REFERENCES caregiver_matching_plans(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_matching_notification_segment FOREIGN KEY (segment_id)
        REFERENCES caregiver_matching_plan_segments(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_matching_notification_delivery FOREIGN KEY (delivery_task_id)
        REFERENCES line_delivery_tasks(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_matching_notification_payload CHECK (
        JSON_TYPE(payload_snapshot) = 'OBJECT'
    ),
    CONSTRAINT chk_matching_notification_fingerprint CHECK (
        payload_fingerprint REGEXP '^[0-9a-f]{64}$'
    ),
    CONSTRAINT chk_matching_notification_target CHECK (
        (notification_kind IN ('caregiver_info_1','caregiver_info_2') AND segment_id IS NOT NULL)
        OR (notification_kind='customer_profiles' AND segment_id IS NULL)
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS matching_line_interactions (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    token_hash CHAR(64) NOT NULL,
    plan_id BIGINT NOT NULL,
    segment_id BIGINT NULL,
    action_scope ENUM('caregiver_willingness','customer_decision') NOT NULL,
    recipient_line_user_id VARCHAR(191) NOT NULL,
    interaction_status ENUM('active','consumed','expired','revoked')
        NOT NULL DEFAULT 'active',
    expires_at_utc DATETIME(6) NOT NULL,
    consumed_at_utc DATETIME(6) NULL,
    consumed_by_line_user_id VARCHAR(191) NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_matching_line_interaction_token (token_hash),
    INDEX idx_matching_line_interaction_plan (plan_id, action_scope, interaction_status),
    CONSTRAINT fk_matching_line_interaction_plan FOREIGN KEY (plan_id)
        REFERENCES caregiver_matching_plans(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_matching_line_interaction_segment FOREIGN KEY (segment_id)
        REFERENCES caregiver_matching_plan_segments(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_matching_line_interaction_token CHECK (
        token_hash REGEXP '^[0-9a-f]{64}$'
    ),
    CONSTRAINT chk_matching_line_interaction_target CHECK (
        (action_scope='caregiver_willingness' AND segment_id IS NOT NULL)
        OR (action_scope='customer_decision' AND segment_id IS NULL)
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS matching_response_events (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    plan_id BIGINT NOT NULL,
    segment_id BIGINT NULL,
    response_type ENUM('caregiver_willingness','customer_decision') NOT NULL,
    response_value ENUM(
        'willing','unwilling','accepted','declined','contact_requested'
    ) NOT NULL,
    response_source ENUM('line','admin') NOT NULL,
    actor_id VARCHAR(191) NOT NULL,
    line_user_id VARCHAR(191) NULL,
    reason VARCHAR(500) NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    payload_fingerprint CHAR(64) NOT NULL,
    occurred_at_utc DATETIME(6) NOT NULL,
    UNIQUE KEY uq_matching_response_idempotency (idempotency_key),
    INDEX idx_matching_response_plan (plan_id, occurred_at_utc, id),
    INDEX idx_matching_response_segment (segment_id, occurred_at_utc, id),
    CONSTRAINT fk_matching_response_plan FOREIGN KEY (plan_id)
        REFERENCES caregiver_matching_plans(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_matching_response_segment FOREIGN KEY (segment_id)
        REFERENCES caregiver_matching_plan_segments(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_matching_response_fingerprint CHECK (
        payload_fingerprint REGEXP '^[0-9a-f]{64}$'
    ),
    CONSTRAINT chk_matching_response_target CHECK (
        (response_type='caregiver_willingness'
         AND segment_id IS NOT NULL
         AND response_value IN ('willing','unwilling'))
        OR
        (response_type='customer_decision'
         AND segment_id IS NULL
         AND response_value IN ('accepted','declined','contact_requested'))
    ),
    CONSTRAINT chk_matching_response_manual_reason CHECK (
        response_source='line' OR CHAR_LENGTH(TRIM(reason)) > 0
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO matching_response_events (
    plan_id, segment_id, response_type, response_value, response_source,
    actor_id, line_user_id, reason, idempotency_key, payload_fingerprint,
    occurred_at_utc
)
SELECT legacy.plan_id,
       legacy.segment_id,
       'caregiver_willingness',
       JSON_UNQUOTE(JSON_EXTRACT(legacy.payload, '$.willingness')),
       'admin',
       legacy.actor,
       NULL,
       'Stage 7 migrated legacy willingness event',
       CONCAT('legacy-matching-response:', legacy.id),
       SHA2(CONCAT_WS('|', legacy.plan_id, legacy.segment_id,
           JSON_UNQUOTE(JSON_EXTRACT(legacy.payload, '$.willingness')),
           legacy.event_key), 256),
       legacy.occurred_at
FROM caregiver_matching_plan_events legacy
WHERE legacy.event_type = 'willingness_changed'
  AND JSON_UNQUOTE(JSON_EXTRACT(legacy.payload, '$.willingness'))
      IN ('willing','unwilling')
  AND NOT EXISTS (
      SELECT 1
      FROM caregiver_matching_plan_events newer
      WHERE newer.plan_id = legacy.plan_id
        AND newer.segment_id = legacy.segment_id
        AND newer.event_type = 'willingness_changed'
        AND (
            newer.occurred_at > legacy.occurred_at
            OR (newer.occurred_at = legacy.occurred_at AND newer.id > legacy.id)
        )
  )
  AND NOT EXISTS (
      SELECT 1 FROM matching_response_events canonical
      WHERE canonical.idempotency_key = CONCAT('legacy-matching-response:', legacy.id)
  );

DROP TRIGGER IF EXISTS trg_matching_response_events_before_update;
CREATE TRIGGER trg_matching_response_events_before_update
BEFORE UPDATE ON matching_response_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'matching_response_events records cannot be updated';

DROP TRIGGER IF EXISTS trg_matching_response_events_before_delete;
CREATE TRIGGER trg_matching_response_events_before_delete
BEFORE DELETE ON matching_response_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'matching_response_events records cannot be deleted';
-- END SOURCE: db/schema_parts/162_matching_line_communication.sql

-- BEGIN SOURCE: db/schema_parts/163_knowledge_runtime.sql
-- Durable indexing and cited-answer runtime for governed knowledge roots.

ALTER TABLE knowledge_items
    ADD COLUMN source_identity VARCHAR(191) NULL AFTER id,
    ADD UNIQUE KEY uq_knowledge_source_identity (source_identity);

UPDATE knowledge_items
SET source_identity = CONCAT('knowledge:', id)
WHERE source_identity IS NULL;

CREATE TABLE IF NOT EXISTS knowledge_item_versions (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    item_id BIGINT NOT NULL,
    item_version BIGINT UNSIGNED NOT NULL,
    content MEDIUMTEXT NOT NULL,
    source_digest CHAR(64) NOT NULL,
    event_type ENUM('ingested','reviewed','published','retired') NOT NULL,
    actor_admin_user_id BIGINT NOT NULL,
    reason VARCHAR(500) NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    recorded_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_knowledge_item_version (item_id, item_version),
    UNIQUE KEY uq_knowledge_version_key (idempotency_key),
    CONSTRAINT fk_knowledge_version_item FOREIGN KEY (item_id)
        REFERENCES knowledge_items(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_knowledge_version_actor FOREIGN KEY (actor_admin_user_id)
        REFERENCES admin_users(id) ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT IGNORE INTO knowledge_item_versions
    (item_id, item_version, content, source_digest, event_type,
     actor_admin_user_id, reason, idempotency_key)
SELECT id, version, content, content_digest,
       CASE state
           WHEN 'reviewed' THEN 'reviewed'
           WHEN 'published' THEN 'published'
           WHEN 'retired' THEN 'retired'
           ELSE 'ingested'
       END,
       created_by_admin_user_id, 'runtime version backfill',
       CONCAT('knowledge-runtime-backfill:', id, ':', version)
FROM knowledge_items
WHERE version > 0;

CREATE TABLE IF NOT EXISTS knowledge_answer_requests (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    question VARCHAR(2000) NOT NULL,
    requester_line_user_id VARCHAR(191) NULL,
    request_status ENUM('pending','processing','answered','unsupported','failed') NOT NULL DEFAULT 'pending',
    idempotency_key VARCHAR(191) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    completed_at_utc DATETIME(6) NULL,
    UNIQUE KEY uq_knowledge_answer_request_key (idempotency_key),
    INDEX idx_knowledge_answer_request_status (request_status, id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS knowledge_jobs (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    job_type ENUM('index_build','answer') NOT NULL,
    processing_status ENUM('pending','processing','completed','retry_pending','failed') NOT NULL DEFAULT 'pending',
    answer_request_id BIGINT UNSIGNED NULL,
    target_index_version INT UNSIGNED NULL,
    question VARCHAR(2000) NULL,
    attempt_count INT UNSIGNED NOT NULL DEFAULT 0,
    max_attempts INT UNSIGNED NOT NULL DEFAULT 3,
    available_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    lease_owner VARCHAR(191) NULL,
    lease_expires_at_utc DATETIME(6) NULL,
    last_error_code VARCHAR(191) NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    created_by_actor_id VARCHAR(191) NOT NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    completed_at_utc DATETIME(6) NULL,
    UNIQUE KEY uq_knowledge_job_key (idempotency_key),
    INDEX idx_knowledge_job_claim (processing_status, available_at_utc, id),
    CONSTRAINT fk_knowledge_job_answer_request FOREIGN KEY (answer_request_id)
        REFERENCES knowledge_answer_requests(id) ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS knowledge_indexes (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    index_version INT UNSIGNED NOT NULL,
    index_status ENUM('requested','building','ready','stale','failed') NOT NULL,
    content_set_digest CHAR(64) NULL,
    built_at_utc DATETIME(6) NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_knowledge_index_version (index_version),
    INDEX idx_knowledge_index_ready (index_status, index_version)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS knowledge_answer_receipts (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    answer_request_id BIGINT UNSIGNED NOT NULL,
    answer_text TEXT NOT NULL,
    index_version INT UNSIGNED NOT NULL,
    authoritative BOOLEAN NOT NULL DEFAULT FALSE,
    line_delivery_task_id BIGINT UNSIGNED NULL,
    answered_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_knowledge_answer_receipt_request (answer_request_id),
    CONSTRAINT fk_knowledge_answer_request FOREIGN KEY (answer_request_id)
        REFERENCES knowledge_answer_requests(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_knowledge_answer_delivery FOREIGN KEY (line_delivery_task_id)
        REFERENCES line_delivery_tasks(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_knowledge_answer_non_authoritative CHECK (authoritative=FALSE)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS knowledge_answer_sources (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    answer_receipt_id BIGINT UNSIGNED NOT NULL,
    source_identity VARCHAR(191) NOT NULL,
    source_version BIGINT UNSIGNED NOT NULL,
    safe_excerpt VARCHAR(500) NOT NULL,
    citation_order INT UNSIGNED NOT NULL,
    UNIQUE KEY uq_knowledge_answer_source_order (answer_receipt_id, citation_order),
    CONSTRAINT fk_knowledge_answer_source_receipt FOREIGN KEY (answer_receipt_id)
        REFERENCES knowledge_answer_receipts(id) ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_knowledge_item_versions_before_update;
CREATE TRIGGER trg_knowledge_item_versions_before_update
BEFORE UPDATE ON knowledge_item_versions FOR EACH ROW
SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='knowledge_item_versions records cannot be updated';

DROP TRIGGER IF EXISTS trg_knowledge_item_versions_before_delete;
CREATE TRIGGER trg_knowledge_item_versions_before_delete
BEFORE DELETE ON knowledge_item_versions FOR EACH ROW
SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='knowledge_item_versions records cannot be deleted';
-- END SOURCE: db/schema_parts/163_knowledge_runtime.sql

-- BEGIN SOURCE: db/schema_parts/164_line_rich_menu_preview_bridge.sql
-- Bind the governed preview confirmation to the canonical publication task.
ALTER TABLE line_rich_menu_publish_previews
    ADD COLUMN canonical_publication_task_id BIGINT UNSIGNED NULL
        AFTER publication_id,
    ADD INDEX idx_line_menu_preview_canonical_task (
        canonical_publication_task_id
    ),
    ADD CONSTRAINT fk_line_menu_preview_canonical_task
        FOREIGN KEY (canonical_publication_task_id)
        REFERENCES line_rich_menu_publication_tasks(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT;
-- END SOURCE: db/schema_parts/164_line_rich_menu_preview_bridge.sql

-- BEGIN SOURCE: db/schema_parts/165_anomaly_workflow_event_idempotency_widen.sql
-- Widen idempotency_key: VARCHAR(191) truncated content-hash dedupe keys,
-- causing INSERT ... ON DUPLICATE KEY to fail with "Data too long for column
-- 'idempotency_key'" and roll back the background anomaly-scan cycle.

ALTER TABLE anomaly_workflow_events
    MODIFY COLUMN idempotency_key VARCHAR(320) NOT NULL;
-- END SOURCE: db/schema_parts/165_anomaly_workflow_event_idempotency_widen.sql

-- BEGIN SOURCE: db/schema_parts/166_contract_signing_workflow.sql
-- 166_contract_signing_workflow.sql
-- 案件契約文件、月嫂／客戶簽署事件與簽約前服務承諾。
-- 文件與事件均 append-only；訂單 lifecycle、正式排班與金流各自維持既有 SSOT。

CREATE TABLE IF NOT EXISTS contract_document_versions (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    case_no VARCHAR(50) NOT NULL,
    document_scope ENUM('staff_segment', 'client_contract') NOT NULL,
    document_role ENUM('template_generated', 'signed_return') NOT NULL,
    matching_plan_id BIGINT NOT NULL,
    matching_segment_id BIGINT NULL,
    document_target_key VARCHAR(100) NOT NULL,
    source_document_version_id BIGINT NULL,
    template_key VARCHAR(100) NULL,
    template_sha256 CHAR(64) NULL,
    mapping_sha256 CHAR(64) NULL,
    facts_snapshot_sha256 CHAR(64) NULL,
    media_asset_id BIGINT NOT NULL,
    version_number INT NOT NULL,
    replaces_document_version_id BIGINT NULL,
    created_by VARCHAR(100) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_contract_document_version (
        case_no, document_scope, document_target_key, version_number
    ),
    INDEX idx_contract_document_case (case_no, document_scope, created_at),
    INDEX idx_contract_document_segment (matching_segment_id, created_at),
    CONSTRAINT fk_contract_document_case
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_contract_document_plan
        FOREIGN KEY (matching_plan_id) REFERENCES caregiver_matching_plans(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_contract_document_segment
        FOREIGN KEY (matching_segment_id) REFERENCES caregiver_matching_plan_segments(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_contract_document_source
        FOREIGN KEY (source_document_version_id) REFERENCES contract_document_versions(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_contract_document_media_asset
        FOREIGN KEY (media_asset_id) REFERENCES media_assets(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_contract_document_replaces
        FOREIGN KEY (replaces_document_version_id) REFERENCES contract_document_versions(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_contract_document_target
        CHECK (
            (document_scope = 'staff_segment'
             AND matching_segment_id IS NOT NULL
             AND CHAR_LENGTH(TRIM(document_target_key)) > 0)
            OR (document_scope = 'client_contract'
                AND matching_segment_id IS NULL
                AND CHAR_LENGTH(TRIM(document_target_key)) > 0)
        ),
    CONSTRAINT chk_contract_document_source
        CHECK (
            (document_role = 'template_generated'
             AND template_key IS NOT NULL
             AND template_sha256 IS NOT NULL
             AND mapping_sha256 IS NOT NULL
             AND facts_snapshot_sha256 IS NOT NULL
             AND source_document_version_id IS NULL)
            OR (document_role = 'signed_return' AND source_document_version_id IS NOT NULL)
        ),
    CONSTRAINT chk_contract_document_version
        CHECK (version_number >= 1 AND CHAR_LENGTH(TRIM(created_by)) > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS contract_document_access_grants (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    document_version_id BIGINT NOT NULL,
    case_no VARCHAR(50) NOT NULL,
    recipient_line_user_id VARCHAR(191) NOT NULL,
    recipient_subject_type ENUM('customer', 'staff') NOT NULL,
    recipient_subject_reference VARCHAR(191) NOT NULL,
    token_sha256 CHAR(64) NOT NULL,
    expires_at DATETIME(6) NOT NULL,
    created_by VARCHAR(100) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_contract_document_access_token (token_sha256),
    INDEX idx_contract_document_access_document (
        document_version_id, recipient_line_user_id, expires_at
    ),
    CONSTRAINT fk_contract_document_access_document
        FOREIGN KEY (document_version_id) REFERENCES contract_document_versions(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_contract_document_access_case
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_contract_document_access_text
        CHECK (
            CHAR_LENGTH(TRIM(recipient_line_user_id)) > 0
            AND CHAR_LENGTH(TRIM(recipient_subject_reference)) > 0
            AND CHAR_LENGTH(TRIM(created_by)) > 0
        ),
    CONSTRAINT chk_contract_document_access_token
        CHECK (token_sha256 REGEXP '^[0-9a-f]{64}$')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS contract_signing_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    case_no VARCHAR(50) NOT NULL,
    document_version_id BIGINT NOT NULL,
    matching_plan_id BIGINT NOT NULL,
    matching_segment_id BIGINT NULL,
    event_type ENUM('sent', 'signed_received') NOT NULL,
    delivery_channel ENUM('line') NULL,
    line_delivery_task_id BIGINT UNSIGNED NULL,
    document_access_grant_id BIGINT UNSIGNED NULL,
    event_key VARCHAR(100) NOT NULL,
    actor VARCHAR(100) NOT NULL,
    payload JSON NOT NULL,
    occurred_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_contract_signing_event_key (event_key),
    INDEX idx_contract_signing_event_case (case_no, occurred_at),
    INDEX idx_contract_signing_event_document (document_version_id, occurred_at),
    INDEX idx_contract_signing_event_segment (matching_segment_id, occurred_at),
    CONSTRAINT fk_contract_signing_event_case
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_contract_signing_event_document
        FOREIGN KEY (document_version_id) REFERENCES contract_document_versions(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_contract_signing_event_plan
        FOREIGN KEY (matching_plan_id) REFERENCES caregiver_matching_plans(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_contract_signing_event_segment
        FOREIGN KEY (matching_segment_id) REFERENCES caregiver_matching_plan_segments(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_contract_signing_event_line_delivery_task
        FOREIGN KEY (line_delivery_task_id) REFERENCES line_delivery_tasks(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_contract_signing_event_document_access_grant
        FOREIGN KEY (document_access_grant_id)
        REFERENCES contract_document_access_grants(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_contract_signing_event_channel
        CHECK (
            (event_type = 'sent' AND delivery_channel = 'line'
             AND line_delivery_task_id IS NOT NULL
             AND document_access_grant_id IS NOT NULL)
            OR (event_type = 'signed_received' AND delivery_channel IS NULL
                AND line_delivery_task_id IS NULL
                AND document_access_grant_id IS NULL)
        ),
    CONSTRAINT chk_contract_signing_event_payload
        CHECK (
            JSON_TYPE(payload) = 'OBJECT'
            AND CHAR_LENGTH(TRIM(event_key)) > 0
            AND CHAR_LENGTH(TRIM(actor)) > 0
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS contract_signing_command_receipts (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    idempotency_key VARCHAR(100) NOT NULL,
    command_fingerprint CHAR(64) NOT NULL,
    command_kind VARCHAR(80) NOT NULL,
    case_no VARCHAR(50) NOT NULL,
    document_version_id BIGINT NULL,
    signing_event_id BIGINT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    result_snapshot JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_contract_signing_receipt_key (idempotency_key),
    CONSTRAINT fk_contract_signing_receipt_case FOREIGN KEY (case_no) REFERENCES orders(case_no),
    CONSTRAINT fk_contract_signing_receipt_document FOREIGN KEY (document_version_id) REFERENCES contract_document_versions(id),
    CONSTRAINT fk_contract_signing_receipt_event FOREIGN KEY (signing_event_id) REFERENCES contract_signing_events(id),
    CONSTRAINT chk_contract_signing_receipt_payload CHECK (JSON_TYPE(result_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS contract_signing_outbox (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    case_no VARCHAR(50) NOT NULL,
    signing_event_id BIGINT NOT NULL,
    intent_key VARCHAR(100) NOT NULL,
    intent_type VARCHAR(80) NOT NULL,
    payload_snapshot JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_contract_signing_outbox_key (intent_key),
    CONSTRAINT fk_contract_signing_outbox_case FOREIGN KEY (case_no) REFERENCES orders(case_no),
    CONSTRAINT fk_contract_signing_outbox_event FOREIGN KEY (signing_event_id) REFERENCES contract_signing_events(id),
    CONSTRAINT chk_contract_signing_outbox_payload CHECK (JSON_TYPE(payload_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS precontract_service_commitments (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    case_no VARCHAR(50) NOT NULL,
    matching_plan_id BIGINT NOT NULL,
    commitment_key VARCHAR(100) NOT NULL,
    plan_snapshot_sha256 CHAR(64) NOT NULL,
    created_by VARCHAR(100) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_precontract_commitment_key (commitment_key),
    UNIQUE KEY uq_precontract_commitment_plan (matching_plan_id),
    INDEX idx_precontract_commitment_case (case_no, created_at),
    CONSTRAINT fk_precontract_commitment_case
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_precontract_commitment_plan
        FOREIGN KEY (matching_plan_id) REFERENCES caregiver_matching_plans(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_precontract_commitment_nonempty
        CHECK (
            CHAR_LENGTH(TRIM(commitment_key)) > 0
            AND CHAR_LENGTH(TRIM(created_by)) > 0
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS precontract_service_commitment_days (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    commitment_id BIGINT NOT NULL,
    matching_segment_id BIGINT NOT NULL,
    staff_id INT NOT NULL,
    service_date DATE NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_precontract_commitment_segment_date (
        commitment_id, matching_segment_id, service_date
    ),
    INDEX idx_precontract_commitment_staff_date (staff_id, service_date),
    CONSTRAINT fk_precontract_commitment_day_header
        FOREIGN KEY (commitment_id) REFERENCES precontract_service_commitments(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_precontract_commitment_day_segment
        FOREIGN KEY (matching_segment_id) REFERENCES caregiver_matching_plan_segments(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_precontract_commitment_day_staff
        FOREIGN KEY (staff_id) REFERENCES staff(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS precontract_service_commitment_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    commitment_id BIGINT NOT NULL,
    event_type ENUM('cancelled', 'converted') NOT NULL,
    event_key VARCHAR(100) NOT NULL,
    actor VARCHAR(100) NOT NULL,
    payload JSON NOT NULL,
    occurred_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_precontract_commitment_event_key (event_key),
    UNIQUE KEY uq_precontract_commitment_terminal (commitment_id),
    CONSTRAINT fk_precontract_commitment_event_header
        FOREIGN KEY (commitment_id) REFERENCES precontract_service_commitments(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_precontract_commitment_event_payload
        CHECK (
            JSON_TYPE(payload) = 'OBJECT'
            AND CHAR_LENGTH(TRIM(event_key)) > 0
            AND CHAR_LENGTH(TRIM(actor)) > 0
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_contract_document_versions_before_update;
CREATE TRIGGER trg_contract_document_versions_before_update BEFORE UPDATE ON contract_document_versions FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'contract_document_versions records cannot be updated';

DROP TRIGGER IF EXISTS trg_contract_document_versions_before_delete;
CREATE TRIGGER trg_contract_document_versions_before_delete BEFORE DELETE ON contract_document_versions FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'contract_document_versions records cannot be deleted';

DROP TRIGGER IF EXISTS trg_contract_signing_events_before_update;
CREATE TRIGGER trg_contract_signing_events_before_update BEFORE UPDATE ON contract_signing_events FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'contract_signing_events records cannot be updated';

DROP TRIGGER IF EXISTS trg_contract_signing_events_before_delete;
CREATE TRIGGER trg_contract_signing_events_before_delete BEFORE DELETE ON contract_signing_events FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'contract_signing_events records cannot be deleted';

DROP TRIGGER IF EXISTS trg_precontract_service_commitments_before_update;
CREATE TRIGGER trg_precontract_service_commitments_before_update BEFORE UPDATE ON precontract_service_commitments FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'precontract_service_commitments records cannot be updated';

DROP TRIGGER IF EXISTS trg_precontract_service_commitments_before_delete;
CREATE TRIGGER trg_precontract_service_commitments_before_delete BEFORE DELETE ON precontract_service_commitments FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'precontract_service_commitments records cannot be deleted';

DROP TRIGGER IF EXISTS trg_precontract_service_commitment_days_before_update;
CREATE TRIGGER trg_precontract_service_commitment_days_before_update BEFORE UPDATE ON precontract_service_commitment_days FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'precontract_service_commitment_days records cannot be updated';

DROP TRIGGER IF EXISTS trg_precontract_service_commitment_days_before_delete;
CREATE TRIGGER trg_precontract_service_commitment_days_before_delete BEFORE DELETE ON precontract_service_commitment_days FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'precontract_service_commitment_days records cannot be deleted';

DROP TRIGGER IF EXISTS trg_precontract_service_commitment_events_before_update;
CREATE TRIGGER trg_precontract_service_commitment_events_before_update BEFORE UPDATE ON precontract_service_commitment_events FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'precontract_service_commitment_events records cannot be updated';

DROP TRIGGER IF EXISTS trg_precontract_service_commitment_events_before_delete;
CREATE TRIGGER trg_precontract_service_commitment_events_before_delete BEFORE DELETE ON precontract_service_commitment_events FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'precontract_service_commitment_events records cannot be deleted';
-- END SOURCE: db/schema_parts/166_contract_signing_workflow.sql

-- BEGIN SOURCE: db/schema_parts/167_client_finance_overage_dispositions.sql
-- Immutable lineage for actual client receipts that exceed one receivable.

CREATE TABLE IF NOT EXISTS client_receipt_overage_dispositions (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    case_no VARCHAR(50) NOT NULL,
    finance_import_row_id BIGINT NOT NULL,
    receipt_ledger_entry_id BIGINT NOT NULL,
    receivable_obligation_identity VARCHAR(191) NOT NULL,
    refund_obligation_identity VARCHAR(191) NOT NULL,
    overage_amount_ntd BIGINT NOT NULL,
    settlement_identity CHAR(64) NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    actor VARCHAR(100) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_client_receipt_overage_bank_row (finance_import_row_id),
    UNIQUE KEY uq_client_receipt_overage_ledger (receipt_ledger_entry_id),
    UNIQUE KEY uq_client_receipt_overage_refund (refund_obligation_identity),
    UNIQUE KEY uq_client_receipt_overage_idempotency (idempotency_key),
    CONSTRAINT fk_client_receipt_overage_order
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_client_receipt_overage_bank_row
        FOREIGN KEY (finance_import_row_id) REFERENCES finance_import_rows(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_client_receipt_overage_ledger
        FOREIGN KEY (receipt_ledger_entry_id) REFERENCES client_ledger_entries(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_client_receipt_overage_receivable
        FOREIGN KEY (receivable_obligation_identity) REFERENCES client_obligations(obligation_identity)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_client_receipt_overage_refund
        FOREIGN KEY (refund_obligation_identity) REFERENCES client_obligations(obligation_identity)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_client_receipt_overage_amount CHECK (overage_amount_ntd > 0),
    CONSTRAINT chk_client_receipt_overage_settlement
        CHECK (settlement_identity REGEXP '^[0-9a-f]{64}$')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_client_receipt_overage_dispositions_before_update;
CREATE TRIGGER trg_client_receipt_overage_dispositions_before_update
BEFORE UPDATE ON client_receipt_overage_dispositions
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client_receipt_overage_dispositions records cannot be updated';

DROP TRIGGER IF EXISTS trg_client_receipt_overage_dispositions_before_delete;
CREATE TRIGGER trg_client_receipt_overage_dispositions_before_delete
BEFORE DELETE ON client_receipt_overage_dispositions
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client_receipt_overage_dispositions records cannot be deleted';

CREATE TABLE IF NOT EXISTS client_over_refund_recoveries (
    recovery_identity VARCHAR(191) PRIMARY KEY,
    case_no VARCHAR(50) NOT NULL,
    finance_import_row_id BIGINT NOT NULL,
    refund_ledger_entry_id BIGINT NOT NULL,
    refund_obligation_identity VARCHAR(191) NOT NULL,
    amount_due_ntd BIGINT NOT NULL,
    status ENUM('open', 'settled', 'cancelled') NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    actor VARCHAR(100) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    projection_version BIGINT UNSIGNED NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_client_over_refund_bank_row (finance_import_row_id),
    UNIQUE KEY uq_client_over_refund_ledger (refund_ledger_entry_id),
    UNIQUE KEY uq_client_over_refund_idempotency (idempotency_key),
    INDEX idx_client_over_refund_case_status (case_no, status),
    CONSTRAINT fk_client_over_refund_order
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_client_over_refund_bank_row
        FOREIGN KEY (finance_import_row_id) REFERENCES finance_import_rows(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_client_over_refund_ledger
        FOREIGN KEY (refund_ledger_entry_id) REFERENCES client_ledger_entries(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_client_over_refund_refund_obligation
        FOREIGN KEY (refund_obligation_identity) REFERENCES client_obligations(obligation_identity)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_client_over_refund_amount CHECK (amount_due_ntd > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS client_over_refund_recovery_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    recovery_identity VARCHAR(191) NOT NULL,
    event_type ENUM('established', 'collected', 'cancelled') NOT NULL,
    finance_import_row_id BIGINT NULL,
    receipt_ledger_entry_id BIGINT NULL,
    before_amount_ntd BIGINT NOT NULL,
    after_amount_ntd BIGINT NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    actor VARCHAR(100) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_client_over_refund_event_idempotency (idempotency_key),
    CONSTRAINT fk_client_over_refund_event_recovery
        FOREIGN KEY (recovery_identity) REFERENCES client_over_refund_recoveries(recovery_identity)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_client_over_refund_event_bank_row
        FOREIGN KEY (finance_import_row_id) REFERENCES finance_import_rows(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_client_over_refund_event_ledger
        FOREIGN KEY (receipt_ledger_entry_id) REFERENCES client_ledger_entries(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_client_over_refund_event_amount
        CHECK (
            after_amount_ntd >= 0
            AND (
                (event_type = 'established' AND before_amount_ntd = 0 AND after_amount_ntd > 0)
                OR (event_type IN ('collected', 'cancelled') AND before_amount_ntd > after_amount_ntd)
            )
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_client_over_refund_recovery_events_before_update;
CREATE TRIGGER trg_client_over_refund_recovery_events_before_update
BEFORE UPDATE ON client_over_refund_recovery_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client_over_refund_recovery_events records cannot be updated';

DROP TRIGGER IF EXISTS trg_client_over_refund_recovery_events_before_delete;
CREATE TRIGGER trg_client_over_refund_recovery_events_before_delete
BEFORE DELETE ON client_over_refund_recovery_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client_over_refund_recovery_events records cannot be deleted';
-- END SOURCE: db/schema_parts/167_client_finance_overage_dispositions.sql

-- BEGIN SOURCE: db/schema_parts/168_staff_payout_difference_recovery.sql
-- Additive Staff Payables payout-difference projection and recovery root.

ALTER TABLE staff_payable_projections
    MODIFY COLUMN status ENUM(
        'payable', 'partially_paid', 'completed', 'recovery_required', 'anomaly'
    ) NOT NULL;

ALTER TABLE staff_payable_projections
    DROP CHECK chk_staff_payable_projection_status;

ALTER TABLE staff_payable_projections
    ADD CONSTRAINT chk_staff_payable_projection_status
    CHECK (
        (status = 'payable' AND net_paid_ntd = 0 AND balance_ntd = obligation_amount_ntd)
        OR (status = 'partially_paid' AND net_paid_ntd > 0 AND balance_ntd > 0)
        OR (status = 'completed' AND net_paid_ntd = obligation_amount_ntd AND balance_ntd = 0)
        OR (status = 'recovery_required' AND net_paid_ntd = obligation_amount_ntd AND balance_ntd = 0)
        OR (status = 'anomaly' AND balance_ntd < 0)
    );

CREATE TABLE IF NOT EXISTS staff_overpayment_recoveries (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    recovery_identity VARCHAR(191) NOT NULL,
    staff_id INT NOT NULL,
    original_amount_ntd BIGINT NOT NULL,
    remaining_amount_ntd BIGINT NOT NULL,
    status ENUM('open', 'partially_recovered', 'recovered', 'adjusted')
        NOT NULL DEFAULT 'open',
    aggregate_version BIGINT UNSIGNED NOT NULL DEFAULT 0,
    source_bank_fact_identities JSON NOT NULL,
    source_payout_event_ids JSON NOT NULL,
    source_obligation_identities JSON NOT NULL,
    actor VARCHAR(100) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_staff_overpayment_recovery_identity (recovery_identity),
    INDEX idx_staff_overpayment_recovery_staff_status (staff_id, status, id),
    CONSTRAINT fk_staff_overpayment_recovery_staff
        FOREIGN KEY (staff_id) REFERENCES staff(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_staff_overpayment_recovery_amount
        CHECK (
            original_amount_ntd > 0
            AND remaining_amount_ntd >= 0
            AND remaining_amount_ntd <= original_amount_ntd
        ),
    CONSTRAINT chk_staff_overpayment_recovery_sources
        CHECK (
            JSON_TYPE(source_bank_fact_identities) = 'ARRAY'
            AND JSON_TYPE(source_payout_event_ids) = 'ARRAY'
            AND JSON_TYPE(source_obligation_identities) = 'ARRAY'
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- This table is the current projection.  Its immutable history is held below,
-- so the recovery workflow may advance remaining/status with an optimistic CAS.
DROP TRIGGER IF EXISTS trg_staff_overpayment_recoveries_before_update;

DROP TRIGGER IF EXISTS trg_staff_overpayment_recoveries_before_delete;
CREATE TRIGGER trg_staff_overpayment_recoveries_before_delete
BEFORE DELETE ON staff_overpayment_recoveries
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'staff_overpayment_recoveries root facts cannot be deleted';

CREATE TABLE IF NOT EXISTS staff_overpayment_recovery_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    recovery_identity VARCHAR(191) NOT NULL,
    event_type ENUM('cash_recovered', 'authorized_adjustment') NOT NULL,
    finance_import_row_id BIGINT NULL,
    before_remaining_ntd BIGINT NOT NULL,
    after_remaining_ntd BIGINT NOT NULL,
    resulting_status ENUM('partially_recovered', 'recovered', 'adjusted') NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    actor VARCHAR(100) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_staff_overpayment_recovery_event_key (idempotency_key),
    UNIQUE KEY uq_staff_overpayment_recovery_event_bank_row (finance_import_row_id),
    CONSTRAINT fk_staff_overpayment_recovery_event_root
        FOREIGN KEY (recovery_identity) REFERENCES staff_overpayment_recoveries(recovery_identity)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_staff_overpayment_recovery_event_bank_row
        FOREIGN KEY (finance_import_row_id) REFERENCES finance_import_rows(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_staff_overpayment_recovery_event_amount
        CHECK (before_remaining_ntd > 0 AND after_remaining_ntd >= 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS staff_overpayment_recovery_apply_receipts (
    idempotency_key VARCHAR(191) PRIMARY KEY,
    command_fingerprint CHAR(64) NOT NULL,
    preview_fingerprint CHAR(64) NOT NULL,
    recovery_identity VARCHAR(191) NOT NULL,
    result_snapshot JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_staff_overpayment_recovery_receipt_root
        FOREIGN KEY (recovery_identity) REFERENCES staff_overpayment_recoveries(recovery_identity)
        ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_staff_overpayment_recovery_events_before_update;
CREATE TRIGGER trg_staff_overpayment_recovery_events_before_update
BEFORE UPDATE ON staff_overpayment_recovery_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'staff_overpayment_recovery_events records cannot be updated';

DROP TRIGGER IF EXISTS trg_staff_overpayment_recovery_events_before_delete;
CREATE TRIGGER trg_staff_overpayment_recovery_events_before_delete
BEFORE DELETE ON staff_overpayment_recovery_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'staff_overpayment_recovery_events records cannot be deleted';
-- END SOURCE: db/schema_parts/168_staff_payout_difference_recovery.sql

-- BEGIN SOURCE: db/schema_parts/169_government_subsidy_overpayment_disposition.sql
-- Immutable root and disposition lineage for government subsidy overpayments.

ALTER TABLE government_subsidy_outbox
    MODIFY COLUMN intent_type ENUM(
        'government_subsidy_receipt_applied',
        'government_subsidy_receipt_allocated',
        'government_subsidy_reversal_applied',
        'government_subsidy_anomaly_root_changed',
        'government_subsidy_overpayment_established',
        'government_subsidy_overpayment_offset',
        'government_overpayment_return_payable',
        'government_overpayment_return_payout'
    ) NOT NULL;

CREATE TABLE IF NOT EXISTS government_payers (
    payer_identity VARCHAR(191) PRIMARY KEY,
    payer_name VARCHAR(191) NOT NULL,
    incoming_memo_match VARCHAR(191) NOT NULL,
    is_active TINYINT(1) NOT NULL DEFAULT 1,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT chk_government_payer_identity
        CHECK (payer_identity = 'hccg'),
    CONSTRAINT chk_government_payer_name
        CHECK (payer_name = '新竹市政府'),
    CONSTRAINT chk_government_payer_memo
        CHECK (incoming_memo_match = '新竹市政府')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO government_payers (payer_identity,payer_name,incoming_memo_match,is_active)
VALUES ('hccg','新竹市政府','新竹市政府',1)
ON DUPLICATE KEY UPDATE payer_name=VALUES(payer_name),
    incoming_memo_match=VALUES(incoming_memo_match),is_active=VALUES(is_active);

CREATE TABLE IF NOT EXISTS government_payer_receiving_accounts (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    payer_identity VARCHAR(191) NOT NULL,
    bank_code VARCHAR(32) NOT NULL,
    account_number VARCHAR(191) NOT NULL,
    account_name VARCHAR(191) NOT NULL,
    effective_from DATE NOT NULL,
    effective_until DATE NULL,
    reason VARCHAR(500) NOT NULL,
    evidence_reference VARCHAR(500) NOT NULL,
    created_by VARCHAR(100) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_government_payer_account_version (payer_identity, effective_from),
    INDEX idx_government_payer_active_account (payer_identity, effective_from, effective_until),
    CONSTRAINT fk_government_payer_account_payer
        FOREIGN KEY (payer_identity) REFERENCES government_payers(payer_identity)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_government_payer_account_period
        CHECK (effective_until IS NULL OR effective_until >= effective_from)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS government_subsidy_overpayments (
    overpayment_identity VARCHAR(191) PRIMARY KEY,
    source_finance_import_row_id BIGINT NOT NULL,
    source_transaction_id BIGINT NOT NULL,
    payer_identity VARCHAR(191) NOT NULL,
    original_amount_ntd BIGINT NOT NULL,
    remaining_amount_ntd BIGINT NOT NULL,
    status ENUM(
        'pending_review', 'offset_reserved', 'offset_applied',
        'return_payable', 'partially_returned', 'returned'
    ) NOT NULL DEFAULT 'pending_review',
    projection_version BIGINT UNSIGNED NOT NULL,
    actor VARCHAR(100) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    evidence_reference VARCHAR(500) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_government_subsidy_overpayment_bank_row (source_finance_import_row_id),
    UNIQUE KEY uq_government_subsidy_overpayment_transaction (source_transaction_id),
    INDEX idx_government_subsidy_overpayment_status (status, created_at),
    CONSTRAINT fk_government_subsidy_overpayment_bank_row
        FOREIGN KEY (source_finance_import_row_id) REFERENCES finance_import_rows(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_government_subsidy_overpayment_transaction
        FOREIGN KEY (source_transaction_id) REFERENCES government_subsidy_transactions(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_government_subsidy_overpayment_amount
        CHECK (
            original_amount_ntd > 0
            AND remaining_amount_ntd >= 0
            AND remaining_amount_ntd <= original_amount_ntd
            AND (
                remaining_amount_ntd > 0
                OR status IN ('offset_applied', 'returned')
            )
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS government_subsidy_overpayment_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    overpayment_identity VARCHAR(191) NOT NULL,
    event_type ENUM(
        'established',
        'offset_applied',
        'return_payable_created',
        'return_paid',
        'return_reconciled'
    ) NOT NULL,
    before_remaining_ntd BIGINT NOT NULL,
    after_remaining_ntd BIGINT NOT NULL,
    resulting_status VARCHAR(32) NOT NULL,
    expected_version BIGINT UNSIGNED NOT NULL,
    resulting_version BIGINT UNSIGNED NOT NULL,
    preview_fingerprint CHAR(64) NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    actor VARCHAR(100) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    evidence_reference VARCHAR(500) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_government_subsidy_overpayment_event_idempotency (idempotency_key),
    INDEX idx_government_subsidy_overpayment_event_root (overpayment_identity, id),
    CONSTRAINT fk_government_subsidy_overpayment_event_root
        FOREIGN KEY (overpayment_identity) REFERENCES government_subsidy_overpayments(overpayment_identity)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_government_subsidy_overpayment_event_amount
        CHECK (before_remaining_ntd > 0 AND after_remaining_ntd >= 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS government_subsidy_overpayment_offsets (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    overpayment_event_id BIGINT NOT NULL,
    overpayment_identity VARCHAR(191) NOT NULL,
    claim_batch_id BIGINT NOT NULL,
    claim_item_id BIGINT NOT NULL,
    allocated_amount_ntd BIGINT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_government_subsidy_overpayment_offset_target (overpayment_identity, claim_item_id),
    INDEX idx_government_subsidy_overpayment_offset_item (claim_batch_id, claim_item_id),
    CONSTRAINT fk_government_subsidy_overpayment_offset_event
        FOREIGN KEY (overpayment_event_id) REFERENCES government_subsidy_overpayment_events(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_government_subsidy_overpayment_offset_root
        FOREIGN KEY (overpayment_identity) REFERENCES government_subsidy_overpayments(overpayment_identity)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_government_subsidy_overpayment_offset_item
        FOREIGN KEY (claim_item_id, claim_batch_id) REFERENCES subsidy_claim_batch_items(id, batch_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_government_subsidy_overpayment_offset_amount CHECK (allocated_amount_ntd > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS government_subsidy_overpayment_target_projection_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    overpayment_event_id BIGINT NOT NULL,
    batch_id BIGINT NOT NULL,
    before_net_allocated_ntd BIGINT UNSIGNED NOT NULL,
    after_net_allocated_ntd BIGINT UNSIGNED NOT NULL,
    outstanding_ntd BIGINT UNSIGNED NOT NULL,
    expected_batch_version BIGINT UNSIGNED NOT NULL,
    resulting_batch_version BIGINT UNSIGNED NOT NULL,
    preview_fingerprint CHAR(64) NOT NULL,
    actor VARCHAR(100) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_government_overpayment_target_projection (
        overpayment_event_id, batch_id
    ),
    CONSTRAINT fk_government_overpayment_target_projection_event
        FOREIGN KEY (overpayment_event_id)
        REFERENCES government_subsidy_overpayment_events(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_government_overpayment_target_projection_batch
        FOREIGN KEY (batch_id) REFERENCES government_subsidy_batch_accounts(batch_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_government_overpayment_target_projection_version
        CHECK (resulting_batch_version = expected_batch_version + 1),
    CONSTRAINT chk_government_overpayment_target_projection_amount
        CHECK (after_net_allocated_ntd >= before_net_allocated_ntd)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS government_overpayment_return_payables (
    payable_identity VARCHAR(191) PRIMARY KEY,
    overpayment_identity VARCHAR(191) NOT NULL,
    amount_due_ntd BIGINT NOT NULL,
    remaining_amount_ntd BIGINT NOT NULL,
    status ENUM('payable', 'partially_paid', 'paid') NOT NULL DEFAULT 'payable',
    agency_identity VARCHAR(191) NOT NULL,
    agency_name VARCHAR(191) NOT NULL,
    bank_code VARCHAR(32) NOT NULL,
    account_display VARCHAR(191) NOT NULL,
    account_fingerprint CHAR(64) NOT NULL,
    effective_date DATE NOT NULL,
    due_date DATE NOT NULL,
    evidence_reference VARCHAR(500) NOT NULL,
    projection_version BIGINT UNSIGNED NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_government_overpayment_return_root (overpayment_identity),
    INDEX idx_government_overpayment_return_due (status, due_date),
    CONSTRAINT fk_government_overpayment_return_root
        FOREIGN KEY (overpayment_identity) REFERENCES government_subsidy_overpayments(overpayment_identity)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_government_overpayment_return_amount
        CHECK (
            amount_due_ntd > 0
            AND remaining_amount_ntd >= 0
            AND remaining_amount_ntd <= amount_due_ntd
            AND (remaining_amount_ntd > 0 OR status = 'paid')
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS government_overpayment_return_payouts (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    overpayment_event_id BIGINT NOT NULL,
    payable_identity VARCHAR(191) NOT NULL,
    finance_import_row_id BIGINT NOT NULL,
    amount_ntd BIGINT NOT NULL,
    preview_fingerprint CHAR(64) NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    actor VARCHAR(100) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    evidence_reference VARCHAR(500) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_government_overpayment_return_payout_bank (finance_import_row_id),
    UNIQUE KEY uq_government_overpayment_return_payout_key (idempotency_key),
    CONSTRAINT fk_government_overpayment_return_payout_event
        FOREIGN KEY (overpayment_event_id) REFERENCES government_subsidy_overpayment_events(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_government_overpayment_return_payout_payable
        FOREIGN KEY (payable_identity) REFERENCES government_overpayment_return_payables(payable_identity)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_government_overpayment_return_payout_bank
        FOREIGN KEY (finance_import_row_id) REFERENCES finance_import_rows(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_government_overpayment_return_payout_amount CHECK (amount_ntd > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_government_subsidy_overpayment_events_before_update;
CREATE TRIGGER trg_government_subsidy_overpayment_events_before_update
BEFORE UPDATE ON government_subsidy_overpayment_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'government_subsidy_overpayment_events records cannot be updated';

DROP TRIGGER IF EXISTS trg_government_subsidy_overpayment_events_before_delete;
CREATE TRIGGER trg_government_subsidy_overpayment_events_before_delete
BEFORE DELETE ON government_subsidy_overpayment_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'government_subsidy_overpayment_events records cannot be deleted';
-- END SOURCE: db/schema_parts/169_government_subsidy_overpayment_disposition.sql

-- BEGIN SOURCE: db/schema_parts/170_client_over_refund_recovery_collection.sql
-- Canonical incoming-bank settlement for a client refund overpayment recovery.

ALTER TABLE client_over_refund_recoveries
    MODIFY COLUMN status ENUM(
        'open',
        'partially_recovered',
        'recovered',
        'adjusted',
        'settled',
        'cancelled'
    ) NOT NULL;

CREATE TABLE IF NOT EXISTS client_over_refund_recovery_apply_receipts (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    idempotency_key VARCHAR(191) NOT NULL,
    command_fingerprint CHAR(64) NOT NULL,
    preview_fingerprint CHAR(64) NOT NULL,
    recovery_identity VARCHAR(191) NOT NULL,
    finance_import_row_id BIGINT NOT NULL,
    receipt_ledger_entry_id BIGINT NOT NULL,
    resulting_version BIGINT UNSIGNED NOT NULL,
    remaining_after_ntd BIGINT NOT NULL,
    resulting_status ENUM('partially_recovered', 'recovered') NOT NULL,
    result_snapshot JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_client_over_refund_recovery_receipt_key (idempotency_key),
    UNIQUE KEY uq_client_over_refund_recovery_receipt_bank_row (finance_import_row_id),
    CONSTRAINT fk_client_over_refund_recovery_receipt_recovery
        FOREIGN KEY (recovery_identity)
        REFERENCES client_over_refund_recoveries(recovery_identity)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_client_over_refund_recovery_receipt_bank_row
        FOREIGN KEY (finance_import_row_id) REFERENCES finance_import_rows(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_client_over_refund_recovery_receipt_ledger
        FOREIGN KEY (receipt_ledger_entry_id) REFERENCES client_ledger_entries(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_client_over_refund_recovery_receipt_fingerprint
        CHECK (
            command_fingerprint REGEXP '^[0-9a-f]{64}$'
            AND preview_fingerprint REGEXP '^[0-9a-f]{64}$'
        ),
    CONSTRAINT chk_client_over_refund_recovery_receipt_remaining
        CHECK (remaining_after_ntd >= 0),
    CONSTRAINT chk_client_over_refund_recovery_receipt_snapshot
        CHECK (JSON_TYPE(result_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_client_over_refund_recovery_receipts_before_update;
CREATE TRIGGER trg_client_over_refund_recovery_receipts_before_update
BEFORE UPDATE ON client_over_refund_recovery_apply_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client over-refund recovery receipts cannot be updated';

DROP TRIGGER IF EXISTS trg_client_over_refund_recovery_receipts_before_delete;
CREATE TRIGGER trg_client_over_refund_recovery_receipts_before_delete
BEFORE DELETE ON client_over_refund_recovery_apply_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client over-refund recovery receipts cannot be deleted';
-- END SOURCE: db/schema_parts/170_client_over_refund_recovery_collection.sql

-- BEGIN SOURCE: db/schema_parts/171_client_over_refund_recovery_adjustment.sql
-- Immutable authorized-adjustment evidence for client over-refund recovery.

ALTER TABLE client_over_refund_recoveries
    DROP CHECK chk_client_over_refund_amount;

ALTER TABLE client_over_refund_recoveries
    ADD CONSTRAINT chk_client_over_refund_amount
    CHECK (
        amount_due_ntd >= 0
        AND (
            (amount_due_ntd > 0 AND status IN ('open', 'partially_recovered'))
            OR (amount_due_ntd = 0 AND status IN ('recovered', 'adjusted'))
        )
    );

ALTER TABLE client_over_refund_recovery_events
    MODIFY COLUMN event_type ENUM(
        'established',
        'collected',
        'authorized_adjustment',
        'cancelled'
    ) NOT NULL;

ALTER TABLE client_over_refund_recovery_events
    DROP CHECK chk_client_over_refund_event_amount;

ALTER TABLE client_over_refund_recovery_events
    ADD CONSTRAINT chk_client_over_refund_event_amount
    CHECK (
        after_amount_ntd >= 0
        AND (
            (event_type = 'established' AND before_amount_ntd = 0 AND after_amount_ntd > 0)
            OR (event_type = 'collected' AND before_amount_ntd > after_amount_ntd)
            OR (event_type = 'authorized_adjustment' AND before_amount_ntd > after_amount_ntd)
            OR (event_type = 'cancelled' AND before_amount_ntd > after_amount_ntd)
        )
    );

CREATE TABLE IF NOT EXISTS client_over_refund_recovery_adjustment_receipts (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    idempotency_key VARCHAR(191) NOT NULL,
    command_fingerprint CHAR(64) NOT NULL,
    preview_fingerprint CHAR(64) NOT NULL,
    recovery_identity VARCHAR(191) NOT NULL,
    resulting_version BIGINT UNSIGNED NOT NULL,
    remaining_after_ntd BIGINT NOT NULL,
    resulting_status ENUM('open', 'adjusted') NOT NULL,
    result_snapshot JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_client_over_refund_adjustment_receipt_key (idempotency_key),
    CONSTRAINT fk_client_over_refund_adjustment_receipt_recovery
        FOREIGN KEY (recovery_identity)
        REFERENCES client_over_refund_recoveries(recovery_identity)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_client_over_refund_adjustment_receipt_fingerprint
        CHECK (
            command_fingerprint REGEXP '^[0-9a-f]{64}$'
            AND preview_fingerprint REGEXP '^[0-9a-f]{64}$'
        ),
    CONSTRAINT chk_client_over_refund_adjustment_receipt_remaining
        CHECK (remaining_after_ntd >= 0),
    CONSTRAINT chk_client_over_refund_adjustment_receipt_snapshot
        CHECK (JSON_TYPE(result_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_client_over_refund_adjustment_receipts_before_update;
CREATE TRIGGER trg_client_over_refund_adjustment_receipts_before_update
BEFORE UPDATE ON client_over_refund_recovery_adjustment_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client over-refund adjustment receipts cannot be updated';

DROP TRIGGER IF EXISTS trg_client_over_refund_adjustment_receipts_before_delete;
CREATE TRIGGER trg_client_over_refund_adjustment_receipts_before_delete
BEFORE DELETE ON client_over_refund_recovery_adjustment_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client over-refund adjustment receipts cannot be deleted';
-- END SOURCE: db/schema_parts/171_client_over_refund_recovery_adjustment.sql

-- BEGIN SOURCE: db/schema_parts/172_client_over_refund_recovery_matching.sql
-- Immutable human-confirmed matching; finance_import_rows remain canonical bank facts.

ALTER TABLE client_finance_outbox
    MODIFY COLUMN intent_type ENUM(
        'orders_deposit_reconciled',
        'orders_deposit_reversed',
        'anomaly_review_required',
        'projection_refresh',
        'client_over_refund_recovery_matched',
        'client_over_refund_recovery_collected'
    ) NOT NULL;

CREATE TABLE IF NOT EXISTS client_over_refund_recovery_matchings (
    matching_identity VARCHAR(191) PRIMARY KEY,
    case_no VARCHAR(50) NOT NULL,
    recovery_identity VARCHAR(191) NOT NULL,
    finance_import_row_id BIGINT NOT NULL,
    recovery_version BIGINT UNSIGNED NOT NULL,
    account_version BIGINT UNSIGNED NOT NULL,
    matching_version BIGINT UNSIGNED NOT NULL,
    actor VARCHAR(100) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_client_recovery_matching_bank_row (finance_import_row_id),
    UNIQUE KEY uq_client_recovery_matching_idempotency (idempotency_key),
    INDEX idx_client_recovery_matching_recovery (recovery_identity, matching_version),
    CONSTRAINT fk_client_recovery_matching_order FOREIGN KEY (case_no)
        REFERENCES orders(case_no) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_client_recovery_matching_recovery FOREIGN KEY (recovery_identity)
        REFERENCES client_over_refund_recoveries(recovery_identity)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_client_recovery_matching_bank_row FOREIGN KEY (finance_import_row_id)
        REFERENCES finance_import_rows(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_client_recovery_matching_version CHECK (matching_version = 1)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS client_over_refund_recovery_matching_receipts (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    idempotency_key VARCHAR(191) NOT NULL,
    command_fingerprint CHAR(64) NOT NULL,
    preview_fingerprint CHAR(64) NOT NULL,
    matching_identity VARCHAR(191) NOT NULL,
    result_snapshot JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_client_recovery_matching_receipt_key (idempotency_key),
    CONSTRAINT fk_client_recovery_matching_receipt FOREIGN KEY (matching_identity)
        REFERENCES client_over_refund_recovery_matchings(matching_identity)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_client_recovery_matching_receipt_fingerprint CHECK (
        command_fingerprint REGEXP '^[0-9a-f]{64}$'
        AND preview_fingerprint REGEXP '^[0-9a-f]{64}$'
    ),
    CONSTRAINT chk_client_recovery_matching_receipt_snapshot CHECK (
        JSON_TYPE(result_snapshot) = 'OBJECT'
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_client_recovery_matchings_before_update;
CREATE TRIGGER trg_client_recovery_matchings_before_update
BEFORE UPDATE ON client_over_refund_recovery_matchings
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client over-refund recovery matchings cannot be updated';

DROP TRIGGER IF EXISTS trg_client_recovery_matchings_before_delete;
CREATE TRIGGER trg_client_recovery_matchings_before_delete
BEFORE DELETE ON client_over_refund_recovery_matchings
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client over-refund recovery matchings cannot be deleted';

DROP TRIGGER IF EXISTS trg_client_recovery_matching_receipts_before_update;
CREATE TRIGGER trg_client_recovery_matching_receipts_before_update
BEFORE UPDATE ON client_over_refund_recovery_matching_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client over-refund recovery matching receipts cannot be updated';

DROP TRIGGER IF EXISTS trg_client_recovery_matching_receipts_before_delete;
CREATE TRIGGER trg_client_recovery_matching_receipts_before_delete
BEFORE DELETE ON client_over_refund_recovery_matching_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client over-refund recovery matching receipts cannot be deleted';
-- END SOURCE: db/schema_parts/172_client_over_refund_recovery_matching.sql

-- BEGIN SOURCE: db/schema_parts/173_staff_overpayment_recovery_matching.sql
-- Immutable staff return matching; canonical bank facts retain no recovery target.

ALTER TABLE staff_payables_outbox
    MODIFY COLUMN intent_type ENUM(
        'payable_projection_refresh',
        'payout_anomaly_required',
        'staff_overpayment_recovery_updated',
        'staff_overpayment_recovery_matched',
        'staff_overpayment_recovery_collected'
    ) NOT NULL;

CREATE TABLE IF NOT EXISTS staff_overpayment_recovery_matchings (
    matching_identity VARCHAR(191) PRIMARY KEY,
    recovery_identity VARCHAR(191) NOT NULL,
    staff_id INT NOT NULL,
    finance_import_row_id BIGINT NOT NULL,
    recovery_version BIGINT UNSIGNED NOT NULL,
    staff_payables_version BIGINT UNSIGNED NOT NULL,
    matching_version BIGINT UNSIGNED NOT NULL,
    actor VARCHAR(100) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_staff_recovery_matching_bank_row (finance_import_row_id),
    UNIQUE KEY uq_staff_recovery_matching_idempotency (idempotency_key),
    CONSTRAINT fk_staff_recovery_matching_root FOREIGN KEY (recovery_identity)
        REFERENCES staff_overpayment_recoveries(recovery_identity)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_staff_recovery_matching_staff FOREIGN KEY (staff_id)
        REFERENCES staff(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_staff_recovery_matching_row FOREIGN KEY (finance_import_row_id)
        REFERENCES finance_import_rows(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_staff_recovery_matching_version CHECK (matching_version = 1)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS staff_overpayment_recovery_matching_receipts (
    idempotency_key VARCHAR(191) PRIMARY KEY,
    command_fingerprint CHAR(64) NOT NULL,
    preview_fingerprint CHAR(64) NOT NULL,
    matching_identity VARCHAR(191) NOT NULL,
    result_snapshot JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_staff_recovery_matching_receipt FOREIGN KEY (matching_identity)
        REFERENCES staff_overpayment_recovery_matchings(matching_identity)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_staff_recovery_matching_receipt_fingerprint CHECK (
        command_fingerprint REGEXP '^[0-9a-f]{64}$'
        AND preview_fingerprint REGEXP '^[0-9a-f]{64}$'
    ),
    CONSTRAINT chk_staff_recovery_matching_receipt_snapshot CHECK (JSON_TYPE(result_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_staff_recovery_matchings_before_update;
CREATE TRIGGER trg_staff_recovery_matchings_before_update
BEFORE UPDATE ON staff_overpayment_recovery_matchings
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'staff overpayment recovery matchings cannot be updated';

DROP TRIGGER IF EXISTS trg_staff_recovery_matchings_before_delete;
CREATE TRIGGER trg_staff_recovery_matchings_before_delete
BEFORE DELETE ON staff_overpayment_recovery_matchings
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'staff overpayment recovery matchings cannot be deleted';
-- END SOURCE: db/schema_parts/173_staff_overpayment_recovery_matching.sql

-- BEGIN SOURCE: db/schema_parts/174_staff_payout_difference_source.sql
-- Immutable multi-bank source for a Staff Payables payout-difference action.

CREATE TABLE IF NOT EXISTS staff_payout_difference_sources (
    payout_difference_identity VARCHAR(191) PRIMARY KEY,
    staff_id INT NOT NULL,
    difference_mode ENUM('underpayment','overpayment') NOT NULL,
    bank_total_ntd BIGINT NOT NULL,
    obligation_total_ntd BIGINT NOT NULL,
    recovery_identity VARCHAR(191) NULL,
    resulting_staff_payables_version BIGINT UNSIGNED NOT NULL,
    source_bank_facts_version BIGINT UNSIGNED NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    actor VARCHAR(100) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_staff_payout_difference_source_key (idempotency_key),
    CONSTRAINT fk_staff_payout_difference_source_staff FOREIGN KEY (staff_id)
        REFERENCES staff(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_staff_payout_difference_source_recovery FOREIGN KEY (recovery_identity)
        REFERENCES staff_overpayment_recoveries(recovery_identity)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_staff_payout_difference_source_amounts CHECK (
        bank_total_ntd > 0 AND obligation_total_ntd > 0
        AND ((difference_mode = 'underpayment' AND bank_total_ntd < obligation_total_ntd)
          OR (difference_mode = 'overpayment' AND bank_total_ntd > obligation_total_ntd))
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS staff_payout_difference_source_bank_rows (
    payout_difference_identity VARCHAR(191) NOT NULL,
    finance_import_row_id BIGINT NOT NULL,
    ordinal INT UNSIGNED NOT NULL,
    PRIMARY KEY (payout_difference_identity, finance_import_row_id),
    UNIQUE KEY uq_staff_payout_difference_source_bank_ordinal (payout_difference_identity, ordinal),
    CONSTRAINT fk_staff_payout_difference_source_bank_root FOREIGN KEY (payout_difference_identity)
        REFERENCES staff_payout_difference_sources(payout_difference_identity)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_staff_payout_difference_source_bank_row FOREIGN KEY (finance_import_row_id)
        REFERENCES finance_import_rows(id) ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS staff_payout_difference_source_obligations (
    payout_difference_identity VARCHAR(191) NOT NULL,
    obligation_identity VARCHAR(191) NOT NULL,
    ordinal INT UNSIGNED NOT NULL,
    PRIMARY KEY (payout_difference_identity, obligation_identity),
    UNIQUE KEY uq_staff_payout_difference_source_obligation_ordinal (payout_difference_identity, ordinal),
    CONSTRAINT fk_staff_payout_difference_source_obligation_root FOREIGN KEY (payout_difference_identity)
        REFERENCES staff_payout_difference_sources(payout_difference_identity)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_staff_payout_difference_source_obligation FOREIGN KEY (obligation_identity)
        REFERENCES staff_obligations(obligation_identity)
        ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_staff_payout_difference_sources_before_update;
CREATE TRIGGER trg_staff_payout_difference_sources_before_update
BEFORE UPDATE ON staff_payout_difference_sources
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'staff payout difference sources cannot be updated';

DROP TRIGGER IF EXISTS trg_staff_payout_difference_sources_before_delete;
CREATE TRIGGER trg_staff_payout_difference_sources_before_delete
BEFORE DELETE ON staff_payout_difference_sources
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'staff payout difference sources cannot be deleted';

DROP TRIGGER IF EXISTS trg_staff_payout_difference_source_rows_before_update;
CREATE TRIGGER trg_staff_payout_difference_source_rows_before_update
BEFORE UPDATE ON staff_payout_difference_source_bank_rows
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'staff payout difference source bank rows cannot be updated';

DROP TRIGGER IF EXISTS trg_staff_payout_difference_source_rows_before_delete;
CREATE TRIGGER trg_staff_payout_difference_source_rows_before_delete
BEFORE DELETE ON staff_payout_difference_source_bank_rows
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'staff payout difference source bank rows cannot be deleted';

DROP TRIGGER IF EXISTS trg_staff_payout_difference_source_obligations_before_update;
CREATE TRIGGER trg_staff_payout_difference_source_obligations_before_update
BEFORE UPDATE ON staff_payout_difference_source_obligations
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'staff payout difference source obligations cannot be updated';

DROP TRIGGER IF EXISTS trg_staff_payout_difference_source_obligations_before_delete;
CREATE TRIGGER trg_staff_payout_difference_source_obligations_before_delete
BEFORE DELETE ON staff_payout_difference_source_obligations
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'staff payout difference source obligations cannot be deleted';
-- END SOURCE: db/schema_parts/174_staff_payout_difference_source.sql

-- BEGIN SOURCE: db/schema_parts/175_government_overpayment_return_payout_immutability.sql
-- Government return-payout receipts are immutable accounting evidence.

DROP TRIGGER IF EXISTS trg_government_overpayment_return_payouts_before_update;
CREATE TRIGGER trg_government_overpayment_return_payouts_before_update
BEFORE UPDATE ON government_overpayment_return_payouts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'government_overpayment_return_payouts records cannot be updated';

DROP TRIGGER IF EXISTS trg_government_overpayment_return_payouts_before_delete;
CREATE TRIGGER trg_government_overpayment_return_payouts_before_delete
BEFORE DELETE ON government_overpayment_return_payouts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'government_overpayment_return_payouts records cannot be deleted';
-- END SOURCE: db/schema_parts/175_government_overpayment_return_payout_immutability.sql

-- BEGIN SOURCE: db/schema_parts/176_client_refund_recipient_snapshot.sql
-- Immutable recipient account selected when a client refund payable is created.
CREATE TABLE IF NOT EXISTS client_refund_recipient_snapshots (
    refund_obligation_identity VARCHAR(191) PRIMARY KEY,
    case_no VARCHAR(50) NOT NULL,
    bank_code VARCHAR(50) NOT NULL,
    bank_account VARCHAR(191) NOT NULL,
    source_kind VARCHAR(80) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_client_refund_snapshot_obligation
        FOREIGN KEY (refund_obligation_identity) REFERENCES client_obligations(obligation_identity)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_client_refund_snapshot_order
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_client_refund_snapshot_account
        CHECK (CHAR_LENGTH(TRIM(bank_code)) > 0 AND CHAR_LENGTH(TRIM(bank_account)) > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_client_refund_recipient_snapshots_before_update;
CREATE TRIGGER trg_client_refund_recipient_snapshots_before_update
BEFORE UPDATE ON client_refund_recipient_snapshots
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client refund recipient snapshots cannot be updated';

DROP TRIGGER IF EXISTS trg_client_refund_recipient_snapshots_before_delete;
CREATE TRIGGER trg_client_refund_recipient_snapshots_before_delete
BEFORE DELETE ON client_refund_recipient_snapshots
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client refund recipient snapshots cannot be deleted';
-- END SOURCE: db/schema_parts/176_client_refund_recipient_snapshot.sql

-- BEGIN SOURCE: db/schema_parts/177_client_refund_underpayment_source.sql
ALTER TABLE client_finance_outbox
    MODIFY COLUMN intent_type ENUM(
        'orders_deposit_reconciled',
        'orders_deposit_reversed',
        'anomaly_review_required',
        'projection_refresh',
        'client_over_refund_recovery_matched',
        'client_over_refund_recovery_collected',
        'client_refund_underpayment_required'
    ) NOT NULL;

CREATE TABLE IF NOT EXISTS client_refund_underpayment_sources (
    underpayment_identity VARCHAR(191) PRIMARY KEY,
    case_no VARCHAR(50) NOT NULL,
    bank_total_ntd BIGINT NOT NULL,
    remaining_after_ntd BIGINT NOT NULL,
    resulting_account_version BIGINT UNSIGNED NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    actor VARCHAR(100) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_client_refund_underpayment_idempotency (idempotency_key),
    CONSTRAINT fk_client_refund_underpayment_order FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_client_refund_underpayment_amount CHECK (bank_total_ntd > 0 AND remaining_after_ntd > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS client_refund_underpayment_source_bank_rows (
    underpayment_identity VARCHAR(191) NOT NULL,
    finance_import_row_id BIGINT NOT NULL,
    ordinal INT NOT NULL,
    PRIMARY KEY (underpayment_identity, finance_import_row_id),
    UNIQUE KEY uq_client_refund_underpayment_consumed_row (finance_import_row_id),
    CONSTRAINT fk_client_refund_underpayment_row_source FOREIGN KEY (underpayment_identity) REFERENCES client_refund_underpayment_sources(underpayment_identity)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_client_refund_underpayment_row FOREIGN KEY (finance_import_row_id) REFERENCES finance_import_rows(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_client_refund_underpayment_row_ordinal CHECK (ordinal > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS client_refund_underpayment_source_obligations (
    underpayment_identity VARCHAR(191) NOT NULL,
    refund_obligation_identity VARCHAR(191) NOT NULL,
    remaining_after_ntd BIGINT NOT NULL,
    PRIMARY KEY (underpayment_identity, refund_obligation_identity),
    CONSTRAINT fk_client_refund_underpayment_obligation_source FOREIGN KEY (underpayment_identity) REFERENCES client_refund_underpayment_sources(underpayment_identity)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_client_refund_underpayment_obligation FOREIGN KEY (refund_obligation_identity) REFERENCES client_obligations(obligation_identity)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_client_refund_underpayment_obligation_remaining CHECK (remaining_after_ntd > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_client_refund_underpayment_sources_before_update;
CREATE TRIGGER trg_client_refund_underpayment_sources_before_update
BEFORE UPDATE ON client_refund_underpayment_sources
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client refund underpayment sources cannot be updated';

DROP TRIGGER IF EXISTS trg_client_refund_underpayment_sources_before_delete;
CREATE TRIGGER trg_client_refund_underpayment_sources_before_delete
BEFORE DELETE ON client_refund_underpayment_sources
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client refund underpayment sources cannot be deleted';

DROP TRIGGER IF EXISTS trg_client_refund_underpayment_source_rows_before_update;
CREATE TRIGGER trg_client_refund_underpayment_source_rows_before_update
BEFORE UPDATE ON client_refund_underpayment_source_bank_rows
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client refund underpayment source bank rows cannot be updated';

DROP TRIGGER IF EXISTS trg_client_refund_underpayment_source_rows_before_delete;
CREATE TRIGGER trg_client_refund_underpayment_source_rows_before_delete
BEFORE DELETE ON client_refund_underpayment_source_bank_rows
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client refund underpayment source bank rows cannot be deleted';

DROP TRIGGER IF EXISTS trg_client_refund_underpayment_source_obligations_before_update;
CREATE TRIGGER trg_client_refund_underpayment_source_obligations_before_update
BEFORE UPDATE ON client_refund_underpayment_source_obligations
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client refund underpayment source obligations cannot be updated';

DROP TRIGGER IF EXISTS trg_client_refund_underpayment_source_obligations_before_delete;
CREATE TRIGGER trg_client_refund_underpayment_source_obligations_before_delete
BEFORE DELETE ON client_refund_underpayment_source_obligations
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client refund underpayment source obligations cannot be deleted';
-- END SOURCE: db/schema_parts/177_client_refund_underpayment_source.sql

-- BEGIN SOURCE: db/schema_parts/178_government_subsidy_overpayment_apply_receipts.sql
-- Durable idempotency receipts for every Government Subsidy overpayment disposition Apply.

CREATE TABLE IF NOT EXISTS government_subsidy_overpayment_apply_receipts (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    idempotency_key VARCHAR(191) NOT NULL,
    command_fingerprint CHAR(64) NOT NULL,
    preview_fingerprint CHAR(64) NOT NULL,
    command_kind ENUM('offset', 'return', 'return_reconciliation') NOT NULL,
    overpayment_identity VARCHAR(191) NOT NULL,
    result_snapshot JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_government_overpayment_apply_receipt_key (idempotency_key),
    CONSTRAINT fk_government_overpayment_apply_receipt_root
        FOREIGN KEY (overpayment_identity)
        REFERENCES government_subsidy_overpayments(overpayment_identity)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_government_overpayment_apply_receipt_fingerprint
        CHECK (
            command_fingerprint REGEXP '^[0-9a-f]{64}$'
            AND preview_fingerprint REGEXP '^[0-9a-f]{64}$'
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_government_overpayment_apply_receipts_before_update;
CREATE TRIGGER trg_government_overpayment_apply_receipts_before_update
BEFORE UPDATE ON government_subsidy_overpayment_apply_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'government_subsidy_overpayment_apply_receipts records cannot be updated';

DROP TRIGGER IF EXISTS trg_government_overpayment_apply_receipts_before_delete;
CREATE TRIGGER trg_government_overpayment_apply_receipts_before_delete
BEFORE DELETE ON government_subsidy_overpayment_apply_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'government_subsidy_overpayment_apply_receipts records cannot be deleted';
-- END SOURCE: db/schema_parts/178_government_subsidy_overpayment_apply_receipts.sql

-- BEGIN SOURCE: db/schema_parts/180_leave_substitution_holiday_only_batch_contract.sql
-- Holiday Query can produce an approved Scheduling change without a manual
-- leave item. Preview fingerprint and fresh-fact checks remain the Apply gate.
ALTER TABLE scheduling_leave_substitution_batches
    DROP CHECK chk_scheduling_leave_batch_identity;

ALTER TABLE scheduling_leave_substitution_batches
    ADD CONSTRAINT chk_scheduling_leave_batch_identity
    CHECK (
        item_count >= 0
        AND CHAR_LENGTH(TRIM(batch_key)) > 0
        AND CHAR_LENGTH(TRIM(actor)) > 0
        AND CHAR_LENGTH(TRIM(reason)) > 0
        AND CHAR_LENGTH(TRIM(correlation_id)) > 0
    );
-- END SOURCE: db/schema_parts/180_leave_substitution_holiday_only_batch_contract.sql

-- BEGIN SOURCE: db/schema_parts/181_matching_service_date_confirmation.sql
-- WP68 confirmed service dates, schedule snapshots and confirmation events.

CREATE TABLE IF NOT EXISTS confirmed_service_date_versions (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    case_no VARCHAR(50) NOT NULL,
    version INT UNSIGNED NOT NULL,
    order_version INT UNSIGNED NOT NULL,
    scheduling_version INT UNSIGNED NOT NULL,
    service_day_count INT UNSIGNED NOT NULL,
    service_date_fingerprint CHAR(64) NOT NULL,
    is_current TINYINT NULL,
    confirmed_by_actor_id VARCHAR(191) NOT NULL,
    reason VARCHAR(500) NULL,
    confirmed_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    invalidated_at_utc DATETIME(6) NULL,
    UNIQUE KEY uq_confirmed_service_date_version (case_no,version),
    UNIQUE KEY uq_confirmed_service_date_current (case_no,is_current),
    CONSTRAINT fk_confirmed_service_date_case FOREIGN KEY (case_no) REFERENCES orders(case_no),
    CONSTRAINT chk_confirmed_service_date_fingerprint CHECK (service_date_fingerprint REGEXP '^[0-9a-f]{64}$'),
    CONSTRAINT chk_confirmed_service_date_current CHECK (is_current IS NULL OR is_current=1)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS confirmed_service_date_days (
    confirmed_version_id BIGINT UNSIGNED NOT NULL,
    ordinal INT UNSIGNED NOT NULL,
    service_date DATE NOT NULL,
    PRIMARY KEY (confirmed_version_id,ordinal),
    UNIQUE KEY uq_confirmed_service_date_day (confirmed_version_id,service_date),
    CONSTRAINT fk_confirmed_service_date_day_version FOREIGN KEY (confirmed_version_id)
        REFERENCES confirmed_service_date_versions(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS confirmed_service_date_receipts (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    idempotency_key VARCHAR(191) NOT NULL,
    command_fingerprint CHAR(64) NOT NULL,
    confirmed_version_id BIGINT UNSIGNED NOT NULL,
    actor_id VARCHAR(191) NOT NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_confirmed_service_date_receipt_key (idempotency_key),
    CONSTRAINT fk_confirmed_service_date_receipt_version FOREIGN KEY (confirmed_version_id)
        REFERENCES confirmed_service_date_versions(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS matching_schedule_snapshots (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    case_no VARCHAR(50) NOT NULL,
    plan_id BIGINT NOT NULL,
    confirmed_version_id BIGINT UNSIGNED NOT NULL,
    snapshot_fingerprint CHAR(64) NOT NULL,
    status ENUM('draft','sent','invalidated') NOT NULL DEFAULT 'draft',
    current_marker TINYINT NULL,
    created_by_actor_id VARCHAR(191) NOT NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    invalidated_at_utc DATETIME(6) NULL,
    UNIQUE KEY uq_matching_schedule_current (case_no,current_marker),
    CONSTRAINT fk_matching_schedule_case FOREIGN KEY (case_no) REFERENCES orders(case_no),
    CONSTRAINT fk_matching_schedule_plan FOREIGN KEY (plan_id) REFERENCES caregiver_matching_plans(id),
    CONSTRAINT fk_matching_schedule_version FOREIGN KEY (confirmed_version_id)
        REFERENCES confirmed_service_date_versions(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS matching_schedule_recipient_snapshots (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    parent_snapshot_id BIGINT UNSIGNED NOT NULL,
    audience_type ENUM('customer','caregiver') NOT NULL,
    recipient_key VARCHAR(191) NOT NULL,
    segment_id BIGINT NULL,
    recipient_line_user_id VARCHAR(191) NULL,
    payload_snapshot JSON NOT NULL,
    payload_fingerprint CHAR(64) NOT NULL,
    delivery_status ENUM('pending','queued','sent','failed','blocked') NOT NULL DEFAULT 'pending',
    UNIQUE KEY uq_matching_schedule_recipient (parent_snapshot_id,recipient_key),
    CONSTRAINT fk_matching_schedule_recipient_parent FOREIGN KEY (parent_snapshot_id)
        REFERENCES matching_schedule_snapshots(id),
    CONSTRAINT fk_matching_schedule_recipient_segment FOREIGN KEY (segment_id)
        REFERENCES caregiver_matching_plan_segments(id),
    CONSTRAINT chk_matching_schedule_recipient_target CHECK (
        (audience_type='customer' AND segment_id IS NULL) OR
        (audience_type='caregiver' AND segment_id IS NOT NULL)
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS matching_schedule_confirmation_events (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    recipient_snapshot_id BIGINT UNSIGNED NOT NULL,
    confirmation_value ENUM('confirmed','rejected','manually_confirmed','manually_revoked') NOT NULL,
    source ENUM('line','admin') NOT NULL,
    actor_id VARCHAR(191) NOT NULL,
    reason VARCHAR(500) NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    occurred_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_matching_schedule_confirmation_key (idempotency_key),
    CONSTRAINT fk_matching_schedule_confirmation_recipient FOREIGN KEY (recipient_snapshot_id)
        REFERENCES matching_schedule_recipient_snapshots(id),
    CONSTRAINT chk_matching_schedule_rejection_reason CHECK (
        confirmation_value<>'rejected' OR CHAR_LENGTH(TRIM(reason))>0
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS matching_schedule_line_interactions (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    recipient_snapshot_id BIGINT UNSIGNED NOT NULL,
    token_hash CHAR(64) NOT NULL,
    interaction_status ENUM('active','awaiting_rejection_reason','consumed','invalidated') NOT NULL DEFAULT 'active',
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    consumed_at_utc DATETIME(6) NULL,
    UNIQUE KEY uq_matching_schedule_line_token (token_hash),
    UNIQUE KEY uq_matching_schedule_recipient_interaction (recipient_snapshot_id),
    CONSTRAINT fk_matching_schedule_interaction_recipient FOREIGN KEY (recipient_snapshot_id)
        REFERENCES matching_schedule_recipient_snapshots(id),
    CONSTRAINT chk_matching_schedule_line_token CHECK (token_hash REGEXP '^[0-9a-f]{64}$')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
-- END SOURCE: db/schema_parts/181_matching_service_date_confirmation.sql

-- BEGIN SOURCE: db/schema_parts/182_candidate_contact_pool.sql
-- 182. Candidate Contact Pool: negotiation contacts, never formal service segments.
CREATE TABLE IF NOT EXISTS caregiver_candidate_contact_pools (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    case_no VARCHAR(50) NOT NULL,
    created_by VARCHAR(100) NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_candidate_contact_pool_case (case_no),
    CONSTRAINT fk_candidate_contact_pool_case FOREIGN KEY (case_no) REFERENCES orders(case_no)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS caregiver_candidate_contact_entries (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    pool_id BIGINT UNSIGNED NOT NULL,
    staff_id INT NOT NULL,
    service_start_date DATE NOT NULL,
    service_end_date DATE NOT NULL,
    coverage_fingerprint CHAR(64) NOT NULL,
    status ENUM('active','selected','withdrawn') NOT NULL DEFAULT 'active',
    active_marker TINYINT NULL DEFAULT 1,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_candidate_contact_active_staff (pool_id,staff_id,active_marker),
    CONSTRAINT fk_candidate_contact_entry_pool FOREIGN KEY (pool_id) REFERENCES caregiver_candidate_contact_pools(id),
    CONSTRAINT fk_candidate_contact_entry_staff FOREIGN KEY (staff_id) REFERENCES staff(id),
    CONSTRAINT chk_candidate_contact_dates CHECK (service_start_date<=service_end_date),
    CONSTRAINT chk_candidate_contact_active CHECK (active_marker IS NULL OR active_marker=1)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS caregiver_candidate_contact_events (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    pool_id BIGINT UNSIGNED NOT NULL,
    candidate_id BIGINT UNSIGNED NULL,
    event_type ENUM('candidates_added','info_1_sent','info_2_sent','willingness_changed','candidate_selected','candidate_withdrawn') NOT NULL,
    event_key VARCHAR(100) NOT NULL,
    actor VARCHAR(100) NOT NULL,
    payload JSON NOT NULL,
    occurred_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_candidate_contact_event_key (event_key),
    KEY idx_candidate_contact_event_candidate (candidate_id,occurred_at),
    CONSTRAINT fk_candidate_contact_event_pool FOREIGN KEY (pool_id) REFERENCES caregiver_candidate_contact_pools(id),
    CONSTRAINT fk_candidate_contact_event_candidate FOREIGN KEY (candidate_id) REFERENCES caregiver_candidate_contact_entries(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
-- END SOURCE: db/schema_parts/182_candidate_contact_pool.sql

-- BEGIN SOURCE: db/schema_parts/183_staff_leave_requests.sql
CREATE TABLE IF NOT EXISTS staff_leave_requests (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    staff_id INT NOT NULL COMMENT '提出請假的月嫂',
    line_user_id VARCHAR(100) NOT NULL COMMENT '提出申請的 LINE 用戶',
    leave_start_date DATE NOT NULL COMMENT '請假開始日期',
    leave_end_date DATE NOT NULL COMMENT '請假結束日期',
    leave_reason TEXT NULL COMMENT '請假原因',
    substitute_found BOOLEAN NOT NULL DEFAULT FALSE COMMENT '是否已找到代班人員',
    substitute_name VARCHAR(100) NULL COMMENT '代班人員姓名',
    substitute_phone VARCHAR(30) NULL COMMENT '代班人員電話',
    substitute_note TEXT NULL COMMENT '代班補充資訊',
    status ENUM('pending','approved','rejected','cancelled') NOT NULL DEFAULT 'pending',
    reviewed_by_admin_user_id BIGINT NULL COMMENT '審核工會人員',
    reviewed_at DATETIME NULL COMMENT '審核時間',
    review_note TEXT NULL COMMENT '審核備註',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_staff_leave_staff_status (staff_id, status, leave_start_date),
    INDEX idx_staff_leave_line_user (line_user_id, created_at),
    CONSTRAINT fk_staff_leave_staff
        FOREIGN KEY (staff_id) REFERENCES staff(id) ON DELETE RESTRICT,
    CONSTRAINT fk_staff_leave_reviewer
        FOREIGN KEY (reviewed_by_admin_user_id) REFERENCES admin_users(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
-- END SOURCE: db/schema_parts/183_staff_leave_requests.sql

-- BEGIN SOURCE: db/schema_parts/184_provisional_registration_case_issue.sql
CREATE TABLE IF NOT EXISTS provisional_registration_case_issue_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    registration_id BIGINT NOT NULL,
    case_no VARCHAR(50) NOT NULL,
    client_id INT NOT NULL,
    beclass_record_id INT NOT NULL,
    case_import_event_id BIGINT NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    actor VARCHAR(100) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_provisional_case_issue_registration (registration_id),
    UNIQUE KEY uq_provisional_case_issue_case (case_no),
    UNIQUE KEY uq_provisional_case_issue_idempotency (idempotency_key),
    CONSTRAINT fk_provisional_case_issue_registration FOREIGN KEY (registration_id)
        REFERENCES provisional_client_registrations(id) ON DELETE RESTRICT,
    CONSTRAINT fk_provisional_case_issue_client FOREIGN KEY (client_id)
        REFERENCES clients(id) ON DELETE RESTRICT,
    CONSTRAINT fk_provisional_case_issue_beclass FOREIGN KEY (beclass_record_id)
        REFERENCES beclass_records(id) ON DELETE RESTRICT,
    CONSTRAINT fk_provisional_case_issue_import_event FOREIGN KEY (case_import_event_id)
        REFERENCES case_import_events(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

ALTER TABLE case_import_receipts
    ADD COLUMN provisional_registration_id BIGINT NULL,
    ADD COLUMN provisional_case_issue_event_id BIGINT NULL,
    ADD CONSTRAINT fk_case_import_receipt_provisional_registration
        FOREIGN KEY (provisional_registration_id) REFERENCES provisional_client_registrations(id)
        ON DELETE RESTRICT,
    ADD CONSTRAINT fk_case_import_receipt_provisional_issue_event
        FOREIGN KEY (provisional_case_issue_event_id) REFERENCES provisional_registration_case_issue_events(id)
        ON DELETE RESTRICT;
-- END SOURCE: db/schema_parts/184_provisional_registration_case_issue.sql

-- BEGIN SOURCE: db/schema_parts/185_customer_service_runtime.sql
CREATE TABLE IF NOT EXISTS customer_service_tickets (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    line_user_id VARCHAR(100) NOT NULL,
    client_id INT NULL,
    case_no VARCHAR(50) NULL,
    category ENUM('service_flow','payment_subsidy','service_progress','profile_update','contact_union','other') NOT NULL,
    status ENUM('waiting','handling','resolved') NOT NULL DEFAULT 'waiting',
    assigned_to_admin_user_id BIGINT NULL,
    internal_note TEXT NULL,
    version BIGINT NOT NULL DEFAULT 0,
    resolved_at_utc DATETIME NULL,
    created_at_utc DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at_utc DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    active_marker TINYINT GENERATED ALWAYS AS (
        CASE WHEN status IN ('waiting','handling') THEN 1 ELSE NULL END
    ) STORED,
    UNIQUE KEY uq_customer_service_active_category (line_user_id, category, active_marker),
    INDEX idx_customer_service_status_time (status, created_at_utc),
    INDEX idx_customer_service_client (client_id, created_at_utc),
    INDEX idx_customer_service_case (case_no, created_at_utc),
    CONSTRAINT fk_customer_service_client FOREIGN KEY (client_id)
        REFERENCES clients(id) ON UPDATE RESTRICT ON DELETE SET NULL,
    CONSTRAINT fk_customer_service_order FOREIGN KEY (case_no)
        REFERENCES orders(case_no) ON UPDATE CASCADE ON DELETE SET NULL,
    CONSTRAINT fk_customer_service_admin FOREIGN KEY (assigned_to_admin_user_id)
        REFERENCES admin_users(id) ON UPDATE RESTRICT ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS customer_service_ticket_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    ticket_id BIGINT NOT NULL,
    event_key VARCHAR(191) NOT NULL,
    event_type ENUM('customer_message','agent_reply','status_changed','internal_note') NOT NULL,
    message_text TEXT NULL,
    actor_id VARCHAR(191) NOT NULL,
    created_at_utc DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_customer_service_event_key (event_key),
    INDEX idx_customer_service_ticket_events (ticket_id, id),
    CONSTRAINT fk_customer_service_event_ticket FOREIGN KEY (ticket_id)
        REFERENCES customer_service_tickets(id) ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
-- END SOURCE: db/schema_parts/185_customer_service_runtime.sql

-- BEGIN SOURCE: db/schema_parts/186_line_identity_management.sql
ALTER TABLE line_identity_bindings
    MODIFY COLUMN binding_status ENUM(
        'unbound','pending_review','bound','revocation_pending','revoked'
    ) NOT NULL DEFAULT 'unbound';

ALTER TABLE line_identity_bindings
    MODIFY COLUMN active_subject_key VARCHAR(400)
    GENERATED ALWAYS AS (
        CASE
            WHEN binding_status IN ('pending_review','bound','revocation_pending')
            THEN CONCAT(subject_type, ':', subject_reference)
            ELSE NULL
        END
    ) STORED;

ALTER TABLE line_identity_binding_events
    MODIFY COLUMN action ENUM(
        'claim_submitted','bound','revocation_requested','revoked','rebound',
        'legacy_imported'
    ) NOT NULL;

CREATE TABLE IF NOT EXISTS line_identity_revocation_requests (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    line_user_id VARCHAR(191) NOT NULL,
    subject_type ENUM('customer','staff','admin') NOT NULL,
    subject_reference VARCHAR(191) NOT NULL,
    request_status ENUM(
        'pending_menu_reset','menu_reset_failed','completed','manual_completed'
    ) NOT NULL DEFAULT 'pending_menu_reset',
    requested_binding_version BIGINT UNSIGNED NOT NULL,
    pending_binding_version BIGINT UNSIGNED NOT NULL,
    completed_binding_version BIGINT UNSIGNED NULL,
    default_menu_publication_id BIGINT NOT NULL,
    provider_menu_id VARCHAR(191) NOT NULL,
    requested_by_actor_id VARCHAR(191) NOT NULL,
    request_reason VARCHAR(1000) NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    attempt_count INT UNSIGNED NOT NULL DEFAULT 0,
    last_error_code VARCHAR(191) NULL,
    last_error_message VARCHAR(1000) NULL,
    requested_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    menu_reset_at_utc DATETIME(6) NULL,
    completed_at_utc DATETIME(6) NULL,
    completed_by_actor_id VARCHAR(191) NULL,
    completion_reason VARCHAR(1000) NULL,
    active_marker TINYINT GENERATED ALWAYS AS (
        CASE
            WHEN request_status IN ('pending_menu_reset','menu_reset_failed')
            THEN 1
            ELSE NULL
        END
    ) STORED,
    UNIQUE KEY uq_line_identity_revocation_idempotency (idempotency_key),
    UNIQUE KEY uq_line_identity_active_revocation (line_user_id, active_marker),
    INDEX idx_line_identity_revocation_status (request_status, requested_at_utc),
    CONSTRAINT fk_line_identity_revocation_binding FOREIGN KEY (line_user_id)
        REFERENCES line_identity_bindings(line_user_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_line_identity_revocation_publication
        FOREIGN KEY (default_menu_publication_id)
        REFERENCES line_rich_menu_publications(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_line_identity_revocation_version CHECK (
        pending_binding_version = requested_binding_version + 1
        AND (
            completed_binding_version IS NULL
            OR completed_binding_version = pending_binding_version + 1
        )
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
-- END SOURCE: db/schema_parts/186_line_identity_management.sql

-- BEGIN SOURCE: db/schema_parts/179_line_identity_canonical_menu_publication.sql
ALTER TABLE line_identity_revocation_requests
    MODIFY COLUMN default_menu_publication_id BIGINT NULL,
    ADD COLUMN canonical_default_menu_publication_id BIGINT UNSIGNED NULL
        AFTER default_menu_publication_id,
    ADD INDEX idx_line_identity_revocation_canonical_publication (
        canonical_default_menu_publication_id
    ),
    ADD CONSTRAINT fk_line_identity_revocation_canonical_publication
        FOREIGN KEY (canonical_default_menu_publication_id)
        REFERENCES line_rich_menu_publication_tasks(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    ADD CONSTRAINT chk_line_identity_revocation_publication_source CHECK (
        (default_menu_publication_id IS NULL)
        <> (canonical_default_menu_publication_id IS NULL)
    );
-- END SOURCE: db/schema_parts/179_line_identity_canonical_menu_publication.sql

-- BEGIN SOURCE: db/schema_parts/187_case_architecture_bootstrap_receipt_version_contract.sql
-- Bootstrap may adopt an already-versioned Scheduling aggregate. Finance and
-- Payroll roots are still created at version zero by this transaction.
ALTER TABLE case_architecture_bootstrap_receipts
    DROP CHECK chk_case_architecture_receipt_initial_versions;

ALTER TABLE case_architecture_bootstrap_receipts
    ADD CONSTRAINT chk_case_architecture_receipt_bootstrap_versions
    CHECK (
        client_finance_version = 0
        AND payroll_version = 0
    );
-- END SOURCE: db/schema_parts/187_case_architecture_bootstrap_receipt_version_contract.sql

-- BEGIN SOURCE: db/schema_parts/188_matching_preferences_and_staff_availability.sql
-- WP72 additive Staff Matching Profile and Scheduling availability roots.

ALTER TABLE orders
    ADD COLUMN requires_cooking TINYINT(1) NULL
        COMMENT '是否需要月嫂下廚；NULL 只允許 legacy/待人工補正',
    ADD CONSTRAINT chk_orders_requires_cooking
        CHECK (requires_cooking IS NULL OR requires_cooking IN (0, 1));

CREATE TABLE IF NOT EXISTS staff_matching_preference_definitions (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    preference_key VARCHAR(100) NOT NULL,
    display_name VARCHAR(100) NOT NULL,
    value_kind ENUM('integer_range','integer_set') NOT NULL,
    is_filterable TINYINT(1) NOT NULL DEFAULT 0,
    order_fact_key ENUM('service_days','service_hours_per_day') NULL,
    comparison_operator ENUM('range_with_tolerance','contains_integer') NOT NULL,
    status ENUM('active','inactive') NOT NULL DEFAULT 'active',
    version BIGINT UNSIGNED NOT NULL DEFAULT 1,
    created_by VARCHAR(100) NOT NULL,
    updated_by VARCHAR(100) NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
        ON UPDATE CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_staff_matching_preference_key (preference_key),
    CONSTRAINT chk_staff_matching_preference_definition_text CHECK (
        CHAR_LENGTH(TRIM(preference_key)) > 0
        AND CHAR_LENGTH(TRIM(display_name)) > 0
        AND CHAR_LENGTH(TRIM(created_by)) > 0
        AND CHAR_LENGTH(TRIM(updated_by)) > 0
    ),
    CONSTRAINT chk_staff_matching_preference_filter_source CHECK (
        (is_filterable=0 AND order_fact_key IS NULL)
        OR (is_filterable=1 AND order_fact_key IS NOT NULL)
    ),
    CONSTRAINT chk_staff_matching_preference_comparison CHECK (
        (value_kind='integer_range' AND comparison_operator='range_with_tolerance')
        OR (value_kind='integer_set' AND comparison_operator='contains_integer')
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS staff_matching_preference_profiles (
    staff_id INT PRIMARY KEY,
    version BIGINT UNSIGNED NOT NULL DEFAULT 0,
    created_by VARCHAR(100) NOT NULL,
    updated_by VARCHAR(100) NOT NULL,
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
        ON UPDATE CURRENT_TIMESTAMP(6),
    CONSTRAINT fk_staff_matching_preference_profile_staff
        FOREIGN KEY (staff_id) REFERENCES staff(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_staff_matching_preference_profile_actor
        CHECK (CHAR_LENGTH(TRIM(updated_by)) > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS staff_matching_preference_values (
    staff_id INT NOT NULL,
    definition_id BIGINT NOT NULL,
    value_json JSON NOT NULL,
    profile_version BIGINT UNSIGNED NOT NULL,
    updated_by VARCHAR(100) NOT NULL,
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
        ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (staff_id,definition_id),
    CONSTRAINT fk_staff_matching_preference_value_profile
        FOREIGN KEY (staff_id) REFERENCES staff_matching_preference_profiles(staff_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_staff_matching_preference_value_definition
        FOREIGN KEY (definition_id) REFERENCES staff_matching_preference_definitions(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_staff_matching_preference_value_json
        CHECK (JSON_TYPE(value_json)='OBJECT'),
    CONSTRAINT chk_staff_matching_preference_value_actor
        CHECK (CHAR_LENGTH(TRIM(updated_by)) > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS staff_matching_preference_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    event_type VARCHAR(100) NOT NULL,
    aggregate_identity VARCHAR(191) NOT NULL,
    resulting_version BIGINT UNSIGNED NOT NULL,
    actor VARCHAR(100) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    before_json JSON NOT NULL,
    after_json JSON NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_staff_matching_preference_event_key (idempotency_key),
    CONSTRAINT chk_staff_matching_preference_event_snapshots CHECK (
        resulting_version>0
        AND JSON_TYPE(before_json)='OBJECT'
        AND JSON_TYPE(after_json)='OBJECT'
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS staff_matching_preference_receipts (
    idempotency_key VARCHAR(191) PRIMARY KEY,
    command_family VARCHAR(100) NOT NULL,
    aggregate_identity VARCHAR(191) NOT NULL,
    command_fingerprint CHAR(64) NOT NULL,
    preview_fingerprint CHAR(64) NOT NULL,
    result_json JSON NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT chk_staff_matching_preference_receipt_fingerprints CHECK (
        command_fingerprint REGEXP '^[0-9a-f]{64}$'
        AND preview_fingerprint REGEXP '^[0-9a-f]{64}$'
    ),
    CONSTRAINT chk_staff_matching_preference_receipt_snapshot
        CHECK (JSON_TYPE(result_json)='OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS staff_matching_preference_migration_reviews (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    staff_id INT NOT NULL,
    source_kind ENUM('staff_time_slot') NOT NULL,
    source_value VARCHAR(100) NOT NULL,
    issue_code ENUM('source_not_ready') NOT NULL,
    status ENUM('open','resolved') NOT NULL DEFAULT 'open',
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    resolved_at DATETIME(6) NULL,
    UNIQUE KEY uq_staff_matching_preference_migration_review
        (staff_id,source_kind,source_value,issue_code),
    CONSTRAINT fk_staff_matching_preference_migration_review_staff
        FOREIGN KEY (staff_id) REFERENCES staff(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS scheduling_staff_availability_aggregates (
    staff_id INT PRIMARY KEY,
    aggregate_version BIGINT UNSIGNED NOT NULL DEFAULT 0,
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
        ON UPDATE CURRENT_TIMESTAMP(6),
    CONSTRAINT fk_scheduling_staff_availability_staff
        FOREIGN KEY (staff_id) REFERENCES staff(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS scheduling_staff_unavailability_blocks (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    staff_id INT NOT NULL,
    block_kind ENUM('long_leave','paused_service') NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE NULL,
    status ENUM('effective','cancelled') NOT NULL DEFAULT 'effective',
    reason VARCHAR(500) NOT NULL,
    source_block_id BIGINT NULL,
    created_by VARCHAR(100) NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    ended_by VARCHAR(100) NULL,
    ended_at DATETIME(6) NULL,
    cancelled_by VARCHAR(100) NULL,
    cancelled_at DATETIME(6) NULL,
    CONSTRAINT fk_scheduling_staff_unavailability_staff
        FOREIGN KEY (staff_id) REFERENCES staff(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_scheduling_staff_unavailability_source
        FOREIGN KEY (source_block_id) REFERENCES scheduling_staff_unavailability_blocks(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_scheduling_staff_unavailability_dates CHECK (
        (block_kind='long_leave' AND end_date IS NOT NULL AND end_date>=start_date)
        OR (block_kind='paused_service' AND (end_date IS NULL OR end_date>=start_date))
    ),
    CONSTRAINT chk_scheduling_staff_unavailability_reason
        CHECK (CHAR_LENGTH(TRIM(reason))>0 AND CHAR_LENGTH(TRIM(created_by))>0),
    INDEX idx_scheduling_staff_unavailability_current
        (staff_id,status,start_date,end_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS scheduling_staff_availability_events (
    event_key VARCHAR(191) PRIMARY KEY,
    staff_id INT NOT NULL,
    aggregate_version BIGINT UNSIGNED NOT NULL,
    block_id BIGINT NOT NULL,
    event_type ENUM('created','pause_ended','cancelled') NOT NULL,
    before_snapshot JSON NOT NULL,
    after_snapshot JSON NOT NULL,
    actor VARCHAR(100) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    occurred_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT fk_scheduling_staff_availability_event_staff
        FOREIGN KEY (staff_id) REFERENCES scheduling_staff_availability_aggregates(staff_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_scheduling_staff_availability_event_block
        FOREIGN KEY (block_id) REFERENCES scheduling_staff_unavailability_blocks(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_scheduling_staff_availability_event_snapshots CHECK (
        aggregate_version>0
        AND JSON_TYPE(before_snapshot)='OBJECT'
        AND JSON_TYPE(after_snapshot)='OBJECT'
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS scheduling_staff_availability_apply_receipts (
    idempotency_key VARCHAR(191) PRIMARY KEY,
    request_fingerprint CHAR(64) NOT NULL,
    preview_fingerprint CHAR(64) NOT NULL,
    staff_id INT NOT NULL,
    aggregate_version BIGINT UNSIGNED NOT NULL,
    block_id BIGINT NOT NULL,
    action ENUM('create_long_leave','create_pause','end_pause','cancel') NOT NULL,
    result_snapshot JSON NOT NULL,
    actor VARCHAR(100) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT fk_scheduling_staff_availability_receipt_staff
        FOREIGN KEY (staff_id) REFERENCES scheduling_staff_availability_aggregates(staff_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_scheduling_staff_availability_receipt_block
        FOREIGN KEY (block_id) REFERENCES scheduling_staff_unavailability_blocks(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_scheduling_staff_availability_receipt_fingerprints CHECK (
        request_fingerprint REGEXP '^[0-9a-f]{64}$'
        AND preview_fingerprint REGEXP '^[0-9a-f]{64}$'
    ),
    CONSTRAINT chk_scheduling_staff_availability_receipt_snapshot
        CHECK (JSON_TYPE(result_snapshot)='OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO staff_matching_preference_definitions
    (preference_key,display_name,value_kind,is_filterable,order_fact_key,
     comparison_operator,status,version,created_by,updated_by)
VALUES
    ('preferred_service_days','可承接服務天數','integer_range',1,
     'service_days','range_with_tolerance','active',1,'wp72','wp72'),
    ('daily_service_hours','可承接每日服務時數','integer_set',1,
     'service_hours_per_day','contains_integer','active',1,'wp72','wp72')
ON DUPLICATE KEY UPDATE preference_key=VALUES(preference_key);

INSERT INTO staff_matching_preference_profiles
    (staff_id,version,created_by,updated_by)
SELECT DISTINCT staff_id,1,'wp72-time-slot-backfill','wp72-time-slot-backfill'
FROM staff_time_slots
WHERE slot_name IN (
    '4小時_上午','4小時_下午','4小時(上午8:30-12:30)',
    '4小時(下午13:00-17:00)','8小時','24小時'
)
ON DUPLICATE KEY UPDATE staff_id=VALUES(staff_id);

INSERT INTO staff_matching_preference_values
    (staff_id,definition_id,value_json,profile_version,updated_by)
SELECT normalized.staff_id,definition.id,
       JSON_OBJECT(
           'values',
           CAST(CONCAT('[',GROUP_CONCAT(
               normalized.hours ORDER BY normalized.hours SEPARATOR ','
           ),']') AS JSON)
       ),1,
       'wp72-time-slot-backfill'
FROM (
    SELECT DISTINCT staff_id,
        CASE
            WHEN slot_name IN (
                '4小時_上午','4小時_下午','4小時(上午8:30-12:30)',
                '4小時(下午13:00-17:00)'
            ) THEN 4
            WHEN slot_name='8小時' THEN 8
            WHEN slot_name='24小時' THEN 24
        END AS hours
    FROM staff_time_slots
    WHERE slot_name IN (
        '4小時_上午','4小時_下午','4小時(上午8:30-12:30)',
        '4小時(下午13:00-17:00)','8小時','24小時'
    )
) normalized
JOIN staff_matching_preference_definitions definition
  ON definition.preference_key='daily_service_hours'
GROUP BY normalized.staff_id,definition.id
ON DUPLICATE KEY UPDATE staff_id=VALUES(staff_id);

INSERT INTO staff_matching_preference_migration_reviews
    (staff_id,source_kind,source_value,issue_code)
SELECT staff_id,'staff_time_slot',
       LEFT(CASE
           WHEN custom_slot_detail IS NULL OR TRIM(custom_slot_detail)='' THEN slot_name
           ELSE CONCAT(slot_name,':',custom_slot_detail)
       END,100),
       'source_not_ready'
FROM staff_time_slots
WHERE slot_name NOT IN (
    '4小時_上午','4小時_下午','4小時(上午8:30-12:30)',
    '4小時(下午13:00-17:00)','8小時','24小時'
)
   OR (custom_slot_detail IS NOT NULL AND TRIM(custom_slot_detail)<>'')
ON DUPLICATE KEY UPDATE id=id;
-- END SOURCE: db/schema_parts/188_matching_preferences_and_staff_availability.sql

-- BEGIN SOURCE: db/schema_parts/191_line_staff_self_service_identity_flow.sql
ALTER TABLE line_identity_flows
    MODIFY COLUMN flow_purpose ENUM(
        'customer_binding',
        'staff_verification',
        'admin_binding',
        'staff_self_service'
    ) NOT NULL;
-- END SOURCE: db/schema_parts/191_line_staff_self_service_identity_flow.sql

-- BEGIN SOURCE: db/schema_parts/192_government_subsidy_outbox_intent_type_repair.sql
-- File: 192_government_subsidy_outbox_intent_type_repair.sql
-- Description: 補齊政府補助 outbox 的 overpayment disposition intent enum。

ALTER TABLE government_subsidy_outbox
    MODIFY COLUMN intent_type ENUM(
        'government_subsidy_receipt_applied',
        'government_subsidy_receipt_allocated',
        'government_subsidy_reversal_applied',
        'government_subsidy_anomaly_root_changed',
        'government_subsidy_overpayment_established',
        'government_subsidy_overpayment_offset',
        'government_overpayment_return_payable',
        'government_overpayment_return_payout'
    ) NOT NULL;
-- END SOURCE: db/schema_parts/192_government_subsidy_outbox_intent_type_repair.sql

-- BEGIN SOURCE: db/schema_parts/193_staff_historical_adoption_hcm_review.sql
-- File: 193_staff_historical_adoption_hcm_review.sql
-- Description: 新增 Staff 歷史採納 receipt 與 HCM Case Import review/outbox。

CREATE TABLE IF NOT EXISTS staff_historical_adoption_receipts (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    idempotency_key VARCHAR(191) NOT NULL,
    command_fingerprint CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    source_event_identity VARCHAR(191) NOT NULL,
    source_fingerprint CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    preview_fingerprint CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    staff_id INT NULL,
    outcome ENUM(
        'created', 'adopted_existing', 'blocked_identity',
        'identity_conflict', 'failed_retryable'
    ) NOT NULL,
    changed_fields JSON NOT NULL,
    review_identity VARCHAR(191) NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_staff_historical_adoption_key (idempotency_key),
    UNIQUE KEY uq_staff_historical_adoption_source (source_event_identity),
    CONSTRAINT fk_staff_historical_adoption_staff
        FOREIGN KEY (staff_id) REFERENCES staff(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_staff_historical_adoption_review
        FOREIGN KEY (review_identity) REFERENCES beclass_import_review_rows(review_identity)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_staff_historical_adoption_fingerprints
        CHECK (
            command_fingerprint REGEXP '^[0-9a-f]{64}$'
            AND source_fingerprint REGEXP '^[0-9a-f]{64}$'
            AND preview_fingerprint REGEXP '^[0-9a-f]{64}$'
        ),
    CONSTRAINT chk_staff_historical_adoption_changed_fields
        CHECK (JSON_TYPE(changed_fields) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS case_import_hcm_review_rows (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    review_identity VARCHAR(191) NOT NULL,
    source_event_identity VARCHAR(191) NOT NULL,
    source_content_digest CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    source_sheet_identity CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    source_row INT NOT NULL,
    masked_case_identity VARCHAR(64) NOT NULL,
    source_fingerprint CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    issue_codes JSON NOT NULL,
    evidence_snapshot JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_case_import_hcm_review_identity (review_identity),
    UNIQUE KEY uq_case_import_hcm_review_source (source_event_identity),
    CONSTRAINT chk_case_import_hcm_review_digests
        CHECK (
            source_content_digest REGEXP '^[0-9a-f]{64}$'
            AND source_sheet_identity REGEXP '^[0-9a-f]{64}$'
            AND source_fingerprint REGEXP '^[0-9a-f]{64}$'
        ),
    CONSTRAINT chk_case_import_hcm_review_source_row CHECK (source_row > 0),
    CONSTRAINT chk_case_import_hcm_review_payloads
        CHECK (JSON_TYPE(issue_codes) = 'ARRAY' AND JSON_TYPE(evidence_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS case_import_hcm_review_outbox (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    review_row_id BIGINT NOT NULL,
    intent_key VARCHAR(191) NOT NULL,
    bounded_snapshot JSON NOT NULL,
    published_at TIMESTAMP NULL,
    attempts INT NOT NULL DEFAULT 0,
    last_error VARCHAR(500) NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_case_import_hcm_review_outbox_intent (intent_key),
    INDEX idx_case_import_hcm_review_outbox_pending (published_at, attempts, id),
    CONSTRAINT fk_case_import_hcm_review_outbox_row
        FOREIGN KEY (review_row_id) REFERENCES case_import_hcm_review_rows(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_case_import_hcm_review_outbox_snapshot
        CHECK (JSON_TYPE(bounded_snapshot) = 'OBJECT'),
    CONSTRAINT chk_case_import_hcm_review_outbox_attempts CHECK (attempts >= 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_staff_historical_adoption_receipts_before_update;
CREATE TRIGGER trg_staff_historical_adoption_receipts_before_update
BEFORE UPDATE ON staff_historical_adoption_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'staff_historical_adoption_receipts records cannot be updated';

DROP TRIGGER IF EXISTS trg_staff_historical_adoption_receipts_before_delete;
CREATE TRIGGER trg_staff_historical_adoption_receipts_before_delete
BEFORE DELETE ON staff_historical_adoption_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'staff_historical_adoption_receipts records cannot be deleted';

DROP TRIGGER IF EXISTS trg_case_import_hcm_review_rows_before_update;
CREATE TRIGGER trg_case_import_hcm_review_rows_before_update
BEFORE UPDATE ON case_import_hcm_review_rows
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'case_import_hcm_review_rows records cannot be updated';

DROP TRIGGER IF EXISTS trg_case_import_hcm_review_rows_before_delete;
CREATE TRIGGER trg_case_import_hcm_review_rows_before_delete
BEFORE DELETE ON case_import_hcm_review_rows
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'case_import_hcm_review_rows records cannot be deleted';
-- END SOURCE: db/schema_parts/193_staff_historical_adoption_hcm_review.sql

-- BEGIN SOURCE: db/schema_parts/194_historical_order_adoption.sql
-- File: 194_historical_order_adoption.sql
-- Description: 新增 Historical Order Adoption receipt、pairing evidence、review 與 outbox。

CREATE TABLE IF NOT EXISTS historical_order_adoption_reviews (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    review_identity VARCHAR(191) NOT NULL,
    source_event_identity VARCHAR(191) NOT NULL,
    source_fingerprint CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    masked_case_identity VARCHAR(64) NOT NULL,
    issue_codes JSON NOT NULL,
    evidence_snapshot JSON NOT NULL,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    UNIQUE KEY uq_historical_order_review_identity (review_identity),
    UNIQUE KEY uq_historical_order_review_source (source_event_identity),
    CONSTRAINT chk_historical_order_review_fingerprint
        CHECK (source_fingerprint REGEXP '^[0-9a-f]{64}$'),
    CONSTRAINT chk_historical_order_review_payloads
        CHECK (JSON_TYPE(issue_codes) = 'ARRAY' AND JSON_TYPE(evidence_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS historical_order_adoption_receipts (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    idempotency_key VARCHAR(191) NOT NULL,
    command_fingerprint CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    source_event_identity VARCHAR(191) NOT NULL,
    source_fingerprint CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    preview_fingerprint CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    case_no VARCHAR(50) NULL,
    outcome ENUM('adopted','review_required','current_conflict','unmatched_case') NOT NULL,
    expected_version BIGINT UNSIGNED NULL,
    resulting_version BIGINT UNSIGNED NULL,
    lifecycle_event_id BIGINT UNSIGNED NULL,
    assignment_count INT UNSIGNED NOT NULL DEFAULT 0,
    review_identity VARCHAR(191) NULL,
    result_snapshot JSON NOT NULL,
    actor VARCHAR(255) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    UNIQUE KEY uq_historical_order_adoption_key (idempotency_key),
    UNIQUE KEY uq_historical_order_adoption_source (source_event_identity),
    INDEX idx_historical_order_adoption_case (case_no, created_at),
    CONSTRAINT fk_historical_order_adoption_case
        FOREIGN KEY (case_no) REFERENCES orders(case_no) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_historical_order_adoption_lifecycle_event
        FOREIGN KEY (lifecycle_event_id) REFERENCES order_lifecycle_state_events(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_historical_order_adoption_review
        FOREIGN KEY (review_identity) REFERENCES historical_order_adoption_reviews(review_identity)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_historical_order_adoption_fingerprints
        CHECK (
            command_fingerprint REGEXP '^[0-9a-f]{64}$'
            AND source_fingerprint REGEXP '^[0-9a-f]{64}$'
            AND preview_fingerprint REGEXP '^[0-9a-f]{64}$'
        ),
    CONSTRAINT chk_historical_order_adoption_snapshot
        CHECK (JSON_TYPE(result_snapshot) = 'OBJECT'),
    CONSTRAINT chk_historical_order_adoption_shape
        CHECK (
            (outcome = 'unmatched_case' AND lifecycle_event_id IS NULL
             AND expected_version IS NULL AND resulting_version IS NULL)
            OR
            (outcome = 'adopted' AND lifecycle_event_id IS NOT NULL
             AND expected_version IS NOT NULL AND resulting_version = expected_version + 1
             AND case_no IS NOT NULL)
            OR
            (outcome IN ('review_required','current_conflict') AND lifecycle_event_id IS NULL
             AND expected_version IS NOT NULL AND resulting_version = expected_version
             AND case_no IS NOT NULL)
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS historical_order_pairing_evidence (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    receipt_id BIGINT UNSIGNED NOT NULL,
    caregiver_ordinal INT UNSIGNED NOT NULL,
    masked_staff_name VARCHAR(100) NOT NULL,
    staff_id INT NULL,
    resolution ENUM(
        'blank','staff_missing','staff_ambiguous','evidence_only',
        'assignment_candidate','assignment_conflict'
    ) NOT NULL,
    source_start_date DATE NULL,
    source_end_date DATE NULL,
    assignment_id BIGINT NULL,
    issue_codes JSON NOT NULL,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    UNIQUE KEY uq_historical_order_pairing_ordinal (receipt_id, caregiver_ordinal),
    INDEX idx_historical_order_pairing_staff (staff_id, created_at),
    CONSTRAINT fk_historical_order_pairing_receipt
        FOREIGN KEY (receipt_id) REFERENCES historical_order_adoption_receipts(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_historical_order_pairing_staff
        FOREIGN KEY (staff_id) REFERENCES staff(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_historical_order_pairing_assignment
        FOREIGN KEY (assignment_id) REFERENCES case_staff_assignments(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_historical_order_pairing_ordinal CHECK (caregiver_ordinal > 0),
    CONSTRAINT chk_historical_order_pairing_issues CHECK (JSON_TYPE(issue_codes) = 'ARRAY'),
    CONSTRAINT chk_historical_order_pairing_assignment_shape
        CHECK (
            (resolution = 'assignment_candidate' AND assignment_id IS NOT NULL AND staff_id IS NOT NULL)
            OR (resolution <> 'assignment_candidate' AND assignment_id IS NULL)
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS historical_order_adoption_outbox (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    receipt_id BIGINT UNSIGNED NOT NULL,
    intent_key VARCHAR(191) NOT NULL,
    intent_type ENUM('historical_order_adopted','historical_order_review_required') NOT NULL,
    bounded_snapshot JSON NOT NULL,
    published_at TIMESTAMP(6) NULL,
    attempts INT UNSIGNED NOT NULL DEFAULT 0,
    last_error VARCHAR(500) NULL,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    UNIQUE KEY uq_historical_order_adoption_outbox_intent (intent_key),
    INDEX idx_historical_order_adoption_outbox_pending (published_at, attempts, id),
    CONSTRAINT fk_historical_order_adoption_outbox_receipt
        FOREIGN KEY (receipt_id) REFERENCES historical_order_adoption_receipts(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_historical_order_adoption_outbox_snapshot
        CHECK (JSON_TYPE(bounded_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_historical_order_adoption_reviews_before_update;
CREATE TRIGGER trg_historical_order_adoption_reviews_before_update
BEFORE UPDATE ON historical_order_adoption_reviews
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'historical_order_adoption_reviews records cannot be updated';

DROP TRIGGER IF EXISTS trg_historical_order_adoption_reviews_before_delete;
CREATE TRIGGER trg_historical_order_adoption_reviews_before_delete
BEFORE DELETE ON historical_order_adoption_reviews
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'historical_order_adoption_reviews records cannot be deleted';

DROP TRIGGER IF EXISTS trg_historical_order_adoption_receipts_before_update;
CREATE TRIGGER trg_historical_order_adoption_receipts_before_update
BEFORE UPDATE ON historical_order_adoption_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'historical_order_adoption_receipts records cannot be updated';

DROP TRIGGER IF EXISTS trg_historical_order_adoption_receipts_before_delete;
CREATE TRIGGER trg_historical_order_adoption_receipts_before_delete
BEFORE DELETE ON historical_order_adoption_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'historical_order_adoption_receipts records cannot be deleted';

DROP TRIGGER IF EXISTS trg_historical_order_pairing_evidence_before_update;
CREATE TRIGGER trg_historical_order_pairing_evidence_before_update
BEFORE UPDATE ON historical_order_pairing_evidence
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'historical_order_pairing_evidence records cannot be updated';

DROP TRIGGER IF EXISTS trg_historical_order_pairing_evidence_before_delete;
CREATE TRIGGER trg_historical_order_pairing_evidence_before_delete
BEFORE DELETE ON historical_order_pairing_evidence
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'historical_order_pairing_evidence records cannot be deleted';
-- END SOURCE: db/schema_parts/194_historical_order_adoption.sql

-- BEGIN SOURCE: db/schema_parts/195_import_warning_tracking.sql
-- File: 195_import_warning_tracking.sql
-- Description: 新增 WP90 匯入欄位警示、追蹤事件、待辦投影、重送關聯、receipt 與 outbox。

CREATE TABLE IF NOT EXISTS import_warning_occurrences (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    occurrence_identity VARCHAR(191) NOT NULL,
    owning_lane VARCHAR(64) NOT NULL,
    source_kind VARCHAR(64) NOT NULL,
    source_event_identity VARCHAR(191) NOT NULL,
    source_receipt_identity VARCHAR(191) NULL,
    logical_code VARCHAR(96) NOT NULL,
    field_path VARCHAR(191) NOT NULL,
    masked_subject VARCHAR(191) NOT NULL,
    issue_codes JSON NOT NULL,
    evidence_snapshot JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_import_warning_occurrence_identity (occurrence_identity),
    UNIQUE KEY uq_import_warning_occurrence_source (
        owning_lane, source_event_identity, logical_code, field_path
    ),
    INDEX idx_import_warning_occurrence_lane_subject (owning_lane, masked_subject),
    CONSTRAINT chk_import_warning_occurrence_payload
        CHECK (JSON_TYPE(issue_codes) = 'ARRAY' AND JSON_TYPE(evidence_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS import_warning_tracking_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    event_identity VARCHAR(191) NOT NULL,
    occurrence_id BIGINT NOT NULL,
    action ENUM(
        'opened', 'awaiting_external_confirmation', 'response_recorded',
        'reimport_requested', 'closed', 'auto_resolved'
    ) NOT NULL,
    before_status ENUM(
        'open', 'awaiting_external_confirmation', 'response_recorded',
        'reimport_requested', 'closed', 'auto_resolved'
    ) NULL,
    after_status ENUM(
        'open', 'awaiting_external_confirmation', 'response_recorded',
        'reimport_requested', 'closed', 'auto_resolved'
    ) NOT NULL,
    expected_version BIGINT UNSIGNED NOT NULL,
    resulting_version BIGINT UNSIGNED NOT NULL,
    actor_kind ENUM('union_operator', 'system') NOT NULL,
    actor_identity VARCHAR(100) NOT NULL,
    reason_code VARCHAR(100) NOT NULL,
    note VARCHAR(500) NULL,
    evidence_reference VARCHAR(191) NULL,
    command_fingerprint CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_import_warning_tracking_event_identity (event_identity),
    UNIQUE KEY uq_import_warning_tracking_event_key (idempotency_key),
    INDEX idx_import_warning_tracking_event_occurrence (occurrence_id, resulting_version),
    CONSTRAINT fk_import_warning_tracking_event_occurrence
        FOREIGN KEY (occurrence_id) REFERENCES import_warning_occurrences(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_import_warning_tracking_event_version
        CHECK (resulting_version = expected_version + 1),
    CONSTRAINT chk_import_warning_tracking_event_fingerprint
        CHECK (command_fingerprint REGEXP '^[0-9a-f]{64}$')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS import_warning_current_tasks (
    occurrence_id BIGINT PRIMARY KEY,
    tracking_status ENUM(
        'open', 'awaiting_external_confirmation', 'response_recorded',
        'reimport_requested', 'closed', 'auto_resolved'
    ) NOT NULL,
    tracking_version BIGINT UNSIGNED NOT NULL,
    replacement_occurrence_id BIGINT NULL,
    last_event_id BIGINT NOT NULL,
    last_event_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_import_warning_current_active (tracking_status, last_event_at),
    CONSTRAINT fk_import_warning_current_occurrence
        FOREIGN KEY (occurrence_id) REFERENCES import_warning_occurrences(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_import_warning_current_replacement
        FOREIGN KEY (replacement_occurrence_id) REFERENCES import_warning_occurrences(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_import_warning_current_event
        FOREIGN KEY (last_event_id) REFERENCES import_warning_tracking_events(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_import_warning_current_version CHECK (tracking_version > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS import_warning_resubmission_associations (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    association_identity VARCHAR(191) NOT NULL,
    prior_occurrence_id BIGINT NOT NULL,
    owning_lane VARCHAR(64) NOT NULL,
    prior_source_event_identity VARCHAR(191) NOT NULL,
    new_source_event_identity VARCHAR(191) NOT NULL,
    new_receipt_identity VARCHAR(191) NOT NULL,
    import_outcome ENUM('failed', 'succeeded') NOT NULL,
    replacement_occurrence_id BIGINT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_import_warning_resubmission_identity (association_identity),
    UNIQUE KEY uq_import_warning_resubmission_new_source (owning_lane, new_source_event_identity),
    CONSTRAINT fk_import_warning_resubmission_prior
        FOREIGN KEY (prior_occurrence_id) REFERENCES import_warning_occurrences(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_import_warning_resubmission_replacement
        FOREIGN KEY (replacement_occurrence_id) REFERENCES import_warning_occurrences(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_import_warning_resubmission_links
        CHECK (
            (import_outcome = 'failed' AND replacement_occurrence_id IS NOT NULL)
            OR (import_outcome = 'succeeded' AND replacement_occurrence_id IS NULL)
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS import_warning_tracking_receipts (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    idempotency_key VARCHAR(191) NOT NULL,
    command_fingerprint CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    occurrence_id BIGINT NOT NULL,
    tracking_event_id BIGINT NOT NULL,
    expected_version BIGINT UNSIGNED NOT NULL,
    resulting_version BIGINT UNSIGNED NOT NULL,
    result_snapshot JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_import_warning_tracking_receipt_key (idempotency_key),
    UNIQUE KEY uq_import_warning_tracking_receipt_event (tracking_event_id),
    CONSTRAINT fk_import_warning_tracking_receipt_occurrence
        FOREIGN KEY (occurrence_id) REFERENCES import_warning_occurrences(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_import_warning_tracking_receipt_event
        FOREIGN KEY (tracking_event_id) REFERENCES import_warning_tracking_events(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_import_warning_tracking_receipt_fingerprint
        CHECK (command_fingerprint REGEXP '^[0-9a-f]{64}$'),
    CONSTRAINT chk_import_warning_tracking_receipt_snapshot
        CHECK (JSON_TYPE(result_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS import_warning_tracking_outbox (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    tracking_event_id BIGINT NOT NULL,
    intent_key VARCHAR(191) NOT NULL,
    bounded_snapshot JSON NOT NULL,
    published_at TIMESTAMP NULL,
    attempts INT NOT NULL DEFAULT 0,
    last_error VARCHAR(500) NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_import_warning_tracking_outbox_intent (intent_key),
    INDEX idx_import_warning_tracking_outbox_pending (published_at, attempts, id),
    CONSTRAINT fk_import_warning_tracking_outbox_event
        FOREIGN KEY (tracking_event_id) REFERENCES import_warning_tracking_events(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_import_warning_tracking_outbox_snapshot
        CHECK (JSON_TYPE(bounded_snapshot) = 'OBJECT'),
    CONSTRAINT chk_import_warning_tracking_outbox_attempts CHECK (attempts >= 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_import_warning_occurrences_before_update;
CREATE TRIGGER trg_import_warning_occurrences_before_update
BEFORE UPDATE ON import_warning_occurrences
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'import_warning_occurrences records cannot be updated';

DROP TRIGGER IF EXISTS trg_import_warning_occurrences_before_delete;
CREATE TRIGGER trg_import_warning_occurrences_before_delete
BEFORE DELETE ON import_warning_occurrences
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'import_warning_occurrences records cannot be deleted';

DROP TRIGGER IF EXISTS trg_import_warning_tracking_events_before_update;
CREATE TRIGGER trg_import_warning_tracking_events_before_update
BEFORE UPDATE ON import_warning_tracking_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'import_warning_tracking_events records cannot be updated';

DROP TRIGGER IF EXISTS trg_import_warning_tracking_events_before_delete;
CREATE TRIGGER trg_import_warning_tracking_events_before_delete
BEFORE DELETE ON import_warning_tracking_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'import_warning_tracking_events records cannot be deleted';

DROP TRIGGER IF EXISTS trg_import_warning_resubmission_associations_before_update;
CREATE TRIGGER trg_import_warning_resubmission_associations_before_update
BEFORE UPDATE ON import_warning_resubmission_associations
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'import_warning_resubmission_associations records cannot be updated';

DROP TRIGGER IF EXISTS trg_import_warning_resubmission_associations_before_delete;
CREATE TRIGGER trg_import_warning_resubmission_associations_before_delete
BEFORE DELETE ON import_warning_resubmission_associations
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'import_warning_resubmission_associations records cannot be deleted';

DROP TRIGGER IF EXISTS trg_import_warning_tracking_receipts_before_update;
CREATE TRIGGER trg_import_warning_tracking_receipts_before_update
BEFORE UPDATE ON import_warning_tracking_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'import_warning_tracking_receipts records cannot be updated';

DROP TRIGGER IF EXISTS trg_import_warning_tracking_receipts_before_delete;
CREATE TRIGGER trg_import_warning_tracking_receipts_before_delete
BEFORE DELETE ON import_warning_tracking_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'import_warning_tracking_receipts records cannot be deleted';
-- END SOURCE: db/schema_parts/195_import_warning_tracking.sql

-- BEGIN SOURCE: db/schema_parts/196_case_import_partial_formal_case.sql
-- File: 196_case_import_partial_formal_case.sql
-- Description: 允許 HCM partial formal case 保存完整來源列而延後建立 case architecture bootstrap。

ALTER TABLE case_import_events
    MODIFY COLUMN bootstrap_event_id BIGINT NULL;

ALTER TABLE case_import_receipts
    MODIFY COLUMN bootstrap_event_id BIGINT NULL;
-- END SOURCE: db/schema_parts/196_case_import_partial_formal_case.sql

-- BEGIN SOURCE: db/schema_parts/197_client_beclass_transition_binding.sql
-- File: 197_client_beclass_transition_binding.sql
-- Description: 將唯一比對的 Client BeClass 來源記錄綁定 Client 與案件。

-- Client BeClass query_no is source provenance, not a Client or case identity.
ALTER TABLE beclass_records
    ADD COLUMN client_id INT NULL COMMENT '過渡期唯一比對後的 Client 綁定' AFTER query_no,
    ADD COLUMN bound_case_no VARCHAR(50) NULL COMMENT '過渡期唯一比對後的案件編號' AFTER client_id,
    ADD INDEX idx_beclass_client_case (client_id, bound_case_no),
    ADD CONSTRAINT fk_beclass_client
        FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE RESTRICT;
-- END SOURCE: db/schema_parts/197_client_beclass_transition_binding.sql

-- BEGIN SOURCE: db/schema_parts/198_case_import_pending_completion_status.sql
-- File: 198_case_import_pending_completion_status.sql
-- Description: 為 partial HCM formal case 新增待補件訂單狀態。

-- Partial HCM formal cases exist, but must not enter the service lifecycle before required fields are complete.
ALTER TABLE orders
    MODIFY COLUMN `status` ENUM('待補件', '洽談中', '訂單成立', '服務中', '訂單完成', '訂單取消')
    NOT NULL DEFAULT '洽談中'
    COMMENT '專案狀態；待補件案件不得進入服務生命週期';
-- END SOURCE: db/schema_parts/198_case_import_pending_completion_status.sql

-- BEGIN SOURCE: db/schema_parts/199_retire_finance_import_reclassification_events.sql
-- File: 199_retire_finance_import_reclassification_events.sql
-- Description: Fresh schema 不再建立已退役的 finance reclassification event 結構。

DROP TRIGGER IF EXISTS trg_finance_import_reclassification_events_before_update;
DROP TRIGGER IF EXISTS trg_finance_import_reclassification_events_before_delete;
DROP TABLE IF EXISTS finance_import_reclassification_events;
-- END SOURCE: db/schema_parts/199_retire_finance_import_reclassification_events.sql

-- BEGIN SOURCE: db/schema_parts/200_finance_import_source_reviews.sql
-- File: 200_finance_import_source_reviews.sql
-- Description: 新增 Finance 去敏來源列 review、批次 occurrence 與投影 outbox。

CREATE TABLE IF NOT EXISTS finance_import_source_reviews (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    review_identity VARCHAR(191) NOT NULL,
    source_content_digest CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    format_id ENUM('legacy', 'taishin', 'sinopac') NOT NULL,
    sheet_name VARCHAR(191) NOT NULL,
    source_row INT UNSIGNED NOT NULL,
    masked_source_identity VARCHAR(191) NOT NULL,
    issue_codes JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_finance_source_review_identity (review_identity),
    UNIQUE KEY uq_finance_source_review_source (
        source_content_digest, format_id, sheet_name, source_row
    ),
    INDEX idx_finance_source_review_location (format_id, sheet_name, source_row),
    CONSTRAINT chk_finance_source_review_digest
        CHECK (source_content_digest REGEXP '^[0-9a-f]{64}$'),
    CONSTRAINT chk_finance_source_review_row CHECK (source_row >= 1),
    CONSTRAINT chk_finance_source_review_issues
        CHECK (JSON_TYPE(issue_codes) = 'ARRAY' AND JSON_LENGTH(issue_codes) > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS finance_import_source_review_occurrences (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    batch_id BIGINT NOT NULL,
    review_id BIGINT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_finance_source_review_occurrence (batch_id, review_id),
    INDEX idx_finance_source_review_occurrence_review (review_id, id),
    CONSTRAINT fk_finance_source_review_occurrence_batch
        FOREIGN KEY (batch_id) REFERENCES finance_import_batches(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_finance_source_review_occurrence_review
        FOREIGN KEY (review_id) REFERENCES finance_import_source_reviews(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS finance_import_source_review_outbox (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    review_id BIGINT NOT NULL,
    intent_key VARCHAR(191) NOT NULL,
    published_at TIMESTAMP NULL,
    attempts INT UNSIGNED NOT NULL DEFAULT 0,
    last_error VARCHAR(1000) NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_finance_source_review_outbox_review (review_id),
    UNIQUE KEY uq_finance_source_review_outbox_intent (intent_key),
    INDEX idx_finance_source_review_outbox_pending (published_at, attempts, id),
    CONSTRAINT fk_finance_source_review_outbox_review
        FOREIGN KEY (review_id) REFERENCES finance_import_source_reviews(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_finance_source_review_outbox_attempts CHECK (attempts >= 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_finance_import_source_reviews_before_update;
CREATE TRIGGER trg_finance_import_source_reviews_before_update
BEFORE UPDATE ON finance_import_source_reviews
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'finance_import_source_reviews cannot be updated';

DROP TRIGGER IF EXISTS trg_finance_import_source_reviews_before_delete;
CREATE TRIGGER trg_finance_import_source_reviews_before_delete
BEFORE DELETE ON finance_import_source_reviews
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'finance_import_source_reviews cannot be deleted';

DROP TRIGGER IF EXISTS trg_finance_source_review_occurrences_before_update;
CREATE TRIGGER trg_finance_source_review_occurrences_before_update
BEFORE UPDATE ON finance_import_source_review_occurrences
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'finance_import_source_review_occurrences cannot be updated';

DROP TRIGGER IF EXISTS trg_finance_source_review_occurrences_before_delete;
CREATE TRIGGER trg_finance_source_review_occurrences_before_delete
BEFORE DELETE ON finance_import_source_review_occurrences
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'finance_import_source_review_occurrences cannot be deleted';
-- END SOURCE: db/schema_parts/200_finance_import_source_reviews.sql

-- BEGIN SOURCE: db/schema_parts/201_hcm_resubmission_corrections.sql
-- File: 201_hcm_resubmission_corrections.sql
-- Description: 新增 HCM 修正版來源的案件綁定、採納事件、receipt 與重掃 outbox。

CREATE TABLE IF NOT EXISTS case_import_hcm_review_case_bindings (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    binding_identity VARCHAR(191) NOT NULL,
    review_row_id BIGINT NOT NULL,
    case_no VARCHAR(50) NOT NULL,
    root_import_event_id BIGINT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_hcm_review_case_binding_identity (binding_identity),
    UNIQUE KEY uq_hcm_review_case_binding_review (review_row_id),
    INDEX idx_hcm_review_case_binding_case (case_no, id),
    CONSTRAINT fk_hcm_review_case_binding_review
        FOREIGN KEY (review_row_id) REFERENCES case_import_hcm_review_rows(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_hcm_review_case_binding_order
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_hcm_review_case_binding_import_event
        FOREIGN KEY (root_import_event_id) REFERENCES case_import_events(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS case_import_hcm_correction_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    event_identity VARCHAR(191) NOT NULL,
    case_no VARCHAR(50) NOT NULL,
    client_id INT NOT NULL,
    review_binding_id BIGINT NOT NULL,
    prior_occurrence_id BIGINT NOT NULL,
    source_event_identity VARCHAR(191) NOT NULL,
    source_fingerprint CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    candidate_fingerprint CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    adopted_field_paths JSON NOT NULL,
    root_before_fingerprint CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    root_after_fingerprint CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    actor VARCHAR(100) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_hcm_correction_event_identity (event_identity),
    UNIQUE KEY uq_hcm_correction_event_prior_source (prior_occurrence_id, source_event_identity),
    INDEX idx_hcm_correction_event_case (case_no, id),
    INDEX idx_hcm_correction_event_prior (prior_occurrence_id, id),
    CONSTRAINT fk_hcm_correction_event_order
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_hcm_correction_event_client
        FOREIGN KEY (client_id) REFERENCES clients(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_hcm_correction_event_binding
        FOREIGN KEY (review_binding_id) REFERENCES case_import_hcm_review_case_bindings(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_hcm_correction_event_occurrence
        FOREIGN KEY (prior_occurrence_id) REFERENCES import_warning_occurrences(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_hcm_correction_event_fingerprints
        CHECK (
            source_fingerprint REGEXP '^[0-9a-f]{64}$'
            AND candidate_fingerprint REGEXP '^[0-9a-f]{64}$'
            AND root_before_fingerprint REGEXP '^[0-9a-f]{64}$'
            AND root_after_fingerprint REGEXP '^[0-9a-f]{64}$'
        ),
    CONSTRAINT chk_hcm_correction_event_fields
        CHECK (JSON_TYPE(adopted_field_paths) = 'ARRAY' AND JSON_LENGTH(adopted_field_paths) > 0),
    CONSTRAINT chk_hcm_correction_event_text
        CHECK (
            CHAR_LENGTH(TRIM(actor)) > 0
            AND CHAR_LENGTH(TRIM(reason)) > 0
            AND CHAR_LENGTH(TRIM(correlation_id)) > 0
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS case_import_hcm_correction_receipts (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    idempotency_key VARCHAR(191) NOT NULL,
    command_fingerprint CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    preview_fingerprint CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    correction_event_id BIGINT NOT NULL,
    result_snapshot JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_hcm_correction_receipt_key (idempotency_key),
    UNIQUE KEY uq_hcm_correction_receipt_event (correction_event_id),
    CONSTRAINT fk_hcm_correction_receipt_event
        FOREIGN KEY (correction_event_id) REFERENCES case_import_hcm_correction_events(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_hcm_correction_receipt_fingerprints
        CHECK (
            command_fingerprint REGEXP '^[0-9a-f]{64}$'
            AND preview_fingerprint REGEXP '^[0-9a-f]{64}$'
        ),
    CONSTRAINT chk_hcm_correction_receipt_snapshot
        CHECK (JSON_TYPE(result_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS case_import_hcm_correction_outbox (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    correction_event_id BIGINT NOT NULL,
    intent_key VARCHAR(191) NOT NULL,
    bounded_snapshot JSON NOT NULL,
    published_at TIMESTAMP NULL,
    attempts INT UNSIGNED NOT NULL DEFAULT 0,
    last_error VARCHAR(500) NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_hcm_correction_outbox_event (correction_event_id),
    UNIQUE KEY uq_hcm_correction_outbox_intent (intent_key),
    INDEX idx_hcm_correction_outbox_pending (published_at, attempts, id),
    CONSTRAINT fk_hcm_correction_outbox_event
        FOREIGN KEY (correction_event_id) REFERENCES case_import_hcm_correction_events(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_hcm_correction_outbox_snapshot
        CHECK (JSON_TYPE(bounded_snapshot) = 'OBJECT'),
    CONSTRAINT chk_hcm_correction_outbox_attempts CHECK (attempts >= 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_hcm_review_case_bindings_before_update;
CREATE TRIGGER trg_hcm_review_case_bindings_before_update
BEFORE UPDATE ON case_import_hcm_review_case_bindings
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'case_import_hcm_review_case_bindings cannot be updated';

DROP TRIGGER IF EXISTS trg_hcm_review_case_bindings_before_delete;
CREATE TRIGGER trg_hcm_review_case_bindings_before_delete
BEFORE DELETE ON case_import_hcm_review_case_bindings
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'case_import_hcm_review_case_bindings cannot be deleted';

DROP TRIGGER IF EXISTS trg_hcm_correction_events_before_update;
CREATE TRIGGER trg_hcm_correction_events_before_update
BEFORE UPDATE ON case_import_hcm_correction_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'case_import_hcm_correction_events cannot be updated';

DROP TRIGGER IF EXISTS trg_hcm_correction_events_before_delete;
CREATE TRIGGER trg_hcm_correction_events_before_delete
BEFORE DELETE ON case_import_hcm_correction_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'case_import_hcm_correction_events cannot be deleted';

DROP TRIGGER IF EXISTS trg_hcm_correction_receipts_before_update;
CREATE TRIGGER trg_hcm_correction_receipts_before_update
BEFORE UPDATE ON case_import_hcm_correction_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'case_import_hcm_correction_receipts cannot be updated';

DROP TRIGGER IF EXISTS trg_hcm_correction_receipts_before_delete;
CREATE TRIGGER trg_hcm_correction_receipts_before_delete
BEFORE DELETE ON case_import_hcm_correction_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'case_import_hcm_correction_receipts cannot be deleted';
-- END SOURCE: db/schema_parts/201_hcm_resubmission_corrections.sql

-- BEGIN SOURCE: db/schema_parts/999_v_order_details_view.sql
-- 25. 訂單與帳務整合檢視表 (獨立拆分訂金與樓層費，並提供首筆應付加總)
CREATE OR REPLACE VIEW v_order_details AS
SELECT 
    o.case_no AS case_no,
    o.status AS order_status,
    o.lifecycle_version,
    o.cancel_reason,
    o.line_group_id,
    o.actual_start_date,
    o.actual_end_date,
    o.contract_identity,
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
    c.identity_status,
    o.floor_fee,           -- 樓層費用 (獨立顯示，生成契約用)
    o.deposit_date,
    o.start_date,
    o.end_date,
    
    -- 1. 時數計算
    (o.service_days * o.service_hours_per_day) AS total_hours,
    
    -- 2. 補助時數與自費時數
    CASE 
        WHEN c.identity_status = '一般市民' THEN 40
        WHEN c.identity_status = '補助市民' THEN 120
        ELSE 0 
    END AS subsidy_hours,
    
    GREATEST(0, (o.service_days * o.service_hours_per_day) - 
        CASE 
            WHEN c.identity_status = '一般市民' THEN 40
            WHEN c.identity_status = '補助市民' THEN 120
            ELSE 0 
        END
    ) AS self_pay_hours,
    
    -- 3. 雇主單價與訂金天數
    CASE 
        WHEN c.identity_status = '非市民' THEN 350
        ELSE 300 
    END AS employer_unit_price,
    
    CASE 
        WHEN c.identity_status = '補助市民' THEN 0
        ELSE 5 
    END AS deposit_days,
    
    -- 4. 純訂金金額 (獨立欄位，生成契約用)
    (CASE 
        WHEN c.identity_status = '補助市民' THEN 0
        ELSE 5 
    END * 
     CASE 
        WHEN c.identity_status = '非市民' THEN 350
        ELSE 300 
     END * 
     o.service_hours_per_day
    ) AS deposit_amount,
    
    -- 5. 首筆應付總額 = 純訂金 + 樓層費
    ((CASE 
        WHEN c.identity_status = '補助市民' THEN 0
        ELSE 5 
      END * 
      CASE 
        WHEN c.identity_status = '非市民' THEN 350
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
            GREATEST(0, o.service_days - CASE WHEN c.identity_status = '補助市民' THEN 0 ELSE 5 END)
        ELSE NULL 
    END AS remaining_days,
    
    CASE 
        WHEN o.status NOT IN ('洽談中', '訂單取消') THEN 
            LEAST(15, GREATEST(0, o.service_days - CASE WHEN c.identity_status = '補助市民' THEN 0 ELSE 5 END))
        ELSE NULL 
    END AS first_payment_days,
    
    CASE 
        WHEN o.status NOT IN ('洽談中', '訂單取消') THEN 
            LEAST(15, GREATEST(0, o.service_days - CASE WHEN c.identity_status = '補助市民' THEN 0 ELSE 5 END)) *
            o.service_hours_per_day * 
            CASE WHEN c.identity_status = '非市民' THEN 350 ELSE 300 END
        ELSE NULL 
    END AS first_payment_amount,
    
    CASE 
        WHEN o.status NOT IN ('洽談中', '訂單取消') AND 
             (o.service_days - CASE WHEN c.identity_status = '補助市民' THEN 0 ELSE 5 END - 15) > 0 THEN
            DATE_ADD(o.start_date, INTERVAL 15 DAY)
        ELSE NULL 
    END AS second_payment_date,
    
    CASE 
        WHEN o.status NOT IN ('洽談中', '訂單取消') THEN 
            GREATEST(0, o.service_days - CASE WHEN c.identity_status = '補助市民' THEN 0 ELSE 5 END - 15)
        ELSE NULL 
    END AS second_payment_days,
    
    CASE 
        WHEN o.status NOT IN ('洽談中', '訂單取消') THEN 
            GREATEST(0, o.service_days - CASE WHEN c.identity_status = '補助市民' THEN 0 ELSE 5 END - 15) *
            o.service_hours_per_day * 
            CASE WHEN c.identity_status = '非市民' THEN 350 ELSE 300 END
        ELSE NULL 
    END AS second_payment_amount,
    
    -- 7. 雇主自費合計金額 (首筆 + 後續款項之總和，若後續款項未計算則只包含首筆)
    (
      ((CASE WHEN c.identity_status = '補助市民' THEN 0 ELSE 5 END * CASE WHEN c.identity_status = '非市民' THEN 350 ELSE 300 END * o.service_hours_per_day) + COALESCE(o.floor_fee, 0)) +
      COALESCE(
        CASE 
            WHEN o.status NOT IN ('洽談中', '訂單取消') THEN 
                LEAST(15, GREATEST(0, o.service_days - CASE WHEN c.identity_status = '補助市民' THEN 0 ELSE 5 END)) *
                o.service_hours_per_day * 
                CASE WHEN c.identity_status = '非市民' THEN 350 ELSE 300 END
            ELSE 0 
        END, 0
      ) +
      COALESCE(
        CASE 
            WHEN o.status NOT IN ('洽談中', '訂單取消') THEN 
                GREATEST(0, o.service_days - CASE WHEN c.identity_status = '補助市民' THEN 0 ELSE 5 END - 15) *
                o.service_hours_per_day * 
                CASE WHEN c.identity_status = '非市民' THEN 350 ELSE 300 END
            ELSE 0 
        END, 0
      )
    ) AS total_employer_self_pay_payable,
    
    -- 8. 服務人員 (月嫂) 薪資與付款日計算
    CASE 
        WHEN c.identity_status = '一般市民' THEN 300
        WHEN c.identity_status = '補助市民' THEN 350
        ELSE 320 
    END AS service_unit_price,
    
    CASE 
        WHEN o.status NOT IN ('洽談中', '訂單取消') THEN 
            (o.service_days * o.service_hours_per_day) *
            CASE WHEN c.identity_status = '一般市民' THEN 300 WHEN c.identity_status = '補助市民' THEN 350 ELSE 320 END
        ELSE NULL 
    END AS service_salary, -- 月嫂純薪資；樓層費以 floor_fee 獨立顯示與支付
    
    CASE
        WHEN o.status NOT IN ('洽談中', '訂單取消') AND o.end_date IS NOT NULL
             AND c.identity_status = '補助市民' THEN
            DATE_ADD(LAST_DAY(DATE_ADD(o.end_date, INTERVAL 1 MONTH)), INTERVAL 15 DAY)
        WHEN o.status NOT IN ('洽談中', '訂單取消') AND o.end_date IS NOT NULL THEN
            DATE_ADD(LAST_DAY(o.end_date), INTERVAL 15 DAY)
        ELSE NULL 
    END AS salary_payment_date_1, -- 單次發薪：一般次月 15 日；補助市民次次月 15 日
    
    CASE 
        WHEN o.status NOT IN ('洽談中', '訂單取消') THEN 
            (CASE WHEN c.identity_status = '一般市民' THEN 40 WHEN c.identity_status = '補助市民' THEN 120 ELSE 0 END *
             CASE WHEN c.identity_status = '一般市民' THEN 300 WHEN c.identity_status = '補助市民' THEN 350 ELSE 320 END)
        ELSE NULL 
    END AS subsidy_salary,
    
    CASE 
        WHEN o.status NOT IN ('洽談中', '訂單取消') AND c.identity_status != '非市民' AND o.end_date IS NOT NULL THEN
            DATE_ADD(LAST_DAY(o.end_date), INTERVAL 5 DAY)
        ELSE NULL 
    END AS govt_claim_date
FROM orders o
JOIN clients c ON o.client_id = c.id
LEFT JOIN staff s ON o.staff_id = s.id;
-- END SOURCE: db/schema_parts/999_v_order_details_view.sql

-- BEGIN SOURCE: db/schema_parts/1000_staff_retirement.sql
-- File: 1000_staff_retirement.sql
-- Description: Staff lifecycle state、不可變事件與冪等 receipt。

CREATE TABLE IF NOT EXISTS staff_lifecycle_states (
    staff_id INT NOT NULL PRIMARY KEY,
    lifecycle_state ENUM('active','retired') NOT NULL DEFAULT 'active',
    aggregate_version BIGINT UNSIGNED NOT NULL DEFAULT 0,
    effective_at DATETIME(6) NULL,
    reason_code VARCHAR(64) NULL,
    updated_by VARCHAR(100) NULL,
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    CONSTRAINT fk_staff_lifecycle_state_staff FOREIGN KEY (staff_id) REFERENCES staff(id) ON DELETE RESTRICT,
    CONSTRAINT chk_staff_lifecycle_state_version CHECK (aggregate_version >= 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS staff_lifecycle_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    staff_id INT NOT NULL,
    event_type ENUM('retired','reactivated') NOT NULL,
    before_state ENUM('active','retired') NOT NULL,
    resulting_state ENUM('active','retired') NOT NULL,
    effective_at DATETIME(6) NOT NULL,
    reason_code VARCHAR(64) NOT NULL,
    expected_version BIGINT UNSIGNED NOT NULL,
    resulting_version BIGINT UNSIGNED NOT NULL,
    actor VARCHAR(100) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_staff_lifecycle_event_version (staff_id, resulting_version),
    INDEX idx_staff_lifecycle_event_time (staff_id, effective_at),
    CONSTRAINT fk_staff_lifecycle_event_staff FOREIGN KEY (staff_id) REFERENCES staff(id) ON DELETE RESTRICT,
    CONSTRAINT chk_staff_lifecycle_event_version CHECK (resulting_version = expected_version + 1)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS staff_lifecycle_apply_receipts (
    idempotency_key VARCHAR(191) NOT NULL PRIMARY KEY,
    command_fingerprint CHAR(64) NOT NULL,
    preview_fingerprint CHAR(64) NOT NULL,
    staff_id INT NOT NULL,
    resulting_state ENUM('active','retired') NOT NULL,
    resulting_version BIGINT UNSIGNED NOT NULL,
    event_id BIGINT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT fk_staff_lifecycle_receipt_staff FOREIGN KEY (staff_id) REFERENCES staff(id) ON DELETE RESTRICT,
    CONSTRAINT fk_staff_lifecycle_receipt_event FOREIGN KEY (event_id) REFERENCES staff_lifecycle_events(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
-- END SOURCE: db/schema_parts/1000_staff_retirement.sql

-- BEGIN SOURCE: db/schema_parts/1001_line_rich_menu_publication_step_saga.sql
-- File: 1001_line_rich_menu_publication_step_saga.sql
-- Description: Rich Menu 分步確認、provider 嘗試結果與 cleanup anomaly 的不可變保存契約。

-- Option B is additive. The legacy step-receipt table is intentionally retained
-- unchanged; this part has no data copy, seed, backfill, ALTER, or DROP.
CREATE TABLE IF NOT EXISTS line_rich_menu_publication_step_acknowledgements (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    publication_id BIGINT UNSIGNED NOT NULL,
    step_name ENUM('create','upload','link','switch','cleanup') NOT NULL,
    request_fingerprint CHAR(64) NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    provider_menu_id VARCHAR(191) NOT NULL,
    acknowledged_at_utc DATETIME(6) NOT NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_line_rich_menu_step_ack (publication_id, step_name),
    UNIQUE KEY uq_line_rich_menu_step_ack_idempotency (idempotency_key),
    INDEX idx_line_rich_menu_step_ack_publication (publication_id, id),
    CONSTRAINT fk_line_rich_menu_step_ack_publication
        FOREIGN KEY (publication_id) REFERENCES line_rich_menu_publication_tasks(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_line_rich_menu_step_ack_fingerprint
        CHECK (request_fingerprint REGEXP '^[0-9a-f]{64}$'),
    CONSTRAINT chk_line_rich_menu_step_ack_provider_id
        CHECK (CHAR_LENGTH(TRIM(provider_menu_id)) > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS line_rich_menu_publication_step_attempt_events (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    publication_id BIGINT UNSIGNED NOT NULL,
    step_name ENUM('create','upload','link','switch','cleanup') NOT NULL,
    attempt_number INT UNSIGNED NOT NULL,
    request_fingerprint CHAR(64) NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    outcome ENUM(
        'success','rate_limited','rejected','unavailable','timeout','lost_ack'
    ) NOT NULL,
    provider_menu_id VARCHAR(191) NULL,
    error_code VARCHAR(191) NULL,
    attempted_at_utc DATETIME(6) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_line_rich_menu_step_attempt (
        publication_id, step_name, attempt_number
    ),
    UNIQUE KEY uq_line_rich_menu_step_attempt_idempotency (idempotency_key),
    INDEX idx_line_rich_menu_step_attempt_publication (
        publication_id, step_name, attempt_number
    ),
    CONSTRAINT fk_line_rich_menu_step_attempt_publication
        FOREIGN KEY (publication_id) REFERENCES line_rich_menu_publication_tasks(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_line_rich_menu_step_attempt_number
        CHECK (attempt_number > 0),
    CONSTRAINT chk_line_rich_menu_step_attempt_fingerprint
        CHECK (request_fingerprint REGEXP '^[0-9a-f]{64}$'),
    CONSTRAINT chk_line_rich_menu_step_attempt_outcome
        CHECK (
            (outcome = 'success'
                AND provider_menu_id IS NOT NULL
                AND CHAR_LENGTH(TRIM(provider_menu_id)) > 0
                AND error_code IS NULL)
            OR
            (outcome <> 'success'
                AND provider_menu_id IS NULL
                AND error_code IS NOT NULL
                AND CHAR_LENGTH(TRIM(error_code)) > 0)
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS line_rich_menu_publication_cleanup_anomalies (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    publication_id BIGINT UNSIGNED NOT NULL,
    request_fingerprint CHAR(64) NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    error_code VARCHAR(191) NOT NULL,
    occurred_at_utc DATETIME(6) NOT NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_line_rich_menu_cleanup_anomaly_idempotency (idempotency_key),
    INDEX idx_line_rich_menu_cleanup_anomaly_publication (publication_id, id),
    CONSTRAINT fk_line_rich_menu_cleanup_anomaly_publication
        FOREIGN KEY (publication_id) REFERENCES line_rich_menu_publication_tasks(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_line_rich_menu_cleanup_anomaly_fingerprint
        CHECK (request_fingerprint REGEXP '^[0-9a-f]{64}$'),
    CONSTRAINT chk_line_rich_menu_cleanup_anomaly_error
        CHECK (CHAR_LENGTH(TRIM(error_code)) > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_line_rich_menu_step_ack_before_update;
CREATE TRIGGER trg_line_rich_menu_step_ack_before_update
BEFORE UPDATE ON line_rich_menu_publication_step_acknowledgements
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_rich_menu_publication_step_acknowledgements records cannot be updated';

DROP TRIGGER IF EXISTS trg_line_rich_menu_step_ack_before_delete;
CREATE TRIGGER trg_line_rich_menu_step_ack_before_delete
BEFORE DELETE ON line_rich_menu_publication_step_acknowledgements
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_rich_menu_publication_step_acknowledgements records cannot be deleted';

DROP TRIGGER IF EXISTS trg_line_rich_menu_step_attempt_before_update;
CREATE TRIGGER trg_line_rich_menu_step_attempt_before_update
BEFORE UPDATE ON line_rich_menu_publication_step_attempt_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_rich_menu_publication_step_attempt_events records cannot be updated';

DROP TRIGGER IF EXISTS trg_line_rich_menu_step_attempt_before_delete;
CREATE TRIGGER trg_line_rich_menu_step_attempt_before_delete
BEFORE DELETE ON line_rich_menu_publication_step_attempt_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_rich_menu_publication_step_attempt_events records cannot be deleted';

DROP TRIGGER IF EXISTS trg_line_rich_menu_cleanup_anomaly_before_update;
CREATE TRIGGER trg_line_rich_menu_cleanup_anomaly_before_update
BEFORE UPDATE ON line_rich_menu_publication_cleanup_anomalies
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_rich_menu_publication_cleanup_anomalies records cannot be updated';

DROP TRIGGER IF EXISTS trg_line_rich_menu_cleanup_anomaly_before_delete;
CREATE TRIGGER trg_line_rich_menu_cleanup_anomaly_before_delete
BEFORE DELETE ON line_rich_menu_publication_cleanup_anomalies
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_rich_menu_publication_cleanup_anomalies records cannot be deleted';
-- END SOURCE: db/schema_parts/1001_line_rich_menu_publication_step_saga.sql

-- BEGIN SOURCE: db/schema_parts/1002_customer_service_human_escalation.sql
-- File: 1002_customer_service_human_escalation.sql
-- Description: Customer Service HIGH escalation 與不可變事件的 additive schema。

-- M4-DB is additive only. It does not alter, seed, backfill, or remove any
-- existing Customer Service, LINE, anomaly, runtime, or scheduling object.
CREATE TABLE IF NOT EXISTS customer_service_escalations (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    source_event_identity VARCHAR(191) NOT NULL,
    source_kind VARCHAR(64) NOT NULL,
    source_fingerprint CHAR(64) NOT NULL,
    trigger_code ENUM(
        'explicit_human_request',
        'explicit_wrong_answer',
        'binding_failure_threshold_2',
        'complaint',
        'runtime_critical'
    ) NOT NULL,
    trigger_policy_version VARCHAR(191) NOT NULL,
    ticket_id BIGINT NOT NULL,
    ticket_category ENUM(
        'service_flow',
        'payment_subsidy',
        'service_progress',
        'profile_update',
        'contact_union',
        'other'
    ) NOT NULL,
    urgency ENUM('high') NOT NULL DEFAULT 'high',
    workflow_status ENUM('open','claimed','handling','resolved') NOT NULL DEFAULT 'open',
    workflow_version BIGINT NOT NULL DEFAULT 0,
    hold_scope_ref VARCHAR(191) NOT NULL,
    automation_hold_state ENUM('active','released') NOT NULL DEFAULT 'active',
    hold_version BIGINT NOT NULL DEFAULT 0,
    actor_ref VARCHAR(191) NOT NULL,
    claim_at_utc DATETIME(6) NULL,
    handling_started_at_utc DATETIME(6) NULL,
    resolved_at_utc DATETIME(6) NULL,
    resolution_code VARCHAR(64) NULL,
    resolution_evidence_digest CHAR(64) NULL,
    masked_context JSON NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    masked_alert_intent_ref VARCHAR(191) NULL,
    delivery_task_ref VARCHAR(191) NULL,
    delivery_outcome_ref VARCHAR(191) NULL,
    alert_status ENUM('pending','queued','sent','failed','unknown') NOT NULL DEFAULT 'pending',
    active_hold_scope_key VARCHAR(191)
        GENERATED ALWAYS AS (
            CASE WHEN automation_hold_state = 'active' THEN hold_scope_ref ELSE NULL END
        ) STORED,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_customer_service_escalation_source (source_event_identity),
    UNIQUE KEY uq_customer_service_escalation_idempotency (idempotency_key),
    UNIQUE KEY uq_customer_service_escalation_active_scope (active_hold_scope_key),
    INDEX idx_customer_service_escalation_ticket (ticket_id, id),
    INDEX idx_customer_service_escalation_status_time (workflow_status, updated_at_utc),
    INDEX idx_customer_service_escalation_trigger_time (trigger_code, created_at_utc),
    CONSTRAINT fk_customer_service_escalation_ticket
        FOREIGN KEY (ticket_id) REFERENCES customer_service_tickets(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_customer_service_escalation_source_fingerprint
        CHECK (source_fingerprint REGEXP '^[0-9a-f]{64}$'),
    CONSTRAINT chk_customer_service_escalation_source_kind
        CHECK (CHAR_LENGTH(TRIM(source_kind)) > 0),
    CONSTRAINT chk_customer_service_escalation_policy_version
        CHECK (CHAR_LENGTH(TRIM(trigger_policy_version)) > 0),
    CONSTRAINT chk_customer_service_escalation_scope
        CHECK (CHAR_LENGTH(TRIM(hold_scope_ref)) > 0),
    CONSTRAINT chk_customer_service_escalation_actor
        CHECK (CHAR_LENGTH(TRIM(actor_ref)) > 0),
    CONSTRAINT chk_customer_service_escalation_identities
        CHECK (
            CHAR_LENGTH(TRIM(idempotency_key)) > 0
            AND CHAR_LENGTH(TRIM(correlation_id)) > 0
        ),
    CONSTRAINT chk_customer_service_escalation_hold_state
        CHECK (
            (workflow_status = 'resolved' AND automation_hold_state = 'released')
            OR (workflow_status <> 'resolved' AND automation_hold_state = 'active')
        ),
    CONSTRAINT chk_customer_service_escalation_resolution
        CHECK (
            workflow_status <> 'resolved'
            OR (
                resolution_code IS NOT NULL
                AND resolution_evidence_digest IS NOT NULL
                AND
                CHAR_LENGTH(TRIM(resolution_code)) > 0
                AND resolution_evidence_digest REGEXP '^[0-9a-f]{64}$'
            )
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS customer_service_escalation_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    escalation_id BIGINT NOT NULL,
    event_type ENUM('created','claimed','handling_started','resolved','hold_released') NOT NULL,
    expected_escalation_version BIGINT NOT NULL,
    resulting_escalation_version BIGINT NOT NULL,
    expected_ticket_version BIGINT NULL,
    resulting_ticket_version BIGINT NULL,
    expected_hold_version BIGINT NOT NULL,
    resulting_hold_version BIGINT NOT NULL,
    actor_ref VARCHAR(191) NOT NULL,
    reason_code VARCHAR(64) NOT NULL,
    reason_evidence_digest CHAR(64) NOT NULL,
    receipt_id VARCHAR(191) NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_customer_service_escalation_event_receipt (receipt_id),
    UNIQUE KEY uq_customer_service_escalation_event_idempotency (idempotency_key),
    INDEX idx_customer_service_escalation_event_stream (escalation_id, id),
    INDEX idx_customer_service_escalation_event_type_time (event_type, created_at_utc),
    CONSTRAINT fk_customer_service_escalation_event_escalation
        FOREIGN KEY (escalation_id) REFERENCES customer_service_escalations(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_customer_service_escalation_event_versions
        CHECK (
            resulting_escalation_version >= expected_escalation_version
            AND resulting_hold_version >= expected_hold_version
            AND (
                expected_ticket_version IS NULL
                OR resulting_ticket_version IS NOT NULL
            )
        ),
    CONSTRAINT chk_customer_service_escalation_event_actor
        CHECK (CHAR_LENGTH(TRIM(actor_ref)) > 0),
    CONSTRAINT chk_customer_service_escalation_event_reason
        CHECK (
            CHAR_LENGTH(TRIM(reason_code)) > 0
            AND reason_evidence_digest REGEXP '^[0-9a-f]{64}$'
        ),
    CONSTRAINT chk_customer_service_escalation_event_identities
        CHECK (
            CHAR_LENGTH(TRIM(receipt_id)) > 0
            AND CHAR_LENGTH(TRIM(idempotency_key)) > 0
            AND CHAR_LENGTH(TRIM(correlation_id)) > 0
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_customer_service_escalation_events_before_update;
CREATE TRIGGER trg_customer_service_escalation_events_before_update
BEFORE UPDATE ON customer_service_escalation_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'customer_service_escalation_events records cannot be updated';

DROP TRIGGER IF EXISTS trg_customer_service_escalation_events_before_delete;
CREATE TRIGGER trg_customer_service_escalation_events_before_delete
BEFORE DELETE ON customer_service_escalation_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'customer_service_escalation_events records cannot be deleted';
-- END SOURCE: db/schema_parts/1002_customer_service_human_escalation.sql

-- BEGIN SOURCE: db/schema_parts/1003_matching_coordination_successor.sql
-- File: 1003_matching_coordination_successor.sql
-- Description: 保存 M3 不可變條件、方案血緣、事件、收據與 typed outbox。

-- Additive M3 persistence only.  These tables do not copy or write any
-- Orders, Assignment, Leave, Scheduling, Payroll, or LINE provider root.
CREATE TABLE IF NOT EXISTS matching_coordination_criteria_snapshots (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    snapshot_id VARCHAR(191) NOT NULL,
    case_no VARCHAR(50) NOT NULL,
    criteria_version BIGINT UNSIGNED NOT NULL,
    criteria_snapshot JSON NOT NULL,
    source_version_tuple JSON NOT NULL,
    criteria_digest CHAR(64) NOT NULL,
    actor_ref VARCHAR(191) NOT NULL,
    occurred_at_utc DATETIME(6) NOT NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_matching_criteria_snapshot_id (snapshot_id),
    UNIQUE KEY uq_matching_criteria_case_version (case_no, criteria_version),
    INDEX idx_matching_criteria_case_time (case_no, created_at_utc),
    CONSTRAINT chk_matching_criteria_identity CHECK (
        CHAR_LENGTH(TRIM(snapshot_id)) > 0 AND CHAR_LENGTH(TRIM(case_no)) > 0
    ),
    CONSTRAINT chk_matching_criteria_payload CHECK (
        JSON_TYPE(criteria_snapshot) = 'OBJECT' AND JSON_LENGTH(criteria_snapshot) > 0
    ),
    CONSTRAINT chk_matching_criteria_sources CHECK (
        JSON_TYPE(source_version_tuple) = 'ARRAY' AND JSON_LENGTH(source_version_tuple) > 0
    ),
    CONSTRAINT chk_matching_criteria_digest CHECK (criteria_digest REGEXP '^[0-9a-f]{64}$'),
    CONSTRAINT chk_matching_criteria_actor CHECK (CHAR_LENGTH(TRIM(actor_ref)) > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS matching_coordination_package_lineage (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    package_id VARCHAR(191) NOT NULL,
    case_no VARCHAR(50) NOT NULL,
    criteria_snapshot_id BIGINT UNSIGNED NOT NULL,
    parent_package_id BIGINT UNSIGNED NULL,
    package_version BIGINT UNSIGNED NOT NULL,
    lineage_kind ENUM('initial','criteria_diff','rematch','alternative') NOT NULL,
    package_state ENUM(
        'candidate_pool_open','proposed','awaiting_caregiver_willingness',
        'awaiting_customer_decision','no_candidate','alternative_previewed',
        'alternative_applied','no_candidate_terminal','accepted','declined',
        'expired','rematch_required','superseded'
    ) NOT NULL,
    package_snapshot JSON NOT NULL,
    source_version_tuple JSON NOT NULL,
    package_digest CHAR(64) NOT NULL,
    actor_ref VARCHAR(191) NOT NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_matching_package_id (package_id),
    UNIQUE KEY uq_matching_package_case_version (case_no, package_version),
    INDEX idx_matching_package_criteria (criteria_snapshot_id, id),
    INDEX idx_matching_package_parent (parent_package_id, id),
    INDEX idx_matching_package_state_time (package_state, created_at_utc),
    CONSTRAINT fk_matching_package_criteria FOREIGN KEY (criteria_snapshot_id)
        REFERENCES matching_coordination_criteria_snapshots(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_matching_package_parent FOREIGN KEY (parent_package_id)
        REFERENCES matching_coordination_package_lineage(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_matching_package_identity CHECK (
        CHAR_LENGTH(TRIM(package_id)) > 0 AND CHAR_LENGTH(TRIM(case_no)) > 0
    ),
    CONSTRAINT chk_matching_package_payload CHECK (
        JSON_TYPE(package_snapshot) = 'OBJECT' AND JSON_LENGTH(package_snapshot) > 0
    ),
    CONSTRAINT chk_matching_package_sources CHECK (
        JSON_TYPE(source_version_tuple) = 'ARRAY' AND JSON_LENGTH(source_version_tuple) > 0
    ),
    CONSTRAINT chk_matching_package_digest CHECK (package_digest REGEXP '^[0-9a-f]{64}$'),
    CONSTRAINT chk_matching_package_actor CHECK (CHAR_LENGTH(TRIM(actor_ref)) > 0),
    CONSTRAINT chk_matching_package_parent CHECK (
        (lineage_kind = 'initial' AND parent_package_id IS NULL)
        OR (lineage_kind <> 'initial' AND parent_package_id IS NOT NULL)
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS matching_coordination_events (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    event_id VARCHAR(191) NOT NULL,
    case_no VARCHAR(50) NOT NULL,
    criteria_snapshot_id BIGINT UNSIGNED NOT NULL,
    package_lineage_id BIGINT UNSIGNED NULL,
    event_type ENUM(
        'criteria_snapshotted','package_proposed','candidate_contacted',
        'caregiver_willingness','customer_decision','criteria_diff',
        'rematch_required','conversion_requested','stale','superseded'
    ) NOT NULL,
    expected_version BIGINT UNSIGNED NOT NULL,
    resulting_version BIGINT UNSIGNED NOT NULL,
    event_payload JSON NOT NULL,
    source_version_tuple JSON NOT NULL,
    event_digest CHAR(64) NOT NULL,
    actor_ref VARCHAR(191) NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    occurred_at_utc DATETIME(6) NOT NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_matching_event_id (event_id),
    UNIQUE KEY uq_matching_event_idempotency (idempotency_key),
    INDEX idx_matching_event_case_time (case_no, id),
    INDEX idx_matching_event_criteria (criteria_snapshot_id, id),
    INDEX idx_matching_event_package_time (package_lineage_id, id),
    INDEX idx_matching_event_type_time (event_type, created_at_utc),
    CONSTRAINT fk_matching_event_criteria FOREIGN KEY (criteria_snapshot_id)
        REFERENCES matching_coordination_criteria_snapshots(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_matching_event_package FOREIGN KEY (package_lineage_id)
        REFERENCES matching_coordination_package_lineage(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_matching_event_identity CHECK (
        CHAR_LENGTH(TRIM(event_id)) > 0 AND CHAR_LENGTH(TRIM(case_no)) > 0
        AND CHAR_LENGTH(TRIM(idempotency_key)) > 0
        AND CHAR_LENGTH(TRIM(correlation_id)) > 0
    ),
    CONSTRAINT chk_matching_event_payload CHECK (
        JSON_TYPE(event_payload) = 'OBJECT' AND JSON_LENGTH(event_payload) > 0
    ),
    CONSTRAINT chk_matching_event_sources CHECK (
        JSON_TYPE(source_version_tuple) = 'ARRAY' AND JSON_LENGTH(source_version_tuple) > 0
    ),
    CONSTRAINT chk_matching_event_versions CHECK (resulting_version >= expected_version),
    CONSTRAINT chk_matching_event_digest CHECK (event_digest REGEXP '^[0-9a-f]{64}$'),
    CONSTRAINT chk_matching_event_actor CHECK (CHAR_LENGTH(TRIM(actor_ref)) > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS matching_coordination_apply_receipts (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    receipt_id VARCHAR(191) NOT NULL,
    case_no VARCHAR(50) NOT NULL,
    event_id BIGINT UNSIGNED NOT NULL,
    criteria_snapshot_id BIGINT UNSIGNED NOT NULL,
    package_lineage_id BIGINT UNSIGNED NULL,
    command_name VARCHAR(96) NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    command_fingerprint CHAR(64) NOT NULL,
    preview_fingerprint CHAR(64) NULL,
    source_version_tuple JSON NOT NULL,
    result_snapshot JSON NOT NULL,
    outcome_state ENUM('applied','replayed','rematch_required','rejected_as_stale','conflict') NOT NULL,
    actor_ref VARCHAR(191) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    applied_at_utc DATETIME(6) NOT NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_matching_receipt_id (receipt_id),
    UNIQUE KEY uq_matching_receipt_idempotency (idempotency_key),
    INDEX idx_matching_receipt_event (event_id, id),
    INDEX idx_matching_receipt_criteria (criteria_snapshot_id, id),
    INDEX idx_matching_receipt_package (package_lineage_id, id),
    INDEX idx_matching_receipt_outcome_time (outcome_state, created_at_utc),
    CONSTRAINT fk_matching_receipt_event FOREIGN KEY (event_id)
        REFERENCES matching_coordination_events(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_matching_receipt_criteria FOREIGN KEY (criteria_snapshot_id)
        REFERENCES matching_coordination_criteria_snapshots(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_matching_receipt_package FOREIGN KEY (package_lineage_id)
        REFERENCES matching_coordination_package_lineage(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_matching_receipt_identity CHECK (
        CHAR_LENGTH(TRIM(receipt_id)) > 0 AND CHAR_LENGTH(TRIM(command_name)) > 0
        AND CHAR_LENGTH(TRIM(idempotency_key)) > 0 AND CHAR_LENGTH(TRIM(actor_ref)) > 0
        AND CHAR_LENGTH(TRIM(correlation_id)) > 0
    ),
    CONSTRAINT chk_matching_receipt_fingerprints CHECK (
        command_fingerprint REGEXP '^[0-9a-f]{64}$'
        AND (preview_fingerprint IS NULL OR preview_fingerprint REGEXP '^[0-9a-f]{64}$')
    ),
    CONSTRAINT chk_matching_receipt_sources CHECK (
        JSON_TYPE(source_version_tuple) = 'ARRAY' AND JSON_LENGTH(source_version_tuple) > 0
    ),
    CONSTRAINT chk_matching_receipt_result CHECK (
        JSON_TYPE(result_snapshot) = 'OBJECT' AND JSON_LENGTH(result_snapshot) > 0
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS matching_coordination_outbox (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    reference_id VARCHAR(191) NOT NULL,
    event_id BIGINT UNSIGNED NOT NULL,
    receipt_id BIGINT UNSIGNED NOT NULL,
    case_no VARCHAR(50) NOT NULL,
    intent_type ENUM(
        'line_matching_interaction','line_criteria_diff_resend',
        'assignment_conversion_requested','rematch_requested',
        'orders_terms_update_requested'
    ) NOT NULL,
    target_owner ENUM('line_integration','assignment_workflow','orders_workflow') NOT NULL,
    intent_payload JSON NOT NULL,
    source_version_tuple JSON NOT NULL,
    reference_digest CHAR(64) NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_matching_outbox_reference_id (reference_id),
    UNIQUE KEY uq_matching_outbox_idempotency (idempotency_key),
    INDEX idx_matching_outbox_event (event_id, id),
    INDEX idx_matching_outbox_receipt (receipt_id, id),
    INDEX idx_matching_outbox_created_time (created_at_utc, id),
    INDEX idx_matching_outbox_case (case_no, id),
    CONSTRAINT fk_matching_outbox_event FOREIGN KEY (event_id)
        REFERENCES matching_coordination_events(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_matching_outbox_receipt FOREIGN KEY (receipt_id)
        REFERENCES matching_coordination_apply_receipts(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_matching_outbox_identity CHECK (
        CHAR_LENGTH(TRIM(reference_id)) > 0 AND CHAR_LENGTH(TRIM(case_no)) > 0
        AND CHAR_LENGTH(TRIM(idempotency_key)) > 0 AND CHAR_LENGTH(TRIM(correlation_id)) > 0
    ),
    CONSTRAINT chk_matching_outbox_target CHECK (
        (intent_type IN ('line_matching_interaction','line_criteria_diff_resend')
            AND target_owner = 'line_integration')
        OR (intent_type IN ('assignment_conversion_requested','rematch_requested')
            AND target_owner = 'assignment_workflow')
        OR (intent_type = 'orders_terms_update_requested'
            AND target_owner = 'orders_workflow')
    ),
    CONSTRAINT chk_matching_outbox_payload CHECK (
        JSON_TYPE(intent_payload) = 'OBJECT' AND JSON_LENGTH(intent_payload) > 0
    ),
    CONSTRAINT chk_matching_outbox_sources CHECK (
        JSON_TYPE(source_version_tuple) = 'ARRAY' AND JSON_LENGTH(source_version_tuple) > 0
    ),
    CONSTRAINT chk_matching_outbox_digest CHECK (reference_digest REGEXP '^[0-9a-f]{64}$')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_matching_criteria_snapshots_before_update;
CREATE TRIGGER trg_matching_criteria_snapshots_before_update
BEFORE UPDATE ON matching_coordination_criteria_snapshots
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'matching_coordination_criteria_snapshots records cannot be updated';
DROP TRIGGER IF EXISTS trg_matching_criteria_snapshots_before_delete;
CREATE TRIGGER trg_matching_criteria_snapshots_before_delete
BEFORE DELETE ON matching_coordination_criteria_snapshots
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'matching_coordination_criteria_snapshots records cannot be deleted';

DROP TRIGGER IF EXISTS trg_matching_package_lineage_before_update;
CREATE TRIGGER trg_matching_package_lineage_before_update
BEFORE UPDATE ON matching_coordination_package_lineage
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'matching_coordination_package_lineage records cannot be updated';
DROP TRIGGER IF EXISTS trg_matching_package_lineage_before_delete;
CREATE TRIGGER trg_matching_package_lineage_before_delete
BEFORE DELETE ON matching_coordination_package_lineage
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'matching_coordination_package_lineage records cannot be deleted';

DROP TRIGGER IF EXISTS trg_matching_coordination_events_before_update;
CREATE TRIGGER trg_matching_coordination_events_before_update
BEFORE UPDATE ON matching_coordination_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'matching_coordination_events records cannot be updated';
DROP TRIGGER IF EXISTS trg_matching_coordination_events_before_delete;
CREATE TRIGGER trg_matching_coordination_events_before_delete
BEFORE DELETE ON matching_coordination_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'matching_coordination_events records cannot be deleted';

DROP TRIGGER IF EXISTS trg_matching_apply_receipts_before_update;
CREATE TRIGGER trg_matching_apply_receipts_before_update
BEFORE UPDATE ON matching_coordination_apply_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'matching_coordination_apply_receipts records cannot be updated';
DROP TRIGGER IF EXISTS trg_matching_apply_receipts_before_delete;
CREATE TRIGGER trg_matching_apply_receipts_before_delete
BEFORE DELETE ON matching_coordination_apply_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'matching_coordination_apply_receipts records cannot be deleted';

DROP TRIGGER IF EXISTS trg_matching_outbox_before_update;
CREATE TRIGGER trg_matching_outbox_before_update
BEFORE UPDATE ON matching_coordination_outbox
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'matching_coordination_outbox records cannot be updated';
DROP TRIGGER IF EXISTS trg_matching_outbox_before_delete;
CREATE TRIGGER trg_matching_outbox_before_delete
BEFORE DELETE ON matching_coordination_outbox
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'matching_coordination_outbox records cannot be deleted';
-- END SOURCE: db/schema_parts/1003_matching_coordination_successor.sql

-- BEGIN SOURCE: db/schema_parts/1004_controlled_file_storage_foundation.sql
-- File: 1004_controlled_file_storage_foundation.sql
-- Description: 建立受控檔案 staging、版本、Apply、cleanup 與 reconciliation 的 additive schema。

CREATE TABLE IF NOT EXISTS controlled_file_staging_objects (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    staging_id VARCHAR(64) NOT NULL,
    storage_locator VARCHAR(500) NOT NULL,
    owner_type ENUM(
        'contract_signing', 'scheduling', 'orders', 'staff', 'line_integration'
    ) NOT NULL,
    subject_reference VARCHAR(191) NOT NULL,
    object_key VARCHAR(191) NOT NULL,
    purpose ENUM(
        'final_signed_contract', 'service_date_confirmation', 'baby_log_photo',
        'meal_photo', 'order_notice', 'staff_resume', 'staff_certificate',
        'staff_health_exam', 'rich_menu_background'
    ) NOT NULL,
    logical_folder VARCHAR(500) NOT NULL,
    original_filename VARCHAR(255) NOT NULL,
    content_type VARCHAR(100) NOT NULL,
    size_bytes BIGINT UNSIGNED NOT NULL,
    content_sha256 CHAR(64) NOT NULL,
    staging_state ENUM('staged', 'applied', 'quarantined', 'cleaned')
        NOT NULL DEFAULT 'staged',
    staging_version BIGINT UNSIGNED NOT NULL DEFAULT 1,
    idempotency_key VARCHAR(191) NOT NULL,
    command_fingerprint CHAR(64) NOT NULL,
    created_by_actor VARCHAR(191) NOT NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    expires_at_utc DATETIME(6) NOT NULL,
    applied_at_utc DATETIME(6) NULL,
    cleaned_at_utc DATETIME(6) NULL,
    UNIQUE KEY uq_controlled_file_staging_id (staging_id),
    UNIQUE KEY uq_controlled_file_staging_locator (storage_locator),
    UNIQUE KEY uq_controlled_file_staging_idempotency (idempotency_key),
    INDEX idx_controlled_file_staging_owner (
        owner_type, subject_reference, purpose, staging_state, id
    ),
    INDEX idx_controlled_file_staging_cleanup (
        staging_state, expires_at_utc, id
    ),
    CONSTRAINT chk_controlled_file_staging_identity CHECK (
        staging_id REGEXP '^cfs_[0-9a-f]{32}$'
        AND CHAR_LENGTH(TRIM(storage_locator)) > 0
        AND CHAR_LENGTH(TRIM(subject_reference)) > 0
        AND CHAR_LENGTH(TRIM(object_key)) > 0
        AND CHAR_LENGTH(TRIM(purpose)) > 0
        AND CHAR_LENGTH(TRIM(original_filename)) > 0
        AND CHAR_LENGTH(TRIM(content_type)) > 0
        AND idempotency_key REGEXP '^[a-z0-9][a-z0-9._:-]{0,190}$'
        AND CHAR_LENGTH(TRIM(created_by_actor)) > 0
        AND size_bytes > 0
        AND expires_at_utc > created_at_utc
    ),
    CONSTRAINT chk_controlled_file_staging_digest CHECK (
        content_sha256 REGEXP '^[0-9a-f]{64}$'
        AND command_fingerprint REGEXP '^[0-9a-f]{64}$'
    ),
    CONSTRAINT chk_controlled_file_staging_owner_purpose CHECK (
        (owner_type = 'contract_signing' AND purpose = 'final_signed_contract')
        OR (owner_type = 'scheduling' AND purpose IN (
            'service_date_confirmation', 'baby_log_photo', 'meal_photo'
        ))
        OR (owner_type = 'orders' AND purpose = 'order_notice')
        OR (owner_type = 'staff' AND purpose IN (
            'staff_resume', 'staff_certificate', 'staff_health_exam'
        ))
        OR (owner_type = 'line_integration' AND purpose = 'rich_menu_background')
    ),
    CONSTRAINT chk_controlled_file_staging_state CHECK (
        (staging_state = 'applied' AND applied_at_utc IS NOT NULL AND cleaned_at_utc IS NULL)
        OR (staging_state = 'cleaned' AND applied_at_utc IS NULL AND cleaned_at_utc IS NOT NULL)
        OR (staging_state IN ('staged', 'quarantined')
            AND applied_at_utc IS NULL AND cleaned_at_utc IS NULL)
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS controlled_file_objects (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    opaque_object_id VARCHAR(64) NOT NULL,
    source_staging_id BIGINT UNSIGNED NOT NULL,
    owner_type ENUM(
        'contract_signing', 'scheduling', 'orders', 'staff', 'line_integration'
    ) NOT NULL,
    subject_reference VARCHAR(191) NOT NULL,
    object_key VARCHAR(191) NOT NULL,
    purpose ENUM(
        'final_signed_contract', 'service_date_confirmation', 'baby_log_photo',
        'meal_photo', 'order_notice', 'staff_resume', 'staff_certificate',
        'staff_health_exam', 'rich_menu_background'
    ) NOT NULL,
    logical_folder VARCHAR(500) NOT NULL,
    filename VARCHAR(255) NOT NULL,
    storage_locator VARCHAR(500) NOT NULL,
    content_type VARCHAR(100) NOT NULL,
    size_bytes BIGINT UNSIGNED NOT NULL,
    content_sha256 CHAR(64) NOT NULL,
    version_number BIGINT UNSIGNED NOT NULL,
    supersedes_object_id BIGINT UNSIGNED NULL,
    supersedes_version_number BIGINT UNSIGNED NULL,
    created_by_actor VARCHAR(191) NOT NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_controlled_file_object_id (opaque_object_id),
    UNIQUE KEY uq_controlled_file_object_staging (source_staging_id),
    UNIQUE KEY uq_controlled_file_object_locator (storage_locator),
    UNIQUE KEY uq_controlled_file_owner_version (
        owner_type, subject_reference, object_key, version_number
    ),
    UNIQUE KEY uq_controlled_file_version_identity (
        id, owner_type, subject_reference, object_key, purpose, version_number
    ),
    INDEX idx_controlled_file_object_owner (
        owner_type, subject_reference, purpose, id
    ),
    INDEX idx_controlled_file_object_supersedes (supersedes_object_id, id),
    CONSTRAINT fk_controlled_file_object_staging FOREIGN KEY (source_staging_id)
        REFERENCES controlled_file_staging_objects(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_controlled_file_object_supersedes FOREIGN KEY (
        supersedes_object_id, owner_type, subject_reference, object_key,
        purpose, supersedes_version_number
    ) REFERENCES controlled_file_objects (
        id, owner_type, subject_reference, object_key, purpose, version_number
    )
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_controlled_file_object_identity CHECK (
        opaque_object_id REGEXP '^cf_[0-9a-f]{32}$'
        AND CHAR_LENGTH(TRIM(subject_reference)) > 0
        AND CHAR_LENGTH(TRIM(object_key)) > 0
        AND CHAR_LENGTH(TRIM(purpose)) > 0
        AND CHAR_LENGTH(TRIM(filename)) > 0
        AND CHAR_LENGTH(TRIM(storage_locator)) > 0
        AND CHAR_LENGTH(TRIM(content_type)) > 0
        AND CHAR_LENGTH(TRIM(created_by_actor)) > 0
        AND size_bytes > 0
        AND version_number > 0
    ),
    CONSTRAINT chk_controlled_file_object_digest CHECK (
        content_sha256 REGEXP '^[0-9a-f]{64}$'
    ),
    CONSTRAINT chk_controlled_file_object_chain CHECK (
        (supersedes_object_id IS NULL
            AND supersedes_version_number IS NULL AND version_number = 1)
        OR (supersedes_object_id IS NOT NULL
            AND supersedes_version_number IS NOT NULL
            AND version_number = supersedes_version_number + 1)
    ),
    CONSTRAINT chk_controlled_file_object_owner_purpose CHECK (
        (owner_type = 'contract_signing' AND purpose = 'final_signed_contract')
        OR (owner_type = 'scheduling' AND purpose IN (
            'service_date_confirmation', 'baby_log_photo', 'meal_photo'
        ))
        OR (owner_type = 'orders' AND purpose = 'order_notice')
        OR (owner_type = 'staff' AND purpose IN (
            'staff_resume', 'staff_certificate', 'staff_health_exam'
        ))
        OR (owner_type = 'line_integration' AND purpose = 'rich_menu_background')
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS controlled_file_apply_receipts (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    receipt_id VARCHAR(64) NOT NULL,
    staging_object_id BIGINT UNSIGNED NOT NULL,
    controlled_object_id BIGINT UNSIGNED NOT NULL,
    command_type ENUM('controlled_file_apply') NOT NULL,
    schema_version ENUM('controlled-file-apply-receipt.v1') NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    command_fingerprint CHAR(64) NOT NULL,
    preview_fingerprint CHAR(64) NOT NULL,
    expected_staging_version BIGINT UNSIGNED NOT NULL,
    result_snapshot JSON NOT NULL,
    outcome_state ENUM('created') NOT NULL DEFAULT 'created',
    actor_ref VARCHAR(191) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    applied_at_utc DATETIME(6) NOT NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_controlled_file_receipt_id (receipt_id),
    UNIQUE KEY uq_controlled_file_receipt_idempotency (idempotency_key),
    UNIQUE KEY uq_controlled_file_receipt_staging (staging_object_id),
    UNIQUE KEY uq_controlled_file_receipt_object (controlled_object_id),
    CONSTRAINT fk_controlled_file_receipt_staging FOREIGN KEY (staging_object_id)
        REFERENCES controlled_file_staging_objects(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_controlled_file_receipt_object FOREIGN KEY (controlled_object_id)
        REFERENCES controlled_file_objects(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_controlled_file_receipt_identity CHECK (
        receipt_id REGEXP '^cfr_[0-9a-f]{32}$'
        AND idempotency_key REGEXP '^[a-z0-9][a-z0-9._:-]{0,190}$'
        AND CHAR_LENGTH(TRIM(actor_ref)) > 0
        AND CHAR_LENGTH(TRIM(correlation_id)) > 0
        AND expected_staging_version > 0
    ),
    CONSTRAINT chk_controlled_file_receipt_fingerprints CHECK (
        command_fingerprint REGEXP '^[0-9a-f]{64}$'
        AND preview_fingerprint REGEXP '^[0-9a-f]{64}$'
    ),
    CONSTRAINT chk_controlled_file_receipt_result CHECK (
        JSON_TYPE(result_snapshot) = 'OBJECT'
        AND JSON_LENGTH(result_snapshot) > 0
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS controlled_file_reconciliation_events (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    event_id VARCHAR(64) NOT NULL,
    staging_object_id BIGINT UNSIGNED NULL,
    controlled_object_id BIGINT UNSIGNED NULL,
    outcome ENUM(
        'exact', 'missing_object', 'digest_mismatch', 'orphan_object', 'still_writing'
    ) NOT NULL,
    observation_fingerprint CHAR(64) NOT NULL,
    observed_sha256 CHAR(64) NULL,
    observed_size_bytes BIGINT UNSIGNED NULL,
    observation_snapshot JSON NOT NULL,
    actor_ref VARCHAR(191) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    observed_at_utc DATETIME(6) NOT NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_controlled_file_reconciliation_event (event_id),
    UNIQUE KEY uq_controlled_file_reconciliation_fingerprint (observation_fingerprint),
    INDEX idx_controlled_file_reconciliation_staging (staging_object_id, id),
    INDEX idx_controlled_file_reconciliation_object (controlled_object_id, id),
    INDEX idx_controlled_file_reconciliation_outcome (outcome, observed_at_utc, id),
    CONSTRAINT fk_controlled_file_reconciliation_staging FOREIGN KEY (staging_object_id)
        REFERENCES controlled_file_staging_objects(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_controlled_file_reconciliation_object FOREIGN KEY (controlled_object_id)
        REFERENCES controlled_file_objects(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_controlled_file_reconciliation_identity CHECK (
        event_id REGEXP '^cfe_[0-9a-f]{32}$'
        AND observation_fingerprint REGEXP '^[0-9a-f]{64}$'
        AND CHAR_LENGTH(TRIM(actor_ref)) > 0
        AND CHAR_LENGTH(TRIM(correlation_id)) > 0
        AND (
            (outcome IN ('exact', 'missing_object', 'digest_mismatch')
                AND controlled_object_id IS NOT NULL)
            OR (outcome IN ('orphan_object', 'still_writing')
                AND staging_object_id IS NOT NULL AND controlled_object_id IS NULL)
        )
    ),
    CONSTRAINT chk_controlled_file_reconciliation_observation CHECK (
        (outcome IN ('exact', 'digest_mismatch')
            AND observed_sha256 REGEXP '^[0-9a-f]{64}$'
            AND observed_size_bytes IS NOT NULL)
        OR (outcome = 'missing_object'
            AND observed_sha256 IS NULL AND observed_size_bytes IS NULL)
        OR (outcome IN ('orphan_object', 'still_writing')
            AND (observed_sha256 IS NULL
                OR observed_sha256 REGEXP '^[0-9a-f]{64}$'))
    ),
    CONSTRAINT chk_controlled_file_reconciliation_snapshot CHECK (
        JSON_TYPE(observation_snapshot) = 'OBJECT'
        AND JSON_LENGTH(observation_snapshot) > 0
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS controlled_file_cleanup_events (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    cleanup_id VARCHAR(64) NOT NULL,
    event_id VARCHAR(64) NOT NULL,
    staging_object_id BIGINT UNSIGNED NOT NULL,
    event_sequence TINYINT UNSIGNED NOT NULL,
    event_type ENUM('intent', 'completed', 'reconciliation_required') NOT NULL,
    reason ENUM('expired', 'abandoned') NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    command_fingerprint CHAR(64) NOT NULL,
    expected_staging_version BIGINT UNSIGNED NOT NULL,
    expected_sha256 CHAR(64) NOT NULL,
    actor_ref VARCHAR(191) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    occurred_at_utc DATETIME(6) NOT NULL,
    error_code VARCHAR(100) NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_controlled_file_cleanup_event (event_id),
    UNIQUE KEY uq_controlled_file_cleanup_sequence (cleanup_id, event_sequence),
    UNIQUE KEY uq_controlled_file_cleanup_idempotency_sequence (
        idempotency_key, event_sequence
    ),
    INDEX idx_controlled_file_cleanup_staging (
        staging_object_id, event_sequence, id
    ),
    INDEX idx_controlled_file_cleanup_terminal (
        event_type, occurred_at_utc, id
    ),
    CONSTRAINT fk_controlled_file_cleanup_staging FOREIGN KEY (staging_object_id)
        REFERENCES controlled_file_staging_objects(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_controlled_file_cleanup_identity CHECK (
        cleanup_id REGEXP '^cfc_[0-9a-f]{32}$'
        AND event_id REGEXP '^cfce_[0-9a-f]{32}$'
        AND idempotency_key REGEXP '^[a-z0-9][a-z0-9._:-]{0,190}$'
        AND command_fingerprint REGEXP '^[0-9a-f]{64}$'
        AND expected_staging_version > 0
        AND expected_sha256 REGEXP '^[0-9a-f]{64}$'
        AND CHAR_LENGTH(TRIM(actor_ref)) > 0
        AND CHAR_LENGTH(TRIM(correlation_id)) > 0
    ),
    CONSTRAINT chk_controlled_file_cleanup_event CHECK (
        (event_sequence = 1 AND event_type = 'intent' AND error_code IS NULL)
        OR (event_sequence = 2 AND event_type = 'completed' AND error_code IS NULL)
        OR (event_sequence = 2
            AND event_type = 'reconciliation_required'
            AND error_code IS NOT NULL
            AND CHAR_LENGTH(TRIM(error_code)) > 0)
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_controlled_file_objects_before_update;
CREATE TRIGGER trg_controlled_file_objects_before_update
BEFORE UPDATE ON controlled_file_objects FOR EACH ROW
SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'controlled_file_objects records cannot be updated';

DROP TRIGGER IF EXISTS trg_controlled_file_objects_before_delete;
CREATE TRIGGER trg_controlled_file_objects_before_delete
BEFORE DELETE ON controlled_file_objects FOR EACH ROW
SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'controlled_file_objects records cannot be deleted';

DROP TRIGGER IF EXISTS trg_controlled_file_apply_receipts_before_update;
CREATE TRIGGER trg_controlled_file_apply_receipts_before_update
BEFORE UPDATE ON controlled_file_apply_receipts FOR EACH ROW
SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'controlled_file_apply_receipts records cannot be updated';

DROP TRIGGER IF EXISTS trg_controlled_file_apply_receipts_before_delete;
CREATE TRIGGER trg_controlled_file_apply_receipts_before_delete
BEFORE DELETE ON controlled_file_apply_receipts FOR EACH ROW
SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'controlled_file_apply_receipts records cannot be deleted';

DROP TRIGGER IF EXISTS trg_controlled_file_reconciliation_events_before_update;
CREATE TRIGGER trg_controlled_file_reconciliation_events_before_update
BEFORE UPDATE ON controlled_file_reconciliation_events FOR EACH ROW
SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'controlled_file_reconciliation_events records cannot be updated';

DROP TRIGGER IF EXISTS trg_controlled_file_reconciliation_events_before_delete;
CREATE TRIGGER trg_controlled_file_reconciliation_events_before_delete
BEFORE DELETE ON controlled_file_reconciliation_events FOR EACH ROW
SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'controlled_file_reconciliation_events records cannot be deleted';

DROP TRIGGER IF EXISTS trg_controlled_file_cleanup_events_before_update;
CREATE TRIGGER trg_controlled_file_cleanup_events_before_update
BEFORE UPDATE ON controlled_file_cleanup_events FOR EACH ROW
SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'controlled_file_cleanup_events records cannot be updated';

DROP TRIGGER IF EXISTS trg_controlled_file_cleanup_events_before_delete;
CREATE TRIGGER trg_controlled_file_cleanup_events_before_delete
BEFORE DELETE ON controlled_file_cleanup_events FOR EACH ROW
SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'controlled_file_cleanup_events records cannot be deleted';
-- END SOURCE: db/schema_parts/1004_controlled_file_storage_foundation.sql
