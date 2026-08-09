# `finance_import_batches` 欄位權威性與計算邏輯盤點

- 狀態：討論與裁決用工作清冊；不是 SSOT，不代表 CP-1、Task 或實作核准。
- 分類：`07_財務匯入與警示`
- 總索引：[06_欄位權威性與計算邏輯盤點](../../06_欄位權威性與計算邏輯盤點.md)
- 第一遍（live 現況）：已完成
- 第二遍（衍生判定）：已完成
- 根事實展開：已完成
- 規格反查：已完成

- Schema：`db/schema_parts/60_finance_import_staging.sql`
- 父表關係：無
- 子表關係：`finance_import_occurrences`
- 已確認跨表裁決：本表為**財務 Excel 匯入批次 (Header)**。每次會計人員上傳銀行對帳單 (Excel/CSV) 時，系統會建立一個批次，用來追蹤檔案處理狀態與錯誤紀錄。這是一切後續「對帳、警告、重新分類」的起點。

| 欄位 | Schema 定義 | 現況架構／用途 | 初步分類 | 現況公式 | 直接來源 | 第一層根事實 | 建議權威公式 | 修改命令／Owner | 重算觸發 | 凍結邊界 | 現況漂移／風險 | 裁決 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `id` | `BIGINT AUTO_INCREMENT PRIMARY KEY` | 技術主鍵。 | 系統鍵 | 不計算。 | DB 自增。 | 匯入操作事實。 | 無。 | Import Service | 無 | 不變 | 無 | 已確認：SSOT 鍵 |
| `format_id` | `ENUM('legacy', 'taishin', 'sinopac') NOT NULL` | 本批匯入採用的對帳資料來源格式：歷史紀錄、台新對帳單或永豐對帳單。 | 正規化來源格式快照 | 由 workbook normalizer 依來源與版型判定。 | normalized result。 | 被解析的對帳資料來源格式。 | 保留作本批 parser 格式快照；`legacy` 雖是獨立歷史格式，其銀行來源仍為永豐。不得由 caller 任意指定。 | Finance Normalizer／Import Service | 建立 batch | 建立後不變 | caller 若當成純銀行 enum 會誤讀 legacy。 | 已確認：沿用三種來源格式語意 |
| `source_file` | `VARCHAR(1024) NULL` | 匯入當時的來源檔案路徑稽核快照；目前實作儲存絕對路徑，畫面僅取檔名顯示。 | 技術稽核事實（不具檔案內容或業務權威性） | 不計算；不得作為檔案身分、去重、fingerprint 或帳務判斷依據。 | Import Application 解析後的 `source_path`。 | 匯入主機上的來源絕對路徑。 | 保留實際來源路徑作操作稽核；同一檔案在不同主機或目錄可有不同值，不代表不同帳務資料。 | Import Service | 建立 batch | commit 後不變 | 把主機路徑誤當成檔案內容身分，導致跨主機或搬移後產生錯誤去重。 | 已確認：保留作來源路徑稽核快照；畫面只顯示檔名，不具業務權威性 |
| `sheet_name` | `VARCHAR(191) NOT NULL` | 工作表名稱。 | 來源事實 | 不計算。 | 上傳檔案。 | 工作表名。 | 無。 | Import Service | 無 | 不變 | 無 | 已確認 |
| `header_row` | `INT UNSIGNED NOT NULL` | 標題列列號。 | 來源事實 | 不計算。 | 解析邏輯。 | 解析參數。 | 必須 `>= 1`。 | Import Service | 無 | 不變 | 無 | 已確認 |
| `row_count` | `INT UNSIGNED NOT NULL DEFAULT 0` | 本批正規化資料列總數。 | 衍生摘要／長期考慮移除 | `COUNT(finance_import_occurrences WHERE batch_id = 本批次)`；包含命中既有 canonical fingerprint 的重複流水 occurrence。 | `len(normalized_rows)`。 | 本批每一筆成功建立的 occurrence。 | 不具獨立權威性；長期考慮移除，需要時直接計算 occurrences。過渡期由 Service 計算且必須與 occurrence count 相同，不得由 caller 指定。 | Import Service（過渡期） | 建立 batch／occurrences | commit 後不變 | 與 occurrence 明細形成兩套答案。 | 已確認：衍生摘要，長期考慮移除 |
| `status` | `ENUM('staged','completed','failed') NOT NULL DEFAULT 'staged'` | 匯入批次處理狀態的相容欄位；原子 transaction 下只有 completed row 會持久存在。 | 單值相容投影／長期考慮移除 | transaction 內 INSERT staged，全部處理成功後 UPDATE completed 再 commit；任何失敗整筆 rollback。 | Import Application Service。 | completed batch row 是否存在。 | 沿用目前原子匯入，不拆 durable job；持久資料中 row 存在即代表 completed。本欄長期考慮移除，不新增 staged／failed 的持久狀態機。 | Import Application Service（過渡期） | 同一 transaction 完成匯入 | commit 後不變 | Schema 看似三態，但 production 不會留下 staged／failed row。 | 已確認：原子匯入，單值相容欄位長期移除 |
| `failure_message` | `TEXT NULL` | 原本預留給 failed batch 的錯誤訊息；原子 rollback 模型下不會持久存在。 | 停用欄位／長期考慮移除 | production 完成時設 NULL；失敗時整個 batch rollback。 | 無持久來源。 | 操作例外／錯誤回應與 log。 | 停止作持久狀態來源並長期考慮移除；匯入失敗由錯誤回應及操作 log 記錄，不為此拆分 transaction。 | 無新 owner | 停用 | 維持 NULL | Schema 暗示會保存 failed reason，但 production 無法留下該 row。 | 已確認：停止寫入、長期考慮移除 |
| `created_at` | `TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP` | batch row 在匯入 transaction 中建立的技術時間。 | 技術建立時間 | DB default。 | batch INSERT。 | DB 接受 batch row 的時點。 | 保留作稽核與處理耗時起點；不代表銀行交易日、檔案產生日或帳務歸屬日。 | DB／Import Service | 建立 batch | 建立後不變 | transaction rollback 時本列與時間都不存在。 | 已確認：沿用技術建立時間規則 |
| `completed_at` | `TIMESTAMP NULL` | batch 全部 staging、dispatch 與 Alert 投影完成的技術時間。 | 技術完成時間 | 成功 UPDATE 時取 DB `CURRENT_TIMESTAMP`。 | Import Application Service。 | 同一匯入 transaction 完成全部處理。 | 成功完成時寫入；只表示匯入處理完成，不代表每筆銀行流水均正式核銷。 | Import Application Service | 完成匯入 | 成功後不變 | 現況失敗會 rollback 整個 batch，因此沒有對應 failed completed time。 | 已確認：保留技術完成時間 |
