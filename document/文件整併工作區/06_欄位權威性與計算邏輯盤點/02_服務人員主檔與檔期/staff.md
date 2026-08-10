# `staff` 欄位權威性與計算邏輯盤點

- 狀態：討論與裁決用工作清冊；不是 SSOT，不代表 CP-1、Task 或實作核准。
- 分類：`02_服務人員主檔與檔期`
- 總索引：[06_欄位權威性與計算邏輯盤點](../../06_欄位權威性與計算邏輯盤點.md)
- 第一遍（live 現況）：已完成
- 第二遍（衍生判定）：已完成
- 根事實展開：已完成
- 規格反查：已完成

- Schema：`db/schema.sql`
- 父表關係：無已宣告外鍵
- 子表關係：`staff_regions`, `staff_weekly_rest`, `staff_cooking_skills`, `staff_baby_types`, `staff_time_slots`, `staff_transportation`, `staff_bank_accounts`, `staff_availability` 等多項 1:N 關聯（完整清單見下或 schema）。
- 已確認跨表裁決：關於月嫂的進階偏好（區域、休假、胎數、技能等），統一將「1:N 子表」視為唯一的 SSOT（Single Source of Truth）；本主表內的 JSON 及對應數值欄位（`weekly_rest_days`, `service_regions`, `special_skills`, `care_babies`）因架構重疊 (Schema Drift)，已標記為遺留／待移除。

| 欄位 | Schema 定義 | 現況架構／用途 | 初步分類 | 現況公式 | 直接來源 | 第一層根事實 | 建議權威公式 | 修改命令／Owner | 重算觸發 | 凍結邊界 | 現況漂移／風險 | 裁決 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `id` | `INT AUTO_INCREMENT PRIMARY KEY` | 月嫂主檔技術主鍵；供資料庫關聯使用。 | 技術識別／關聯鍵 | DB 自增。 | DB INSERT。 | 資料庫列建立。 | 不得被 UI 任意修改；各種子表（如排班、訂單等）以此建立技術關聯。 | DB／Repository | INSERT | 不變。 | 應確保與外部識別（身分證）一對一。 | 已確認：技術主鍵 |
| `registered_at` | `DATETIME COMMENT '報名時間'` | BeClass 報名時間。 | 來源事實 | 不計算。 | 匯入資料。 | 原始報名時間。 | 保留原值，供歷史稽核；不是實際上線或媒合的時間。 | HCM import | 匯入 | 不應一般覆寫 | 格式需確保不受時區漂移影響。 | 已確認 |
| `ip_address` | `VARCHAR(45) COMMENT '註冊IP'` | 原始報名 IP 稽核資料。 | 敏感遺留資料／待移除 | 不計算。 | 匯入來源。 | 原始報名網路位置。 | 長期考慮移除；無媒合或排班權威。若需資安追查應轉移至稽核日誌。 | HCM import | 匯入 | 無 | 無業務讀取；增加敏感資料暴露。 | 已確認：長期考慮移除 |
| `name` | `VARCHAR(100) NOT NULL COMMENT '姓名'` | 月嫂姓名。 | 來源事實 | 不計算。 | HCM 匯入／Data Browser。 | 月嫂登錄與授權修正資料。 | 基本客資；可更正，但不可在無稽核下改動。 | HCM import／Data Browser | 匯入、授權修正 | 可變 | 無 | 已確認 |
| `identity_card` | `VARCHAR(20) UNIQUE COMMENT '身分證字號'` | 身分證字號，匯入時的去重識別碼。 | 來源事實／唯一識別 | 不計算。 | HCM 匯入。 | 官方身分證明。 | 系統去重 SSOT。建立後原則上不可任意改動，錯誤應由特殊程序更正。 | HCM import／Admin | 匯入、特殊更正 | 建立後不可一般修改 | 個資保護需求高。 | 已確認：匯入去重鍵 |
| `phone` | `VARCHAR(20) COMMENT '行動電話'` | 行動電話。 | 來源事實 | 不計算。 | HCM 匯入／Data Browser。 | 月嫂登錄與授權修正資料。 | 基本聯絡資料，不參與媒合計算。 | HCM import／Data Browser | 匯入、授權修正 | 可變 | 匯入時已經過正規化處理。 | 已確認 |
| `tel` | `VARCHAR(20) COMMENT '市話'` | 市話。 | 來源事實 | 不計算。 | HCM 匯入／Data Browser。 | 月嫂登錄與授權修正資料。 | 聯絡資料。 | HCM import／Data Browser | 匯入、授權修正 | 可變 | 無 | 已確認 |
| `tel_ext` | `VARCHAR(10) COMMENT '分機'` | 市話分機。 | 來源事實 | 不計算。 | HCM 匯入／Data Browser。 | 月嫂登錄與授權修正資料。 | 聯絡資料。 | HCM import／Data Browser | 匯入、授權修正 | 可變 | 無 | 已確認 |
| `email` | `VARCHAR(100) COMMENT 'EMAIL'` | 電子郵件。 | 來源事實 | 不計算。 | HCM 匯入／Data Browser。 | 月嫂登錄與授權修正資料。 | 聯絡資料。 | HCM import／Data Browser | 匯入、授權修正 | 可變 | 無 | 已確認 |
| `birthday` | `DATE COMMENT '生日 (由民國生日整合)'` | 生日。 | 來源事實 | 依民國/西元轉換公式。 | HCM 匯入／Data Browser。 | 月嫂登錄資料。 | 僅為客資，不直接驅動業務。 | HCM import／Data Browser | 匯入、授權修正 | 可變 | 日期轉換容易出錯，匯入時已處理。 | 已確認 |
| `city` | `VARCHAR(50) COMMENT '居住縣市'` | 居住縣市。 | 來源事實 | 不計算。 | HCM 匯入／Data Browser。 | 月嫂登錄資料。 | 僅為居住地客資；實際「接案區域」判定應以 `staff_regions` 為 SSOT。 | HCM import／Data Browser | 匯入、授權修正 | 可變 | 容易與 `staff_regions` (接案區域) 混淆，需釐清僅為居住地。 | 已確認 |
| `zip_code` | `VARCHAR(10) COMMENT '郵遞區號'` | 居住郵遞區號。 | 來源事實 | 不計算。 | HCM 匯入／Data Browser。 | 月嫂登錄資料。 | 聯絡資料。 | HCM import／Data Browser | 匯入、授權修正 | 可變 | 無 | 已確認 |
| `address` | `VARCHAR(255) COMMENT '詳細地址'` | 詳細地址。 | 來源事實 | 不計算。 | HCM 匯入／Data Browser。 | 月嫂登錄資料。 | 聯絡資料。 | HCM import／Data Browser | 匯入、授權修正 | 可變 | 無 | 已確認 |
| `has_massage_cert` | `BOOLEAN DEFAULT FALSE COMMENT '有嬰幼兒按摩證書嗎'` | 嬰幼兒按摩證書。 | 來源事實／專業資格 | 不計算。 | HCM 匯入／審核。 | 官方資格認證。 | 媒合過濾條件之一。 | HCM import／Admin | 匯入、資格審核 | 資格變更時可變 | 無 | 已確認 |
| `status` | `VARCHAR(20) DEFAULT 'active' COMMENT '在職狀態'` | 在職狀態 (active/inactive)。 | 衍生狀態／控制 | 依管理決策設定。 | Admin / Data Browser。 | 管理端任用決策。 | 影響派案與媒合過濾的最上層門檻。 | Admin | 管理操作 | 可變 | 應確保 inactive 時不再產生新排班或新媒合推薦。 | 已確認 |
| `line_user_id` | `VARCHAR(100) COMMENT 'LINE 平台用戶唯一識別碼'` | LINE 平台帳號綁定。 | 來源事實／外部帳號 | 不計算。 | LINE webhook／審核綁定。 | 平台 webhook 所得帳號。 | 發送通知的技術憑證；允許可與 `clients` 表的 line_user_id 重疊（同人身兼兩角），通知時依事件角色發送。 | LINE service | 綁定操作 | 可變 | 無 | 已確認 |
| `weekly_rest_days` | `JSON COMMENT '固定休假偏好 JSON 陣列'` | 遺留 JSON；曾被誤當作月嫂實際每週休假日。 | 重複資料／待移除 | 不應參與排班計算。 | 歷史或遺留程式寫入。 | 無；月嫂可接受排休方案以 `staff_weekly_rest` 多列為唯一來源。 | 月嫂可同時接受多種方案，不能合併推導成其實際休假星期。媒合時只檢查訂單的固定排休規則是否落在其可接受集合；正式排班只依訂單條款，不讀本欄位。 | 無 | 停用 | 凍結 | 現況排班／指派路徑仍讀此 JSON，會錯把「可接受選項」轉成月嫂實際休假日，必須移除。 | 已確認：長期考慮移除；不得用於排休 |
| `care_babies` | `INT DEFAULT 1 COMMENT '最大可照顧寶寶數量'` | 遺留的最大胎數數字；不能完整表示月嫂可接受的寶寶類型集合。 | 重複資料／待移除 | 不應參與媒合或排班計算。 | 歷史或遺留程式寫入。 | 無；可承接類型以 `staff_baby_types` 多列為唯一來源。 | 媒合依 `staff_baby_types` 判斷：月嫂勾選雙胞胎即同時可承接雙胞胎與單胞胎；單胞胎僅涵蓋單胞胎；其他類型必須有明確對應值。不得以本數字反推資格。 | 無 | 停用 | 凍結 | 現況媒合仍以本欄位數字拒絕雙胞胎，會與子表裁決衝突，必須移除。 | 已確認：長期考慮移除；不得用於媒合 |
| `service_regions` | `JSON COMMENT '接受服務區域 JSON 陣列'` | 遺留的服務區域 JSON。 | 重複資料／待移除 | 不應參與媒合或排班計算。 | 歷史或遺留程式寫入。 | 無；可服務區域以 `staff_regions` 多列為唯一來源。 | 月嫂搬家等資格變更直接更新 `staff_regions` 集合；媒合僅讀子表，不能把本欄位與子表合併或回寫。 | 無 | 停用 | 凍結 | 現況媒合仍合併本 JSON 與子表，且 Data Browser 可直接改，會產生錯誤候選，必須移除。 | 已確認：長期考慮移除；不得用於媒合 |
| `special_skills` | `JSON COMMENT '特殊技能與偏好標籤 JSON 陣列'` | 遺留技能／偏好 JSON。 | 重複資料／待移除 | 不應參與媒合或計算。 | 歷史或遺留程式寫入。 | 無；料理技能以 `staff_cooking_skills` 多列為唯一來源。 | `staff_cooking_skills` 命中客戶需求時僅提高候選分數，不命中仍可列入候選；不得以本 JSON 輸入、加分或淘汰。 | 無 | 停用 | 凍結 | 現況 Data Browser 可直接改本欄位，子表卻唯讀，且 matcher 尚未讀取技能，與裁決相反。 | 已確認：長期考慮移除；不得用於媒合 |
| `created_at` | `TIMESTAMP DEFAULT CURRENT_TIMESTAMP` | DB 建立時間。 | 技術中繼資料 | DB `CURRENT_TIMESTAMP` | DB INSERT | DB 執行時間。 | 僅供技術稽核與除錯；不得當作業務生效時間。 | DB | INSERT | 不變 | 無 | 已確認：技術時間 |
| `updated_at` | `TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP` | DB 更新時間。 | 技術中繼資料 | DB `ON UPDATE` | DB UPDATE | DB 執行時間。 | 僅供技術除錯；任何更新皆會變動。 | DB | UPDATE | 可變 | 無 | 已確認：技術時間 |
