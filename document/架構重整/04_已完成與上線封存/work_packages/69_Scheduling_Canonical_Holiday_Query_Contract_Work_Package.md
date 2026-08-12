---
doc_type: work-package
declared_status: completed
date: 2026-08-12
owner: Assignments / Scheduling Domain
scope: Canonical Holiday Query contract consumed by Scheduling Preview and Apply
write_set: [document/架構重整/01_規格基線/02_Assignments_Scheduling_Domain.md, subsystems/scheduling, api/schemas]
acceptance: Preview and Apply use one versioned, fail-closed Holiday Query contract without UI-owned holiday calculation.
out_of_scope: Holiday source administration, holiday data migration, and leave/substitution UI rendering.
---

# 69 Scheduling Canonical Holiday Query Contract Work Package

## 文件狀態

- 狀態：`blocked`
- 實作狀態：`in-progress`
- 優先級：`P0 dependency of WP67`
- Owner：`Assignments／Scheduling Domain`
- 依賴者：[WP67 Scheduling Leave/Substitution Calendar Precision Completion](67_Scheduling_Leave_Substitution_Calendar_Precision_Completion_Work_Package.md)
- 實作授權：`contract-definition-authorized-by-2026-08-12-user-direction`；production code、schema 與資料 migration 必須在本契約確認後另行授權。

### 2026-08-12 封存阻塞

`SchedulingHolidayQuery` 已接入 Preview／Apply 與 fingerprint，但其 Apply fresh-read／lock 的
disposable-MySQL E2E 無法在未配置 `LABOR_UNION_TEST_MYSQL_*` 的情況下執行。不得以 unit
test 或本機 production-like 資料取代 disposable database evidence；設定完整測試環境並通過
WP67 的 Apply E2E 後才可解除阻塞與進入 archive gate。

## Business scenario

管理人員對正式服務指派建立請假、順延或代班 Preview 時，系統必須使用與 Apply 相同的權威假日事實，判定每個日期是否為國定假日及其名稱。假日資料不可用或無法驗證時，Preview 必須 fail closed；不得由 Streamlit 以一般列表 API 自行推算。

## Contract decision

1. `SchedulingHolidayQuery` 是 Scheduling Domain 的唯讀 port；Holiday source 的資料維護 owner 不因本契約轉移。
2. Preview 與 Apply 都必須透過同一 port 讀取相同服務期間的 holiday facts；Apply 必須 fresh-read，不得信任 Preview session state。
3. Query 結果至少包含：`holiday_date`、`holiday_name`、`holiday_version`、`source_identity`。
4. Holiday facts 必須納入 leave/substitution Preview fingerprint；事實改變後既有 Preview 必須 stale。
5. 無法讀取、資料形狀不完整、版本不可判定或資料來源無法證明時，回傳 typed `holiday_calendar_unavailable`；不得以空清單表示成功。
6. 2026-08-12 人工裁決：國定假日預設為休假、扣除服務日並順延；Scheduling leave/substitution 規則使用 Query facts 執行此政策。

## Typed boundary

```text
SchedulingHolidayQuery.query(service_start_date, service_end_date) ->
  HolidayCalendarFacts(
    source_identity,
    holiday_version,
    holidays: [HolidayFact(holiday_date, holiday_name)]
  )

SchedulingHolidayQueryError -> holiday_calendar_unavailable
```

## Acceptance

- Preview 可從同一 query 取得服務期間內的假日清單，並把 facts 放入 typed calendar candidate 與 fingerprint。
- Apply fresh-read 同一範圍的 facts；若 version 或事實改變，回 typed stale/conflict 且零寫入。
- Query error 不被轉成空假日清單，Preview 與 Apply 都 fail closed。
- UI 僅 render API 回傳的 holiday rows，不計算假日、版本或 service-day policy。
- [WP67](67_Scheduling_Leave_Substitution_Calendar_Precision_Completion_Work_Package.md) 可移除 holiday dependency blocker 後，才可完成其完整天數對帳驗收。

## Out of scope

- 建立或維護 `holidays` 資料表、外部假日資料同步、歷史資料修補。
- 假日管理 UI 與資料輸入流程。
- 固定排休、請假、順延、代班本身的 Domain 規則；它們由 WP67 承接。

## Required decisions before implementation

1. 現有 Holiday API／repository 是否可被證明為此 port 的 source identity，並提供穩定 `holiday_version`。
2. 假日 source 更新的版本遞增、快取失效與 Apply fresh-read 邊界。
3. 已裁決：國定假日預設休假、扣除服務日並順延。

## 2026-08-12 實作與驗收狀態

- status: in-progress
- Canonical Holiday Query 已接入 Leave/Substitution Preview 與 Apply，holiday version 已納入 preview fingerprint，Apply 會以鎖定讀重新取得 holiday facts。
- 本次受控寫入驗收確認請假／順延流程可完成 Preview、Apply、idempotency replay 與正式 Calendar data-source 回讀；沒有把 Holiday Query 以 UI 或 SQL 旁路實作。
- 未完成驗收：目前測試案件的 holiday rows 為空，尚需一筆含國定假日的可寫入案例，驗證「國定假日預設休假、扣除服務日並順延」的實際 Apply 與 UI 呈現後才能封存。
## 2026-08-12 Holiday-only Apply 實證

- 透過 `/api/v1/holidays/preview`、`/apply` 建立測試國定假日 `2026-08-14`，再以案件 `115000051`、assignment `358`、零手動 leave items 進行 Preview。
- Preview：8/14 成為 holiday rest，服務日維持 5，結束日 `2026-08-15 -> 2026-08-16`，Apply readiness 為 ready。
- Apply：正式 application layer receipt 為 order `4 -> 5`、scheduling `2 -> 3`、client finance `5 -> 6`、payroll `2 -> 3`；`outcome_event_ids=[]` 是 Holiday-only batch 的正確結果。
- Replay：同 actor、同 idempotency key 重播回傳同一 receipt；跨 actor 的同 key HTTP 呼叫正確回傳 idempotency mismatch，沒有重複寫入。
- Calendar data source：replacement assignment `364` 正式服務日為 `8/10、8/11、8/12、8/15、8/16`，不含 8/14，符合「國定假日預設休假、扣除服務日並順延」。
- live-drift 修復：新增 receipt version constraint migration、Holiday-only batch constraint migration，並略過零額 Payroll obligation event；以上皆有 targeted tests。
- archive gate：尚未通過，原因是與 WP67 共用的最後人工 UI click-flow 未完成。

## 2026-08-12 封存 gate 完成紀錄

- 最終狀態：`completed`；Holiday Query 已由 Preview 與 Apply 共用，Apply 鎖定 Holiday 根事實，fingerprint 納入 Holiday 版本。
- 業務驗收：國定假日預設為休假，扣除服務日並順延；測試資料庫 2026-08-14 Holiday-only Apply 成功，服務日由 8/10、8/11、8/12、8/14、8/15 調整為 8/10、8/11、8/12、8/15、8/16。
- UI 驗收：Chrome 行事曆確認 8/14 顯示 Holiday 與可接案，不顯示服務工作日；同月其他有效服務日維持正確。
- 回歸：受影響 focused suite 共 `23 passed`。
- current successor：`document/架構重整/01_規格基線/02_Assignments_Scheduling_Domain.md`；本 Work Package 不再作為 current 行為授權。
- release identity：本次為使用者授權的本機測試資料庫受控驗收，無 production deployment release。
- restore triggers：Holiday-only Apply、Holiday version replay、或國定假日服務日精算回歸。