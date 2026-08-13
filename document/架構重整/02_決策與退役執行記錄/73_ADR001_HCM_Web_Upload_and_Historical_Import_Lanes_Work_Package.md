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

## 2. 核准範圍

1. HCM 增加 authenticated multipart upload endpoint，使用 server-managed temporary file、大小與
   `.xlsx` gate、typed receipt、idempotency identity，完成後刪除 temporary file。
2. HCM adapter 停止 fabricated defaults；必要欄位或跨欄 validation 失敗時不得建立 Client／Order，
   回 `review_required` 並保留 privacy-safe issue evidence。
3. HCM 正式寫入維持 Case Import typed Preview／Apply 與唯一 outer UoW，不新增 direct SQL writer。
4. Client／Staff BeClass scripts 保留，但明確定位為 `restricted_historical_import`；本包可加入
   operator mode guard 與 File Watcher exclusion，不刪除 parser 或歷史能力。
5. 正式文件、entrypoint inventory、focused tests 與 evidence 同步更新。

## 3. Out of scope

- 不裁決 Staff profile 的 canonical Domain owner。
- 不實作完整 Staff／Client HistoricalAdoption mapping、identity matching 或 production cutover。
- 不執行 production DB、migration、deployment、File Watcher 主機操作或資料回填。
- 不把 LIFF 變成 DB client；LIFF 只能呼叫 typed API。
- 不完成 ADR-001 P0～P8 全部工作，也不封存 ADR。

## 4. Write set

- `document/功能開發計畫/ADR-001-import-architecture-refactor.md`
- `document/架構重整/01_規格基線/15_正式規格索引與裁決總表.md`
- `document/架構重整/01_規格基線/17_External_Integration_LINE_Access正式規格.md`
- 本 Work Package 與同目錄 `README.md`
- `scripts/imports/import_client_hcm.py`
- `scripts/imports/import_client_beclass.py`
- `scripts/imports/import_staff_beclass.py`
- `scripts/file_watcher.py`
- `document/架構重整/03_追蹤清單與證據/evidence/entrypoint_review_queue_v1.jsonl`
- HCM upload 所需的 `api/routes/`、`api/schemas/`、`api/dependencies/`、`subsystems/case_import/`
  精確檔案
- HCM upload／validation／historical-entry guard 的 focused tests

若需 schema、Staff owner、Client／Staff historical root mutation 或一般 import registry，必須另立
後續 Work Package，不得擴張本 write set。

## 5. Acceptance

1. 無效 HCM required field 不建立 Client／Order，且不存在 fabricated date／service terms。
2. 有效 HCM upload 經 admin authentication、typed endpoint 與 Case Import application 完成；相同
   idempotency key＋相同檔案 replay，相同 key＋不同 digest conflict。
3. temporary workbook 在 terminal success／validation failure 後刪除；retryable infrastructure
   failure 的保留策略若尚未具 durable job，必須明確 fail closed，不誤報成功。
4. response 為 strict typed view，統計互斥且滿足 source rows 守恆。
5. Client／Staff scripts 仍存在，但 source scan 證明一般 Web UI／File Watcher 不會把它們當 current writer。
6. LIFF path 只呼叫 typed API；browser source 不含 DB credential 或 SQL。
7. Module → Subsystem → API focused pytest 以 `-W error` 通過，`git diff --check` 通過。
8. 不接觸 production DB，不執行 migration 或 deployment。

## 6. Completion／archive gate

完成只代表 WP73 第一階段驗收，不代表 ADR-001 完成。必須留下 focused receipt、未完成後續項與
rollback trigger；在 HCM Web upload UI／API 實際驗收前不得標記 completed 或封存。
