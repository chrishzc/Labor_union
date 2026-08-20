---
doc_type: implementation-specification
declared_status: approved
identity: PROV-20260816-react-admin-phase4a-hcm-current-preview
date: 2026-08-16
owner: Case Import / React Integration
domain: Case Import
subsystem: HCM Current Workbook Preview / React Presentation
authority: user-approved-autonomous-phase-progression-2026-08-16
---

# React 管理端 Phase 4A-P：HCM Current Workbook 真檔 Preview 規格

## 0. 目的與合法完成邊界

保留既有 `DataImportPage` 六張 category card 與共用 Drawer，只把第一張「HCM 案件匯入」的
檔案選擇與 Preview 改成真實 multipart API。Apply、逐列修正、人工放行及其餘五類匯入全部原位
顯示但原生 disabled。

本波成功只代表：操作者選擇一份 `.xlsx`，React 保存 immutable bytes snapshot，呼叫
`POST /api/v1/case-import/hcm/workbooks/preview`，嚴格解碼 typed aggregate，且 UI 顯示 server
回傳的 digest、fingerprint 與 counts。不得宣稱已匯入、已建立案件、已建立 warning task 或已保存 receipt。

## 1. Business scenario

已通過帳密 Challenge 與 TOTP 的工會人員，在資料匯入頁選擇 HCM current workbook。UI 必須先於
本機 fail closed 驗證 `.xlsx`、非空、最大 20 MiB，再保存相同 bytes 並執行 Preview。Preview 是零寫入；
任何 schema mismatch、session error、timeout、network error 或 digest mismatch 都顯示確定失敗，不能
沿用舊 preview，也不能啟用 Apply。

## 2. 權威與不變量

- Global：`01_規格基線/00_Global_共同契約.md`。
- Case Import／HCM：`01_規格基線/17_External_Integration_LINE_Access正式規格.md` 第 5 節。
- React 主計畫：`document/功能開發計畫/React管理端遷移與UI真實業務流程驗收計畫.md` Phase 4。

不可破壞：

1. Preview 零寫入；React 不建立 root、warning、receipt 或 fake sample row。
2. source digest 與 preview fingerprint 只來自 server；本機 SHA-256 只用來驗證同一 bytes lineage。
3. `HCM historical whole-row overwrite` 已退役，不得復活。
4. 缺漏與修正版使用完整來源重新提交；本頁不提供單欄修正／放行。
5. UI 不從 aggregate counts 推導逐列 outcome、案件號、姓名、warning code 或 navigation。
6. Apply 在 Phase 3 warning disposition 與 Phase 4A-H transaction/receipt gate 閉合前固定 unavailable。

## 3. 唯一允許 HTTP contract

`POST /api/v1/case-import/hcm/workbooks/preview`

- Auth：每次 request 即時取得 current memory bearer；不得快取、持久化或寫入 URL/log。
- Body：`multipart/form-data`，唯一 file field 名為 `workbook`；不得手動設定 multipart Content-Type boundary。
- File：`.xlsx`、非空、`<= 20 * 1024 * 1024` bytes。
- Timeout：30 秒，支援 AbortSignal；Drawer 關閉或換檔可取消尚未完成的 Preview。
- Request budget：每次明確按 Preview 最多一個 request；選檔、開 Drawer、render 不得自動 POST。
- 禁止端點：Apply、ingest、historical、resubmission 及其他 import family。

成功 envelope 的 `data` 必須嚴格包含：

| field | contract |
|---|---|
| `source_content_digest` | lowercase 64-hex |
| `source_row_count` | integer `>= 0` |
| `ready_count` | integer `>= 0` |
| `ready_with_warning_count` | integer `>= 0` |
| `review_required_count` | integer `>= 0` |
| `preview_fingerprint` | lowercase 64-hex |

## 4. Frontend state machine

```text
idle
→ file_hashing
→ file_ready
→ preview_loading
→ preview_ready

file_hashing／preview_loading → known_error
file_ready／preview_ready／known_error → file_hashing（使用者選擇新檔）
preview_loading → idle（Abort後關閉）
```

- 使用 discriminated union；禁止互相矛盾的 loading/success/error booleans。
- 選檔時讀取一次，保存 `filename/contentType/bytes/sha256` immutable snapshot。
- `crypto.subtle.digest` 不可用時 fail closed。
- server `source_content_digest` 必須等於 snapshot SHA-256；不一致視為 contract drift。
- 新檔即清除舊 preview；同名不同 bytes 也不得沿用。
- memory only；不得 localStorage/sessionStorage/cookie/URL。

## 5. UI preservation 與 stable IDs

必須保留六張 cards、Drawer、aggregate summary 與 row-table 視覺槽位。row-table 改顯示「後端未開放
逐列 typed Preview」，不可刪除整個資訊區假裝完成。

- `imports.page`
- `imports.hcm-current.open-preview`
- `imports.hcm-current.open-apply`（disabled）
- `imports.hcm-current.drawer`
- `imports.hcm-current.file`
- `imports.hcm-current.preview`
- `imports.hcm-current.preview-summary`
- `imports.hcm-current.row-detail-unavailable`
- `imports.hcm-current.apply`（disabled）
- `imports.hcm-current.close`
- `imports.hcm-historical.preview`／`.apply`（disabled，顯示已退役）
- `imports.client-beclass.preview`／`.apply`（disabled）
- `imports.staff-historical.preview`／`.apply`（disabled）
- `imports.historic-orders.preview`／`.apply`（disabled）
- `imports.bank-statements.preview`／`.apply`（disabled）

## 6. Strict decoder 與 failures

- Zod envelope 與 data 都 `.strict()`；required 不得 optional/default。
- 禁止 `z.any/z.unknown/z.record/.passthrough/.catch/.default/.coerce/.preprocess/.transform`、
  `as any` 與 `unknown as`。
- 必測 missing required、wrong primitive、extra envelope/data、null violation、invalid hex、negative/fraction count。
- current backend 的 `detail.code` 可轉為本 slice bounded error，但不能宣稱已符合 Global typed error；完整
  typed error hardening 屬 4A-H。
- error UI 不 render raw payload、traceback、token、完整檔案 bytes 或來源個資。

## 7. Out of scope

HCM Apply／receipt、row detail、warning transition、resubmission、historical、其他 import family、backend、DB、
shared transport/runtime decoder、Auth、App/router、Streamlit/cutover/deployment。

## 8. Completion semantics

G0–G6 全 PASS 後最高狀態為 `completed-local-validated-preview-only`。不得省略 `preview-only`，也不得把
Apply disabled 或 backend gaps 寫成整個 HCM import 已完成。
