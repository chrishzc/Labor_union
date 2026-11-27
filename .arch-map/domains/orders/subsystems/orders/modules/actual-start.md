# Module: actual-start

## Parent
- domain: `orders`
- subsystem: `orders`

## Responsibility
擁有 Actual Start Query／Preview／Apply。尚無有效正式 assignment（含歷史重啟空 tombstone）時，只以 Orders owner version 保存或修正日期，不建立 Scheduling、Finance、Payroll、lifecycle event 或永久 receipt；歷史案件後續由明確正式安排操作建立 assignment。已有正式 assignment 時，依每個 segment 原有服務日數、當前排休及假日逐段精算，保留人員／順序／lineage，重建有效 Scheduling generation、actual end 與 lifecycle。Actual Start 不重算或寫入 Client Finance／Payroll 金額與 root；僅唯讀既有訂金核銷狀態作一般案件 lifecycle gate，並由 Payroll adapter 同交易搬移各 source assignment immutable 費率快照至新 identity。
已有正式排班的更正亦須按月嫂逐段套用仍有效的已核准請假／代班，無法保留核准 outcome 時零寫入；合法 replacement 在同一交易續接 effective leave occupancy，不改 immutable outcome。

## Implementation
- primary:
  - `domains/orders/actual_start.py`
  - `domains/orders/terms.py`
  - `subsystems/orders/actual_start_workflow.py`
  - `infrastructure/mysql/order_actual_start_repository.py`
  - `infrastructure/mysql/historical_actual_start_date_planner.py`
  - `api/dependencies/order_actual_start.py`
  - `api/routes/order_actual_start.py`
  - `api/schemas/order_actual_start.py`
  - `ui_react/src/api/orders/order_actual_start_client.ts`
  - `ui_react/src/components/OrderActualStartPanel.tsx`
  - `ui_react/src/adapters/orders/order_mutation_flow_store.ts` — per-case original command／receipt recovery。
  - `ui_react/src/components/OrderWorkbenchV2Drawer.tsx`

## Dependencies
- outbound: `scheduling/scheduling` — replacement generation 擁有正式服務日期、assignment lineage 及已核准請假／代班的 active occupancy；Actual Start 只協調同交易重排。
- outbound: `client-finance/client-finance` — 唯讀既有訂金核銷與仍有效的未付人工放行作一般案件 lifecycle gate；不重算 projection，也不把放行視為核銷。
- inbound: `orders/historical-adoption` — 已付訂金且來源開始日異於 HCM 預定開始日的 historical actual-start assertion 經 typed delegation 進入。
- inbound: `orders/historical-precision-restart` — 重啟後空 tombstone 的 HTTP Actual Start 為日期-only；歷史採納內部仍可使用 immutable source delegation，不代表一般入口自動建立 Scheduling。
- outbound: `staff-payables/payroll` — source rate snapshot 唯讀驗證與 successor identity 原值搬移，不寫 Payroll root／obligation。

管理 UI 對已有正式 assignment 的重排先顯示逐段 Preview 及將保存的實際開始日，內部操作者最後確認才呼叫單一原子 Apply。此畫面不編輯請假、假日或正式服務日。重排保留試算輸入與候選首日供確認及讀回，沿用 Orders／Scheduling owner versions、fingerprint 與 idempotency 契約。
一般日期-only 分支綁 Orders version 與該次 Preview fingerprint；取消合併／分裂結果的日期-only 預覽另納入目前確認日期版本、Scheduling version 與正常日期候選。若 Apply fresh-read 發現正式 assignment 已形成，回 typed conflict 並要求重新 Preview。一般 Terms reader 不得只因日期存在便投影 `service_started`。

## Contracts
- 變更開始日涉及既有日期合併／分裂結果時，Preview 提供 typed 取消重排候選，明確確認的單一 Apply 依調整前正常服務量與人員歸屬重建日期並恢復原訂時段。事前日期不建立正式指派；正式重排保留來源 identity 與計薪快照。取消結果、正常確認日期及正式班表沿同一 outer UoW 保存，讀回不得繼續呈現舊日期、時數覆寫或舊結果的有效配對。規則見 `02_Assignments_Scheduling_Domain.md#service-date-merge-split`。
- `.arch-map/requirements/01_Orders_Domain.md` — Actual Start、歷史來源與 completion instant 語意。
- `subsystems/orders/actual_start_workflow.py` — Preview／Apply 與單一 outer UoW contract。

## Verification
- layout_status: custom_current
- test_root: `ui_react/src/tests/domains/orders/subsystems/orders/modules/actual-start/`
- higher_boundary: `tests/domains/orders/subsystems/orders/integration/test_order_actual_start_workflow.py`
- test_root: `ui_react/src/tests/order_workbench_v2_actual_start.test.tsx` — existing drawer mutation／recovery integration。 既有模擬案例核對正式讀回尚未符合回執時不顯示完成、不重送套用，直到讀回一致才顯示完成。

## Provenance
- 逐日時數承接與零日來源保留 — `source_observed` — `domains/orders/actual_start.py`、`subsystems/orders/actual_start_workflow.py`、`infrastructure/mysql/scheduling_replacement_writer.py`；驗證由既有 `test_order_actual_start_workflow.py` 涵蓋。
- Actual Start writer and cross-owner persistence — `source_observed` — `subsystems/orders/actual_start_workflow.py`.
- Order Workbench V2 drawer eligibility gate — `source_observed` — `ui_react/src/components/OrderWorkbenchV2Drawer.tsx`。
- Historical tombstone date-only 與逐段精算／快照搬移 — `architecture_declared` — `.arch-map/requirements/01_Orders_Domain.md` §3.4。

## Change triggers
Reconcile when Actual Start official-date calculation, cross-owner projection, lifecycle completion instant, or historical delegation changes.
