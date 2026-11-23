# 非市民新案資料帶入與 LINE 綁定轉移施工交接

## 1. Authority 與規格基準

- 使用者已採用三個獨立入口，並明確要求先修改正式規格、確認無殘留或衝突後才實作。
- 程式基準為 `main@2cf2e231f0365ab9b068ed265fbd268ed2d956db`；本文件是先前建立的未追蹤成果，本次保留並原地更新。
- 本次依最新人工指示先同步正式規格；業務契約及 STAR 僅由下列 owner 文件擁有，本文件不再複述。

| Owner | 正式規格與驗收 |
| --- | --- |
| Case Import | [§3.1.1 原案資料帶入與獨立操作](../../../.arch-map/requirements/17B_Case_Import與非市民Redis待審正式規格.md)，NC-MANUAL-01～04、NC-SEPARATE-01 |
| LINE Identity | [§8.1 管理介面](../../../.arch-map/requirements/23_LINE身分管理與解除正式規格.md)，NC-BIND-01～02 |
| Reporting | [§3 統計口徑](../../../.arch-map/requirements/34_營運報表與統計口徑正式規格.md)，NC-REPORT-01 |

## 2. 執行順序與證據

1. 先完成上述正式規格與直接相關條文的殘留、衝突及獨立檢查，通過前不修改程式。
2. 實作資料帶入建案介面及既有 replacement 管理介面，沿既有 API、writer 及 UI owner 定位，不修改取消或報表計算。
3. 依下列覆蓋完成受影響驗證與獨立驗收，綁定精確候選版本及實際工作區狀態。

| 驗收 | 施工與驗證邊界 |
| --- | --- |
| NC-MANUAL-01～04 | 原案資料帶入、手動建案表單及原建案交易；沿用 `tests/subsystems/case_import/test_manual_non_citizen_case.py` 與 `ui_react/src/tests/registration_applications.test.tsx` |
| NC-BIND-01～02 | 既有 replacement Preview／Apply 管理介面及其版本衝突；沿用 LINE Identity module 測試根 |
| NC-SEPARATE-01 | 回讀取消已成功、建案失敗的獨立提交結果 |
| NC-REPORT-01 | 按現行報表入口回讀原案取消及新案分軌統計，不變更計算 |

- 直接定位證據：`api/routes/registration_applications.py::ManualNonCitizenCaseCreateRequest`、`subsystems/case_import/non_citizen_registration_application.py::create_manual_non_citizen_case`、`subsystems/line/identity_management_application.py::preview_replacement`／`replace_subject`。
- 規格收斂為 `SPEC_READY`，工作包路由為 `PACKAGE_REUSED`，使用此單一交接文件，不另建重複工作包。
- 效果上限：本機文件、程式及 focused 驗證；使用者已另行授權本次範圍 commit、push 及 bounded cleanup。不操作正式資料、LINE provider 或部署，不新增安裝或資料庫異動。
- 實作與獨立驗證由不同代理負責；各次派工使用新代理。必要驗收通過即收尾。
- 程式候選已完成：名冊詳情入口透過 `source_case` 開啟既有手動建案表單，重用 Client Registry typed Query；LINE 客戶列接既有候選查詢、Preview、確認 Apply 及回讀。沒有新增後端 API、DB schema 或跨步驟 writer。
- 獨立驗證 `passed`：React 最終四個 focused 檔 108 tests，涵蓋建案 10、名冊 74、LINE 工作區 24；Python 既有手動建案 32 tests。LINE client 與管理頁另有獨立回歸通過。名冊測試雖 exit 0，stderr 有 localhost:3000 ECONNREFUSED，只支持隔離 UI 回歸；Python 使用 fake DB，不能冒充真 DB 驗收。
- 最終候選 `npm run build`、`git diff --check` 及 architecture closure 均 `passed`。建置有既有大型 chunk 警告，未因此擴大調整範圍。
- 實際瀏覽器以合成 client／query 檢視兩個真實元件：LINE 核對視窗來源／目標姓名及案號可見；建案來源提示、帶入欄位及底部確認按鈕可見。此為隔離視覺檢查，不是正式登入或後端整合驗收。畫面證據保留於 `scratch/non-citizen-case/evidence/page-2026-11-17T11-40-33-612Z.png`、`scratch/non-citizen-case/evidence/page-2026-11-17T11-41-56-458Z.png`。
- 真 DB 建案、實際 LINE 授權／provider、取消及週報業務回讀為 `not_run`；剩餘責任為驗收人員在授權測試環境依上述 STAR 完成這些結果的回讀。不宣稱全流程業務驗收完成。
- 固定候選 SHA-256：RegistrationApplications `07159E225CDC6B5978B79E652A3F6DA9987F59DCA84BB0D7AC6A395ADE0AC3AC`；ClientRegistryPage `9350CF93F61CE97B3F388C9E786EF491CB9B9D5CB14F109F5BA447834A977DAA`；ClientRosterPage `2FE82B6C53E6776D2994EEEA9A32C2D3B9776113D2E37B3AE7944A0656B91E7D`；LineIdentityWorkbench `9012EBD8C10CB2A4E4791A3D4A9239219D1B8EA5DCE406EB13435469CD86F38A`；建案測試 `0115D2169FBD07E26891A83E0AFA8E4F2C4B1B5022611659BA7EEFA25C8654AB`；LINE 工作區測試 `D9576FF0DC81A19FD0952F57D53EE3E45AECEEE33AAE860354338167616FE1F4`。候選為基準 HEAD 加本次 working tree diff，未提交。
- 已關閉本次瀏覽器及 5175 測試服務；既有使用者服務未動。
- 規格檢核：40 份正式基線與本交接文件的 `validate_spec_hygiene --mode strict` 均通過，`git diff --check` 通過。獨立首審發現既有 Redis anchor 位置偏移；移回 §3.2 並整理報表驗收表位置後，由新代理複驗 `passed`，直接衝突語句搜尋無殘留。
- 獨立複驗版本 SHA-256：17B `6770C9BF7BAFB1C5415F6957C52F5FCE96FC14205761D284855F494A78504915`；23 `058A6C09B4BC89DEE76A067247DA788898842344196FC44D545D13383EA90B36`；34 `8DDA97A84107188AF0141CC5A831AB291D7DFEBCEF28C4F8B00C86F57E7A11E2`。這些結果只證明規格檢查，不代表功能驗收。
- 工作區另有 `scripts/launchers/WINDOWS-REMOTE.md`、`scripts/launchers/manage_windows.ps1` 及 runtime-supervision 的 `test_windows_manager.py` 修改，均非本任務產生，保留且不納入交付。
- 本文件保留為目前施工交接；完成後的移出或封存依授權處理，不自行刪除。

## 3. 取消後入口漏接修正

- 使用者回報取消多案後看不到新功能。唯讀確認現行 5173 Gateway 的 `/admin/` 主 JS 包含原資料帶入入口及 `source_case`，不是單純沒有載入上一版；原入口僅位於客戶名冊案件詳情，取消結果與工作台未提供入口。
- 已補齊共用 `OrderCancellationPanel` 的取消完成與已取消 Query 畫面，以及 `OrderWorkbenchV2Drawer` header。工作台入口不依案件狀態限制；人員點擊後才帶來源導覽，不執行取消、建案或轉綁。既有 busy 與未儲存離頁保護保留。
- 歷史失敗證據：原碼新增入口測試為 `4 failed / 32 passed`；首版修正後 36 passed。獨立審查發現 historicalRepair 仍排除入口；補測重現 `1 failed / 16 skipped`，改以 Query 的訂單取消狀態判定後，panel 17 passed。最終獨立複驗及 artifact 結果另依實際輸出確認。
- 最終 panel SHA-256 `7C0E997969727CFFE89798308938D1F7339528A28B904E8030DEBE0889173CCC`；工作台 drawer `10C81FA3884D61F9E0CB9574AB28BC06748D7A48DCE155C7815863DD054F1976`。
- 瀏覽器以合成的已取消 Query 檢視真實取消元件，確認入口及來源 URL 可見；畫面 `scratch/non-citizen-case/evidence/page-2026-11-17T13-00-13-726Z.png`。沒有再次取消使用者案件，亦未操作真 DB。
- 原網站採固定前端 artifact，修正候選需另行只更新前端才能反映到目前網站。準備產物不等於已切換；未執行正式入口切換、API／worker 重啟或 DB 異動。
- 最終獨立複驗 `passed`：兩個 focused 檔共 37 tests；artifact prepare 建置、scoped diff check 及 architecture closure 通過。最終產物指標為 `scratch/windows-remote/prepared-non-citizen-entry-fix-final.txt`，主 JS 為 `index-uqdv7ac6.js`；先前首版產物未部署，不能作為修正後版本。現行網站仍為原 artifact，換版待人工授權。

## 4. 手動建案服務時數與起訖範圍

- 使用者已手動更新前端並成功帶入原案，要求同日起訖時間差由等於改為至少涵蓋所選服務時數。正式契約及 STAR 已同步 [Case Import §3.1、NC-MANUAL-05](../../../.arch-map/requirements/17B_Case_Import與非市民Redis待審正式規格.md)。本節僅記錄施工與證據。
- 變更既有手動建案 Domain validator 及 React 驗證。手動選單改名為「每日服務時數（預設時段）」，四選項先顯時數再註明預設起訖，內部值及選取行為保留。實際起訖由下方欄位保存。
- 已核對表單差異：LIFF 是固定四個服務時段；手動新案是 4／8 小時加可調起訖；Orders Terms 為可編輯的每日時數與分開保存的起訖，常用班次提供建議值。本次不修改 LIFF 或 Orders 規則，不把時間跨度視為自動加計服務時數。
- 修正前新增正例重現：Python 3 failed／2 passed；React targeted 3 failed／1 passed。修正後獨立驗證為 Python 37 passed、React 15 passed；API seam 確認 08:00–17:00、8 小時建案仍保存每日 8 小時及原起訖。小於、反向、空值及非法時間拒絕；LIFF allowlist 不變。
- 正式規格 hygiene、scoped diff check、architecture closure 及最終 `npm run build` 通過。建置保留既有大型 chunk 警告。候選未套用現行網站，真 DB、正式網站驗收為 `not_run`；測試使用 fake DB／隔離 client。
- 固定候選 SHA-256：Domain validator `1151D64C4A8A65AF8551AC7C19C1D88D161B8B397F7812E485056235B7626DF7`；表單 `32993CBAA9F3A7C1962B04F4C82F3C726499F8283BFBAF4972E251C8C10E6441`；Python test `CCB4FA509148FA9FD086537C5FE160C4D5BCBCAED07279D5FC0D3AA2EAD172CC`；React test `58A47C4ABC2E9E1C9885775AF8369B4C2401A5C2050E472F53F946C6DDBEB154`。
- 後續套用須包含前端與後端 API 載入新程式；只更新前端不足。本次未重啟服務、切換 artifact、操作 DB 或 provider。

## 5. 提交前檢核與清理

- 本次提交前回歸：React 四個 focused 檔 76 passed；Python 手動建案 37 passed；40 份正式規格 hygiene 通過。既有建置及獨立驗證沿用同候選結果；此次未變更程式。
- React 測試仍有 socket hang up／localhost:3000 ECONNREFUSED stderr，exit 0，只支持隔離 UI 回歸。針對變更元件的 oxlint exit 0，五項 hooks／Fast Refresh warnings 保留，未擴大重構。
- 清理刪除本任務產生且已無 consumer 的兩份 console log 及兩份空白頁 snapshot；runner audit 與 apply 均 passed，共四檔 7,170 bytes。三張仍供驗收回讀的畫面已移到 ignored `scratch/non-citizen-case/evidence/`，文內路徑同步。保留建置產物與既有回復資料。
- 僅提交本功能 paths；20／27 正式規格、追蹤 README、Windows launcher 與其測試的既有 dirty 修改不納入，也不清除。後續真 DB／現行網站驗收仍由驗收人員負責，此交接文件保留到該階段結束。
