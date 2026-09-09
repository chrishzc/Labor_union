# Controlled File Storage／NAS 正式規格

## 1. 文件狀態與 Authority

- 狀態：`consolidated-current-baseline`
- 收斂日期：2026-09-09
- Owner：Controlled File Storage / Infrastructure boundary
- 上位共同契約：`00_Global_共同契約.md`
- 關聯規格：各 owning Domain 的文件產生、送出、核銷、簽署、報表與附件契約
- 歷史來源：`document/功能開發計畫/NAS_檔案庫與資料中心管理介面正式規範.md`（完成遷移後只保留於 Git history）

本文件承接 Controlled File Storage 與 NAS-backed storage 的 exact machine contract。`00_Global_共同契約.md` 保留跨 Domain 不變量；本文件負責 purpose registry、管理 API、Preview／Apply、receipt、Freeze-Before-Send、staging、reconciliation、readiness、backup／restore 與管理 UI 的正式邊界。

本文件不授權任何特定 production NAS mount、credential、外部傳送、付款、簽署或資料庫 migration。實作存在不等於外部／production acceptance 已完成。

## 2. 核心原則

1. 所有受治理業務檔案必須經 typed Controlled File Storage boundary；不得由 generic Data Browser、任意檔案上傳、前端、script 或直接 filesystem write 建立另一套正式寫入路徑。
2. DB metadata 與 storage bytes 必須可用 stable `file_id`、`version`、`purpose`、hash 與 owning business reference 對帳。
3. Preview 零 durable 副作用；Apply 才可建立正式檔案／版本或執行明確允許的 cleanup／reconciliation command。
4. 同一正式檔案 identity 不可覆寫既有 frozen revision；更正使用 additive revision 並保留 lineage。
5. 外送、列印、下載供正式用途或提交政府／合作方前，必須引用 immutable frozen artifact，不得讀取仍可變動的 live workspace 檔案。
6. NAS 只是 storage backend；「NAS 上有檔案」本身不是 business Authority、publication receipt、簽署成功或 owner state。

## 3. FILE_PURPOSE_REGISTRY

系統必須維護唯一的 `FILE_PURPOSE_REGISTRY`。至少涵蓋：

- `final_signed_contract`
- `client_receipt`
- `case_report`
- `government_subsidy_application`
- `service_date_confirmation`
- `rich_menu_background`

每個 purpose 至少定義：

- `owner_domain`
- `file_format`
- `source_of_truth`
- `generation_cadence`
- `db_reference`
- `consumers`
- `overwrite_policy`
- `retention_policy`
- `backup_required`
- `restore_owner`

新增 purpose 必須先有唯一 owner 與 typed consumer；不得用自由字串繞過 registry。

## 4. 正式檔案 metadata

正式 record 至少可 read back：

- `file_id`
- `version`
- `purpose`
- `domain`
- owning business `ref`
- `storage_backend`
- `storage_locator`
- `content_sha256`
- `mime_type`
- `size_bytes`
- `status`
- `source_kind`
- uploader／actor
- `created_at`
- `updated_at`
- audit／lineage

`storage_locator` 是 storage adapter 的定位資訊，不得被前端解釋成可繞過 typed download boundary 的任意 OS path。

## 5. Closed management routes

Controlled File Storage 的管理介面使用 closed typed route set：

```text
GET  /api/v1/data-center/files
GET  /api/v1/data-center/files/{file_id}
GET  /api/v1/data-center/files/{file_id}/download
POST /api/v1/data-center/files/preview
POST /api/v1/data-center/files/apply
GET  /api/v1/data-center/storage/readiness
GET  /api/v1/data-center/backup/readiness
GET  /api/v1/data-center/reconciliation
POST /api/v1/data-center/reconciliation/preview
POST /api/v1/data-center/reconciliation/apply
POST /api/v1/data-center/staging/preview
POST /api/v1/data-center/staging/cleanup
```

不得建立 generic alternate upload route、Data Browser table mutation 或直接 filesystem endpoint 來取代上述 owner boundary。若 current implementation 的 exact route 變更，必須先更新本 formal contract 與 consumer／test，再移除舊 route；不得雙軌長期並存。

## 6. Preview／Apply／idempotency

### 6.1 File Preview

`POST /api/v1/data-center/files/preview`：

- 只驗證輸入、purpose、owner、格式、大小、reference、readiness、預期版本與 policy；
- 可計算 hash／計畫，但不得留下 DB row、正式 storage bytes、publication task 或其他 durable business side effect；
- backend／permission／purpose／owner 不明確時 fail closed。

### 6.2 File Apply

`POST /api/v1/data-center/files/apply`：

- 必須使用 typed command 與 idempotency identity；
- exact replay 回原 committed receipt；
- 相同 idempotency identity 搭配不同 payload 必須 conflict／fail closed；
- bytes staging 與 DB metadata commit 的順序／補償必須避免 metadata 指向不存在檔案或失敗後遺留被誤認為正式的 provisional bytes。

成功 receipt 至少包含：

```json
{
  "kind": "controlled-file-apply-receipt.v1",
  "status": "committed",
  "payload": {
    "kind": "controlled-file-record.v1",
    "file_id": "...",
    "version": 1,
    "purpose": "...",
    "storage_backend": "...",
    "storage_locator": "...",
    "content_sha256": "...",
    "size_bytes": 0,
    "created_at": "...",
    "updated_at": "..."
  }
}
```

欄位可 additive 擴充，但既有 discriminator 與 business identity 不得被前端自行重解釋。

## 7. Query／download 邊界

- `GET /files` 與 `GET /files/{file_id}` 回 structured metadata／read model。
- `GET /files/{file_id}/download` 只能透過 typed boundary 串流 committed bytes。
- authorization 必須同時檢查 actor、purpose／domain 與 owning business reference；知道 `file_id` 不代表可下載。
- UI 不得顯示 filesystem 路徑作為直接操作入口。
- missing／hash mismatch／storage unavailable／unauthorized 一律 fail closed，不以空檔或舊快取偽裝成功。

## 8. Storage readiness

`GET /api/v1/data-center/storage/readiness` 至少檢查：

- shared storage root；
- local temp／staging directory；
- required root directories；
- read／write／create／rename／delete 等實際需要能力；
- mount／path 存在性與 permission；
- configured backend identity。

缺 path、mount、permission 或 required capability 時 readiness 必須 false；不得因 process 本身健康就宣稱 storage ready。

## 9. Backup／restore readiness

`GET /api/v1/data-center/backup/readiness` 至少 read back：

- backup destination 與 primary storage 的隔離性；
- required credential／permission readiness；
- last successful backup；
- last restore drill；
- applicable RPO／RTO；
- immutable／versioned backup 能力；
- integrity verification 結果。

只有同一 primary storage 內的複本、DB 本機備份或未驗證 restore 的備份，不得宣稱完整 backup readiness。

Production-ready 必須以實際 backup＋restore drill 與其 evidence 判定，不得由設定檔推定。

## 10. Freeze-Before-Send

對至少下列正式格式：

- `application/pdf`
- `application/vnd.openxmlformats-officedocument.wordprocessingml.document`
- `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`

正式外送／列印／提交前必須形成 immutable frozen revision，至少保存：

- `file_id`
- `version`
- `purpose`
- `content_sha256`
- exact bytes／size
- primary location
- backup location（purpose 要求時）
- `frozen_at`
- actor／reason
- integrity manifest

規則：

1. 同一 business identity 的 frozen revision 不得 in-place overwrite。
2. 新 revision 必須 additive 並連回前一 revision。
3. 若來源由多段資料／附件合併，merge 完成後才 freeze。
4. 同一 business event 的多個 outbound references 必須指向同一 frozen `file_id + version + hash`。
5. replacement 必須保留 reason、actor、time 與被取代 revision。
6. outbound print／download／send／government submission 只能消費 frozen revision。
7. live Excel／Word／NAS workspace directory 不是 outbound Authority。
8. outbound receipt 必須保存 exact frozen identity／revision／hash，不能只記 filename。

## 11. Staging／cleanup

相容性 `/data` 或 runtime 暫存內容只能進入明確 `_staging/<runtime namespace>/<category>` 類型目錄；不得被誤認為 formal business storage。

允許的 staging residue category 必須 closed／enumerated。Cleanup：

- Preview 零副作用；
- 只處理 declared operation plan 與 boundary 內的檔案；
- 必須使用 minimum age gate，預設不得低於 30 分鐘，除非另有更嚴格 owner contract；
- 不得刪除 frozen／committed business artifact；
- 每次 cleanup 必須有 actor、plan、deleted set、skipped set、reason 與 receipt；
- cleanup 後重新評估 disk pressure／readiness。

## 12. Reconciliation

Reconciliation 必須能對照四個世界：

1. DB governed root／metadata；
2. storage truth；
3. business page／report／receipt reference；
4. external send／scan／submission evidence（若適用）。

最低檢查：

- committed storage object 存在；
- size／hash 與 metadata 一致；
- purpose／owner／domain／business ref 一致；
- business read model 指向同一 revision；
- outbound receipt 指向同一 frozen `file_id/version/hash`；
- orphan NAS file 不會自動升格為 Authority。

missing file、owner mismatch、reference mismatch、hash mismatch、frozen revision 被覆寫等狀況必須 fail closed，進 anomaly／manual review。

Reconciliation Apply 只可執行 deterministic、預先允許的 technical repair；不得自行修改 business semantics、重送外部訊息、還原備份或修 NAS mount，除非有另一份 owning contract 明確授權。

## 13. 管理 UI

Data Center／檔案庫 UI 只呈現 formal read model 與 typed actions。至少能顯示：

- file identity／version／purpose／domain／business reference；
- filename／mime／size／hash；
- storage backend 與 readiness；
- frozen／status／created／updated；
- download eligibility；
- backup／restore readiness；
- staging／reconciliation preview/result；
- error／unknown／not-ready 狀態。

UI 不能：

- 直接改 DB row 或 filesystem；
- 把 browser local state 當正式狀態；
- 因下載成功就宣稱 business submission 成功；
- 因 NAS path 可見就跳過 owner authorization。

## 14. Current implementation／acceptance 邊界

截至 2026-09-01 的 repository-local evidence 已證明：typed storage port、local storage adapter、staging、Preview／Apply、list／get／download、cleanup／reconciliation、Data Center adapter、source tests 與 shared-MySQL DB gate 已有通過證據。

但下列不得由上述證據推定完成：

- enabled human Session 的 fresh Chrome 正向 list／download acceptance；
- 正式 NAS mount／permission／failure injection；
- 真 backup destination 與 restore drill；
- production credential／network／operator／RPO／RTO；
- 任何真實 outbound send／government submission／external signing。

因此 current overall acceptance 應維持「repository-local foundation 可用；external／production gate 另行驗證」，不得把 source／DB pass 升格成 production-ready。

## 15. Formal acceptance gate

至少需要：

1. source contract／focused tests PASS；
2. shared MySQL Apply／replay／constraint／fail-closed PASS；
3. authenticated browser list／detail／download／readiness PASS；
4. local preview／staging／cleanup／reconciliation 證明零越權與 deterministic readback；
5. NAS mount／permission／unavailable／recovery 測試 PASS；
6. backup＋restore drill PASS；
7. Freeze-Before-Send 的 immutable revision／manifest／replacement lineage PASS；
8. owning business consumer 與 outbound receipt 指向相同 frozen identity／hash；
9. production 外部行為只有在另有明確授權的環境／operator／credential／rollback 下才可執行。

未跑的層級標 `NOT_RUN`，有 blocker 標 `BLOCKED`；不得以「已有 API／UI」代替 acceptance。

## 16. 歷史來源處置

`document/功能開發計畫/NAS_檔案庫與資料中心管理介面正式規範.md` 的仍有效 machine-contract 語意已由本文件承接。其舊 UI 排版、環境假設、歷史實作描述與非 formal wording 不再建立 Authority。

來源文件完成 migration 後應從 working tree 移除；稽核與歷史脈絡由 Git history 取得。