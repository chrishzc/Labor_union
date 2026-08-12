# ADR-001：匯入邊界、異常追溯與對帳架構修正版

## 文件狀態

- ADR 狀態：`Amended Proposed`
- 實作狀態：`partial`
- 原始日期：2026-08-05
- 修訂日期：2026-08-10
- 實作授權：`not-authorized-before-human-confirmation`

本文件原版提出欄位級 partial write 與 `system_alerts` 投影。後續正式架構已建立獨立的
Finance Import、Case Import 與 Anomalies Domain，因此原版模組名稱與部分交易語意已過時。
本修正版保留「匯入結果可追溯、可對帳、錯誤可處理」的業務目標，改以目前正式架構重新定義。

本文件是待人工確認的修正版 ADR，不取代下列正式基線：

- `../架構重整/01_規格基線/09_Finance_Import_Domain.md`
- `../架構重整/01_規格基線/17_External_Integration_LINE_Access正式規格.md` 的 Case Import
- `../架構重整/01_規格基線/06_Anomalies_Domain.md`
- `../架構重整/01_規格基線/15_正式規格索引與裁決總表.md`

若本文件與上述正式基線衝突，實作前必須先取得人工裁決並同步更新正式基線；不得只修改
production code 或 pytest 來默認改變業務語意。

## 1. 業務問題

匯入流程必須同時回答四個問題：

1. 來源檔的每一列最後發生了什麼事；
2. 哪些資料成為正式根事實，哪些仍只是待確認來源；
3. 為何某列或某欄不能套用，以及人員應從哪個入口修正；
4. CLI、API 與 UI 的統計是否使用同一套互斥口徑。

原始問題包括舊 `services.*` import 路徑、列級跳過但原因不可查、腳本與 UI 數量不一致、
錯誤欄位缺乏持久化證據，以及告警路徑分裂。舊 import 路徑多數已退役，但其餘業務問題尚未
形成完整閉環。

## 2. 目前實作盤點

以下是 2026-08-10 對 current working tree 與 candidate DB 的只讀證據，不是永久規格：

| 切片 | 狀態 | 現況 |
|---|---|---|
| 舊 `services.*` 路徑退役 | `implemented` | production import 已改走 Domain／Subsystem／Infrastructure；舊 `services` 目錄已不存在 |
| 統一匯入分層 | `partial` | Finance／HCM 已使用 typed application；Staff／Client BeClass 腳本仍直接管理 DB 連線與 SQL |
| 欄位級錯誤模型 | `partial` | 已有 validation error dict、`issue_codes` 與 invalid-row review root；尚無統一 `ImportFieldIssue`／codebook contract |
| 安全的欄位級寫入 | `partial-conflict` | Staff 會把錯欄設為 `NULL` 後寫入；Client BeClass 整列進 review；HCM 會填入假預設值後寫正式資料 |
| Canonical anomaly | `partial` | Finance／BeClass 已有 outbox 與 canonical anomaly；部分腳本仍直接寫 `system_alerts` |
| 匯入 Manifest／Review Query | `backend-only` | typed API client 與後端 query 已存在，但沒有正式掛載的 UI 對帳入口 |
| 對帳公式 | `missing` | 尚無全匯入流程共用的互斥 row outcome SSOT |
| `48/43/5` 回歸 | `missing` | 沒有可驗證 fixture、assertion 或 receipt |
| Current candidate schema | `drift` | Finance Import tables 已存在；目前 candidate DB 缺 BeClass review tables |
| Script／schema compatibility | `unsafe-partial` | Finance 已有 versioned adapter；HCM／Client BeClass／Staff 仍以來源表頭、runtime DB 欄位過濾與 direct SQL 相容 schema，會把 schema drift 變成靜默漏欄 |
| 真實格式回歸語料 | `partial` | Finance 有三類格式 adapter 與固定 Excel fixture；HCM／Client BeClass／Staff 缺少版本化、去識別的真實格式變體 corpus |

不得把局部單元測試 PASS 或模組可 import 誤報為本 ADR 已完成。

### 2.1 Finance Import CLI 測試 Adapter 整併邊界

原 `44_Finance_Import_CLI_Test_Adapter_Work_Package.md` 於 2026-08-12 整併至本 ADR。現行
`scripts/imports/import_finance_excel.py` 只定位為測試／受控維運期 adapter：

- 正常模式只能呼叫 typed `subsystems.finance_import.ingestion`，使用固定
  `finance-import-cli-test` actor 及由檔案內容衍生的穩定 idempotency key；
- `--dry-run` 只做格式偵測、normalization 與列數摘要，必須零資料庫寫入；
- 不得 import、復活或呼叫 legacy `services.finance_import_application`；
- 不得被視為正式人工操作入口，也不得與 authenticated Web upload 形成雙 active writer。

目前 Finance Web upload、Preview／Apply 與 typed API 已存在，replacement 條件已成立；但 CLI
仍由 `scripts/file_watcher.py` 引用，移除前必須完成 caller replacement、entrypoint review、focused
regression 與 validator。這項整併不直接授權刪除 CLI 或變更 File Watcher。

## 3. Global → Domain → Subsystem → Module

### 3.1 Global

Global 不變量：

- 每個來源列在一個 committed import run 中只能有一個互斥 row outcome；
- 每個 active writer 必須先證明 source format contract、canonical candidate contract 與 target schema contract 相容；
- 正式根事實只能由 owning Domain 的 typed command 與交易 owner 寫入；
- invalid source 可以保存為 review evidence，但不得以假值或部分不一致資料污染正式根事實；
- CLI／File Watcher 只建立 typed import command 或 durable job，不直接編排跨 Domain SQL；
- Domain transaction 只寫 root fact、event、receipt 與 outbox；Anomalies 在 commit 後投影；
- UI 只呼叫 typed API client，不讀 DB、不重算統計、不接收未驗證 raw `dict`；
- source、review、apply、replay、stale、partial failure、rollback 與 projection recovery 都有分層證據。

### 3.2 Domain ownership

| Domain | 擁有 | 不擁有 |
|---|---|---|
| Finance Import | source file identity、canonical bank fact、occurrence、classification、ingestion／reprocess receipt | Client／Staff／Government ledger、正式 Alert workflow |
| Case Import | BeClass／HCM source row、normalized candidate、validation、review、source→internal mapping、bootstrap receipt | Client、Order、Scheduling 等正式根事實 |
| Staff profile owner（待裁決） | staff identity 與經核准的正式 profile 欄位 | 原始 BeClass row、匯入告警 workflow |
| Anomalies | definition、current alert、workflow event、投影 checkpoint | source row、正式業務根事實、匯入交易 |

### 3.3 Subsystems

- Source Intake／Archive
- Normalization／Validation
- Row Outcome Classification
- Invalid-row Review
- Typed Preview／Apply
- Canonical Staging／Occurrence
- Outbox／Anomaly Projection
- Import Manifest／Review Query

### 3.4 Modules

- `SourceFileFingerprint`
- `SourceRowIdentity`
- `ImportFieldPolicy`
- `ImportFieldIssue`
- `ImportRowOutcomeBuilder`
- `ImportManifestBuilder`
- `CaseImportNormalizer`／`CaseImportValidator`
- `CanonicalBankRowNormalizer`／`CanonicalBankRowValidator`
- `ReviewCandidateBuilder`
- `ImportIssueCodebook`
- `ImportAnomalyDesiredStateBuilder`
- `SourceFormatProfile`／`SourceHeaderFingerprint`
- `ImportSchemaContract`／`ImportSchemaCompatibilityChecker`
- `CanonicalImportCandidate`

## 4. 衝突裁決與建議方向

### 4.1 衝突一：所有錯欄都 partial write，或正式根事實列級原子

原版 ADR 要求任一欄錯誤時只阻擋該欄。這對互不影響的 optional profile 欄位可能可行，
但不適用 identity、日期區間、服務條件、金額、fingerprint 或狀態機欄位。

建議採「欄位政策分級」：

| Policy | 欄位類型 | 行為 |
|---|---|---|
| `root_required` | identity、case no、交易日期／金額、服務日期／天數、狀態機必要欄位 | 任一錯誤即 `review_required`；不建立或更新正式 root |
| `cross_field_invariant` | 需與其他欄位共同驗證的條件 | 整組阻擋；不得拆欄寫入 |
| `optional_allowlisted` | nullable、非 identity、非計算依據、非授權依據的附加資料 | 可省略錯欄並得到 `applied_with_omissions` |
| `source_only` | 原始問卷、診斷欄位 | 只保存於 source／review evidence，不直接成為正式 root |

只有 `optional_allowlisted` 可做欄位級 omission。Allowlist 必須由 owning Domain 明列；不得根據 DB
欄位可為 `NULL` 就自動推定安全。

建議裁決：`ACCEPT`。這保留安全的欄位級寫入，同時符合正式根事實與跨欄不變量。

### 4.2 衝突二：HCM 用假預設值繼續寫入

目前 HCM 會把錯誤日期替換為 `2000-01-01`、服務天數替換為 `1`，再建立正式 case。
這些值會影響 Orders、Scheduling、Finance 與 Payroll，不能視為資料清洗。

建議裁決：`RETIRE`。禁止 fabricated defaults。必要欄位錯誤時保存 privacy-safe review root，
不建立正式 Client／Order；人員修正後重新 Preview／Apply。

### 4.3 衝突三：`system_alerts` 或 canonical Anomalies

原版 ADR 指定將所有匯入結果投影至 `system_alerts`。現行正式架構已由 Anomalies 擁有
canonical current alert 與 workflow，`system_alerts` 只保留流程提醒／相容資料邊界。

建議裁決：`CANONICAL_ANOMALIES_ONLY`。新的 Finance／Case／Staff import review 只寫 owning
Domain outbox，由 projector 更新 canonical anomaly。腳本不得同步 direct upsert
`system_alerts`；legacy rows 依既定 migration／retirement 證據處理，不雙寫。

### 4.4 衝突四：告警顯示原始 `sample_value`

原版要求告警直接帶 sample。這可能洩漏姓名、電話、身分證、帳號或銀行內容。

建議裁決：`MASKED_SAMPLE_ONLY`。typed issue 保存 stable error code、canonical field name、
reason code 與可選的 allowlisted masked sample；完整 source payload 只存在受控 review storage，
不進 anomaly summary、log 或一般 UI。

### 4.5 衝突五：精確保留 `48/43/5`

原版把 `48/43/5` 當回歸案例，但目前沒有可定位的版本化 fixture。

建議方向：

1. 若能找到合法、去識別且內容固定的原始 fixture，建立 digest、欄位版本與預期 manifest，保留
   `48/43/5` 作 Domain acceptance；
2. 若原 fixture 已遺失或含不可提交個資，人工裁決退役魔術數字，改用 versioned synthetic fixture
   驗證同一守恆式與錯誤類型分布。

在 fixture 身分未確認前，不得建立只為湊出 `48/43/5` 的假測試。

### 4.6 衝突六：整檔交易或逐列交易

不同匯入的交易根事實不同，不採全系統單一答案：

- Finance Import canonical ingestion 依正式基線維持 batch outer UoW，任一必要步驟失敗整批 rollback；
- Case／Staff source rows 建議以單一 source row 為 mutation UoW，batch durable job 只編排進度；
- 每列需先完成 root／review、row receipt 與 outbox，再標記 terminal outcome；
- transient failure 的列保持 `retry_required`，batch 不得標成 completed，也不得輸出完成對帳宣告；
- 只有所有列進入 terminal outcome 後，才能套用第 5.2 節守恆式。

建議裁決：`DOMAIN_SPECIFIC_UOW`。若 Case／Staff 改採整檔交易，必須另行證明單列錯誤回滾整批
符合實際操作需求，並重畫 retry、idempotency 與長交易風險。

### 4.7 衝突七：遇到舊 schema 時靜默略過不存在欄位

歷史 `INV-IMPORT-03` 允許腳本查詢 live columns，將不存在的 DB 欄位從 INSERT／UPDATE 移除，
以避免 MySQL 1054。這能暫時避免程序中斷，卻無法區分「可安全省略的 optional 欄位」與
「migration 漏套、欄位改名、型別改變或 root-required 欄位不存在」。最危險的結果是匯入顯示
成功，但正式資料已少寫且沒有 review evidence。

建議裁決：`REPLACE_WITH_EXPLICIT_SCHEMA_CONTRACT`：

- release 前以 migration manifest／`INFORMATION_SCHEMA` 產出 compatibility report；
- `root_required`、writer-owned、FK／unique／check 或型別不相容時 fail closed，不處理任何來源列；
- 只有 contract 明列為可向後相容的 additive optional 欄位，才允許舊 writer 暫時不提供值；
- 欄位改名、拆表、enum/check 收斂或 ownership 改變，必須先升級 adapter／command，再 writer cutover；
- 禁止 `SELECT *`、欄位位置猜測、runtime 靜默 drop unknown target field，以及捕捉 1054 後繼續匯入。

這不是要求 import 綁死某個實體 schema；相反地，腳本只綁定版本化 application contract，
Infrastructure adapter 才宣告可支援的 schema contract range。

### 4.8 衝突八：歷史訂單狀態是否必須完全由現行狀態機重建

現行 Orders 正式基線規定 lifecycle status 只能由 cancellation、contract completion、deposit、
actual start、assignment-owned service dates、settlement 與 service lock 等根事實投影，caller 不得傳入
target status。這適用一般新訂單，但 113 年等歷史訂單可能只有當時系統保存的「已完成／已取消」
狀態與部分日期，沒有足以重播現行狀態機的完整契約、排班、付款與事件資料。

既有 `scripts/import_historical_orders.py` 證明過去確實採直接初始化：

- `0 → 訂單取消`、`1 → 訂單完成`、`2 → 洽談中`；
- 同列直接 INSERT `orders.status`、`actual_start_date`、`actual_end_date`；
- 只在 order 尚不存在且能唯一找到 client 時寫入；
- 但空值會被映成 `訂單取消`，未知值會回退 `洽談中`，不支援 `訂單成立／服務中`；
- 沒有 lifecycle event、source evidence、version、idempotency receipt 或 outbox；目前 production CLI 已退役。

建議裁決：`HISTORICAL_ASSERTED_INITIAL_STATE`。歷史來源可提供 `source_asserted_status`，作為「當時
系統已存在狀態」的根事實；不要求補造現行狀態機從洽談中一路走到該狀態的虛假事件。但直接寫入
只能發生在受限 `HistoricalOrderAdoption Preview／Apply`：

2026-08-10 人工已確認 historical order source profile v1 只有三種狀態碼：

| Source code | Canonical asserted status |
|---|---|
| `0` | `訂單取消` |
| `1` | `訂單完成` |
| `2` | `洽談中` |

來源不存在文字狀態、其他數字代碼，也不以此 profile 表達 `訂單成立`／`服務中`。空值、非整數、
`0／1／2` 以外的值或同列矛盾證據一律 `review_required`；禁止沿用舊腳本的 blank→取消或
unknown→洽談中 fallback。

2026-08-10 人工另確認 `HIST-STATUS-02`：來源狀態 `0／1` 已足以作為歷史取消／完成根事實。
即使來源缺少實際日期、取消原因、排班或付款明細，仍保留 asserted terminal status；缺值維持
`NULL`／不存在，不補猜、不建立 completeness issue、不投影資料不完整 anomaly，也不要求人工補件。
這項寬容只適用 historical order source profile v1，不得延伸到一般訂單或其他來源。

- 只允許初始化不存在的 order；既有 order 一律 conflict／link／review，不直接改 status；
- 同交易 append immutable historical adoption event，再初始化 `orders.status` current projection、
  lifecycle version、receipt 與 outbox；禁止只有裸 `INSERT orders.status`；
- command 接受的是帶來源版本與證據的 `source_asserted_status`，不是一般管理 API 可任意指定的
  `target_status`；這是 Orders lifecycle unique-writer 規則的 scoped historical exception；
- status mapping 必須由上述 versioned source profile exact 定義；blank、unknown、超出允許 source codes
  或相互矛盾的 code/text 一律 `review_required`，不得回退洽談中或取消；
- 不補造不存在的 contract、deposit、assignment、schedule、payment、cancellation 或 completion event；
- `訂單完成`／`訂單取消` 保留為 asserted terminal history；缺少日期、原因、排班或帳務不影響
  adoption，維持 `NULL`／不存在且不標示不完整；仍不得為了通過現行 event contract 猜值；
- 此 profile 不會產生 `訂單成立`／`服務中`；未來若出現另一來源，必須另建 profile 並重新裁決，
  不能讓過期案件變成今天的 active work；
- lifecycle projection 必須辨識 `lifecycle_origin=historical_assertion`，不得因缺現行 deposit／schedule
  facts 自動降回洽談中，也不得自動觸發今天的義務、通知或排班。

此裁決與目前 Orders 正式基線「caller 不得傳 target status」存在明確衝突；人工確認後必須先同步
更新 Orders Domain baseline 與 lifecycle root facts，才能修改 production code 或 schema。

### 4.9 衝突九：網站上傳檔案是否作為長期稽核資料保存

2026-08-10 人工確認 `UPLOAD-FILE-01`：未來 import 由登入後網站上傳；來源檔只作處理期間的
ephemeral artifact，在匯入完成且資料已 durable materialized 後自動刪除，避免重複占用儲存空間。

上傳檔案通常占用暫存磁碟／物件儲存，不是 DB；DB 禁止保存完整 Excel BLOB。DB 只保留業務必要的
normalized facts、review evidence、source digest、檔名 metadata、manifest、receipt、audit 與 deletion
receipt。若 Domain 的 raw row JSON 本身仍很大，必須另有 bounded payload／retention 決策；刪除 Excel
不會自動減少這類 DB 欄位空間。

刪除判斷不使用模糊的「成功／失敗」，而是回答：伺服器之後是否還需要重新讀取原始 Excel。
「來源已 materialize」精確定義為：所有需要的 workbook bytes 已讀取，而且每個來源列都已成為
terminal row outcome 或 durable review evidence。這時即使某列／某欄有錯，後續也由 DB manifest／
review UI 處理，原 Excel 可以刪除。processing、automatic retry 仍需重讀、或錯誤發生在 durable
evidence 建立前時不得先刪除。

建議裁決：`DELETE_AFTER_DURABLE_MATERIALIZATION`。刪除是 commit 後的獨立 idempotent cleanup，不能
和 DB transaction 假裝原子；刪除失敗不回滾已提交匯入，但必須進 `deletion_pending`、重試並告警。

### 4.10 網站是否直接列舉／執行 `scripts/` 內的 Python 檔案

2026-08-10 人工確認 `IMPORT-UI-01`：管理端新增分頁，名稱為「匯入資料」；有幾個核准的檔案型
import，就顯示幾列說明，每列各自有選檔與上傳按鈕，點擊後觸發該列對應的匯入流程。

「觸發腳本」在正式架構中的意思是呼叫核准的 typed upload endpoint／durable job，不是讓 web process
以使用者輸入組出 `python <path>` 或直接 `subprocess`。頁面不得掃描 `scripts/` 自動產生按鈕；否則新放入
或被竄改的 Python 檔可能意外變成可遠端執行入口。

建議裁決：`EXPLICIT_IMPORT_TYPE_REGISTRY`。由 server-side registry 明列 import type、Domain owner、
capability、endpoint、format profile、size budget 與 UI 文案；UI 只顯示 typed registry view。新增第六種
import 必須先新增規格、owner、endpoint、權限與驗收，不能只把腳本丟進目錄。

## 5. 修正版資料契約

### 5.1 `ImportFieldIssue`

```text
ImportFieldIssue
- error_code: stable codebook identity
- field_name: canonical source／domain field name
- reason_code: stable machine-readable reason
- codebook_version: reason mapping version
- severity: warning | blocker
- write_policy: root_required | cross_field_invariant | optional_allowlisted | source_only
- masked_sample: optional, bounded, privacy-safe
```

人類可讀 `reason` 由 `reason_code + codebook_version` 衍生。原始值不得為了 UI 方便複製到
anomaly snapshot。

### 5.2 互斥 row outcome

成功 committed run 的每列必須且只能屬於：

- `applied`
- `applied_with_omissions`
- `skipped_existing`
- `review_required`
- `ignored_by_policy`

`failed` 是 attempt／batch outcome，不得與 committed row outcomes 混在同一加總。若 batch rollback，
保存獨立 failure attempt，但不得宣稱任何列已 applied。

統一守恆式：

```text
total_input = applied
            + applied_with_omissions
            + skipped_existing
            + review_required
            + ignored_by_policy

db_written = applied + applied_with_omissions
```

`review_item_created_count` 是正交指標：`applied_with_omissions` 也可建立 review item，但不能因此
再計入 `review_required`。這避免目前同一列同時計入 written／reviewed 所造成的假差異。

Finance Import 另保留 occurrence 守恆：

```text
source_row_count = canonical_created_count + duplicate_occurrence_count
```

以上公式只適用對應 contract，不得用 Finance occurrence count 取代 Case／Staff row outcome。

### 5.3 Manifest

每個 import run／batch 至少提供：

- import identity、source digest、format／schema version；
- total input 與五種互斥 row outcome counts；
- review item count、field issue counts by error／field／policy；
- transaction outcome、receipt identity、created／completed time；
- bounded row-result query cursor，不在單一 response 回傳無上限明細。

每筆 row result 至少包含 source row identity、outcome、issue codes、review identity／正式 root
reference（若適用）與 privacy-safe處理建議。

## 6. 流程規格

### 6.1 Finance Import

```text
source file
→ normalize and validate complete canonical row
→ stage canonical fact／occurrence in outer UoW
→ classification／typed dispatch intent
→ receipt＋outbox
→ commit
→ Anomalies projector
```

- canonical fingerprint fields 任一 invalid 時，不產生部分 canonical bank fact；
- 支援的完整 row 才可 staging；duplicate 只新增 occurrence；
- owning Finance Domain apply 失敗時依 outer transaction contract rollback；
- 一般 Query 只讀 manifest／review projection，不觸發 reclassification 或 full scan。

### 6.2 Client BeClass／HCM Case Import

```text
source row
→ archive identity＋normalize＋validate
→ ready → Preview → ApplyCaseImport → owning-Domain roots＋mapping＋receipt＋outbox
→ invalid／ambiguous → immutable review root＋outbox
→ human correction → Preview → ApplyBeClassReview／ApplyCaseImport
```

- invalid row 不直接 insert／update Client、Order；
- BeClass source record 是問卷來源／review evidence，不是 Client／Order SSOT；在 source identity
  有效時，可以保存完整原始快照與依 policy 接受的 source fields，但 promotion 必須走 Case Import；
- 禁止 fabricated date、service term、identity status 或其他可影響業務的預設值；
- existing identity 不做 insert-or-update 覆寫，固定進 typed review；
- Apply 必須驗證 expected version、fingerprint、idempotency 與 fresh owning-Domain facts。

### 6.3 Staff BeClass

在 Staff owning Domain 正式規格補齊前，採 fail-safe 邊界：

- identity／name 或任何 root／cross-field 欄位錯誤時不建立 staff root；
- 只有經人工確認的 `optional_allowlisted` 欄位可 omission；
- omission 必須保存 field issue、row outcome、review／audit evidence；
- 腳本不得自行根據 `NULL` capability 擴張 allowlist；
- File Watcher 應提交 durable typed command，不直接持有跨層 SQL transaction。

## 7. Anomalies 與 UI

### 7.1 Canonical anomaly

- Domain transaction 同交易 append bounded outbox intent；
- projector 以 source identity、version 與 definition code idempotent create／update／resolve／reopen；
- projection failure 不回滾已提交的 Domain root，但必須 retry、保留 checkpoint 並告警；
- anomaly summary 只包含 allowlisted display snapshot；完整 review payload 由 owning review Query 控制；
- direct `system_alerts` writer 與 canonical outbox 不得雙寫同一問題。

### 7.2 UI 正式入口

管理 UI 必須提供已掛載且可導航的：

1. import run／batch manifest 清單；
2. 五種 row outcome 統計與守恆檢查結果；
3. error code、field、reason、masked sample、source row 與 review status 篩選；
4. bounded row detail／review detail；
5. 導向 owning Domain Preview／Apply 的處理入口。

UI 不得只以 `st.json` 或手動輸入 `review_identity` 作正式操作流程，也不得從 summary counts 猜測
缺少的 row outcomes。

## 8. Typed errors、retry 與 conflict

| Code | 行為 |
|---|---|
| `import_source_format_invalid` | fail attempt，不建立 committed row outcome |
| `import_source_format_unknown` | 不猜測 adapter；建立 format review／operator alert |
| `import_source_format_ambiguous` | 多個 layout／sheet 同時匹配；要求人工選擇或新規格裁決 |
| `import_header_contract_changed` | 表頭 fingerprint 未知；不得以相似字串自動對應 root-required 欄位 |
| `import_schema_incompatible` | release／startup fail closed；禁止開始 mutation |
| `import_writer_contract_stale` | writer 支援範圍落後 migration contract；先升級 writer 或走核准 rollback |
| `import_value_representation_unsafe` | 識別碼前導零等資訊已不可逆遺失；進人工 review，不猜值 |
| `historical_cutoff_overlap` | 來源時間落在一般匯入與歷史匯入重疊區；停止並對帳 source identity |
| `historical_identity_ambiguous` | 歷史名稱／舊案號無法唯一映到 canonical identity；人工 resolution |
| `historical_policy_unavailable` | 無法證明當時適用的政策版本；只保存 legacy evidence，不套用現行政策 |
| `historical_side_effect_forbidden` | 歷史 lane 嘗試發送現行通知、重建目前義務或改變 current state；整批阻擋 |
| `import_upload_too_large` | 413；暫存 bytes 立即刪除，不建立 import run |
| `import_upload_content_rejected` | extension／magic／container 不符；立即刪除並回 bounded diagnostics |
| `import_upload_storage_unavailable` | 503；未建立 job；可由使用者固定同一 key 重試 |
| `import_upload_digest_conflict` | 409；同 idempotency key 不同 digest，不得覆寫原 job |
| `import_upload_cleanup_failed` | 匯入 commit 保留；cleanup bounded retry＋storage alert，不重做 import |
| `import_upload_expired` | retry 前 artifact 已依 retention 刪除；要求重新上傳新 command |
| `import_row_invalid` | 建立 review evidence；不自動 retry |
| `import_field_policy_violation` | fail closed；需規格／allowlist 修正 |
| `import_source_identity_conflict` | 409；人工確認來源 |
| `import_candidate_stale` | 409；重新 Preview |
| `import_idempotency_conflict` | 409；不得換 key 規避 |
| `import_review_schema_unavailable` | 503；整個受影響交易 rollback、告警 |
| `import_anomaly_projection_unavailable` | Domain commit 後 bounded retry，不重做 Domain mutation |
| `import_manifest_invariant_failed` | release blocker，不得向 UI 宣稱完成 |

相同 idempotency key＋相同 canonical payload 回原 receipt；相同 key＋不同 payload 固定 conflict。
validation、stale、identity conflict 不自動 retry；只有 deadlock、timeout 或明確 transient storage
failure 可沿用相同 command identity bounded retry。

## 9. 交易、migration 與 live schema

- Source intake／review root／outbox 必須共享明確 Unit of Work；不得 helper 私自 commit；
- owning-Domain Apply 的 root、mapping、receipt、outbox 由唯一 outer UoW commit；
- candidate DB 缺少 BeClass review tables 時，相關 import 必須 fail closed，不得退回 console-only；
- schema 只能走 additive migration、preserved-data rehearsal、candidate validation 與核准 cutover；
- 不得直接 `init_db` 正式資料庫，也不得修改 `fixtures/db_snapshot_v2/v3` 解決 schema 漂移；
- migration 前後驗證 review root、event、receipt、outbox、FK、append-only trigger 與 runtime caller。

## 10. Import script／schema compatibility gate

### 10.1 Active entry 與目前升級需求

`scripts/file_watcher.py` 目前仍會啟動四支 import CLI，因此下表皆是 live release scope，不可因
「目前可 import module」就視為 schema-compatible：

| Entry | 目前相容能力 | 已知缺口／升級方向 |
|---|---|---|
| HCM Client | 完整 validation release 下 clients 欄名相符；sheet 名含 HCM／市府、民國年與部分非標準日期、電話前導 0 修復、typed Case Import apply | 另依賴 order time terms 與 Case Import／bootstrap receipts 等 schema parts，卻無 preflight；timezone-aware datetime 寫 MySQL DATETIME、legacy client date snapshot 與正式 order terms 雙寫仍需裁決；雙列表頭未落實；fabricated defaults 必須退役 |
| Client BeClass | 完整 validation release 下 beclass_records 欄名相符；找第一個非空 sheet、query no mapping、birth date／電話／銀行分行 validation、invalid-row review | review／outbox 與 anomaly 依賴額外 schema parts，舊 candidate 會在 invalid path 才失敗；可能把說明頁或題號列當資料；錯一欄目前整列 `continue`；仍 direct SQL；numeric 帳號可能產生 `.0` 或已遺失前導 0 |
| Staff BeClass | 完整 validation release 下 staff、bank 與 relation 欄名相符；找第一個非空 sheet、兩種銀行分行表頭別名、identity/name conflict review、部分欄位 omission | review／anomaly schema 無 preflight；仍 direct SQL 寫多表且整檔尾端才 commit；dynamic table／column 無 typed allowlist；合併生日 validation 與 parser 不一致；自由文字長度／strict SQL mode、unique race 與 row receipt 尚未驗證 |
| Finance Excel | 完整 validation release 下 ingestion 欄名相符；不依檔名，掃所有 sheet 前 40 列；legacy／Taishin／Sinopac adapter、typed normalization、fingerprint／occurrence／receipt | 正式 File Watcher 未帶 dry-run，卻以 test actor／`test_ingestion` mode 寫入；至少依賴 Finance staging／classification／receipt／attempt schema parts，無 preflight；DECIMAL schema 與 application 正整數 NTD policy 要明定；新 layout、多 sheet 與 invalid amount 策略仍需裁決 |

`scripts/imports/imports_map.md` 是歷史說明，不是現行 runtime SSOT。其中「雙列表頭自動探針」與
目前 HCM／BeClass 實作不一致；「動態過濾不存在 DB 欄位」依第 4.7 節退役；Finance 仍直接寫
`payments` 的敘述也已被現行 typed Finance Import 取代。升級時必須同步更新或明確標成 legacy，
不能繼續把過時 invariant 當驗收證據。

### 10.2 三份獨立版本契約

每次匯入必須保存並驗證三個互不混用的版本：

1. `source_format_version`：外部檔案 provider、layout、sheet selection、header row、header aliases、
   value representation；
2. `canonical_candidate_version`：正規化後 typed candidate、field policy、issue codebook、fingerprint；
3. `target_schema_contract_version`：application port 所需 table／column／type／constraint／trigger／
   migration release range。

來源 adapter 只負責 `external row → CanonicalImportCandidate | ImportFieldIssue`；不得知道實體 DB
欄名。Infrastructure writer 只接受 typed command，並宣告支援的 target contract range；不得重新
解析 Excel 或依 live nullable 欄位決定業務政策。

每個 `SourceFormatProfile` 至少包含：

- stable `format_id`／version、provider 與可接受副檔名；
- sheet selection policy、header search range、必要表頭、核准 aliases 與 unknown-column policy；
- `SourceHeaderFingerprint`、adapter version 與 canonical candidate version；
- 每欄資料表示法：text／identifier／date／datetime／money／enum／free text；
- root-required、optional、source-only 與跨欄規則；
- fixture digest、expected manifest 及 supersedes／retired version。

格式偵測不得依檔名、欄位順序或 fuzzy matching 猜測。未辨識或同時符合多個 profile 時，保存
檔案 digest、privacy-safe header diagnostics 與 operator action，進 format review；不得自動套用「最像」
的 adapter。

### 10.3 Schema 變更分類與 writer 行為

| Schema 變更 | 相容判定 |
|---|---|
| 新增 nullable／有安全 default 的非業務欄位 | 可 backward-compatible，但要加入 drift report；不得藉 default 建立假的 root fact |
| 新增 NOT NULL／無 default、root-required 或 writer-owned 欄位 | incompatible；先升級 canonical command／writer，再 cutover |
| 欄位 rename／split／merge／搬表 | incompatible；additive 雙欄 migration＋backfill＋read/writer cutover，不以 runtime drop column 相容 |
| type、precision、length、enum、check 收斂 | 以 fixture corpus 與 preserved-data rehearsal 證明；可能被截斷或改義即 incompatible |
| unique／FK／trigger／append-only policy 變更 | 重新驗證 idempotency、鎖序、rollback 與既有資料；不可只比 column names |
| projection／衍生欄位變更 | 不得要求 import writer 直接補寫；由 owning projector/backfill 負責 |

Compatibility checker 在 migration rehearsal、release CI、candidate validation 與 runtime startup 各執行一次。
報告至少列出 expected／actual column type、nullability、default、key／FK／check／trigger、migration
release identity、writer supported range 與 blocking reason。startup check 只讀且不可自行 migration。

不能只檢查 table/column 存在。最低 release artifact inventory 包含：HCM 的 clients／orders、order
time terms、Case Import command／receipt／bootstrap dependencies；Client／Staff BeClass 的 core、review、
outbox 與 canonical anomaly dependencies；Finance 的 staging、classification/outbox、ingestion receipt 與
failure-attempt audit。連 failure audit schema 都缺少時，只回一個 `import_schema_incompatible`，不得在記錄
失敗時再次觸發缺表例外而覆蓋原始原因。

### 10.4 開發歷史形成的來源資料風險清單

下列不是可以刪除的 edge cases，而是曾在真實或歷史匯入路徑出現、必須成為版本化回歸的
相容需求：

| 類型 | 已知實例 | 正式處理政策 |
|---|---|---|
| 表頭／版型 | BeClass／HCM 第一列題號、第二列中文表頭；全形／空白；表頭位於第 3／16 列；銀行分行表頭少一個「碼」字 | 只接受 profile 內 exact canonicalized header／alias；記錄 header row 與 fingerprint；未知版型 fail to review |
| Sheet 選擇 | 說明頁在資料頁之前、任意 sheet 名、歷史多 sheet、同 workbook 多個有效 sheet | 由 profile 明定全匯或人工選擇；兩個有效候選不得靜默取第一個 |
| 日期時間 | 西元／民國年、不同分隔符、Excel datetime、`24:00`、閏日、非法日期、文字月份 | 共用 typed parser；保存原始表示；不可解析的 root-required 日期進 review，禁止 `2000-01-01` |
| 識別碼 | 手機、銀行帳號、分行碼、虛擬帳號被 Excel 轉 numeric、尾端 `.0`、前導 0 遺失、全形數字 | 以 text/identifier 讀取；若資訊已不可逆遺失就 `import_value_representation_unsafe`，不得猜補 |
| 金額 | 整數／小數／千分位、空白、`--`、負數、±0、科學記號、極大值、公式 cell | 共用 Decimal parser 與 precision/range policy；所有 Finance adapter 使用相同 blocker/warning 規則 |
| 空白與尾列 | 空列、NaN、公式空字串、合計/footer、只有格式無值 | 由 profile 定義 row predicate；ignored row 也要有可對帳 outcome，不以例外或資料列誤判處理 |
| 身分衝突 | 同身分同姓名、同身分不同姓名、同 query no 不同內容、缺唯一識別 | exact replay 與 identity conflict 分流；不得 insert-or-update 覆寫既有人工資料 |
| 歷史語意 | legacy cancellation code 與 Sinopac 欄位語意不同，直接改 adapter 會改變既有 fingerprint | 舊 adapter／fingerprint version immutable；以 projection/reprocess migration 補正，不重解釋舊 canonical raw fact |
| Unicode／輸出 | NFKC 等價、繁中、換行/tab、emoji、Windows console | canonicalization 明列；報告／manifest strict UTF-8 無 BOM；敏感原值不進 log |

「支援格式差異」不等於無限制容錯。任何 normalization 都必須可逆說明：保留 raw source evidence、
輸出 stable reason code，並能證明未把兩個不同來源值正規化成同一錯誤 identity。

### 10.5 Privacy-safe fixture corpus

真實附件只作受控 format evidence，不直接複製進 repository fixture。建立最小化、去識別 synthetic
workbook，保留欄位 shape／cell type／sheet layout，並為每組附 `manifest.json`：`format_id`、adapter
version、sheet/header、input row identity、expected candidate、issues、row outcome、warnings、fingerprint／
occurrence expectation 與 fixture digest。

最低 corpus：

1. Finance legacy／Taishin／Sinopac 三種既有 shape；
2. header row 1／2／3／16／40／41、全形、空白、alias、缺欄、重複欄、未知欄；
3. 說明頁先於資料頁、任意 sheet 名、HCM 無關鍵字、兩個有效 Finance sheet；
4. 西元／民國／Excel datetime／24:00／閏日／非法日；
5. money 與 identifier 的字串、numeric、前導 0、`.0`、千分位、科學記號與 overflow；
6. blank／NaN／formula empty／footer；
7. identity conflict、同檔 duplicate、跨檔 replay、同秒同備註但 amount／balance 不同；
8. historical cancellation-code recovery 與 fingerprint 不變；
9. `48/43/5`：只有原語意與 fixture identity 經人工確認後才固定逐列 manifest。

Corpus 驗收不只 assert adapter row count；必須一路驗證 normalized payload、row decision、canonical
root／occurrence、receipt/outbox、manifest 守恆、anomaly projection 與 UI query parity。

### 10.6 Upgrade／release gate

每次 schema 或來源 profile 升級依序執行：

```text
caller inventory
→ source/profile compatibility matrix
→ canonical candidate diff
→ target schema compatibility report
→ sanitized corpus Module tests
→ preserved-data migration rehearsal
→ disposable DB Domain E2E
→ candidate dry-run／manifest review
→ writer cutover
→ post-cutover reconciliation／old writer retirement
```

任何 blocker、unknown format、manifest 不守恆或 candidate schema drift 都停止 writer cutover。不得透過
動態 drop 欄位、加假 default、直接 init DB、修改正式資料或放寬測試來通過 gate。

Writer activation 另須滿足：

- 每個 CLI 標記 `production_writer`、`maintenance_read_only` 或 `retired`；只有前者可掛 File Watcher；
- Finance production writer 使用正式 actor／mode，不得沿用 test identity；
- 明確驗證 environment、DB target allowlist 與 schema release，禁止 fallback 到預設 root 密碼或未知 DB；
- File Watcher 接受的 extension 必須有直接 dependency 與 fixture；目前 `.xls` 在未加入 `xlrd` 前不列支援；
- schema／format failure 的檔案保留於 quarantine 並可用同一 source identity 重跑，不靠 5 秒 cooldown 去重；
- disposable schema dry-run／throwaway apply 必須使用與 production 相同的 strict SQL mode，覆蓋長度、
  timezone、Decimal、JSON、NULL、unique、FK 與 trigger；不得對 production DB 做 probe。

### 10.7 Historical Data Import Lane

歷史資料匯入不是一般 import 的舊格式 adapter。一般 import 的目的，是把現在收到的來源資料送入
現行 Domain workflow；歷史 import 的目的，是保存、辨識、對帳過去已發生的事實，而且不得假裝
這些事實在今天重新發生。

目前能力盤點：

| 歷史資料類型 | 現況 | 裁決 |
|---|---|---|
| Historical Finance statements | 已有 legacy format adapter、canonical occurrence 與 typed historical reprocess workflow；舊 reprocess CLI apply 已退役 | 保留正式 typed workflow，不恢復 legacy direct writer；補 source cutoff／side-effect gate |
| Historical Orders | `scripts/import_historical_orders.py` 能讀具名或六欄 legacy layout，並將 0／1／2 直接映成取消／完成／洽談中及寫入實際起訖日；但 blank／unknown 有危險 default，且 CLI production 入口已固定拒絕 | 不得重新開啟原 direct SQL；依第 4.8 節另建 asserted-initial-state HistoricalOrderAdoption Preview／Apply |
| Historical HCM／Client BeClass | 無獨立 historical mode；目前只能走一般 Case Import | 規劃獨立 staging／identity resolution；不得套用 fabricated defaults 或覆寫 current Client／Order |
| Historical Staff | 無獨立 historical mode；一般 Staff BeClass 仍 direct SQL | 先裁決 Staff owner，再建立 historical staff adoption；不得改寫目前 profile、銀行帳戶或 availability |
| Preserved production database | 已有 Global Preserve-data Migration／Cutover Subsystem | 它只做 source DB 唯讀複製、schema migration、backfill 與 cutover；不等於外部歷史 Excel 匯入，也不擁有業務補猜 |

#### 10.7.1 四種操作必須分開

1. `historical_source_import`：匯入過去外部檔案，先成為 immutable staging／review facts；
2. `preserved_database_migration`：完整保留既有 production DB，建立 candidate 並 cutover；
3. `historical_reconciliation`：把已存在的 legacy facts 與 canonical identities／obligations 建立可證明連結；
4. `current_data_correction`：修正現在仍有效的主檔或狀態，必須走 owning Domain correction command。

不得用 historical import 規避 current correction 的權限、expected version、audit 或狀態機，也不得用
schema backfill 暗中完成業務 promotion。

#### 10.7.2 Historical root facts

每個 historical run／row 至少保存：

- source artifact digest、custody reference、format profile、sheet/header、raw row digest；
- `source_effective_at`／業務發生時間、`source_recorded_at`（若可證明）、`ingested_at`；三者不得混用；
- historical cutoff identity、來源系統／機構與當時可證明的 policy／schema version；
- legacy natural keys、canonical identity resolution state、evidence references 與人工決策；
- normalized candidate、unmapped fields、field issues、row disposition、receipt／outbox；
- `side_effect_policy` 與是否允許 promotion，預設 `evidence_only`。

現在的 `created_at`／DB current time 不得冒充歷史業務時間。來源沒有時間、政策版本或 owner 證據時，
保存 `unknown` 與 typed issue；禁止用檔案修改時間、row number、今天日期或現行預設值補猜。

#### 10.7.3 Historical dispositions

歷史 row outcomes 與一般 import 分開，且每列互斥：

- `historical_fact_adopted`：證據充分，建立明確 historical canonical fact/event；
- `linked_to_existing`：只建立 legacy→canonical linkage，不建立第二筆 fact；
- `preserved_legacy_only`：資料有保存價值，但不足以成為 canonical root；
- `review_required`：identity、時間、policy、amount 或 ownership 尚待人工裁決；
- `ignored_out_of_scope`：依核准 policy 不在本次 migration 範圍。

守恆式：

```text
historical_total_input = historical_fact_adopted
                       + linked_to_existing
                       + preserved_legacy_only
                       + review_required
                       + ignored_out_of_scope
```

`failed` 仍屬 attempt outcome；batch rollback 時不得宣稱任何 row 已 adopted。

#### 10.7.4 Identity、時間與 overlap

- 先以來源系統的穩定 key、歷史 alias table 與有效時間區間解析 identity；姓名、電話、同額或 Excel
  row number 只能作 evidence，不能單獨自動配對；
- identity resolution 需保存 resolver／rule version、candidate set、chosen identity、reason、actor 與
  expected version；無唯一解固定 `historical_identity_ambiguous`；
- 每個 source 設定明確 cutoff，例如「截至某日由 historical lane 負責，其後由 general lane 負責」；
- cutoff 前後的 overlap window 必須以 source-event identity 對帳，避免同一事實由歷史檔與一般匯入各寫一次；
- 歷史事件順序依 `source_effective_at`，但 ingestion／audit 順序永遠 append-only，不回填或竄改既有
  event `created_at`。

#### 10.7.5 Current state 與副作用隔離

Historical lane 預設只建立 staging、history event、linkage、receipt 與 anomaly，不得自動：

- 發送 LINE／Email／簡訊或建立「新案件」通知；
- 以現行價格、資格、補助、薪資或排班政策重算過去資料；
- 將已結案／取消的歷史案件轉成今天的 active order；
- 覆寫目前 Client／Staff profile、銀行帳號、聯絡方式、availability 或人工修正；
- 建立今天的新應收／應付、重新開啟已結算 ledger，或改寫歷史付款／排班；
- 因缺舊欄位而套用現行 schema default。

若業務確實要求形成 canonical history，必須由 owning Domain 的 `HistoricalAdoption Preview／Apply`
明列會建立的 root／event、current projection impact、suppressed side effects、conflict 與 rollback。
會影響 current state 的項目改走獨立 correction／rebuild command，不藏在 import transaction。

#### 10.7.6 執行架構與順序

```text
offline source inventory／custody
→ immutable archive＋format detection
→ historical staging（不寫 current roots）
→ typed normalization＋issue capture
→ identity/time/policy resolution
→ Preview：adopt／link／preserve／review／ignore
→ human approval＋plan fingerprint
→ owning-Domain HistoricalAdoption Apply
→ receipt／outbox／reconciliation
→ current-state no-impact verifier
```

歷史 writer 必須標為 `restricted_historical_migration`，不能掛入一般 File Watcher。Apply 只在明確
maintenance window、write freeze／stale check、candidate或核准 target DB 上執行；預設 dry-run。

匯入順序依 dependency graph，而不是依檔名：identity/master evidence → Case／Staff linkage → Orders
historical facts → Assignment／Schedule history → Finance／Payroll linkage。任一 downstream row 找不到唯一
upstream identity 時進 review，不建立 orphan 或用名稱補關聯。

#### 10.7.7 Historical acceptance corpus

除了第 10.5 節一般格式 corpus，歷史 lane 必須另驗：

1. 同一人／案件跨年代使用不同案號、姓名、電話或銀行帳號；
2. 來源只有姓名、缺 stable key，或同名多人的 ambiguous resolution；
3. 日期早於現行 schema、時區未知、只知道月份、事件順序互相矛盾；
4. 當時政策已退役或無法證明，不得套用現行資格／價格／狀態；
5. historical file 與 general import overlap、改名重送與部分批次重跑；
6. current profile 已被人工更新，歷史 row 不得覆寫；
7. 已結算 Finance／Payroll／Schedule history 不得被重新開啟或重算；
8. Preview 核准後 source/canonical facts 漂移必須 stale；
9. batch 中一列 ambiguous 時依核准 strict／partial policy 行為，manifest 仍守恆；
10. no-impact verifier 證明通知、current state、open obligations 與 current projections 沒有非預期差異。

### 10.8 Authenticated Web Upload／File Lifecycle

目前 Finance 已有網站上傳原型：Streamlit `file_uploader` 經 typed API client POST multipart 到
`/api/v1/finance-import/workbooks/ingest`；後端限制 20 MiB、將內容寫入 OS temporary file，ingestion
結束後在 `finally` unlink。此能力只涵蓋 Finance 的同步 request scope，不代表 HCM／BeClass／Staff／
Historical Orders 已完成，也尚未形成 crash recovery／deletion receipt 的共用契約。

#### 10.8.1 邊界與權限

- Browser／Streamlit 只選檔、顯示 upload/job/manifest typed results，不解析 Excel、不直接寫 DB；
- API 驗證已完成 password＋TOTP 的 AdminPrincipal，並使用 bounded-domain capability，例如
  `case.import.upload`、`staff.import.upload`、`finance.import.upload`；historical adoption 另需
  `orders.historical_import.manage`，不得只因能上傳一般名冊就能寫歷史狀態；
- 每個 endpoint 對應單一 bounded domain client；共用 multipart transport／auth，不共用業務 parser；
- filename 只作 display metadata，禁止組 path；server 產生 upload identity 與不含原檔名的 storage key；
- audit 保存 actor、capability、digest、size、format、batch、結果與 deletion receipt，不保存檔案 bytes、
  password、TOTP、session token 或未遮罩個資。

#### 10.8.2 Upload root facts／狀態機

DB 不保存 workbook BLOB。`ImportUpload` root facts 至少包含：

- `upload_identity`、domain／purpose、original filename（bounded）、byte size、detected media／format；
- SHA-256 digest、actor、received time、idempotency key、command fingerprint；
- ephemeral storage reference（不可公開下載）、storage encryption／key version（若使用 object storage）；
- linked import run／batch、lifecycle timestamps、deletion attempts／receipt；
- failure code、retry eligibility 與 retention deadline（若尚未刪除）。

```text
received
→ validating
→ staged
→ processing
→ materialized
→ deletion_pending
→ deleted

received／validating／staged／processing
→ failed_retryable | failed_terminal
```

- `materialized` 表示 DB root／review／row receipts 已 commit，不等於所有列成功套用；
- `deleted` 只表示 ephemeral source bytes 已不存在，不刪除 import facts、manifest、review、audit；
- upload exact replay 依 digest＋purpose＋idempotency 回原 job／receipt，不另存第二份檔案；
- 同 idempotency key 不同 digest 固定 conflict；同 digest 不同明確 command 依 Domain policy link／review；
- deletion worker 使用 stable cleanup identity；檔案已不存在視為成功 replay，但仍驗證 storage reference
  屬於核准 temporary root／bucket prefix。

#### 10.8.3 儲存與刪除政策

1. 上傳先串流寫入 server-managed temporary storage，同時計算 digest；不得把整檔 base64／BLOB 寫 DB；
2. 驗證 extension、magic bytes／container、size、sheet/header budget、壓縮膨脹量與核准 parser；目前未具
   dependency／fixture 的 `.xls` 不接受；
3. 同步小檔可在 request 內 materialize，並於 commit／terminal failure 後 `finally` cleanup；
4. 非同步或大型檔案由 durable job lease storage reference；worker 完成 DB commit 後 append cleanup
   intent，再由 idempotent cleanup worker 刪除；
5. `materialized`（包含單欄 omission、整列 `review_required`、duplicate／ignored）立即排入刪除，
   不等待人員完成 review；
6. 無法辨識格式、空檔、超量等 terminal upload rejection 不會自動 retry，立即刪除 server temp copy，
   使用者保留自己電腦上的原檔並依錯誤說明修正後重新上傳；
7. retryable infrastructure failure 的檔案不能在 worker 尚需讀取時刪除；保留期限與到期後是否要求
   重新上傳仍待人工確認；
8. process crash／host restart 後由 sweeper 查 `deletion_pending` 與 expired nonterminal uploads；不得只靠
   Python `finally`；
9. deletion 失敗保存 typed cause、attempt count、next retry，不回滾 import；超過門檻建立 storage alert；
10. operator 可重試 cleanup，但不得從一般 UI 下載原始檔或手動輸入任意 filesystem path 刪除。

#### 10.8.4 安全與資料最小化

- 限制每檔大小、同帳號／IP concurrency、每日容量及 request timeout；rate limit 不以檔名作 identity；
- 拒絕 path traversal、雙副檔名、macro-enabled／未知 container、zip bomb、公式／external link 等未核准
  workbook capability；parser 必須在非執行模式開啟；
- temporary directory／bucket private、最小權限、不可由 web server static route 存取；正式環境依部署
  policy使用 at-rest encryption；
- log、error、metrics 不輸出 raw cells；UI 只顯示 masked diagnostics；
- DB 的 raw row／source payload 需按 Domain 定義必要欄位、大小上限及 retention，不能因「已刪檔」就
  無限制複製完整 workbook JSON；
- account disable、session expiry 不取消已 commit 的 job，但 job 執行時驗證提交 actor／capability
  snapshot與 revocation policy；敏感 Historical Apply 仍需 fresh authorization。

#### 10.8.5 驗收

1. success、all-review 與 mixed outcomes 完成 materialization 後檔案皆刪除，DB manifest 可查；
2. empty／oversize／wrong magic／unknown format 在無 durable job 時刪除暫存檔；
3. DB rollback、worker crash、API timeout、delete permission denied、host restart 後不遺失 job 且 cleanup
   最終收斂；
4. delete replay、同檔重送、同 key 不同檔、同檔不同 purpose 行為符合 idempotency contract；
5. unauthorized、capability insufficient、disabled account、expired session、TOTP 未完成均不能建立 upload；
6. filename traversal、macro／container、zip bomb、超量並行與大檔被 fail closed；
7. storage scan 證明 terminal uploads 無 orphan bytes；DB scan 證明無 workbook BLOB／base64；
8. UI 顯示 received／processing／materialized／deletion pending／deleted 與 typed failure，不把 HTTP timeout
   誤報為匯入失敗；
9. HCM、Client BeClass、Staff、Finance、Historical Orders 各有 multipart→Domain→manifest→cleanup E2E。

#### 10.8.6 業務場景與刪除判斷

刪除 gate 使用 `source_bytes_required`，不直接看「有沒有錯誤」：

```text
source_bytes_required =
    尚未讀完 workbook
    OR 尚有來源列沒有 durable outcome／review evidence
    OR automatic retry 需要重新讀取同一份檔案
```

只有 `source_bytes_required = false` 才能刪除 server temp copy。

| 業務場景 | 資料結果 | 是否刪除上傳檔 | 原因 |
|---|---|---|---|
| HCM 100 筆都合法 | 100 筆各自得到 applied／receipt | 刪除 | 每列已有 durable outcome，不再需要 Excel |
| Client BeClass 某筆 Email 格式錯誤，Email 屬核准 optional 欄位 | 該筆以 `applied_with_omissions` 寫入其他合法欄位；保存 Email field issue | 刪除 | 單欄錯誤已被 durable 記錄，後續不需重讀原檔 |
| HCM 某筆 `case_no` 空白 | 該筆不建立 Client／Order，建立 `review_required`；其他列照核准 transaction policy處理 | 刪除 | 錯列與原因已在 review queue；人員從 UI 補正，不靠原 Excel 重跑 |
| Client BeClass 某筆電話錯誤 | 依 field policy omission 或整列 review；保存 row／field issue | 刪除 | 無論 omission 或 review，只要 evidence 已 materialize 就完成來源處理 |
| Staff 某筆銀行分行碼錯誤 | Staff root 若符合 policy 可建立；銀行帳戶整組不寫並保存 issue | 刪除 | 銀行群組的處置已確定，原檔不再是待執行工作 |
| 歷史訂單 100 筆中一筆 status 空白 | 該筆 `review_required`；合法 0／1／2 依 HistoricalAdoption plan；不得把空值當取消 | 刪除 | status 空值是業務資料問題，不是系統重試；review evidence 已保存 |
| 歷史訂單 status=1，但日期／付款明細空白 | 保留 `訂單完成`，其他缺值為 NULL，不標示不完整 | 刪除 | 依 `HIST-STATUS-02` 已是合法 terminal historical fact |
| 同一檔案重複上傳 | 回原 job／receipt或列為 skipped existing，不建立第二份 root | 刪除新 temp copy | digest／idempotency 已完成判定，第二份 bytes 沒有用途 |
| Excel 第一頁是說明頁，但能依已核准 profile 找到唯一資料 sheet | 正常解析資料 sheet；說明頁依 policy ignored | 刪除 | 所有 sheet／rows 都已有處置 |
| Excel 表頭完全未知，無法選 adapter | 回 terminal `import_source_format_unknown`，不匯入任何正式資料 | 刪除 server temp copy | 這不是自動 retry；使用者依診斷修正或申請新增 format profile 後重新上傳原檔 |
| 某列因 DB deadlock／短暫斷線而尚未 commit | job 為 `failed_retryable`，尚無 terminal outcome | 暫不刪除 | automatic retry 還需要同一份 bytes；成功或 retention 到期後再刪除 |
| schema 缺表／版本不相容 | 整批 fail closed，沒有開始 row mutation | 依 retry policy暫存 | 若部署修復後會自動 retry則保留；若判定 terminal則刪除並要求重傳 |
| 匯入已 commit，但刪檔權限錯誤 | DB 結果保持完成，upload 為 `deletion_pending` | cleanup worker持續刪除 | 不為清理失敗重做匯入；超過門檻告警 |
| API timeout，但後端 job仍在執行 | UI 查同一 job identity，不重新上傳 | 暫不刪除 | timeout 不是業務結果；worker materialize 後才刪除 |

重點是「單筆／單欄錯誤」通常不等於保留整份檔案。只要系統已將錯誤欄位、來源列 identity、
處置理由與人工補正入口 durable 化，Excel 就完成它的 transport 任務。只有系統故障導致 bytes 尚未
完整轉成可重試的 DB evidence 時，才需要暫時保留。

### 10.9 管理端「匯入資料」分頁

#### 10.9.1 導航與頁面責任

- 新增獨立頁面，顯示名稱固定為 `匯入資料`（可搭配圖示，但文字不得改成「資料庫工具」）；
- 頁面只負責列出核准 import types、選檔、提交、顯示 job／manifest／review link；
- 不解析 Excel、不決定欄位政策、不顯示 filesystem path、不直接執行 Python script；
- 頁面受全域 LoginGate 保護；未完成 password＋TOTP 不渲染 upload controls；
- 每列依 principal capability 顯示可上傳或唯讀／無權限狀態，後端仍須重新授權；
- 現有 Finance `file_uploader` 從 Finance panel 移到本頁作為唯一 upload入口；Finance Preview／Apply、
  correction 與 historical reprocess 仍留在 Finance Domain 頁面，本頁提供批次連結；
- File Watcher 與 web upload 在 cutover 後不得同時作 production writer。

#### 10.9.2 初始五列 registry

| 顯示名稱 | 說明 | Import type | 後端流程 | 權限 | 初始格式 |
|---|---|---|---|---|---|
| HCM 客戶資料 | 匯入 HCM 客戶與案件來源資料；必要欄位錯誤進 review | `case_hcm` | Case Import intake／review／bootstrap job | `case.import.upload` | `.xlsx` |
| Client BeClass 客戶問卷 | 匯入客戶 BeClass 問卷；不直接覆寫 Client／Order SSOT | `case_beclass` | Case Import source／review job | `case.import.upload` | `.xlsx` |
| Staff BeClass 服務人員 | 匯入服務人員 profile、銀行群組與核准關聯集合 | `staff_beclass` | Staff Import intake／review job | `staff.import.upload` | `.xlsx` |
| 銀行流水 | 匯入 legacy／Taishin／Sinopac 對帳單，建立 Finance batch | `finance_statement` | Finance ingestion job | `finance.import.upload` | `.xlsx` |
| 歷史訂單 | 匯入歷史訂單 0／1／2 asserted status；空值／其他值進 review | `historical_orders_v1` | HistoricalOrderAdoption intake／Preview job | `orders.historical_import.manage` | `.xlsx` |

`reprocess_finance_import_batch.py`、schema migration、backfill、cleanup 或 anomaly rescan 沒有新的來源檔，
不是本頁的一列；它們保留在各自的 maintenance／Domain workflow。

#### 10.9.3 每列 UI contract

每列固定包含：

1. import 顯示名稱與一行業務說明；
2. 支援格式、單檔大小與格式 profile link；
3. 該列獨立 `file_uploader`，key 以 stable import type 區隔；
4. `上傳並匯入` 按鈕；沒有選檔、無權限或已有同列 submit in-flight 時 disabled；
5. 最近一次提交的 upload／job status、進度、batch identity；
6. terminal result：總列數、applied、omission、review、skipped、ignored 與 cleanup state；
7. `查看匯入結果`／`前往待覆核`／`前往 Finance Preview` 等 typed navigation action。

按鈕按下後：

```text
fresh capability check
→ validate selected file metadata
→ reuse or create stable idempotency／correlation identity
→ multipart upload to row-specific endpoint
→ receive UploadJobView
→ bounded polling／manual refresh
→ show manifest and cleanup result
```

UI 不顯示 `st.json` 作正式結果，不以 HTTP request timeout 清除 job identity，也不因 rerender 產生新的
idempotency key。使用者重新整理頁面後，仍可由 server query 恢復未完成 job。

#### 10.9.4 業務互動範例

- 使用者在「HCM 客戶資料」列選檔，只會呼叫 Case HCM endpoint，不可能觸發銀行或 Staff parser；
- 使用者在「歷史訂單」列上傳 status 0／1／2 檔案，系統顯示 asserted-status intake 結果；不會呼叫
  一般 Case bootstrap 把歷史案件預設成洽談中；
- 一個檔案中有單欄錯誤，該列結果顯示 omission／review count，整份來源 materialized 後仍自動刪檔；
- 上傳後關閉瀏覽器，server job 繼續執行；再次登入可查相同 job，不必重傳檔案；
- 使用者沒有 `finance.import.upload` 時，銀行列顯示無權限且按鈕 disabled；直接呼叫 API 仍回 403；
- 同一列快速連點只建立一個 command；不同列使用不同 import type，不共用 idempotency scope；
- upload cleanup 失敗時顯示「資料已匯入，暫存檔清理重試中」，不得誤報匯入失敗。

#### 10.9.5 UI 驗收

1. 導覽列只出現一個「匯入資料」，五列順序與 registry 一致；
2. 每列選檔與按鈕 state 隔離，HCM 檔不會出現在其他列；
3. 五種 import type 各自命中唯一 endpoint／capability／typed response；
4. 未登入、TOTP 未完成、capability 不足、session expired 均無法提交；
5. double-click、rerender、refresh、timeout、browser close/reopen 不重複建 job；
6. row field issue、row review、system retry、terminal rejection、cleanup pending 使用不同文案；
7. terminal job 的 manifest counts 守恆，cleanup state 與 import result 分開；
8. Finance 舊 upload UI 與 File Watcher production writer 已退役，caller scan 無第二入口；
9. Streamlit render 只接收 Pydantic `ImportTypeView`、`UploadJobView`、`ImportManifestView` 與 typed errors，
   不讓 raw dict 穿透。

## 11. 實作待辦

### P0：決策與立即風險收斂

- [ ] `IMP-P0-01` 人工確認第 4 節十項衝突裁決；
- [ ] `IMP-P0-02` 將本 ADR 裁決同步到 Finance Import、Case Import、Anomalies 與 Staff owning Domain 正式基線；
- [ ] `IMP-P0-03` inventory File Watcher／CLI／API／UI 的 active import entry 與 writer；
- [ ] `IMP-P0-04` 停止 HCM fabricated defaults 寫正式 root，改走 invalid-row review；
- [ ] `IMP-P0-05` 定義 Staff `root_required`／`cross_field_invariant`／`optional_allowlisted` 欄位表；
- [ ] `IMP-P0-06` 依核准 migration chain 補齊 current candidate BeClass review schema；
- [ ] `IMP-P0-07` schema 未就緒時新增 typed fail-closed 與 startup／operator warning。
- [ ] `IMP-P0-08` 人工指定 staff identity／profile 的 canonical Domain owner；不得預設為 Staff Payables；
- [ ] `IMP-P0-09` fresh inventory 四支 active CLI、File Watcher、API、UI、migration release 與實際 target schema；
- [ ] `IMP-P0-10` 對 HCM／BeClass 雙列表頭、sheet selection 與 Finance multi-match 取得人工格式裁決；
- [ ] `IMP-P0-11` 將 `INV-IMPORT-03` 標為退役，禁止 runtime 靜默略過 target columns。
- [ ] `IMP-P0-12` 修正 Finance File Watcher 正式 writer 的 test actor／mode 漂移；
- [ ] `IMP-P0-13` 移除未具直接 dependency／fixture 的 `.xls` 支援宣告，或正式加入並驗收 `xlrd`；
- [ ] `IMP-P0-14` 禁止 import DB 設定 fallback 到預設帳密／未知 database，加入 environment＋target allowlist。

### P1：共用 typed contract

- [ ] `IMP-P1-01` 實作 `ImportFieldPolicy`、`ImportFieldIssue`、versioned issue codebook；
- [ ] `IMP-P1-02` 實作互斥 `ImportRowOutcome` 與守恆 validator；
- [ ] `IMP-P1-03` 定義 bounded manifest、row result、review query Pydantic contracts；
- [ ] `IMP-P1-04` 為姓名、電話、身分證、帳號、銀行內容定義 masking／allowlist tests；
- [ ] `IMP-P1-05` 移除 console-only skip reason，所有 outcome 保存 typed reason identity。
- [ ] `IMP-P1-06` 實作 `SourceFormatProfile`、header fingerprint、versioned aliases 與 unknown-format diagnostics；
- [ ] `IMP-P1-07` 實作共用 typed date／datetime／money／identifier／blank parser；
- [ ] `IMP-P1-08` 定義 `ImportSchemaContract` 與 writer supported range。

### P2：Case／Staff import 收斂

- [ ] `IMP-P2-01` Client BeClass／HCM 統一走 Source Intake／Review／Preview／Apply；
- [ ] `IMP-P2-02` Staff BeClass 從 direct SQL 搬到 typed application＋owning-Domain port；
- [ ] `IMP-P2-03` optional omission 只接受已確認 allowlist，並產生 `applied_with_omissions`；
- [ ] `IMP-P2-04` identity／cross-field error 不建立正式 root；
- [ ] `IMP-P2-05` duplicate／ambiguous identity 進 review，不靜默 overwrite；
- [ ] `IMP-P2-06` File Watcher 只建立 durable job，移除直接啟動 mutation script 的正式路徑。
- [ ] `IMP-P2-07` 修正 Client／Staff BeClass numeric account、`.0`、前導 0 與不可逆遺失的 review policy；
- [ ] `IMP-P2-08` 修正 Staff 合併生日欄 validation／normalization 漂移；
- [ ] `IMP-P2-09` HCM／BeClass 補 versioned header/sheet detector，不再取第一個非空 sheet 或只依名稱猜測。
- [ ] `IMP-P2-10` 裁決 HCM timezone-aware source 寫 MySQL DATETIME 的 canonical time contract；
- [ ] `IMP-P2-11` 裁決 clients legacy date snapshots 與 orders typed terms 的 ownership，停止未定義雙寫；
- [ ] `IMP-P2-12` Staff dynamic relation writer 加 typed table／column allowlist、長度與 strict-mode validation。

### P3：Anomalies 單一路徑

- [ ] `IMP-P3-01` Finance／Case／Staff 各自產生 bounded anomaly desired state；
- [ ] `IMP-P3-02` 退役 import scripts 對 `system_alerts` 的 direct writer；
- [ ] `IMP-P3-03` 驗證 outbox replay、checkpoint、duplicate delivery、resolve／reopen；
- [ ] `IMP-P3-04` anomaly snapshot 只含 code、field、masked sample、row identity 與 review link；
- [ ] `IMP-P3-05` projection failure 告警與人工 retry 入口完成。

### P4：Manifest／UI 對帳閉環

- [ ] `IMP-P4-01` 後端 manifest query 回傳五種互斥 outcome 與 invariant result；
- [ ] `IMP-P4-02` 完成 review-row pagination、field／code／status filter；
- [ ] `IMP-P4-03` 掛載 Finance Import 對帳頁與 BeClass／HCM／Staff review queue；
- [ ] `IMP-P4-04` 使用獨立 bounded API clients 與 typed views，不讓 raw dict 進 render function；
- [ ] `IMP-P4-05` UI 顯示 total、written、skipped、review、ignored 的明確釋義；
- [ ] `IMP-P4-06` 每筆 review 可導向 owning Domain Preview／Apply，不由 UI 直接修 DB。

### P5：Migration 與回歸

- [ ] `IMP-P5-01` 建立 BeClass review schema 的 preserved-data rehearsal／rollback evidence；
- [ ] `IMP-P5-02` 找回並驗證 `48/43/5` fixture identity，或取得人工裁決改用 versioned synthetic fixture；
- [ ] `IMP-P5-03` 建立 import manifest invariant verifier；
- [ ] `IMP-P5-04` source scan 證明舊 `services.*`、direct import `system_alerts` writer 與 orphan UI caller 已收斂；
- [ ] `IMP-P5-05` 產出 current candidate 與正式 schema 的 drift report；
- [ ] `IMP-P5-06` 以 `.venv\Scripts\python.exe -m pytest -W error` 執行分層驗收。
- [ ] `IMP-P5-07` 建立第 10.5 節 privacy-safe corpus 與逐列 golden manifest；
- [ ] `IMP-P5-08` Finance legacy cancellation-code recovery／fingerprint immutability 加入永久回歸；
- [ ] `IMP-P5-09` 四支 active entry 分別完成 script subprocess＋disposable MySQL E2E；
- [ ] `IMP-P5-10` CI／candidate startup 產出 schema compatibility report，blocker 時阻止 writer 啟動；
- [ ] `IMP-P5-11` 更新或退役 `scripts/imports/imports_map.md` 的漂移敘述。
- [ ] `IMP-P5-12` candidate gate 比對 migration release identity，不以「table 存在」冒充 schema compatible；
- [ ] `IMP-P5-13` schema failure 保留原始 typed cause、quarantine source 並驗證可重跑，不得混成 row validation。

### P6：Historical Data Import

- [ ] `IMP-P6-01` 盤點歷史 HCM／BeClass／Staff／Orders／Finance artifacts、來源期間、custody、個資與資料 owner；
- [ ] `IMP-P6-02` 為每個來源人工確認 cutoff、overlap window、stable keys、當時 policy/schema version 與 out-of-scope 規則；
- [ ] `IMP-P6-03` 將 historical source import、preserved DB migration、reconciliation、current correction 四種 command 完全分離；
- [ ] `IMP-P6-04` 定義 historical run／row／identity resolution／adoption plan／receipt／outbox schema；
- [ ] `IMP-P6-05` 建立 `source_effective_at`、`source_recorded_at`、`ingested_at` 三時間契約與 unknown policy；
- [ ] `IMP-P6-06` HCM／Client BeClass 建立 evidence-only staging 與 Case HistoricalAdoption Preview／Apply；
- [ ] `IMP-P6-07` Staff owner 裁決後建立 Staff HistoricalAdoption；禁止覆寫 current profile／bank／availability；
- [ ] `IMP-P6-08` 以 typed Orders historical adoption 取代已退役 `scripts/import_historical_orders.py` direct SQL，不重新開放舊 CLI writer；
- [ ] `IMP-P6-09` Finance historical workflow 補 cutoff、overlap、policy version、current-state no-impact 與 legacy CLI retirement gates；
- [ ] `IMP-P6-10` 建立 identity alias／candidate／manual resolution workflow，姓名與電話不得單獨自動配對；
- [ ] `IMP-P6-11` 建立 side-effect suppressor 與 verifier，阻止通知、現行政策重算、current state／open obligation 非預期變更；
- [ ] `IMP-P6-12` 建立第 10.7.7 節 historical corpus、逐列 manifest、stale／replay／overlap／rollback E2E；
- [ ] `IMP-P6-13` 歷史 writer 標為 restricted maintenance，預設 dry-run，要求 maintenance window／write freeze／target allowlist；
- [ ] `IMP-P6-14` 產出 adoption 後 reconciliation receipt 與 unresolved review queue，未唯一還原者永久保留 legacy evidence。
- [ ] `IMP-P6-15` 實作已確認的 v1 mapping：0→取消、1→完成、2→洽談中；blank／unknown 一律 review；
- [ ] `IMP-P6-16` 建立 immutable HistoricalOrderAdoption event、`lifecycle_origin`、initial projection、version、receipt 與 outbox；
- [ ] `IMP-P6-17` lifecycle projection 保留 asserted terminal history；缺日期／原因／排班／付款不降級、不標示不完整，也不觸發 current side effects；
- [ ] `IMP-P6-18` 驗證 v1 不接受 `訂單成立／服務中`；未來新增來源 profile 必須另案裁決；
- [ ] `IMP-P6-19` 以測試鎖定舊 0／1／2 mapping 的可追溯相容行為，並證明 blank、unknown、矛盾 status 進 review。

### P7：Authenticated Web Upload／Ephemeral Cleanup

- [ ] `IMP-P7-01` 定義 ImportUpload root、state machine、storage port、cleanup intent／receipt 與 typed errors；
- [ ] `IMP-P7-02` 建立共用 secure multipart transport，但 HCM／BeClass／Staff／Finance／Historical Orders 各維持 bounded-domain endpoint/client；
- [ ] `IMP-P7-03` 建立 `case.import.upload`、`staff.import.upload`、`finance.import.upload`、`orders.historical_import.manage` capabilities 與 password＋TOTP auth gate；
- [ ] `IMP-P7-04` 禁止 workbook BLOB／base64 入 DB；定義 filename、digest、size、format、actor 與 deletion receipt schema；
- [ ] `IMP-P7-05` 將 HCM、Client BeClass、Staff、Historical Orders 從 File Watcher／CLI 正式入口搬到 authenticated upload＋durable job；
- [ ] `IMP-P7-06` 收斂 Finance 現有同步 temporary-file cleanup，補 lifecycle、crash recovery、deletion receipt 與 domain-specific capability；
- [ ] `IMP-P7-07` 實作 streaming size／digest、extension＋magic/container、zip-bomb／macro／external-link safety checks；
- [ ] `IMP-P7-08` 由 `source_bytes_required` 統一判斷 cleanup；單欄 omission、row review、duplicate、ignored materialized 後不保留原檔；
- [ ] `IMP-P7-09` 實作 deletion worker／sweeper、retry、retention expiry、storage alert 與 operator retry；
- [ ] `IMP-P7-10` 定義 retryable failure retention；到期刪除後回 `import_upload_expired` 並要求重新上傳；
- [ ] `IMP-P7-11` 對 DB raw row／source payload 設 Domain-specific size／retention budget，避免刪除 Excel 後仍無限制占用 DB；
- [ ] `IMP-P7-12` UI 顯示 upload/job/import/cleanup 分離狀態，不把 request timeout 當作匯入失敗；
- [ ] `IMP-P7-13` 建立 unauthorized、oversize、wrong-magic、crash、rollback、delete failure、restart、replay 與 orphan scan E2E；
- [ ] `IMP-P7-14` 完成 File Watcher writer retirement／quarantine migration，避免網站與 watcher 雙重匯入同一檔案。
- [ ] `IMP-P7-15` 將第 10.8.6 節每個業務場景做成 upload lifecycle／cleanup acceptance tests。
- [ ] `IMP-P7-16` 完成 Finance CLI／File Watcher caller replacement、entrypoint review 與 focused
  regression 後，退役 `scripts/imports/import_finance_excel.py` 的 active adapter 身分；退役前維持
  typed ingestion、stable idempotency 與 dry-run 零寫入邊界。

### P8：管理端「匯入資料」分頁

- [ ] `IMP-P8-01` 定義五種 allowlisted `ImportTypeView` registry，不掃描／執行任意 scripts；
- [ ] `IMP-P8-02` 新增 `匯入資料` 導航頁與全域 LoginGate；未完成 TOTP 不建立 upload controls；
- [ ] `IMP-P8-03` 實作五列說明、獨立 file uploader、`上傳並匯入` 按鈕及 capability state；
- [ ] `IMP-P8-04` 建立 Case HCM、Client BeClass、Staff BeClass、Finance、Historical Orders 五個 bounded upload endpoint/client；
- [ ] `IMP-P8-05` 實作 stable submit identity、double-click guard、rerender／timeout recovery 與 job query；
- [ ] `IMP-P8-06` 顯示 typed job progress、manifest counts、review／Domain navigation 與 cleanup state；
- [ ] `IMP-P8-07` 將現有 Finance `file_uploader` 搬到新頁，Finance panel 只保留 Preview／Apply／correction／reprocess；
- [ ] `IMP-P8-08` 退役 File Watcher production writer 與重複 upload caller，避免同檔雙重匯入；
- [ ] `IMP-P8-09` UI clients 依 bounded domain 拆分並共用 authenticated multipart transport，不讓 raw dict 進 render；
- [ ] `IMP-P8-10` 完成五列 endpoint/capability、按鈕隔離、replay、browser recovery、manifest／cleanup UI E2E。

## 12. 分層驗收標準

| 層級 | 必須證明 |
|---|---|
| Module | source profile/header detection、typed parsers、field policy、issue codebook、masking、互斥 outcome、守恆式、fingerprint deterministic |
| Subsystem | normalize／review／preview／apply、schema compatibility、same-key replay、different-payload conflict、stale、retry、projection recovery |
| Domain | sanitized corpus＋disposable MySQL 驗證 invalid row 不污染 root、optional omission、FK／unique／append-only、rollback、manifest parity |
| Global | migration rehearsal／candidate gate 與 File Watcher／CLI／API → Domain → outbox → Anomalies → mounted UI 的完整流程與所有列可對帳 |

最低場景：

1. 一個 root-required 欄位錯誤：只產生 review evidence，不建立正式 root；
2. 一個 allowlisted optional 欄位錯誤：正式 root 成功、錯欄省略、outcome 為
   `applied_with_omissions`；
3. 同列多個跨欄錯誤：整組阻擋，不產生拼裝 root；
4. duplicate source exact replay：回原 receipt／`skipped_existing`，不產生第二個 root；
5. 同 identity 不同 payload：conflict；
6. DB 或 audit/outbox failure：同交易 rollback；
7. projector failure：Domain root 不回滾，重試後只出現一筆 current anomaly；
8. UI 的五種 outcome 加總等於 total input，且每列可追到 reason／review／root reference；
9. privacy test 證明 raw sensitive sample 不出現在 log、anomaly summary、API error 或 UI table；
10. schema 尚未 cutover 時 import 明確 fail closed，不退回 console-only 路徑。
11. 雙列表頭、說明頁在前、未知 alias 與多個匹配 sheet 依核准 policy 處理，不靜默選第一個；
12. numeric identifier 已遺失前導 0 時進 review，不自行補值；
13. schema rename／type／constraint drift 在 mutation 前被 compatibility gate 阻擋；
14. 三種 Finance format 與 HCM／Client BeClass／Staff corpus 逐列 manifest 與 DB receipt 一致；
15. legacy adapter／fingerprint version 重播不因新版 mapping 產生第二筆 canonical fact。

## 13. 完成定義

只有同時符合以下條件，ADR 狀態才可由 `Amended Proposed` 改為 `Accepted／Implemented`：

- 第 4 節衝突已人工裁決並同步正式基線；
- P0～P8 無未完成必要項；
- 五種 row outcomes 對所有 active import entry 皆互斥且守恆；
- canonical anomaly 是唯一新寫入路徑；
- 對帳／review UI 已掛載且通過 Global E2E；
- current candidate schema 與 release manifest 一致；
- 每個 active writer 的 source／candidate／target 三份 compatibility contract 均有版本與可重跑報告；
- HCM／Client BeClass／Staff 與 Finance 三種 format 皆有 privacy-safe corpus＋逐列 golden manifest；
- 所有網站上傳不將 workbook bytes 存入 DB，terminal upload 有 deletion receipt，storage 無 orphan bytes；
- 管理端只有一個「匯入資料」入口，固定五列 registry，沒有 File Watcher／Finance 重複 upload writer；
- `48/43/5` 已有合法 fixture evidence，或已有明確人工退役裁決；
- Module／Subsystem／Domain／Global 四層證據可重跑且 `pytest -W error` 通過。

## 14. 非目標

- 不以本 ADR 重建已退役的 `services/finance_import_application.py`、
  `services/finance_import_dispatch.py` 或舊 alert routes；
- 不把 Anomalies 變成 Finance／Case／Staff root fact owner；
- 不允許 Generic Data Browser 直接修正 import root／review／receipt／alert；
- 不以擴大 nullable 欄位、填假預設值、雙寫 alert 或忽略測試失敗來達成表面通過。
- 不承諾接受任意 Excel 版型、模糊表頭或已不可逆遺失的識別碼；未知格式應可處理地 fail closed。

## 15. 待人工確認

1. 是否接受第 4.1 節的四級 `ImportFieldPolicy`，只允許 optional allowlist omission？
2. 是否確認全面禁止 HCM fabricated defaults，invalid row 改走 review？
3. 是否確認新 import anomaly 只走 canonical Anomalies，退役 direct `system_alerts` writer？
4. 是否接受一般 UI 只顯示 masked sample，完整 source payload 僅在受控 review detail 查看？
5. `48/43/5` 若找不到合法原 fixture，是否允許改以 versioned synthetic fixture 取代精確魔術數字？
6. 是否接受 Finance 維持 batch UoW，而 Case／Staff 採逐 source-row UoW＋durable batch orchestration？
7. staff identity／profile 的 canonical owner 應歸於哪個既有 Domain，或是否需要另立正式 Domain？
8. 是否確認退役 runtime dynamic target-column filtering，以 explicit schema contract／compatibility gate 取代？
9. HCM／BeClass 多 sheet 應採「只接受唯一匹配 sheet」或提供人工選擇；Finance 多個有效 sheet 是全匯還是人工選擇？
10. 是否接受真實附件只作受控 evidence，repository 一律使用去識別、最小化 fixture＋golden manifest？
11. unknown header alias 是否一律先進 format review，經人工核准與版本化後才能成為新 alias？
12. Finance 的 invalid amount 是否統一整列 blocker；哪些非 fingerprint 欄位可降為 warning？
13. 歷史來源的 cutoff／overlap 應如何按 HCM、BeClass、Staff、Orders、Finance 分別界定？
14. 歷史資料預設是否確認為 `evidence_only`，只有逐 Domain 核准的 HistoricalAdoption 才可建立 canonical history？
15. HistoricalAdoption 採整批 strict rollback，或允許已無歧義的 rows 分批 commit、其餘進 review？
16. 哪些歷史 current-state projection 需要重建；哪些必須永久保持 no-impact／read-only？
17. 歷史 identity 可接受哪些證據組合；是否確認姓名、電話、金額或 row number 均不能單獨自動配對？
18. 原始歷史附件的保管位置、存取權限、retention 與去識別 fixture 核准人為誰？
19. 是否接受 `source_asserted_status` 作為歷史 Orders 初始根事實，不要求補造現行狀態機事件？
20. retryable infrastructure failure 的原檔保留多久；建議 24 小時後刪除並要求重新上傳？
21. production ephemeral storage 採單機 private temp directory 或 private object storage；多 worker／多主機部署時建議後者？
22. 各來源允許的 extension、單檔大小、sheet／row budget；是否先統一只接受 `.xlsx`？
23. successful／review row 的 raw source payload 在 DB 保留哪些欄位與多久，避免 JSON evidence 無上限成長？
已確認決策 `HIST-STATUS-01`：historical order source profile v1 只接受 0→取消、1→完成、2→洽談中；
沒有文字值、其他代碼、訂單成立或服務中。

已確認決策 `HIST-STATUS-02`：0／1 的 asserted terminal status 即使缺日期、取消原因、排班或付款
明細也照常保留；缺值不補猜、不標示不完整、不建立 anomaly。

已確認決策 `UPLOAD-FILE-01`：登入後由網站上傳；檔案只作 ephemeral processing artifact，durable
materialization 後自動刪除，DB 不保存 workbook BLOB。

已確認決策 `IMPORT-UI-01`：新增管理端「匯入資料」分頁，固定列出五種核准檔案匯入，每列有說明、
選檔與上傳按鈕；正式觸發 typed endpoint／job，不直接執行 filesystem script。以上二十三項其餘
決策確認前，不開始 production code、schema 或 pytest 修改。
