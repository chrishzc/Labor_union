-- 1. 建立唯讀使用者帳號 (將 'readonly_password' 替換為您自訂的安全密碼)
CREATE USER IF NOT EXISTS 'metabase_reader'@'%' IDENTIFIED BY 'readonly_password';

-- 2. 僅授予對 union_db 資料庫的 SELECT 權限
GRANT SELECT ON union_db.* TO 'metabase_reader'@'%';

-- 3. 重新整理權限使其立即生效
FLUSH PRIVILEGES;

-- 4. 驗證權限指令（可選執行，確認權限是否正確授予）
SHOW GRANTS FOR 'metabase_reader'@'%';
