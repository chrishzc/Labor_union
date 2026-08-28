---
doc_type: work-package
declared_status: in-progress
date: 2026-08-26
owner: Contract-Signing-and-Orders-Integration
current_task: CUR-CONTRACT-01
authority: 2026-08-26 user direction to complete all current tasks in 96 and direct DB-test mutation authority
---

# CUR-CONTRACT-01 外部平台簽約與最終 PDF 交接工作包

## 1. Business scenario 與 Authority

工會人員先從系統下載未簽 PDF，人工移交外部簽約平台；月嫂與客戶依序透過已驗證 LINE 身分或
等價受控人工入口回報外部簽署完成。客戶回報只建立「最終 PDF 待回收」，不得提前形成 Contract
Completion。最終 PDF 必須經 staging、零寫入 Preview、明確確認、單一 outer UoW Apply 與 readback，
才保存 Contract-owned 文件版本並完成契約。

正式語意由 `00_Global_共同契約.md` §2.2、
`21_Contract_Signing_Commitment與正常驗收資料鏈正式規格.md` 的 2026-08-25 amendment、
`17_External_Integration_LINE_Access正式規格.md`、`20_LINE客服與月嫂自助服務正式規格.md` 與
`document/功能開發計畫/NAS_檔案庫與資料中心管理介面正式規範.md` 擁有。`96` 已核准本機實作、
必要 `lu_test_*` schema gates 與 sandbox 驗收；2026-08-26 最新人工裁決另授權 `lu_test_*` 建立、
DDL candidate、去識別測試資料、Query／Preview／Apply、readback 與 scoped cleanup，不需逐次請示。

## 2. Global → Domain → Subsystem → Module 架構

- Global：沿用 command envelope、canonical input fingerprint、idempotency、BusinessClock、typed errors、
  單一 outer UoW、receipt 與 durable outbox；timeout 結果未知時只以原 identity 查 receipt。
- Domain：Contract Signing 擁有 external signing session、雙方 completion report 順序、final-PDF-pending、
  completed 狀態機及 stale／replay 不變量；Orders 仍唯一擁有 Contract Completion。
- Subsystem：`DownloadUnsignedContractPdf` 只讀取已保存、current、PDF-only 文件；staff/client report Apply
  鎖定 fresh session／plan／segment／document／binding facts；final Preview 零寫入；final Apply 以 borrowed
  controlled-file persistence 在同一 outer UoW 保存 controlled object、Contract final document、Orders
  completion、剩餘義務、outbox 與 receipt。
- Module／Adapter：LibreOffice headless adapter 將核准且 hash-verified XLSX template 轉為 PDF；NAS adapter
  只接受 opaque logical object reference；FastAPI 只映射 typed contract；React 保留 Orders Drawer 與四分頁，
  移除 current 主路徑的 URL 與 direct signed-return controls。

外部簽約平台不整合、不抓取 provider 狀態，也不向一般 UI 暴露 URL、storage locator、raw path、完整
digest、preview fingerprint 或 raw cursor。既有 `SendStaffContract`／`SendClientContract`／signed-return
只保留未掛載的 legacy compatibility identity，不回溯改寫既有 manual-attested completion。

## 3. Scope、write set 與 effect ceiling

### In scope

- typed PDF renderer port、隔離且有 timeout／size／magic 驗證的 LibreOffice adapter、不可變未簽 PDF 保存與
  authenticated PDF-only download。
- external signing session、staff/client completion reports、verified identity/binding snapshot、順序、防重播、
  status version、final-PDF recovery task 與 closed typed receipts。
- final signed PDF staging → Preview → explicit confirm → atomic Apply → receipt／document readback。
- additive schema release、descriptor、fresh assembly、canonical migration chain、唯讀 plan、`lu_test_*`
  fresh／preserve-data candidate／developer acceptance gates。
- FastAPI、LINE handler composition、既有 Orders／Data Center React typed adapter與 fresh Chrome acceptance。

### Excluded

- `union_db`、production DB／NAS／recipient、真實外部簽約平台 API、正式 deployment、entry switch。
- source replacement、`--switch`、全庫 cleanup、business-row backfill、legacy completion 改寫。
- raw NAS path、公開或 presigned URL、binary DB 欄位、watcher 自動形成 Domain completion。
- 覆蓋或簡化 Orders Drawer、四分頁、SSOT cards、terms、calendar、cancel、reopen 或 Data Center 現有 UI。

### Write set

- `domains/contract_signing/`、`subsystems/contract_signing/`、必要的 `subsystems/controlled_files/` borrowed-UoW
  composition、`infrastructure/file/`／`infrastructure/db/` typed adapters。
- `api/` dependency／schema／route、LINE handler／UoW composition、`ui_react/` contract clients／components／tests。
- `db/schema_parts/`、`db/schema.sql`、canonical release／catalog／descriptor、focused tests、validation scenario／receipt。
- 本工作包、`21` runtime status、`96` current row 與 final evidence index。

## 4. Root facts、commands 與 closed state

### Root facts

- `external_signing_session`：case、matching plan、current document-set fingerprint、commitment、closed state、
  aggregate/status version、active/supersession identity。
- append-only `external_completion_report`：session、scope、segment、document version、verified reporter binding
  snapshot、immutable source event identity／payload digest、occurred-at、actor、idempotency／command fingerprint。
- `final_pdf_recovery_task`：由 client completion report 建立，只有 final Apply 可 fulfilled。
- Contract-owned `final_document_version`：只引用 controlled-file opaque identity、version、MIME、size、digest 與 audit。

### Commands

- `DownloadUnsignedContractPdf`
- `RecordExternalStaffSigningReport`
- `RecordExternalClientSigningReport`
- `PreviewFinalSignedContractUpload`
- `ApplyFinalSignedContractUpload`
- `QueryContractDocumentReadback`

closed state：`staff_reporting → staff_reports_complete → client_reported_final_pdf_pending → completed`；
`superseded` 為 terminal rejection state。最後一筆 staff report 才能在同交易建立／確認 commitment 與 client
reminder intent；client report 只能建立 final-PDF recovery task；final Apply 前不得形成 completion。

## 5. Idempotency、lock 與 failure contract

- canonical command fingerprint 只由 immutable input 產生；同 key＋同 input 回原 receipt，同 key／source event
  不同 payload 固定 conflict，另一 event 重複同 target 固定 `already_recorded`。
- lock order：session → case/order → plan/segments（id 排序）→ commitment → current documents → reports →
  binding/source intent → staging/controlled predecessor → command claim/receipt → finance；CAS session aggregate
  version與 Orders lifecycle version。
- renderer 不在 DB lock 內執行。PDF/NAS candidate 已形成但 DB rollback 時只留下可 reconciliation 的 orphan；
  不可冒充成功。final Apply 任一步失敗時所有 DB roots rollback，staging 保留供同 identity 重試。
- stale session／plan／segment／document／binding／commitment／staging、錯序、MIME 非 PDF、digest drift、
  ambiguous target、audit failure全部 fail closed且零 Domain partial write。

## 6. Dependency 與 renderer 決定

兩份核准 XLSX 模板含大量 merged cells、圖片與 page setup；重畫為 ReportLab／HTML 會改變文件版面與擴大
依賴。採用可注入 `ContractRenderer` port 與 LibreOffice headless adapter，不新增 npm／PyPI package。
adapter 只從明確設定或 portable executable discovery 取得 `soffice`，不得硬編個人絕對路徑；使用獨立 temp
profile、固定參數、硬 timeout、唯一輸出、size cap、`%PDF-`／EOF／MIME 驗證與去敏 stderr。缺少 renderer、
字型或 conversion mismatch 固定 typed fail closed；deployment 必須另做 preflight。

## 7. DB change inventory 與 gates

候選 release identity 先使用 `PROV-20260826-contract-external-signing-successor`，由 integration writer 在
current catalog late-bind；不得修改已發布 release 1004。

| 類別 | 候選效果 | Replay／rollback | 狀態 |
|---|---|---|---|
| `schema-only` | session、completion reports、final recovery task、Contract-owned final document link、closed receipts與 append-only triggers | additive candidate；未 switch 前可丟棄 candidate | `approved-candidate` |
| `system-seed` | 無 | 不適用 | `none` |
| `business-row-backfill` | 無；legacy/manual lane 不回填 successor | 不適用 | `none` |
| `destructive` | 無 | 禁止 | `none` |

| Gate | 狀態 | Current evidence／next evidence |
|---|---|---|
| Scope | PASS | `96` CUR-CONTRACT-01 approved、`21` runtime approved、本工作包 in-progress |
| Change inventory | PASS | 上表：schema-only；無 seed／backfill／destructive |
| Static release | PASS | release／descriptor／assembly hash-bound，canonical focused tests PASS |
| Descriptor | PASS | runner 從 hash-bound SQL 展開完整 column contract；兩個 altered purpose columns、checks、indexes、FK、triggers 均可機械判別且 MySQL exact |
| Read-only plan | PASS | `scripts.update_local_database --dry-run --strategy replacement` 僅列 1005 absent，release identity 正確 |
| Engine verification | PASS | MySQL 8.0.46 fresh bootstrap；1004 source → 1005 candidate apply／verify；第 7/21 statement 中斷後 hash-bound reconciliation／resume exact |
| Developer acceptance | PASS | 正式 updater 對隔離 `lu_test_*` 執行 backup → candidate → same-name replacement → data/schema equivalence readback；rollback dump 保留 |

總結：`DB_CHANGE_READY`。canonical qualification 位於
`validation/receipts/phase4/PROV-20260826-local-additive-qualification-contract-external-signing-successor.json`；
大型 dump、plan、operation 與 replacement receipts 只保存在 ignored `scratch/contract-o2-*`。所有 mutation 僅限
`lu_test_*`；未操作 `union_db`、production 或 `--switch`。

## 8. Acceptance 與停止條件

1. 兩份核准模板產生可讀、非空、`application/pdf` 的未簽 PDF；formula-like facts 不被執行，missing／timeout／
   corrupt／oversize renderer 全部 typed fail closed。
2. persisted enabled human 只能下載 current `template_generated` PDF；signed-return、XLSX、cross-case、stale、
   missing／digest drift拒絕；成功回 attachment／no-store 並先 durable audit。
3. staff report 可任意段落到達但只能記一次；全部 staff 完成前 client report拒絕，delivery success 不等於 report。
4. client report 後只有 final-PDF-pending；final Preview 零寫，修改 file／metadata／status 後舊 Preview失效。
5. final Apply 單一 outer UoW 保存 controlled object、final link、Orders completion、remaining obligations、outbox、
   receipt；timeout只查原 receipt，readback failure保留 committed receipt而不重送。
6. public API／UI 不含 URL、path、locator、raw cursor、完整 digest／fingerprint；React 保留既有高保真 UI invariants。
7. Module → Subsystem → Domain → Global focused tests、DB gates、fresh enabled-human Chrome、strict UTF-8、
   structured headers與 `git diff --check` 全部 passed。

停止條件：production／`union_db`／正式 NAS 或 provider、entry switch、destructive data effect、Work Package 外的
public contract／owner 改變需要新裁決；owned object 出現 `partial`／`drift` 時停止 DB lane；任何單次
`apply_patch` 超過 30 秒立即停止該補丁並通知使用者。
