---
doc_type: work-package
declared_status: completed
date: 2026-08-14
owner: Case Import / Orders / Finance Import / Anomalies / LINE Integration
priority: P0
---

# 90 匯入異常外部確認與重新提交 Work Package

## Execution sequencing／successor

WP90 定義 warning tracking Query 與人工狀態 Preview／Apply 的完整目標契約。WP92 是目前執行
slice：只授權 import scripts、lane Preview／Apply 與正式寫入；warning center UI、typed Query、
人工轉態與 WarningReferral 明確 deferred，需由後續 Work Package 取得 write set 與驗收授權。
這是交付順序，不是撤回或改寫 WP90 已核准的業務決策。

## 人工裁決與 business scenario

資料有誤或缺漏時，公會人員通常無法立即判定正確值，必須聯絡填寫者、客戶、月嫂或其他資料來源
當事人確認。系統不得讓人員在警示中心猜測欄位、直接覆寫匯入原始列，或將 LINE 回覆直接載入正式
資料。警示中心的責任是記錄此筆資料的處理狀態；正確資料必須由新的受驗證來源重新提交，或由既有
owning Domain typed command 依已確認的外部根事實建立新 immutable result。2026-08-15 WP95 已確認：
HCM 已建案的缺漏、無效欄位與同案修正版使用完整修正來源重新走 HCM owner Preview／Apply；不在
警示中心或 Streamlit 單欄改值，typed backend 保留給未來 React 使用。

2026-08-15 補充裁決：未滿足 HCM 最低 import 條件者只留 source review／receipt／outbox
稽核，不進異常中心，因此不存在 `HCM-CASE-001`。欄位缺漏／格式錯誤使用通用
logical code，由 `field_path` 組成人可讀顯示。未登錄狀態屬工程故障，不得誤分類成業務警示。

## 共同不變量

1. HCM、Client BeClass、Staff historical、歷史訂單與銀行來源的 immutable source fact 永不 update／delete。
2. 警示中心只保存 actor、狀態、去敏聯絡摘要、reason、evidence reference、版本與時間；不保存原始
   workbook、完整個資、LINE 對話內容或未驗證的修正欄位。
3. 狀態固定為 `open`、`awaiting_external_confirmation`、`response_recorded`、`reimport_requested`、
   `closed`、`auto_resolved`。前四者維持 active；公會人員可用一般處理說明將外部確認工作推進為
   `closed`，並保存 immutable status event 與 committed outbox，但不得因此宣稱原始資料已修正。
   `auto_resolved` 只能由後續已確認 root fact 的 predicate rescan 產生。
4. 不存在唯一 LINE recipient binding 時，系統不得自動傳送 LINE；公會人員以既有合法管道聯絡。
   具 recipient binding、核准模板與 committed outbox 的未來通知能力另依 LINE Integration contract 實作。
5. 新來源重新提交必須走各 lane 的 typed Preview／Apply、fresh validation、fingerprint 與 idempotency；
   成功後由 root-fact predicate 重掃自動解除關聯警示，不以人工按鈕冒充資料已修正。
6. Finance 不可改寫 bank row。已確認銀行事實只能走既有、有限的 Finance Import／owning Domain
   typed recovery action，append-only 建立 ledger、allocation、recovery 或 return。
7. Finance workbook 必須逐列隔離：可正規化列照常匯入；金額、日期、帳號或格式無法正規化的列不建立
   canonical bank row，但必須建立可追蹤的 Finance source warning。跨檔 fingerprint 完全相同的交易
   不新增 occurrence，只在本次 receipt／計數明示已存在。
8. 每個警示類型必須另有可審核登錄，至少載明 owning Domain、code、觸發條件、正式資料效果、
   顯示的去敏摘要、可採取的後續處理、解除 predicate、可操作 actor與LINE通知狀態。未完成該類型
   登錄及人工審核前，不得自行推定 UI 文案、按鈕、通知或自動解除方式。
9. 警示投影遇到未登錄 issue 時，當次交易整體回滾；錯誤只保存 owning lane 與
   issue digest，總嘗試最多 3 次、相鄰嘗試至少間隔 1 秒，後 dead-letter。retry-ready time 必須
   持久化，不得因 worker 重啟提早。禁止靜默略過、部分投影或以 generic fallback 掩蓋新狀態。

## 第一階段操作裁決

第一階段固定由公會人員以既有 LINE、電話或其他合法管道自行聯絡來源當事人；系統只提供
`待聯絡`、`已聯絡／等待回覆`、`要求重新提交`與終態的去敏追蹤。不得在此階段建立自動 LINE
delivery、recipient 推測、訊息模板或對話內容保存。來源當事人重新提交完整資料後，才回到各 lane
原有的 typed Preview／Apply。

## Scope 與 write set

- 為每個 owning import/review root 建立 immutable tracking/disposition event、current projection、typed Query
  與「更新處理狀態」Preview／Apply；不得新增通用 corrected-payload endpoint。
- HCM `IMPORT-004`、Client／Staff BeClass review、Orders `HISTORICAL-ORDER-001` 及 Finance manual-review
  必須各自保留 owner 與 predicate，僅共用 Global command envelope／outbox contract。
- 異常中心只顯示業務狀態與合法下一步，例如「待聯絡填寫者」與「等待重新提交」。
- 缺漏與格式錯誤不為每個欄位建立新 logical code；Query 回傳例如「缺少身分證」的
  typed `display_message`，現行 Streamlit 與未來 React 不得自行重算業務文字。
- 必要時新增 additive schema、release metadata、descriptor、focused/disposable/preserve-data evidence 與
  entrypoint review；不得操作 production data 或隱式 backfill。

### 2026-08-15 root-fact auto-resolve execution slice

- Finance Import consumer 收到已提交且使 `finance_import_manual_review.active=false` 的 owning event 時，
  以 canonical row 對應的既有 `FINANCE-ROW-001` occurrence 為唯一目標；若 occurrence 不存在則零新增，
  不得為了解除而倒建警示。
- Finance projector 對每個既有 task 追加 system `auto_resolved` event、receipt、current projection 與
  tracking outbox；事件與 owner event identity 綁定，exact replay 零新增。人工 `closed` 仍可在後續
  owner predicate 消失時轉為 `auto_resolved`。
- HCM、Client／Staff BeClass 與 Historical Orders 目前沒有可證明各 field／link／adoption predicate
  已消失的已核准 committed owner completion event。live BeClass `review_resolved` 來自待退役的 generic
  corrected-fields workflow，不構成解除授權；本 slice 固定不解除、不猜測、不以 anomaly／tracking
  狀態代替 root fact。
- 本 slice 僅重用 `195_import_warning_tracking.sql` 已存在的 event／receipt／current／outbox tables，
  不變更 table、column、constraint、index、trigger、view、seed 或 business rows。

### 2026-08-15 Finance source-row isolation execution slice

#### Business scenario／boundary

- 工作簿格式與唯一表頭可辨識後，每一個可定位的銀行交易候選列獨立正規化。必要交易日期、唯一正向
  交易金額，或該格式明確提供的來源銀行帳號無法正規化時，不建立 `finance_import_rows`，但同批其他
  合格列照常建立 canonical row、classification 與 receipt。
- 缺檔、格式偵測失敗、表頭缺漏／重複、adapter 輸出違反 normalized-row structural contract 屬整份
  command failure，維持安全 ingestion attempt；空白列與可辨識的報表尾列零 review、零 warning。
- source review 只保存 source digest、format、sheet、one-based row、去敏 row identity 與
  `finance_source_field_missing|invalid:<field_path>`。不得保存 source path、raw payload、完整帳號、姓名、
  memo、摘要或未遮罩銀行 reference。
- 同一 `source digest + format + sheet + row` 是唯一 immutable review root；同一來源再次匯入只增加
  batch occurrence／receipt existing count，不新增 root、warning occurrence 或 tracking task。

#### Global → Domain → Subsystem → Module

- Finance Import Domain 擁有 source-row qualification 與 safe issue contract；Anomalies 只擁有由 committed
  Finance review outbox 投影出的 `FINANCE-SOURCE-001` tracking occurrence。
- format adapters 只做格式解析，不寫 DB；normalizer 將 adapter row 分流成 `normalized_rows` 與
  `source_reviews`。Subsystem 在同一 outer ingestion UoW 先建立 batch，再 append immutable review root、
  batch occurrence 與 outbox；canonical staging 只接收合格 rows。
- Finance anomaly consumer 在 owner transaction commit 後另開 projection transaction，讀取 review root，
  逐 field 建立 warning。未知 issue 沿用總嘗試 3 次、間隔至少 1 秒、terminal fail-closed policy。
- `FinanceWorkbookIngestionReceipt` additive 回傳 source warning total／created counts；舊 receipt snapshot 缺欄位
  時以零讀取，維持 replay compatibility。

#### DB change inventory／write set

| 類別 | source artifact／target | 資料效果 | replay／rollback／unresolved |
|---|---|---|---|
| schema-only | 新增 `finance_import_source_reviews` | immutable 去敏 source-row root | deterministic unique identity；rollback 移除未套用 successor release |
| schema-only | 新增 `finance_import_source_review_occurrences` | batch→review append-only association | batch＋review unique；不 update／delete |
| schema-only | 新增 `finance_import_source_review_outbox` | committed projection intent 與 3x／1s retry state | intent unique；unknown terminal，修正 mapping 後受控重放 |
| system-seed | 無 | 無 seed 變更 | logical code 已由 warning registry 文件核准 |
| business-row-backfill | 無 | 不掃描舊 workbook、attempt 或 canonical rows | 舊資料不推定 source warning |
| destructive | 無 | 不刪／改既有 object 或 business row | partial／drift 一律 fail closed |

精確 production write set：Finance normalizer／Domain／ingestion／anomaly consumer、typed API receipt schema、上述
三個新 tables 與 immutable triggers、fresh assembly、successor release manifest／descriptor／catalog、focused／
disposable／preserve-data tests 與本 WP／正式規格／evidence。不得操作既有 `union_db` 或 production data。

### 2026-08-15 Client BeClass candidate classification execution slice

- 姓名＋手機精確查詢先分類 Client 候選數：零筆投影 `CLIENT-BECLASS-BIND-001`，多筆投影
  `CLIENT-BECLASS-BIND-002`；只有唯一 Client 才查詢其 canonical Orders 案件候選，零筆或無法唯一時投影
  `CLIENT-BECLASS-BIND-003`。現行 schema 以 case FK／unique constraint 排除多案件 case number，但 Domain
  classifier 仍對 future／legacy drift fail closed，不據此捏造目前會發生的業務警示。
- Preview 使用普通 consistent read、零寫入且不取得 row lock；Apply 在 row UoW 內 fresh read＋`FOR UPDATE`，
  唯一 Client＋唯一案件才建立 `beclass_records.client_id/bound_case_no`。`query_no` 全程只作 source identity。
- review evidence 只增加 `client_candidate_count`／`case_candidate_count` 與既有 `has_name/has_phone` 布林值；
  不保存或回傳候選姓名、手機、案件清單。舊 `client_case_binding_not_unique` occurrence 保留 BIND-003 映射，
  新 producer 不再產生該 umbrella code。
- 本 slice 無 table／column／constraint／index／trigger／view／seed／backfill 變更，不需要新 migration；
  write set 僅限 Client BeClass binding Domain、repository、workbook workflow、warning registry mapping 與測試。

### 2026-08-15 Historical Orders source-adoption execution slice

- 案號可精確對應且來源狀態／實際服務日期有效時，以歷史來源值採納到 Orders；現行值不同不是
  `current_conflict`，不得因此建立警示。來源未提供日期時保留現值，不以空值覆寫。
- 可辨識照服員但雙人紀錄缺少個別服務區間、起日或迄日時，保留配對 evidence 並投影
  `ORDER-HIST-ASSIGNMENT-001`；不得將該業務狀態降為無 issue 的 evidence-only 紀錄。
- 歷史來源日期解析錯誤仍依實際欄位投影 `ORDER-HIST-FIELD-001`；既有
  `historical_current_status_conflict`／`historical_nonempty_conflict:*` mapper 僅為舊 receipt 相容，live producer
  不再建立這些已禁止狀態。
- Domain、workflow、repository、warning mapping 與 disposable MySQL 回歸共 22 passed；驗證來源覆寫、缺值保留、
  指派 evidence 警示、unknown issue 3 次／1 秒停損及零部分投影。
- 本 slice 無 table／column／constraint／index／trigger／view／seed／backfill 變更，不需要新 migration。

### 2026-08-15 Staff historical name-trace execution slice

- 唯一 Staff 的較新歷史快照成功寫入不同姓名時，使用同一 committed adoption／review outbox 建立
  `STAFF-BECLASS-NAME-002/姓名` occurrence；初始 tracking 狀態直接為 `auto_resolved`，只供追溯，
  不成為公會人員待辦。
- projector 先完整解析 typed warning 再決定 generic anomaly active predicate；只有姓名變更 trace 或明確
  no-warning 的 review 不建立 active generic alert，若同一 review 另有真實缺漏／格式錯誤，該警示仍保持 open。
- exact replay 由既有 adoption receipt 保證不重複寫入；unknown issue 仍維持整筆回滾與 3 次／1 秒停損。
- fail-before-fix 證明舊流程會靜默丟棄姓名 trace；舊 `identity_name_mismatch` 未寫入事件改列一般
  `STAFF-BECLASS-FIELD-002/姓名`，不得冒充已完成 trace。修正後 BeClass、Staff disposable MySQL、Client
  binding、tracking Domain／API 擴大回歸共 43 passed。
- 本 slice 無 table／column／constraint／index／trigger／view／seed／backfill 變更，不需要新 migration。

### 2026-08-15 Streamlit warning-navigation acceptance slice

- 在 `APP_ENV=test`、admin auth bypass 與 disposable DB
  `lu_test_wp90_finance_source_20260815b` 啟動本次專用 FastAPI／Streamlit；未操作 `union_db`。
- Browser DOM 驗證異常中心顯示「僅顯示去敏警示與導向業面」及「不會修改來源資料，也不代表正式資料
  已修正」，頁面未出現 corrected payload 輸入。
- 點擊 BeClass「前往資料匯入中心」後，sidebar 實際切換至營運作業／資料匯入中心，且 HCM、Client
  BeClass、Staff BeClass、Historical Orders 各自維持 typed Preview／Apply 入口。
- typed Query 唯讀回傳空 active task list；本次不為畫面捏造 warning。console 無 application error，只有
  Streamlit 內建 popper modifier warning。驗收後關閉頁籤並終止本次記錄的 API／UI PID。

### 2026-08-15 HCM owner backend successor

- 使用者核准 WP95：本段停止新增 Streamlit 工作，只交付 HCM 修正版來源的 typed backend
  Preview／Apply、owner receipt／outbox、warning referral descriptor 與 root-predicate auto-resolution。
- 既有 `ApplyCaseImport` 只支援首次建案與 exact replay；同案不同來源目前只建立
  `case_import_existing_source_conflict` review。WP95 必須以獨立 owner command 實作，不可放寬 replay
  或讓 warning tracking UoW 直接改 formal root。
- additive schema、release、descriptor、fresh bootstrap、preserve-data candidate 與 disposable MySQL
  gate 全部 PASS 後，才能將本 successor 標記完成。

## Out of scope

- 從來源列自動猜 LINE recipient、傳送未核准訊息或保存 LINE 對話。
- 直接修改 workbook row、bank row、Client、Order、Staff 或以人工輸入建立正式資料。
- 以單一 generic correction form 合併不同 Domain 的資料語意。

## Completion evidence

2026-08-15 completion receipt：
[`2026-08-15_wp90_wp95_completion_receipt.md`](../../03_追蹤清單與證據/evidence/2026-08-15_wp90_wp95_completion_receipt.md)。
WP95 已承接 HCM owner scoped workbook command；異常中心沒有新增任何 formal-root mutation。所有
WP90 acceptance gate 已有 focused、cross-lane、disposable MySQL、candidate preserve-data 及 entrypoint
governance evidence。正式 source DB replacement／deployment 不在本 Work Package 授權範圍。

## Acceptance

1. 任一匯入異常可建立、查詢及 versioned Preview／Apply 更新追蹤狀態；same-key replay、different-payload
   conflict、stale version 與 partial failure 均 fail closed。
2. 警示中心無直接編輯來源欄位的 UI/API；來源重新提交後才可能建立正式 root fact。
3. 一般 `closed` 狀態與重新提交成功各有 immutable event、receipt、outbox 與 root-fact-aware anomaly
   projection evidence；`closed` 只代表外部確認工作結束，不能成為原始資料已修正或正式 root 已建立的證據。
4. Finance fixed recovery actions 保持 append-only，且任何未知銀行列只可追蹤、不能強制入帳。
5. focused、disposable MySQL、UI 與 preserve-data gates 分別通過後才可標記完成。
6. 壓力／未來版本測試注入未登錄 issue 時，零部分 warning／task／anomaly；錯誤去敏、
   總嘗試 3 次、間隔至少 1 秒、進入 dead-letter 後停止熱迴圈，並可在補齊 registry／映射後受控重放。
