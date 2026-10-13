# 月嫂清單與公會自訂編號工作包

Authority：2026-10-13 使用者要求主頁改清單、人工輸入公會編號；後續指定禁止完整重複、允許英數組合。正式語意：規格 33 §3.2。Owner：Staff Profile；schema release 由 Global Migration 擁有。本包供本次實作及本機 migration 驗收使用，驗收完成後不擴張任務。

範圍：StaffPage 主頁全部個資、聯絡與銀行主檔的表格／搜尋／詳情選取；新增 authenticated bounded `/staff/roster` 批次唯讀 Query，沿用既有 Staff Profile 欄位與 reader 權限，摘要 selector 保留；既有 Profile 編輯與 Q/P/A；Staff `union_no` nullable 文字欄位與 binary unique index；typed query、相關 focused tests、fresh／preserve release chain 與 metadata descriptor。四個詳情分頁本次保留。主頁另納入服務能力與接案資料的八個欄位，沿用 Qualification-owned 七 relation 與 care_babies；資格證照與接案狀態保留詳情。

Change inventory：schema-only；source 為現有 staff，target 為新增 union_no 與 uq_staff_union_no。既有 rows 保持 NULL，不推測、回填或變更 staff.id。Fresh 使用 part 231，preserve 使用 part 1050。absent 可套用、exact 可重播、partial／drift 阻擋；rollback 在 switch 前丟棄本包建立的 candidate，套用後保留欄位並使用相容 forward release。不執行 system seed、business backfill、destructive 操作。

驗收：表格取代主頁卡片，桌面／窄畫面可使用；整列及鍵盤開詳情。人工儲存 `A001` 保留文字及前導零，主頁立即回讀，跨頁搜尋可找到公會編號；`A001` 重複失敗、`a001`／`001` 可獨立保存，多位未設定合法。Preview 零寫入、stale typed 409、Apply 競爭由 unique index 關閉並完整 rollback。Focused UI／owner／migration tests、build、實際畫面、MySQL fresh／preserve evidence 與 diff check。

效果上限：新增程式／規格／schema release；DB engine 驗證限本包唯一 lu_test_staff_union_* databases、合成資料及正式 writer。資格驗證後，以既有 local additive updater 對 localhost development `union_db` 只套用 part 1050，先保存備份、plan 與 receipt，不修改既有人員業務值。未授權 production、provider、deployment、cutover、reset、source replacement 或 entry switch。

本機操作：先執行 `.venv/Scripts/python.exe -m scripts.update_local_database --dry-run`。資格來源為 `validation/receipts/PROV-STAFF-UNION-NUMBER-local-additive-qualification-20261013.json`；確認只待套 part 1050，再使用 `--apply --strategy additive --confirm-database union_db`，不使用 replacement／switch／reset。若 target、schema metadata 或 qualified identity 漂移，停止 apply 並重新計畫。

交付：對話及 scratch/staff-union-number/ 保留 focused 測試與 DB gate evidence；若必要 engine gate 未通過，回報 DB_CHANGE_NOT_READY。

## 目前驗收

| DB gate | 狀態 | Evidence |
|---|---|---|
| Scope | PASS | 本包與規格 33 §3.2；使用者指定完整個資／聯絡／銀行主檔 |
| Change inventory | PASS | 本包 schema-only inventory；無 seed／backfill／destructive effect |
| Static release | PASS | `scratch/staff-union-number/backend-tests.log`；fresh assembly、preserve chain、hash 與 descriptor 契約通過 |
| Descriptor | PASS | `contract/test_staff_union_number_schema.py`；absent／exact／partial／drift，包含 binary collation 與唯一索引 |
| Read-only plan | PASS | `scratch/staff-union-number/local-plan.log`；qualified latest release ready，只待 part 1050 |
| Engine verification | PASS | `engine-bootstrap.log`、`engine-preserve.log`、`engine-qualification.log`；真 MySQL fresh、source dump→candidate→apply→verify；`business-result.json` 保護字串唯一性與併發 rollback |
| Developer acceptance | PASS | `local-apply.log` 回報 current；`development-readback.log` 確認 localhost development `union_db` 的欄位／索引 exact 且完整主檔 Query 成功；source backup evidence：`scratch/db-upgrade-browser-20261013/migration/fast_additive/union_db.labor-union-staff-union-number-2026-10-13-v1.backup.receipt.json` |

其他驗收：後端 focused 27 tests、前端 focused 39 tests passed。`roster-engine-result.json` 確認真 MySQL 每頁兩個批次查詢、多帳戶不增加人員列及 cursor；`browser-result.json` 與桌面／窄畫面 PNG 確認清單、完整主檔／銀行、編號讀寫與搜尋、表格內捲動及 Enter／Space。Architecture closure passed；本次使用既有 Staff Profile owner、reader 與 UoW，未新增獨立 state owner 或 dependency。

全專案 `npm run build` 的 tsc 階段仍受另一項 Orders 修改中的 `order_intake_completion_entry.test.tsx:157` 型別錯誤阻擋。本次只排除該單一測試檔的型別檢查 passed，Vite 產品打包 passed；不將這兩者冒充全專案 build passed。

服務能力與接案資料延伸驗收：後端 14 tests、前端 34 tests passed；`service-engine-result.json` 確認實際 development DB 的八個欄位與單人 Qualification 詳情一致，名冊固定十次唯讀 SQL。`service-browser.log` 與實際頁面確認八個表頭及桌面／窄畫面表格內捲動；更新目前 8001／8000 後端後，`service-live-result.json` 確認前端代理對應的 live schema 已載入八個欄位，登入保護仍有效。Scoped typecheck、Vite build、architecture closure 與 diff check passed。此次未新增 schema 或執行資料寫入。
