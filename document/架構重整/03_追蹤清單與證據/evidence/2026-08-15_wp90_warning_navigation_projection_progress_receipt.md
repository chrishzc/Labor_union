---
doc_type: evidence-receipt
declared_status: in-progress
date: 2026-08-15
owner: Anomalies / Case Import / Orders / Finance Import
work_package: 90_Import_Review_External_Confirmation_Work_Package
---

# WP90 警示投影與導航進度證據

本收據僅記錄已完成的 field-level warning projection、typed navigation action 與驗收結果；
不代表 WP90 已完成、未授權 owner command 已存在，或可封存。

## 已驗證行為

| 範圍 | 證據 | 結果 |
|---|---|---|
| HCM／Staff BeClass review outbox → field warning | `lu_test_wp90_hcm_unknown_20260815` 下分別重跑 HCM 與 BeClass unknown E2E | PASS：各 1 passed；總嘗試 3 次、每次間隔至少 1 秒，立即重呼為零領取，第 3 次後 terminal，且零部分 anomaly／occurrence／task。 |
| Historical Order unknown projection | `lu_test_wp90_orders` 下執行新增 unknown-state E2E | PASS：1 passed；同樣為 3 次／1 秒／terminal，canonical alert 與 tracking task 零部分寫入。 |
| Finance projection retry | 全新 `lu_test_wp90_finance_retry_v4_20260815` 完整 bootstrap 後直接執行 focused E2E | PASS：`FINANCE_RETRY_E2E_PASS`；原 30 秒無上限改為 3 次／1 秒，canonical bank row 保留、anomaly 零部分寫入。 |
| Historical Orders source adoption／warning projection | `lu_test_wp90_finance_source_20260815b` 執行 Domain、mapping 與完整 disposable MySQL suite | PASS：22 passed；有效歷史狀態／日期覆寫現值且不建立 false conflict，缺日期保留現值，雙人缺個別區間投影 `ORDER-HIST-ASSIGNMENT-001`，unknown issue 3 次／1 秒後 terminal 且零部分投影。 |
| Finance canonical manual-review row → field warning | `lu_test_wp90_finance` 下執行 `tests/test_finance_import_disposable_mysql_e2e.py::test_g11_ordinary_finance_review_projects_once_without_integrity_alert` | PASS：1 passed；`FINANCE-ROW-001` 不建立 ledger。 |
| Finance committed final dispatch → tracking auto-resolve | 全新 `lu_test_wp90_finance_autoresolve_v2_20260815` 執行 `test_finance_final_dispatch_auto_resolves_existing_warning_once` | PASS：1 passed；既有 `FINANCE-ROW-001` 由 open v1 轉為 system auto_resolved v2，event／receipt／outbox 各一，重跑 consumer 零新增。 |
| Finance mixed source-row isolation | `lu_test_wp90_finance_source_20260815b` 執行 `test_mixed_finance_workbook_keeps_valid_row_and_projects_safe_source_warning` | PASS：1 passed；2 個候選列只建立 1 個 canonical row，另 1 個 immutable source review 與 `FINANCE-SOURCE-001`；exact replay 零新增，review／evidence 無 raw memo 或電話。 |
| Finance source unknown projection | `lu_test_wp90_finance_source_20260815c` 執行 `test_unknown_finance_source_projection_stops_after_three_one_second_attempts` | PASS：1 passed；每次至少間隔 1 秒、總嘗試 3 次後 terminal，錯誤只留 digest，零部分 warning occurrence。 |
| Client BeClass candidate classification | unit／mapping 16 passed；`lu_test_wp90_finance_source_20260815b` 執行 binding disposable MySQL E2E 3 passed | PASS：實際區分零 Client→BIND-001、多 Client→BIND-002、唯一 Client 但零案件→BIND-003；Preview 無 row lock，Apply fresh lock；review outbox 成功投影 BIND-001＋SOURCE-001，無候選 PII。 |
| Staff historical newer-name trace | fail-before-fix 2 failed；修正後 BeClass／Staff disposable MySQL／Client binding／tracking Domain＋API 43 passed | PASS：owner adoption 成功更新姓名後建立 `STAFF-BECLASS-NAME-002/姓名`，初始 task 為 `auto_resolved` v1；姓名 trace-only review 無 active generic anomaly。舊 `identity_name_mismatch` 未寫入事件維持一般姓名欄位 warning，不冒充已完成 trace。 |
| 已知 producer mapping | HCM、Client BeClass、Historical Orders mapping／display／intake focused tests | PASS：33 passed；HCM 既有來源衝突、Client 欄位 missing／invalid 與來源衝突、歷史訂單起迄日解析失敗不再誤進 unknown dead-letter。 |
| typed Query／API／navigation contract | 四 lane mapping、retry、tracking、API、WP77 contract 與 worker 相鄰測試 | PASS：78 passed；API 回傳人可讀 `display_message`，不回傳 URL、corrected fields 或 raw source payload。 |
| WP95 HCM referral backend | fail-before-fix import error；完成後 tracking Domain＋API 17 passed | PASS：唯讀 endpoint fresh-read 並檢查 expected warning version；只對核准 HCM 類型回傳 `preview_hcm_resubmission` 或等待 counterpart，completed／non-HCM／unknown 均 fail closed，無 corrected payload、raw source 或 row lock。 |
| Streamlit 顯示與 click-through | disposable DB 上啟動本次專用 FastAPI／Streamlit，以 in-app Browser 驗證異常中心與 BeClass 導向 | PASS：DOM 明示只顯示去敏警示／追蹤／導向且不修改正式資料；點擊「前往資料匯入中心」實際切換 owning 匯入頁。active task API 為空，未捏造 warning；console 無 application error。 |

## 未完成／不得據此宣稱

1. `FINANCE-SOURCE-001` 已有 immutable source-review root、field warning 與去敏跳轉；後續修正版來源與
   舊 review 的 explicit association 仍未實作，因此此類 warning 尚不可自動解除。
2. Finance final dispatch／manual correction 已有 committed owner event，可依同列 root predicate
   `auto_resolved`。HCM owner contract 已由 WP95 核准，referral descriptor 已完成；HCM resubmission
   mutation／association／owner outbox 與 BeClass、Historical Orders completion event 仍在施工，異常中心不得代為實作。
3. HCM、BeClass、Historical Order 與 Finance 的 unknown projection 已統一 fail closed＋去敏＋
   3 次／1 秒／terminal；BeClass 另保留明確 no-warning allowlist，不以靜默 generic fallback 取代登錄。

## DB change gate

| Gate | 結果 | 說明 |
|---|---|---|
| Scope gate | PASS | WP90 Finance source-row slice 已記錄 business scenario、owner、三類 additive write set 與零 backfill／destructive。 |
| Change inventory | PASS | 三個 schema-only tables；system seed、business-row backfill、destructive 均為無。 |
| Static release gate | PASS | part 200、fresh assembly、versioned manifest／descriptor、release catalog 與 generated validation release 一致；assembly／release focused tests 39 passed。 |
| Descriptor gate | PASS | 三 tables、columns、indexes、FK、checks 與四 immutable triggers 由 descriptor 機械驗證為 exact；partial／drift fail closed。 |
| Read-only plan gate | PASS | `scripts.update_local_database` preview 列出只需套用 `200_finance_import_source_reviews.sql`；rehearsal plan status `ready`。 |
| Engine verification gate | PASS | fresh mixed-row／unknown E2E 各 1 passed；preserve-data source → candidate restore／apply／verify status `verified`，part 200 exact，既有資料 count／checksum／PK digest 保留。 |
| Developer acceptance gate | PASS | 專用 `lu_test_wp90_finance_launcher_source_20260815a` clone 完整執行 launcher replacement，status `completed`，保存 source／candidate dump、replacement／rollback receipts；未碰 `union_db`。 |

### WP95 HCM correction DB gate（目前狀態）

| Gate | 結果 | 說明 |
|---|---|---|
| Scope gate | PASS | 人工核准 WP95；business scenario、owner、Global→Domain→Subsystem→Module、exact write set 與 stop conditions 已記錄。 |
| Change inventory | PASS | correction event／receipt／outbox／canonical case binding 為 schema-only；system seed、business-row backfill、destructive 均為無。 |
| Static release gate | NOT_RUN | 尚未建立 successor schema part／release；不得先改 SQL 再補 catalog。 |
| Descriptor gate | NOT_RUN | owned-object descriptor 尚未建立。 |
| Read-only plan gate | NOT_RUN | successor release 尚未進 canonical chain。 |
| Engine verification gate | NOT_RUN | 尚未執行 fresh bootstrap／preserve-data candidate。 |
| Developer acceptance gate | NOT_RUN | 不操作既有 `union_db`；需在前六門 PASS 後以專用 disposable source 驗證。 |

WP95 schema 總結固定為 `DB_CHANGE_NOT_READY`；目前完成的 referral backend 不依賴 schema，不能視為
HCM correction mutation 已完成。

## 結論

此 evidence 使四個已登錄 lane 的「警示投影＋去敏導向 descriptor」、Finance root-fact auto-resolve、Client BeClass
候選分類、Historical Orders source-adoption producer 與 Staff historical newer-name auto-resolved trace 具備
static／disposable MySQL 證據；Finance source warning 與其 DB upgrade path 已完成；其他 lane owner mutation、completion
event 仍為 active work；Streamlit warning-navigation acceptance 已 PASS。
