# Module: waiting-deposit-lock

## Parent
- domain: `scheduling`
- subsystem: `scheduling`

## Responsibility
擁有 waiting-deposit 檔期鎖的取得、釋放與訂單取消時的原子收斂；只解除 Scheduling-owned 占用，不自行推進 Orders lifecycle。

## Implementation
- primary:
  - `domains/scheduling/waiting_deposit_lock.py`
  - `subsystems/scheduling/availability_lock_acquisition_workflow.py`
  - `subsystems/scheduling/availability_lock_helpers.py`
  - `subsystems/scheduling/availability_lock_release_workflow.py`
  - `subsystems/scheduling/availability_lock_cancellation_workflow.py`
- entrypoints:
  - `api/routes/caregiver_availability_locks.py`
  - `api/schemas/waiting_deposit_lock.py`
- presentation: 推薦頁換人沿用 release Preview／Apply；網址中的正整數 plan／lock id 可正常解析，JSON 命令仍維持 strict。缺 settlement projection 時，Client Finance 在同一 UoW 查核完整正式帳務歷史，明確確認未收款才可釋放；不建立財務根事實。Finance 來源版本受既有 Preview fingerprint 保護，成功確認寫入原 release 事件；有帳務歷史卻缺結算回 `deposit_receipt_unconfirmed`。

## Dependencies

- 配對回覆與 Orders confirmed dates 保存借用 `lock_current_matching_staff`／`reserve_confirmed_matching_plan`，在原 outer UoW 自動取得鎖；以 plan／日期版本固定事件識別，fresh-read、mutex、占用及不可服務檢查由既有 Scheduling owner 執行，無 hidden commit。正常 UI 只呈現自動保留狀態，不要求手動 acquire；既有 acquire／release API 保留。
- 單一月嫂的等待訂金候選期間與 occupancy 由 current confirmed dates 投影，容許實際開始日變更後超出原推薦預計期間；不改寫原媒合方案，仍保留實際占用檢查與 fresh-lock Preview／Apply。
- outbound: `orders/orders` — 訂單取消由 Orders outer Unit of Work 傳入已鎖定 lifecycle command envelope。
- outbound: `client-finance/receipt-reconciliation` — 同一借用交易中的 `UnreceivedDepositConfirmation`；Finance 先鎖 account 再查同案根事實，Scheduling 不將缺列轉成零金額。
- outbound: `orders/historical-precision-restart` — precision restart 後，沒有 generation ownership 的舊歷史 assignment 不再構成 waiting-lock occupancy。
- inbound: `scheduling/matching-coordination` — 工會確認的 matching plan 與 current confirmed service dates 提供檔期鎖候選事實；月嫂意願是推薦輸入，不以簽約或 precontract commitment 作為鎖定前置條件。

## Contracts
- Waiting-deposit lock ownership and cancellation — `document/架構重整/01_規格基線/02_Assignments_Scheduling_Domain.md`.
- Cancellation must remove future Scheduling occupancy — `document/架構重整/01_規格基線/01_Orders_Domain.md` §3.5.

## Verification
- test_root: `tests/domains/scheduling/subsystems/scheduling/modules/waiting-deposit-lock/`.
- higher_boundary: 跨 Orders、Scheduling、Client Finance、Payroll 的 disposable-MySQL 取消交易依 Global Test Map 的 higher-boundary exception 路由。
- routing: `.arch-map/tests/index.md` and `.arch-map/tests/domains/scheduling/subsystems/scheduling/index.md`.

## Provenance
- Scheduling ownership and Orders cancellation dependency — `architecture_declared` — current Orders/Scheduling specs.
- Workflow and route paths — `source_observed` — current repository source.
- Restarted generation-less historical assignment exclusion — `source_observed` — current availability-lock acquisition occupancy query.
- Cross-owner disposable MySQL verification — `source_observed` — current Global Test Map higher-boundary exception.

## Change triggers
Reconcile when lock lifecycle、matching-plan eligibility、Orders restart／cancellation integration、assignment generation ownership、occupancy mutex、entrypoint or verification routing changes.
