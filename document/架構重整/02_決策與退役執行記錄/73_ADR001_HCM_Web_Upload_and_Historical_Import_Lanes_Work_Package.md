---
doc_type: work-package
declared_status: in-progress
date: 2026-08-13
owner: Case Import / LINE Integration / Global Import Boundary
priority: P0
---

# 73 ADR-001 HCM Web Upload 與歷史匯入入口分流 Work Package

## 1. 人工裁決與 business scenario

2026-08-13 人工確認 `IMPORT-ENTRY-02`：HCM 日常 Excel 匯入需參考 Finance Web upload
收斂；Client BeClass 與 Staff 現行資料由 LINE LIFF 提交，但實際寫入必須經 authenticated typed
API 與 owning Domain。Client／Staff BeClass import scripts 不退役，保留供歷史紀錄匯入。

操作者需要在管理端安全上傳 HCM workbook；每列不是建立正式 case，就是形成可追溯 review／
replay outcome。LIFF 使用者更新 current facts 時，不得被後續歷史匯入靜默覆蓋。

2026-08-13 人工補充裁決：本包先以現實 current／historical workbook 與其中髒資料做
`rehearsal-first` 驗證，不預設 `HCM Intake Durable Manifest` 是正確解。先證明既有 Case Import
receipt、BeClass review root 與 command identity 能否承接所需語意；只有可重現 evidence 證明
缺少 canonical root 時，才提出最小 schema gap 與另一個已核准 Work Package。

## 2. 核准範圍

### Phase 0：現實資料 rehearsal 與 capability decision

Phase 0 不新增 schema、API 或 UI。先完成以下證據，並由 capability decision 決定後續實作：

1. 對受控 real-shape workbooks 只做欄位／sheet fingerprint、typed issue category、重複與衝突分布盤點；
   原始檔與個資不進 Git／log／receipt。
2. parser／normalizer 真正 no-write dry-run，並以前後 DB snapshot 證明零 mutation，不以「未呼叫 repository」
   的 mock assertion 取代。
3. 以去敏 candidate 驗證 current HCM、historical HCM、Client historical、Staff historical；每 lane 都測
   apply、exact replay、same-key conflict、stale current sentinel、identity ambiguity、invalid root field、
   injected crash 與 partial residual。
4. capability decision 只能是：`reuse-existing-roots`、`code-gap-only`、`schema-gap-required` 或
   `business-owner-blocked`。只有第三種可提出 schema WP，且必須附最小 fail-before evidence。

### Phase 1：依 capability decision 實作

只有 Phase 0 通過且 owner／root／transaction boundary 明確後，才執行下列已核准方向；若決策為
`schema-gap-required` 或 `business-owner-blocked`，WP73 保持 blocked，不得先搭 Web mutation 骨架。

Phase 0 第一批 synthetic characterization evidence 已建立：

- `validation/scenarios/case_import/wp73_phase0_dirty_data_rehearsal_v1.json`
- `tests/fixtures/case_import/wp73_dirty_rows_v1.json`
- `tests/test_wp73_dirty_data_characterization.py`

focused result 為 `12 passed, 3 xfailed`；三個 strict xfail 分別鎖定 HCM、Client BeClass、
Staff BeClass importer 尚無 explicit true no-write mode。HCM current／historical 與 Client historical
目前為 `blocked_code_gap`；Staff historical 因 owner 未裁決為 `blocked_business_owner`。尚未執行
candidate apply／replay／rollback，也未因此推導 schema。

2026-08-13 capability decision已由真實執行失敗與人工裁決更新：HCM invalid-row lane為
`schema-gap-required`，但只建立Case Import自有review root/outbox，不採generic manifest；Staff
historical為`schema-gap-required`，由WP77核准HistoricalAdoption保守合併與immutable receipt。
HCM與Client BeClass必須可獨立匯入；缺少對方只投影current-state anomaly，cooking不再是HCM
root建立前置條件。兩項production/schema施工權限與驗收移交WP77；WP73保留HCM authenticated
Web upload與UI責任。

Phase 0 已提供 `scripts/imports/rehearse_case_import_workbook.py` 作為獨立 operator-only 唯讀入口；
它只重用 Domain validators，不匯入三支 production importer，不連 DB，且只輸出 digest、筆數、
重複 identity 統計與錯誤欄位次數。focused verification 為 `17 passed, 3 xfailed`；xfail 仍代表
production importer 本身尚未具 no-write mode，不能把本入口的成功解讀為可正式 apply。

2026-08-13 來源重新對齊以 `document/資料庫、資料處理/1,HCM.xlsx`、`2.staff.xlsx`、
`3.client_beclass.xlsx` 為現行 workbook shape reference；檔名與 sheet 名稱不作分類依據，改由
各 lane 的實際欄位契約選表。三份實檔唯讀演練皆自動選中第 1 張 sheet、各讀取 1 source row，
且 `database_connections=0`、`writes_performed=0`。目前三列皆為 `review_required`：HCM 命中
姓名／縣市，Client 命中姓名／行動電話，Staff 命中報名時間／行動電話／身分證字號；這是
髒資料 characterization，不代表正式匯入失敗或已完成 candidate apply。

1. HCM 增加 authenticated multipart upload endpoint，使用 server-managed temporary file、大小與
   `.xlsx` gate、typed receipt、idempotency identity，完成後刪除 temporary file。
2. HCM adapter 停止 fabricated defaults；必要欄位或跨欄 validation 失敗時不得建立 Client／Order，
   回 `review_required` 並保留 privacy-safe issue evidence。
3. HCM 正式寫入維持 Case Import typed Preview／Apply 與唯一 outer UoW，不新增 direct SQL writer。
4. Client／Staff BeClass scripts 保留，但明確定位為 `restricted_historical_import`；本包可加入
   operator mode guard 與 File Watcher exclusion，不刪除 parser 或歷史能力。
5. 正式文件、entrypoint inventory、focused tests 與 evidence 同步更新。
6. 在任何 HCM Web mutation 或 historical cutover 前，建立去敏且可重現的 current／historical
   rehearsal：HCM、Client BeClass、Staff BeClass 都要涵蓋正常列、重複列、缺欄、錯型別、
   identity ambiguity、既有 current fact 衝突與部分失敗。真實來源檔只可在受控本機讀取，
   不提交 raw workbook、完整個資或可逆識別值。
7. historical rehearsal 只能在 disposable DB／由備份產生的隔離 candidate 執行；source snapshot
   唯讀，禁止連線或寫入既有 `union_db`。先比對 dry-run before／after fingerprint，再驗證 apply、
   exact replay、same-key different-payload conflict、stale current fact、partial residual 與 rollback。

## 3. Out of scope

- 不裁決 Staff profile 的 canonical Domain owner。
- 不實作完整 Staff／Client HistoricalAdoption mapping、identity matching 或 production cutover。
- 不執行 production DB、migration、deployment、File Watcher 主機操作或資料回填。
- 不把 LIFF 變成 DB client；LIFF 只能呼叫 typed API。
- 不完成 ADR-001 P0～P8 全部工作，也不封存 ADR。
- 不先建 generic import run／row manifest table；schema owner 與最小持久化契約由 rehearsal evidence
  決定，不能從 UI receipt 形狀反推。

## 4. Write set

- `document/功能開發計畫/ADR-001-import-architecture-refactor.md`
- `document/架構重整/01_規格基線/15_正式規格索引與裁決總表.md`
- `document/架構重整/01_規格基線/17_External_Integration_LINE_Access正式規格.md`
- 本 Work Package 與同目錄 `README.md`
- `scripts/imports/import_client_hcm.py`
- `scripts/imports/import_client_beclass.py`
- `scripts/imports/import_staff_beclass.py`
- `scripts/imports/rehearse_case_import_workbook.py`
- `scripts/file_watcher.py`
- `document/架構重整/03_追蹤清單與證據/evidence/entrypoint_review_queue_v1.jsonl`
- HCM upload 所需的 `api/routes/`、`api/schemas/`、`api/dependencies/`、`subsystems/case_import/`
  精確檔案
- HCM upload 所需的 `api/main.py`、bounded `ui/api_clients/`、`ui/pages/` 與 navigation 精確檔案
- `validation/fixtures/case_import/` 下由真實髒資料類型提煉、不可逆去敏的最小 corpus，及其 manifest
- `document/架構重整/03_追蹤清單與證據/evidence/` 下 rehearsal receipt／索引；receipt 只能保存
  counts、不可逆 digest、typed issue category 與不變量結果
- HCM upload／validation／historical-entry guard 的 focused tests
- `tests/test_wp73_workbook_rehearsal_cli.py`

若需 schema、Staff owner、Client／Staff historical root mutation 或一般 import registry，必須另立
後續 Work Package，不得擴張本 write set。

目前已知 fail-before：Domain enum 雖含 `hcm`，但 canonical part 136 的 `source_kind` 只允許
`client／staff`；現有 BeClass review identity／writer 又將非 client 路徑視為 Staff。這表示 HCM 不能只
擴 enum 或借用 BeClass durable root。Phase 0 必須先裁決 Case Import 自有 review／intake owner，
不能讓錯誤 bounded-context reuse 變成 schema。

## 5. Acceptance

1. 無效 HCM required field 不建立 Client／Order，且不存在 fabricated date／service terms。
2. 先完成 rehearsal capability matrix，逐一指出 HCM current、HCM historical、Client historical、
   Staff historical 的 parser、owner、root mutation、review、replay、conflict、rollback 與 residual
   是 PASS、BLOCKED 或 NOT_RUN；不得把單元測試或 mock 冒充真實 MySQL evidence。
3. dry-run 對 source／candidate 的 schema、row count、primary key 與選定 projection fingerprint 為零變更；
   apply 只可在 disposable candidate 執行，且完整成功、exact replay、stale／conflict、髒列隔離、
   中途注入失敗 full rollback／明確 row-level terminal boundary 都有 receipt。
4. historical import 不得覆蓋較新的 LIFF／current facts；identity ambiguity、invalid required fields、
   partial residual 與 unknown schema/header 必須 fail closed 並進人工 review，不得 fabricate defaults。
5. rehearsal 後若既有 roots 足以表達 upload identity、review 與 replay，沿用既有 schema；若不足，
   必須用 fail-before evidence 提出最小 schema gap，WP73 保持 blocked，不能直接新增 manifest table。
6. 有效 HCM upload 經 admin authentication、typed endpoint 與 Case Import application 完成；相同
   idempotency key＋相同檔案 replay，相同 key＋不同 digest conflict。其 durable owner 必須來自第 5 項裁決。
7. temporary workbook 在 terminal success／validation failure 後刪除；retryable infrastructure
   failure 的保留策略若尚未具 durable job，必須明確 fail closed，不誤報成功。
8. response 為 strict typed view；若 business contract 要求逐列守恆，先證明其 canonical owner，
   不因畫面需要統計就新增持久化 root。
9. Client／Staff scripts 仍存在，但 source scan 證明一般 Web UI／File Watcher 不會把它們當 current writer。
10. LIFF path 只呼叫 typed API；browser source 不含 DB credential 或 SQL。
11. Module → Subsystem → API focused pytest 以 `-W error` 通過，`git diff --check` 通過；Web UI 另以
    Chrome 對實際啟動的 API／Streamlit 做 upload、invalid review、replay、conflict 與錯誤顯示驗收。
12. 不接觸 production DB，不執行未另行核准的 migration 或 deployment。

## 6. Completion／archive gate

完成只代表 WP73 第一階段驗收，不代表 ADR-001 完成。必須留下 focused receipt、未完成後續項與
rollback trigger；在 HCM Web upload UI／API 實際驗收前不得標記 completed 或封存。

## 7. 2026-08-14 實作與驗收狀態

HCM 第一階段已新增 Case Import-owned workbook coordinator、authenticated multipart API、strict typed
receipt 與「資料匯入中心」HCM card。workbook identity 重用既有 global command claim／receipt，並以
bounded MySQL coordinator lock 序列化同 key 執行；沒有新增 schema。server temporary workbook 在每個
terminal path 於 `finally` 移除。實機 UI receipt、replay、API conflict 與 focused verification 見
`document/架構重整/03_追蹤清單與證據/evidence/2026-08-14_wp73_hcm_web_upload_receipt.md`。

本包仍是 `in-progress`：去敏 fixture 兩列皆正確進 review，尚無有效 row 建立 root 的實機 receipt，
且 Chrome extension 專項復驗尚未完成。決策責任已收斂：warning Query 由 WP92 定義為 typed
read-only query，但不在目前匯入 slice；通用 `Correct`／`corrected_fields` 已否決，欄位補正必須由
HCM owner 提供明確 typed command；`RejectCaseImportReview` 不得成為正式 entry point，完成退役前
固定 fail closed。剩餘 evidence 缺口不能以 UI 已可上傳或單元測試取代，也不能作為封存依據。

## 2026-08-15 非實機收尾

本包的契約、Case Import-owned coordinator、authenticated multipart API、typed receipt、temporary
workbook cleanup、資料匯入中心 HCM card、entrypoint fail-closed 邊界與去敏 focused evidence 已收斂。
剩餘項目僅為有效 HCM 列建立 root 的實機 receipt 與具 extension 的 Chrome 驗收，兩者皆不得以
文件或靜態檢查替代。統一交接紀錄見
`document/架構重整/03_追蹤清單與證據/evidence/2026-08-15_wp73_wp77_wp82_non_engine_closeout.md`。
