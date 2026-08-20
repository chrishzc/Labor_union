---
doc_type: work-package
declared_status: completed
date: 2026-08-15
owner: Scheduling
domain: Assignments / Scheduling
subsystem: Staff Leave Request Intake / Leave Substitution
implementation_authorization: granted-by-user-2026-08-15
---

# 月嫂 LINE 請假申請與管理待辦工作包

## 1. 目標與裁決

月嫂可在 LINE LIFF 以已驗證、已綁定的身分送出請假申請；此動作只建立
Scheduling-owned 的待辦證據，**不改變** assignment、`staff_schedule`、Orders、Client Finance、
Payroll 或月嫂可接案投影。

管理人員受理後，只能帶著一次性導覽 context 前往既有案件行事曆，另行執行
Leave/Substitution Preview 與 Apply。只有該 Apply 的 canonical receipt 已提交，申請才能標為
`resolved` 並對月嫂通知「正式排班已處理」。

本工作包承接並取代功能計畫
`../../功能開發計畫/Scheduling_月嫂請假申請待辦與管理端處理開發計畫.md` 的實作範圍；
正式語意仍以 `01_規格基線/02_Assignments_Scheduling_Domain.md`、`17` 與 `20` 為 SSOT。

## 2. 實際業務場景

```text
已綁定月嫂在 LINE 填請假起訖日與說明
  → Scheduling 寫入 request、immutable event、receipt 與 LINE notification intent
  → 管理待辦顯示 pending
  → 管理人員受理，取得一次性「前往行事曆」context
  → 管理人員在既有案件／服務日上重新 Preview
  → 管理人員確認並 Apply 現有 leave-substitution command
  → committed canonical receipt 關聯原 request
  → request resolved，LINE outbox 通知完成
```

申請日期不可用來自動猜測案件、assignment、服務日或代班月嫂；管理人員必須在既有
Leave/Substitution 畫面明確選擇，且 Preview／Apply 的版本、fingerprint、lock 與跨 Domain
impact 契約完全不變。

## 3. Owner、根事實與不可變量

| 項目 | Owner／根事實 | 不可做的事 |
|---|---|---|
| LINE ID token、binding、delivery outcome | LINE Integration | 不得擁有請假或排班狀態。 |
| 請假 request、review event、receipt、canonical receipt linkage | Scheduling | 不得把 request 當正式 leave outcome。 |
| 正式請假／順延／指定代班及跨域 impact | 現有 Leave/Substitution workflow | 不得由 LIFF、待辦或通知旁路寫入。 |
| 通知 | committed LINE outbox／delivery worker | 不得在 request transaction 內直接呼叫 LINE。 |

1. LIFF 身分只接受 server-side 驗證的 ID token 或既有有效 flow；query string 的 user ID 永不可信。
2. 請假申請、受理、拒絕、取消與 canonical linkage 各自使用 expected request version、stable
   idempotency key、receipt 與 immutable event；exact replay 回原 receipt，不同 payload 固定 conflict。
3. 所有 authenticated、enabled 的內部人員擁有相同業務操作權限；不得以 persisted role 或 capability
   區分受理、拒絕、取消或查詢功能。
4. request 或 review 狀態不參與 Orders AutoComplete 競爭；只有 canonical Leave/Substitution Apply
   取得既有 Orders／Scheduling locks 並改變正式根事實。
5. LINE delivery timeout 或 5xx 只重試已提交 delivery task；驗證、binding、stale、conflict 和
   business rejection 不自動重試。

## 4. Request 狀態與命令

Canonical request 狀態為 `pending`、`accepted_for_processing`、`rejected`、`cancelled`、`resolved`：

| 命令 | 前置狀態 | 結果 | 必填資料 |
|---|---|---|---|
| `SubmitStaffLeaveRequest` | — | `pending` | 起訖日、可選去敏說明、verified staff identity、idempotency key |
| `AcceptStaffLeaveRequest` | `pending` | `accepted_for_processing` | expected version、review reason、管理 actor |
| `RejectStaffLeaveRequest` | `pending` | `rejected` | expected version、非空 reason、管理 actor |
| `CancelStaffLeaveRequest` | staff：`pending`；管理：`pending`／`accepted_for_processing` | `cancelled` | expected version、非空 reason、actor |
| `ResolveStaffLeaveRequest` | `accepted_for_processing` | `resolved` | request version、唯一 canonical leave-substitution receipt identity |

月嫂一旦被受理後不可自行取消；管理人員可在 canonical Apply 前取消。`resolved`、`rejected`、
`cancelled` 都是 terminal，不可回復或覆寫。受理不是批准正式排班，UI／API／通知一律用「已受理處理」，
禁止用「已核准請假」。

`ResolveStaffLeaveRequest` 不是公開 UI command：它只能由 canonical Leave/Substitution Apply 提交後的
committed receipt/outbox consumer 呼叫。若 receipt 不存在、與 request 指定的 staff 無關、已關聯其他
request，或 request 已非 `accepted_for_processing`，固定 typed conflict 且零正式排班寫入。

## 5. Input、隱私與錯誤契約

- request 僅接受 `leave_start_date`、`leave_end_date` 與可選 `reason`；開始日不得晚於結束日，日期範圍
  與說明長度由 Scheduling validator 限制。
- 不接受月嫂輸入的案件號碼、代班人姓名／電話、正式服務日、薪資或帳務資料；這些欄位不進 request payload。
- 管理端清單僅回必要的月嫂顯示名稱、日期、狀態、去敏說明與 receipt linkage；不回傳原始 LINE token、
  完整聯絡資訊或 provider payload。
- 最低 typed errors：`liff_token_invalid`、`line_staff_binding_not_found`、`leave_request_invalid`、
  `leave_request_not_found`、`leave_request_stale`、`leave_request_state_conflict`、
  `leave_request_idempotency_conflict`、`leave_request_receipt_conflict`、`leave_request_not_resolvable`。

## 6. 實作邊界與預定 write set

1. 新增 Scheduling request Domain／Subsystem（Query、Submit、Review、Cancel、Resolve）；每個 mutation
   有單一 outer Unit of Work、fresh read、lock、receipt 和 committed outbox intent。
2. 新增 verified LIFF intake route；管理 Query／Command routes 和 typed UI client 一律放在 Scheduling boundary，
   不放入 LINE identity review route、`LineAdminApiClient` 或 Streamlit business logic。
3. 將 `line/static/staff_schedule.html` 的現行「請假入口尚未啟用」改為 typed submit client；管理端只提供
   待辦與 deep link，不把 Leave/Substitution Apply 嵌入或自動呼叫。
4. `staff_leave_review_service.py` 與其 legacy `services.*` direct writer 不得作為 caller、adapter 或 fallback；
   舊 `staff_leave_requests` 的 `approved`／`rejected` enum 不得被重新詮釋為本工作包 state。
5. 新增 additive request root、immutable request-event、receipt 與 canonical-receipt-linkage schema artifacts。
   既有 `staff_leave_requests` 僅保留歷史相容／read-only disposition；實作不得 update 整列來覆寫正確資料。
6. 同步更新 `db/schema.sql`、release metadata／descriptor、正式規格、entrypoint queue、focused tests 與 evidence。

舊資料 disposition：已存在的 `staff_leave_requests` 若有資料，維持 legacy historical view；不自動轉成
`accepted_for_processing` 或 `resolved`。任何 backfill 必須另列為 business-row-backfill，提供 dry-run、
fingerprint、unresolved queue、replay 與 rollback evidence。

## 7. 明確不在範圍

- 不改動既有 Leave/Substitution Domain 的 resolution type、Preview／Apply、Orders lock 或跨 Domain impact。
- 不因請假 request 自動選案、選日期、找代班、建立 assignment 或更改可接案狀態。
- 不使用 Streamlit 直接 SQL；未來 React 重寫只替換 UI adapter，不改 API／Domain 契約。
- 不執行實際 LINE provider 發送、production DB migration、部署或 cutover，除非另獲明確執行授權。

## 8. 驗收與資料庫 gate

| 類別 | 必要驗收 |
|---|---|
| Module | 日期／payload validation、狀態機、masking、fingerprint、error mapping。 |
| Subsystem | submit replay/conflict、review stale、取消競爭、receipt linkage、outbox retry。 |
| Domain | request／review 零正式排班寫入；只有 canonical Apply 改變正式服務日與 impacts。 |
| Global | LIFF submit → 管理待辦 → calendar Preview／Apply → receipt linkage → LINE notification。 |
| Entry point | 新 API、LIFF page、管理待辦頁逐一進 entrypoint governance，無 `review_required`。 |
| Schema | Scope、inventory、static release、descriptor、read-only plan、fresh bootstrap、preserve-data candidate、developer acceptance 依專案 DB gate 全數通過。 |

在 schema gate 任一項為 `BLOCKED` 或 `NOT_RUN` 前，結果必須標示 `DB_CHANGE_NOT_READY`；不得套用至任何
既有資料庫。LINE provider publish／實機 LIFF 僅在另行授權後驗收。

## 9. 交付完成條件

- LIFF request 有 verified staff binding、stable replay、receipt 與可稽核 event。
- 管理待辦只處理 request，不可宣稱正式排班已變更。
- `resolved` 僅由唯一 canonical leave-substitution receipt 驅動；delivery failure 不回滾已提交結果。
- legacy direct writer 沒有 active caller，且不會被新 route 重新啟用。
- 所有寫入、schema 與 entrypoint 契約具 focused regression 與 evidence receipt。

## 10. 2026-08-15 執行證據與完成結果

已完成：Scheduling request Domain／workflow、verified LIFF submit／pending cancel、管理待辦 Query／受理命令、
canonical Apply receipt linkage、durable LINE delivery task、immutable schema objects、正式規格與
entrypoint queue 已同步。focused regression 為 `46 passed`。

| DB gate | 狀態 | 證據／結果 |
|---|---|---|
| Scope / inventory | PASS | 本工作包第 1～8 節；變更全為 schema-only，無 backfill。 |
| Static release / descriptor | PASS | `202_scheduling_staff_leave_intake.sql`、release manifest、descriptor、fresh assembly 與 generated validation SQL。 |
| Read-only plan | PASS | `../03_追蹤清單與證據/evidence/staff_leave_intake_preserve_plan_20260815.json`；202 為 `absent`。 |
| Fresh bootstrap | PASS | `scripts.build_validation_schema_release --check` 與 schema assembly focused tests。 |
| Preserve-data candidate | PASS | source backup → restore → apply → verify 完成；所有 owned objects exact、來源資料 preservation 成立。見 `../03_追蹤清單與證據/evidence/staff_leave_intake_candidate_operation_20260815.json`。 |
| Developer acceptance | PASS | 經明確授權，以 `scripts.update_local_database --apply --confirm-configured-database --mysql-container mysql_db` 完成 source backup、candidate 驗證與同名 replacement；其後 `--require-current` 回報 `current`。見 `../03_追蹤清單與證據/evidence/staff_leave_intake_developer_acceptance_20260815.md`。 |

所有必要 DB gate 均為 **PASS**；本工作包完成。實際 LINE provider publish／實機 LIFF 仍不在本次
授權範圍，並非本工作包的完成條件。
