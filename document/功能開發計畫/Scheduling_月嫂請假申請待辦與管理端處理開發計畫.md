---
status: approved
priority: pending-scheduling
owner: Scheduling
domain: Assignments / Scheduling
subsystem: Staff Leave Request Intake / Leave Substitution
updated_date: 2026-08-12
implementation_authorization: not-granted
---

# Scheduling 月嫂請假申請待辦與管理端處理開發計畫

## 1. 決策與目標

2026-08-12 人工選定「方案三」：保留月嫂透過 LINE 頁面送出請假申請，但申請只形成
Scheduling-owned pending evidence 與管理待辦，不直接修改排班、訂單、帳務或薪資。

管理員讀取申請後，仍須進入既有管理端行事曆，依案件及正式服務日建立 leave-substitution
Preview；確認影響後才 Apply。只有既有 canonical leave-substitution receipt 能證明正式排班已變更。

本計畫已確認產品方向，但尚未授權修改 production code、schema、API 或部署。

## 2. Business scenario

```text
月嫂在 LINE 頁面送出請假日期與說明
→ Scheduling 保存不可冒充正式排班的 request evidence
→ 管理員在請假待辦查看申請
→ 管理員接受處理、拒絕或取消待辦
→ 若接受處理，管理員前往既有行事曆選擇案件與正式服務日
→ 既有 leave-substitution Preview 顯示 Scheduling／Orders／Client Finance／Payroll 影響
→ 管理員確認後 Apply
→ request 連結 canonical receipt，標示正式處理完成
→ LINE outbox 通知月嫂處理結果
```

「接受處理」只代表管理員受理申請，不表示排班已核准或已變更。沒有 canonical receipt 時，
UI、通知及 API 都不得顯示「請假已完成」。

## 3. 現況與缺口

- `line/static/staff_schedule.html` 已提供請假表單，呼叫
  `POST /api/line/staff/leave-requests`，但 live API 沒有此 endpoint。
- `db/schema_parts/101_staff_leave_requests.sql` 已定義 `staff_leave_requests`，但 production source
  沒有 INSERT writer。
- `subsystems/scheduling/staff_leave_review_service.py` 依賴不存在的 `services.db_service` 與
  `services.line_task_service`，沒有 route、typed client 或 UI caller，不可掛入 FastAPI。
- canonical order-scoped leave-substitution Domain、Preview／Apply API、typed UI client、repository、
  outer Unit of Work 與跨 Domain impact 已存在，可作正式排班變更的唯一 replacement。
- `/line-staff-schedule` 目前在 entrypoint review queue 為 `review_required`。

## 4. Ownership 與 SSOT

| 資料／行為 | Canonical owner | 說明 |
|---|---|---|
| LINE staff identity evidence | LINE integration | 只證明送件者平台身分與驗證結果 |
| Leave request evidence／待辦 | Scheduling | 保存申請內容、狀態、版本、reviewer 與 linkage |
| 正式請假／代班排班結果 | Scheduling leave-substitution workflow | 只有 Apply receipt 可證明正式結果 |
| Orders／Client Finance／Payroll impact | 各 owning Domain | 由既有 leave-substitution outer UoW 協調 |
| 通知 delivery | LINE outbox／delivery worker | 不在 request 或 Domain transaction 內直接 HTTP 發送 |

LINE payload、request status、管理員受理或通知成功都不是正式排班根事實。

## 5. Request state machine

建議使用不會冒充排班核准的狀態名稱：

```text
pending → accepted_for_processing → resolved
       ├→ rejected
       └→ cancelled
accepted_for_processing → rejected | cancelled
```

- `pending`：申請已 durable 保存，尚未由管理員受理。
- `accepted_for_processing`：管理員決定進入正式行事曆處理，但排班尚未變更。
- `resolved`：已連結成功的 canonical leave-substitution receipt。
- `rejected`：不進入正式排班處理；必須保存 reason。
- `cancelled`：申請者或授權管理員在正式 Apply 前取消。

既有 `approved` enum 容易被誤解為排班已核准，不應直接沿用其語意。實作前須提出 additive
schema migration 與既有資料 disposition；不得直接重建或破壞 `staff_leave_requests`。

## 6. Scope

- 建立 verified LINE staff leave-request typed intake endpoint。
- 驗證日期、身分、payload budget、stable idempotency identity 與 exact replay／conflict。
- 建立 Scheduling request repository、outer UoW、receipt 與 audit/outbox。
- 建立管理端 bounded Query、typed client 與請假待辦 UI。
- 提供「前往行事曆處理」deep link，攜帶一次性 navigation context，不直接觸發 Apply。
- 受理、拒絕、取消採 expected version、reason、capability 與 idempotency。
- canonical Apply 成功後，以 receipt identity 關聯 request 並轉為 `resolved`。
- 透過 committed LINE outbox 通知受理、拒絕、取消與正式完成結果。
- 更新 entrypoint review queue、正式 Scheduling／LINE 規格、evidence index 與 release metadata。

## 7. Out of scope

- LINE request 不自動建立 leave-substitution command。
- 管理員受理不自動修改 `staff_schedule`、assignment、Orders、Client Finance 或 Payroll。
- 不把 `staff_leave_review_service.py` 直接掛入 FastAPI，也不復活任何 `services.*`。
- 不以月嫂自行填寫的代班姓名或電話直接建立 substitute staff identity。
- 不新增 LINE identity review route 或把請假審核放入 `LineAdminApiClient`。
- 不在本計畫內變更既有 canonical leave-substitution Domain 規則。

## 8. Dependencies 與人工確認門檻

- 實作前確認 request state names 與既有 `approved` rows 的 disposition。
- 確認哪些管理 capability 可受理、拒絕、取消與查看申請。
- 確認月嫂是否可在 `accepted_for_processing` 後、正式 Apply 前自行取消。
- 確認 request 與 case／assignment 的人工選擇方式；不得只依日期自動猜測案件。
- 若修改 owner、public interface、schema migration 或 LINE side effect，須建立正式 Work Package
  並取得 implementation authorization。

## 9. 預定 write set

- Scheduling leave-request Domain／Subsystem modules。
- Scheduling MySQL repository／Unit of Work adapter。
- LINE staff self-service intake route 與 typed schemas。
- Scheduling admin Query／Command routes與 typed UI client／panel。
- additive schema part、`db/schema.sql` 與 migration release metadata。
- focused tests、正式規格、entrypoint queue 與 evidence receipt。

精確檔名與互不重疊 write set 必須在實作 Work Package 核准時列出；本節不構成 mutation 授權。

## 10. Acceptance

- verified LINE staff 可送出 request；exact replay 回原 receipt，不同 payload 固定 conflict。
- 無 writer 可因 request 建立、受理或通知而直接改正式排班。
- 待辦 Query 有 bounded pagination、status filter、privacy masking 與 capability gate。
- 管理員受理後只能 deep-link 到既有行事曆，必須重新 Preview 並人工 Apply。
- 沒有 canonical receipt 時不得進入 `resolved`，也不得通知「請假已完成」。
- stale version、重複 review、取消與並行 Apply 都有 deterministic typed error。
- Apply 成功只關聯一個 request 與一個 canonical receipt；重播不重複 Domain writes 或 LINE task。
- LINE delivery 失敗不回滾已提交 request／Scheduling transaction，可由 worker 安全重試。
- legacy service 不再是 caller，`services.*` 不復活。
- `/line-staff-schedule` 與新增 endpoints 完成 entrypoint governance 裁決。

## 11. Required tests

- Module：payload/date validation、state transition、fingerprint、privacy masking。
- Subsystem：intake replay/conflict、review stale、cancel race、receipt linkage、outbox retry。
- Domain：request 不改排班；canonical Apply 才產生 Scheduling／跨 Domain impacts。
- Global：LINE submit → admin queue → calendar Preview／Apply → receipt linkage → LINE notification。
- Migration：既有空表與有資料情境、enum／state migration、rollback／preserve-data rehearsal。

## 12. 已完成的相鄰裁決

- `綁定訂單`、`訂單查詢` 維持 customer binding。
- `綁定後台帳號` 維持 admin binding。
- `LineAdminApiClient` 不擁有 Scheduling leave-review methods。
- `online.sh` 不屬於 Windows merge 驗收。

以上 alias 與 ownership focused regression 已完成，不是本計畫的待辦。

## 13. Decision／evidence links

- 正式 Scheduling 基線：`../架構重整/01_規格基線/02_Assignments_Scheduling_Domain.md`
- Global ownership：`../架構重整/01_規格基線/15_正式規格索引與裁決總表.md`
- LINE／Access：`../架構重整/01_規格基線/17_External_Integration_LINE_Access正式規格.md`
- 現行 canonical API：`api/routes/leave_substitution.py`
- 現行 typed client：`ui/api_clients/leave_substitution_api_client.py`
- 現況 drift service：`subsystems/scheduling/staff_leave_review_service.py`
