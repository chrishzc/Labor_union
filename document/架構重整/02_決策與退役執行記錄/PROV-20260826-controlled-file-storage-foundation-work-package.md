---
doc_type: work-package
declared_status: in-progress
date: 2026-08-26
owner: Data-Center-and-Controlled-Storage-Integration
current_task: CUR-FILE-NAS-01
authority: 2026-08-26 user direction to complete all current tasks in 96
---

# CUR-FILE-NAS-01 受控檔案儲存基礎工作包

## 1. Business scenario 與 Authority

工會人員需要把契約、月嫂文件、寶寶日誌及餐食照片納入同一受控檔案能力；系統只公開
logical folder、檔名與 owner-approved metadata，並以 authenticated download 讀取經 digest 驗證的
NAS bytes。`96_Current_剩餘代辦任務總表.md` 已核准本機實作、必要 `lu_test_*` schema gate、typed
Query／Preview／Apply／receipt／readback、staging、cleanup 與失敗 reconciliation。

正式 owner 與不變量由 `00_Global_共同契約.md` §2.2、`17_External_Integration_LINE_Access正式規格.md`
§3.5、`18_Global_Deployment與治理正式規格.md`、`20_LINE客服與月嫂自助服務正式規格.md` §5.4、
`21_Contract_Signing_Commitment與正常驗收資料鏈正式規格.md` 與
`document/功能開發計畫/NAS_檔案庫與資料中心管理介面正式規範.md` 擁有；本工作包不重寫業務語意。

## 2. Scope、write set 與 effect ceiling

### In scope

- 共用 controlled-file typed port、logical object reference、readiness、discovery 與 verified read。
- owner-scoped metadata、version、digest、staging、Preview／Apply、idempotency receipt、readback。
- reconciliation 對 `exact | missing_object | digest_mismatch | orphan_object | still_writing` 的 fail-closed 投影。
- authenticated list／download API 與既有 Data Center React 元件的 typed adapter 接線。
- additive schema part、fresh assembly、canonical release metadata、descriptor、migration plan 與
  `lu_test_*` disposable fresh／preserve-data 驗證（只在 inventory 證明現有 schema 不足時）。
- focused Module → Subsystem → Global tests、strict UTF-8、structured headers 與 `git diff --check`。

### Excluded

- `union_db`、production DB／mount、實體檔案搬移、正式 NAS 權限／retention、deployment、entry switch。
- LINE provider delivery、production recipient、Cloud 資源、不可逆檔案刪除或全庫 cleanup。
- 由 watcher 掃描結果直接形成任何 Contract、Scheduling、LINE 或其他 Domain root fact。
- 覆蓋、簡化或重建已核准的 Data Center React 元件樹。

### Write set

- `subsystems/controlled_files/`、`infrastructure/file/`、對應 `api/` composition／schema／route。
- 必要時的 `db/schema_parts/`、`db/schema.sql`、canonical migration release／catalog／descriptor。
- 對應 `tests/`、既有 `ui_react/` Data Center typed adapter 與 focused tests。
- 本工作包、owner 正式規格的 runtime status、96 current register 與 final evidence index。

## 3. 必要性 gate

| 步驟 | 保護的 current requirement／failure path | 分類 |
|---|---|---|
| 保留既有唯讀 adapter 並補 typed contract | raw path traversal、未穩定檔案、digest 漂移必須 fail closed | `required_now` |
| 建立 owner-scoped metadata／version／receipt | 既有 `storage_key` 無法證明 owner、版本、staging 與 replay 契約 | `required_now` |
| 建立 reconciliation | metadata/object orphan、digest mismatch、still-writing 不得被合法空結果吞掉 | `required_now` |
| authenticated list／download | Web／LIFF 不得直接存取 mount 或公開 URL | `required_now` |
| 接入既有 Data Center UI | 96 completion 要求真 Query／download，且 UI preservation invariant 禁止覆蓋 | `required_now` |
| 實體刪除與批次 cleanup | 需要 production retention、精確 target 與不可逆操作 gate | `required_later` |
| provider delivery | 屬 `CUR-LINE-PROVIDER`，不能由 storage lane 旁路 | `merge` 至 L3 |

Entry gate：保留步驟都有 current Authority、failure behavior、最小 scope 與 acceptance；狀態 `passed`。

## 4. Source-basis／reuse gate

| Basis | Exact source／revision | 決定 |
|---|---|---|
| Latest Authority | 2026-08-26 user direction；96 current register | `reuse` |
| Canonical specification | `00` §2.2、`17` §3.5、`18`、`20` §5.4、`21` amendment、NAS 正式規範 | `reuse` |
| Current project source | HEAD `7f5f0624f75e7d50217b601639ff58f2c42d7505` 的 `subsystems/controlled_files/contracts.py`、`infrastructure/file/controlled_file_storage.py`、`media_assets`／`line_media_records` | `copy-adapt` existing project capability |
| Current tests | `tests/test_controlled_file_storage.py` baseline `9 passed, 1 skipped` | `reuse` and extend |
| External source／dependency | 無；標準庫 `pathlib`／`hashlib`／`mimetypes` 已足夠 | `reject` new dependency |

現有 schema 可保存部分 legacy metadata，但不能機械證明 staging、owner-scoped version、terminal receipt 與
reconciliation outcome，因此 additive metadata release 是候選；必須先通過第 5 節全部 DB gate 才能施工。

## 5. DB change inventory 與 gates

| 類別 | 候選效果 | Replay／rollback | 狀態 |
|---|---|---|---|
| `schema-only` | 新增 controlled-file metadata／staging／receipt／reconciliation owned objects | additive release；candidate 驗證；未 switch 前丟棄 candidate | `approved-candidate` |
| `system-seed` | 無 | 不適用 | `none` |
| `business-row-backfill` | 無；legacy row 不自動升格為受控 object | 不適用；未知 lineage 留 review | `none` |
| `destructive` | 無 | 禁止 | `none` |

執行順序固定為 scope → inventory → static release → descriptor → read-only plan → disposable fresh →
preserve-data candidate → developer acceptance。任一必要 gate `BLOCKED`／`NOT_RUN` 時總結固定為
`DB_CHANGE_NOT_READY`，不得修改 `union_db`、不得執行 replacement 或 `--switch`。

## 6. Acceptance、negative controls 與停止條件

### Acceptance

1. Query／discovery 只回 logical folder、filename 與 owner-approved typed metadata，不回 host／UNC／mount path。
2. staging Preview 零寫入；Apply 鎖定同一 owner、subject、purpose、digest、version、fingerprint 與
   idempotency，replay 回原 receipt，same-key different payload／stale／digest drift 零寫入。
3. authenticated download 重讀 exact object identity／digest，缺失、漂移、超限、讀取中變更皆 fail closed。
4. reconciliation 可區分 exact、missing、digest mismatch、orphan 與 still-writing，未知狀態不得自動修復。
5. Data Center 保留既有雙欄樹、容量條、提示與彈窗，僅以 typed adapter 置換本機假 facts。
6. 必要 DB gates、focused tests、final drift check、strict UTF-8、headers 與 `git diff --check` 全部 passed。

### Negative controls

- `../`、absolute、drive／UNC、symlink escape、colon／backslash reference 固定拒絕且錯誤不洩漏路徑。
- watcher discovery 不建立 Domain completion、delivery、receipt 或 provider side effect。
- 未登入、owner mismatch、deleted／quarantined object、digest mismatch、stale version 均不可下載或 Apply。

### Stop conditions

- public contract、Domain owner、production target、destructive retention／delete 或 external side effect 需要新裁決。
- release chain、descriptor 或既有 owned object 出現 `partial`／`drift` 時停止 DB lane並保存去敏 evidence。
- 任何單次補丁執行超過 30 秒時停止該補丁並通知使用者。
