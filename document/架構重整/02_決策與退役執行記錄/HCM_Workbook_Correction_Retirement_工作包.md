---
doc_type: work-package
declared_status: completed
owner: Case Import / HCM current workbook import
updated_date: 2026-10-13
implementation_authorization: user-2026-10-13-retire-workbook-correction-entry-and-command
---

# HCM 工作簿修正退役

## Authority 與驗收

人工要求退役工作簿修正入口與專用命令，並評估異常審核頁是否都有替代入口。
正式語意吸收到規格 17；API 退役範圍依規格 19。比較基準為
`a317c02cfcbd3ace19c2a49704f7cb647891024f`，保留任務開始時所有其他 dirty／untracked 成果。

- 匯入頁與異常審核頁均無修正版工作簿上傳、預覽、套用入口。
- `/api/v1/case-import/hcm/resubmissions/{preview|apply}` 不存在於 routing／OpenAPI，請求不得開啟 persistence。
- 移除專用 workbook parser、source derivation、Case Import correction Apply、Client typed correction command 與 Client／Orders 專用 adapters。
- 一般 HCM intake、問題明細、current review Query、逐欄人工略過、typed stale conflict、receipt／outbox 與既有歷史保留。
- 更新訂單工作台與補件面板仍指向退役流程的提示文字；不納入尚未提交的服務方式 writer／直接補件面板。
- 評估整頁替代入口，不在本包刪除異常審核頁、搬移警示／LINE 命令或新增欄位 writer。

## Bounded write set

- `api/{routes,dependencies,schemas}/hcm_import.py`；referral 的既有 schema／workflow。
- `domains/case_import/hcm_resubmission.py`、`subsystems/case_import/hcm_resubmission_workflow.py`、`infrastructure/mysql/hcm_resubmission_repository.py`。
- 專用移除：`domains/clients/hcm_correction.py`、`subsystems/case_import/hcm_resubmission_{workbook,source}.py`、
  `infrastructure/mysql/{client,orders}_hcm_correction_adapter.py`、`ui_react/src/components/HcmControlledCorrectionWorkbench.tsx`。
- 異常頁、HCM typed client／schemas、referral schemas、訂單工作台／補件提示及其直接測試。
- 專用 workbook／workflow／Client command tests 退役；保留 mapping、schema release、outbox、Query／skip 的 current oracles。
- 規格 17／19、受影響 Case Import／Anomalies 架構 leaf 與測試索引。

## 異常審核頁替代入口評估

| 能力 | 已有替代 | 結論 |
|---|---|---|
| HCM 支援欄位編輯 | 客戶名冊、訂單條件、進件補件面板 | 可退役工作簿修正；報名時間／IP 等無正式編輯表單者保留警示與略過 |
| 每案目前所有 HCM／其他匯入警示及待處理清單 | 訂單工作台只查待補件案件；匯入頁只顯示本次收據；財務頁處理自身資料 | 只有部分替代，不能等同集中 current 清單 |
| HCM／其他 import 警示逐筆確認略過 | 無其他頁呼叫對應 skip Preview／Apply | 異常頁仍需保留 |
| LINE 設定、綁定、發送明細 | LINE 管理頁；訂單 context 有通知 timeline | 查閱與修設定可替代 |
| LINE-006 current issue、人工重送與逐筆略過 | LINE 管理發送明細為 Query；其他頁沒有 manual replay／warning skip consumer | 異常頁仍需保留 |

依據：`CurrentAnomaliesPage.tsx`、`OrderWorkbenchV2Page.tsx`、`OrderIntakeRepairPanel.tsx`、
`HcmIntakeProfileRepairPanel.tsx`、`LineManagementPage.tsx`、`OrderWorkbenchV2OwnerContext.tsx` 的 current source。
沒有全功能替代，所以本次不移除整頁。此評估是 code／contract evidence，不宣稱實際使用量或 provider acceptance。

## Effect ceiling 與驗證

不改資料表、migration release、歷史事件／source、production DB、provider 或部署。
既有 outbox consumer 保留，以免已提交修正與略過事件失去 consumer。
2026-10-13 追加人工 Authority：執行實際 DB 與 Browser 驗證。只用 localhost／development，
以既有 canonical bootstrap 建立本任務唯一且原先不存在的 `lu_test_hcm_retirement_*` schema；
不修改既有 `union_db`、DDL 來源或其他測試資料庫。合成來源只走 current HCM／Client Profile／skip 正式 writer，
保存 before／after、receipt 與畫面 evidence。測試服務綁定 localhost、關閉 startup／worker／provider 副作用；
驗證後停止本任務服務，保留測試 schema 與去敏證據供追溯，不執行 DROP／reset。
驗證限定：retirement HTTP／OpenAPI、HCM Query／skip、歷史 outbox、migration evidence、referral、
匯入與異常 React tests、直接補件替代路徑、TypeScript 及 architecture closure。
若需恢復工作簿修正，須有新的人工 Authority；Git history 只作回復 evidence，不是 current entry。

## Closure

2026-10-13：工作簿修正入口及專用命令退役完成；異常審核整頁保留，因上述替代入口仍不完整。

- PASS：76 項後端 focused tests，涵蓋 HTTP 404／OpenAPI 移除、保留 Query／skip、typed conflicts、
  root mappings、既有 outbox、immutable migration evidence 與 wait-only referral。
  使用既有 `.venv`，關閉非本任務的 pytest plugin 自動載入；沒有安裝或修改依賴。
- PASS：10 個前端測試檔，共 98 項不同測試；匯入結果、異常頁略過／LINE 重送、typed query／adapter
  與訂單／Client Profile 直接補件替代路徑均通過。僅對失敗或新增受影響的檔案重跑。
- PASS：TypeScript、architecture closure 與 `git diff --check`。
- PASS：追加實際 DB／Browser 驗證，詳見下節。
- NOT_RUN：provider 實送、正式登入／MFA、production／部署；本次沒有上述副作用。
- 全部資料表、migration releases、歷史資料及 committed outbox consumer 保留。

### 實際 DB 與 Browser evidence

Target：localhost `127.0.0.1:3306`、development、root credential class、
`lu_test_hcm_retirement_20261013_0dd17c0b`。canonical fresh bootstrap 的 171 個 schema parts 與完整 schema
驗證通過；不含既有 `union_db` 的資料複製。使用既有 development bypass 與已安裝 Edge，
current Vite／完整 API routers 均指向此隔離庫，未 mock API 或業務資料。

| Gate／情境 | 結果 | Evidence |
|---|---|---|
| localhost／development／唯一新 target 與完整 schema | PASS | `scratch/hcm-workbook-retirement/runtime/state.json` |
| 既有真 MySQL multipart API：Preview／Apply／exact replay／conflict；已退役 historical overwrite | PASS：2 tests | `tests/test_hcm_import_api_disposable_mysql_e2e.py`，workspace 內唯一 pytest 暫存目錄 |
| 瀏覽器 Preview 零寫入、匯入兩筆合成欄位警示與 receipt | PASS | `runtime-evidence.json` 的 before／after_intake／intake receipt |
| 修正按鈕／區塊／異常跳轉入口不存在，匯入結果與問題明細保留 | PASS | `import-result.png` |
| 退役 Preview／Apply 真 HTTP 404、完整 OpenAPI 無入口、DB 前後完全相同 | PASS | `runtime-evidence.json` 的 retired HTTP check |
| 異常頁 current problems、名冊深連結與逐欄略過可用 | PASS | `anomalies-before-skip.png`、`anomalies-after-skip.png` |
| 略過只解除一項警示，root／來源不變，event／receipt／outbox 各新增一筆 | PASS | after_skip／field_skip receipt |
| 以過期 skip Preview 提交得到 typed 409，零新增事件 | PASS | real_mysql_stale_skip_409_zero_write |
| 從名冊真 Preview／Apply 儲存手機，current review 自動解除，來源／workbook correction evidence 不變 | PASS | after_profile／profile receipt、`registry-correction.png` |
| 最終頁面查詢全部完成、無 alert／page error，兩筆問題均已解除 | PASS | `anomalies-completed.png` |

上述 JSON、PNG 均在 `scratch/hcm-workbook-retirement/runtime/`，包含合成資料的去敏 before／after 與 receipts；
沒有 credential、真實個資或 provider payload。測試服務驗證後停止，隔離 schema 保留作 readback evidence；
pending outbox 未啟動 worker，不宣稱 LINE delivery 或背景事件投遞已通過。

Commit scope：只提交本次退役與驗證；同檔案中的既有直接補件面板修改，以及依賴尚未提交服務方式 writer 的新增名冊深連結，保留在工作區。

Independent commit verification：納入 current review 對 Client Profile validator 的最小 signature 修正（移除已不存在的 city_allowlist 參數與 unused import），避免保留的 Query／skip 在獨立版本拋出 TypeError；不納入 service_type writer 或名冊篩選變更。

獨立暫存版本驗證 PASS：後端 76 項、前端 86 項（8 個檔案）、TypeScript 與 cached diff check；使用 Git index 快照，沒有帶入其他 dirty／untracked source。
