---
doc_type: work-package
declared_status: completed
date: 2026-08-15
owner: Case Import / Orders / Anomalies
priority: P0
successor_of: PROV-20260815_HCM_Owner_Completion_and_Warning_Resolution_Proposal
---

# 95 HCM 修正版來源與警示解除 Work Package

## 人工裁決與 business scenario

2026-08-15 使用者確認：異常中心只提供警示、追蹤與跳轉，不承接資料修正。HCM 缺漏或格式錯誤由
操作人取得修正後的完整 HCM 檔案，再走 HCM owning backend Preview／Apply；不另做 Streamlit
欄位編輯，未來 React 只消費 typed API。未達 HCM 最低 import 條件的來源列不進異常中心。

既有 `ApplyCaseImport` 只擁有首次建案與 exact replay；同案號、不同來源目前固定進
`case_import_existing_source_conflict` review，不能藉重播覆寫。因此本 Work Package 建立獨立的
HCM 修正版來源命令，不改寫 immutable source／review，也不把 warning tracking transaction 與
formal root mutation 混在同一個 Unit of Work。

## Global → Domain → Subsystem → Module

- **Global**：沿用 actor、correlation、idempotency、fingerprint、expected version、typed error、outer UoW、
  immutable receipt 與 committed outbox 契約。Preview 零寫入；Apply 必須 fresh read、鎖定案件與來源。
- **Case Import Domain**：擁有 HCM 修正版候選、允許採納的欄位、來源驗證、既有案件一致性、修正結果與
  root predicate。來源空值或無效值不能覆寫；案件編號不能改；不得以 masked identity 反推案件。
- **Case Import Subsystem**：`PreviewHcmResubmission`／`ApplyHcmResubmission` 驗證新來源 receipt 與
  prior warning 的 explicit association，在一個 owner UoW 更新 formal Client／Order 可寫欄位、追加
  correction event／receipt／outbox。失敗的修正版只建立新 review／warning，不改 formal root。
- **Anomalies Subsystem**：只在 owner outbox commit 後另開 transaction，依 occurrence 的
  `logical_code + field_path` 重讀 formal root predicate；成功才追加 `auto_resolved`。失敗修正版若產生
  replacement occurrence，舊 task 以 system `closed` 指向 replacement。不得倒建警示。
- **API Module**：提供 HCM owner typed Preview／Apply 與 warning referral descriptor。referral 只含
  target command、expected warning version、去敏 context；不接收 corrected payload、不回傳 raw source。
  本段不修改 Streamlit，也不建立 React 專案。

## Command contract

### `PreviewHcmResubmission`

輸入：修正後來源的 opaque row identity、prior occurrence identity、expected warning version、actor、
correlation id。輸出：案件編號、將採納欄位、仍有問題的 typed warnings、候選欄位的 root snapshot fingerprint、preview
fingerprint 與去敏摘要。零寫入。

固定檢查：

1. prior occurrence 存在、仍為 current、owning lane 為 HCM，且 logical code 僅限
   `HCM-FIELD-001`、`HCM-FIELD-002`、`HCM-LINK-001`、`HCM-LINK-002`、`HCM-CASE-002`。
2. 新來源具可用案件編號，且精確等於 prior warning 已綁定的 canonical case number；不得由
   `masked_subject`、姓名、電話、IP 或列順序猜測。
3. 全列重新使用同一 HCM validator；只可採納 prior warning 的單一 `field_path`，且該欄位必須在既有
   HCM→Client／Order authority mapping 中。其他欄位即使新來源提供有效值也不得更新。
4. 案件編號、root identity、受保護狀態、版本、ledger／payroll／scheduling facts 不得由修正版覆寫。

### `ApplyHcmResubmission`

除 Preview 輸入外，接受 expected root snapshot fingerprint、preview fingerprint、idempotency key 與 reason。
Apply fresh read 並鎖定 prior occurrence、新來源與 canonical Client／Order；stale、不同 payload replay、
root mismatch、來源仍無效或 actor 不允許時零 root 寫入並回傳 typed error。

同 key／同 payload回傳同 receipt；同 key／不同 payload 固定 conflict。成功只追加 owner correction
event／receipt／outbox；warning tracking 由後續 projector 獨立處理。

## Formal root effect

- `HCM-FIELD-001/002`：修正版中該 `field_path` 存在且通過同一 validator 時才採納；顯示仍由
  generic logical code 加欄位名稱組成，例如「缺少身分證」。不為每個欄位新增 code。
- `HCM-LINK-001/002`：只有修正版與既有正式資料能得到唯一、可證明的 Client relation 時才建立；
  不提供任意 candidate picker。無唯一結果時保留 warning。
- `HCM-CASE-002`：案件編號相同、來源內容不同但沒有唯一欄位路徑時，不可由整列 diff 推定可寫欄位；
  Preview 固定回傳 `hcm_resubmission_field_scope_ambiguous`，零 root 寫入。後續必須重新投影成具體欄位
  警示，或由人工 `closed` 保留現值；後者不算 auto-resolved。
- `BECLASS-001`：沒有 HCM 修正 action；只在唯一 BeClass counterpart 完成綁定後由 predicate 解除。

## DB change inventory

| 類別 | source artifact／target | 資料效果 | replay／rollback／unresolved policy |
|---|---|---|---|
| schema-only | 新增 HCM correction events | append-only 保存案件、來源與採納欄位 | event identity 唯一；immutable trigger；partial／drift fail closed |
| schema-only | 新增 HCM correction receipts | 保存 command／preview fingerprint、root snapshot fingerprint 與結果 | idempotency key 唯一；exact replay 回同 receipt |
| schema-only | 新增 HCM correction outbox | committed owner intent 驅動 warning rescan | intent 唯一；最多 3 次、間隔 1 秒後 dead-letter |
| schema-only | HCM review／warning → canonical case binding | explicit FK／opaque relation，不由 masked value 反推 | 只新增 relation；同 source 唯一；無法唯一綁定留 unresolved |
| system-seed | 無 | 不新增 enum seed 或 UI 文案 seed | warning registry 維持文件 owner |
| business-row-backfill | 無 | 不掃描或推定既有 review 的案件 | 舊 warning 需由新修正版來源建立 explicit association |
| destructive | 無 | 不刪除／改寫 source、review、receipt、warning 或 root 歷史 | rollback 僅針對尚未套用的 successor release |

Static inventory 已確認 part `200` 由同批 Finance successor 擁有，且 active catalog、archive 與未追蹤
檔案均無 `201` 碰撞；integration identity late-bind 為 `201_hcm_resubmission_corrections.sql`，release
使用 `labor-union-wp95-hcm-resubmission-2026-08-15-v1`。新 part 只新增：

- `case_import_hcm_review_case_bindings`：review row 與 canonical case／原始 import event 的 explicit binding；
- `case_import_hcm_correction_events`、`case_import_hcm_correction_receipts`、
  `case_import_hcm_correction_outbox`：owner mutation、replay 與 committed rescan intent。

重送關聯必須重用 part 195 的 `import_warning_resubmission_associations`，不得建立競爭表；release chain
位置固定在 Finance part 200 successor 後、schema-assembly release 前。以上仍須 descriptor、read-only plan
與 engine gate 驗證，不能只因 identity 無碰撞就宣稱 schema ready。

## Exact write set

- 正式規格 15、17、WP90、本 WP 與 evidence index。
- HCM resubmission Domain、Subsystem、MySQL repository、typed API schema／route、owner outbox consumer。
- additive schema part、fresh assembly、canonical migration release、owned-object descriptor、operator docs。
- fail-before-fix、Domain、Subsystem、API、disposable MySQL、fresh bootstrap 與 preserve-data candidate tests。

不得操作 production data 或既有 `union_db`；不得修改 Streamlit／React；不得把 corrected fields 加到
warning tracking API；不得擴張 Client／Staff BeClass、Historical Orders 或 Finance owner mutation。

## Legacy exit

`/api/v1/case-import/hcm/historical-workbooks/apply` 與其 Preview 入口曾透過
`HcmHistoricalRowIntake` 對既有 Client／Order 做整列覆寫，沒有 prior warning scope、owner receipt 或
committed outbox。它與本 WP 的欄位限定裁決互斥，故自本 WP 起固定回傳
`hcm_historical_whole_row_overwrite_retired`，不得作為相容路徑；未來 React 僅接 HCM owner 的 typed
single-warning Preview／Apply route。

## Acceptance

1. Preview 零寫入；Apply fresh-read＋root lock，same-key replay、different-payload、stale、root mismatch、
   ambiguity 與 partial failure均有 typed evidence。
2. 修正版成功只更新 allowlist 中通過驗證的 HCM-owned formal fields；immutable source／review 不變。
3. owner commit 與 warning transition 是兩個 UoW；成功 predicate 才 `auto_resolved`，失敗則 replacement
   warning 可追溯且舊 task 指向 replacement。
4. unknown issue／predicate 最多嘗試 3 次、相鄰至少 1 秒，去敏 dead-letter，零部分投影。
5. typed API 不揭露 raw workbook、完整個資、任意候選或 generic corrected payload；可由未來 React 消費。
6. DB change gate 七項與 focused／Domain／API／disposable MySQL／preserve-data 驗證全部 PASS 後，才可
   宣稱 HCM owner slice 完成並回寫 WP90。

## Stop conditions

- prior warning 與 canonical case 無 explicit binding、source row／receipt 不存在或案件編號不一致。
- field 不在既有 HCM 欄位權威、驗證失敗、Client relation 不唯一、expected version stale。
- migration release／descriptor／read-only plan／真實 disposable MySQL 任一 gate 未通過。
- 即將把 raw source、完整個資、corrected payload 或 formal mutation 放進異常中心。

## Completion evidence

2026-08-15 completion receipt：
[`2026-08-15_wp90_wp95_completion_receipt.md`](../../03_追蹤清單與證據/evidence/2026-08-15_wp90_wp95_completion_receipt.md)。
完成項目包括完整修正版工作簿 scoped Preview／Apply、single-warning target derivation、fresh root lock、
immutable owner event／receipt／outbox、owner outbox 後的 auto-resolve、legacy whole-row `410` exit、
entrypoint governance、fresh assembly 與 preserve-data candidate engine verification。未替換 source DB，
也未建立 Streamlit／React 實作。
