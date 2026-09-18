---
doc_type: work-package
declared_status: completed
priority: P0
owner: Orders / Scheduling / Client Finance
domain: cross-domain order operations
subsystem: fact-driven order workbench
initiative: fact-driven-order-workbench
updated_date: 2026-09-18
completed_date: 2026-09-18
implementation_authorization: granted-by-user-2026-09-18
---

# 事實驅動代辦看板重整工作包

## 1. Objective

代辦看板不再以十三階段序號創造線性前置；正式 lifecycle state machine 與各 owner command 的必要條件仍保留。看板只依 current owner facts 投影「可辦理、待補事實、已完成、不適用、真正阻擋」，不得把顯示順序當成業務規則。

## 2. Current Authority and requirements

- `R-BOARD-01`：取消十三階段的線性操作前置，但不取消 Orders、Scheduling、Client Finance 等正式狀態機與 command guards。
- `R-TERMS-01`：未有正式排班與 confirmed dates 時，進件條款可先修改服務天數與開始日。
- `R-VA-01`：存在匯入虛擬帳號對照時，匯入事實優先；只有無匯入對照才使用公式。
- `R-HIST-01`：歷史訂單唯一月嫂在重啟精算後仍是既定服務人員，不重新走候選、詢問或推薦。
- Authority：2026-09-18 使用者明確裁決並授權開始修正；正式語意同步維護於 `01_Orders_Domain.md`、`04_Client_Finance_Domain.md`、`27_歷史訂單生命週期與服務天數帳務正式規格.md`。

## 3. Bounded implementation

1. 修正 Orders Terms 的 pre-assignment generation，使服務天數變更建立空的新 generation，而非要求既有 segments。
2. 修正 Client Finance virtual-account resolution 與案件帳號 projection 的來源優先序。
3. 保留並投影 historical pairing binding；重啟後日期確認沿既有 evidence 建立正式 Scheduling assignment，工作台不再要求候選月嫂。
4. 將工作台主要導覽改為 fact-driven group status；十三階段若保留，只作唯讀歷史／技術進度，不作 enabled gate 或唯一「目前待辦」。
5. 同步直接受影響的正式規格、`.arch-map` facts 與 owner-local regression。

## 4. Acceptance

- `A-TERMS-01`：無 segments、無 confirmed dates、未開始服務的案件可 Preview／Apply 新 `service_days`，結果沒有虛構 assignment，且回讀 Orders/Scheduling versions 一致。
- `A-TERMS-02`：已有 confirmed dates 或正式 assignment 時，服務量變更仍須走 replacement／reallocation，錯誤必須指向真正缺少的資料。
- `A-VA-01`：一個帳號同時命中唯一匯入案件與另一個公式案件時，解析為匯入案件。
- `A-VA-02`：同一匯入帳號映射多個案件時保持 pending；沒有匯入映射時才使用公式。
- `A-HIST-01`：歷史重啟後可回讀唯一既定月嫂；候選、詢問、推薦不成為待辦，服務日期確認可直接辦理。
- `A-HIST-02`：日期確認後建立的 current Scheduling assignment 使用同一歷史月嫂，並保留來源 lineage。
- `A-BOARD-01`：使用者可開啟各工作群組；每群組顯示自身 owner facts 的狀態，不再顯示單一線性「目前待辦」作為操作權威。
- `A-BOARD-02`：真正缺少必要事實時仍 fail closed，並顯示缺少的事實，而不是前一階段尚未完成。

## 5. Effect ceiling and exclusions

- 允許：正式規格、現有 Domain／Subsystem／adapter／React、owner-local tests 與 `.arch-map` 的必要同步。
- 不包含：production DB、migration、deployment、外部銀行操作、Git stage／commit／push、全 repository cleanup。
- 不新增第二套 lifecycle、generic workflow engine、平行待辦 API 或 compatibility fallback。

## 6. Verification and stop

- Module：Orders Terms、virtual-account resolution、historical restart/service-date regression。
- Subsystem：operational/core-stage projection 與 Order Workbench React integration。
- Domain：只在跨 owner interaction signal 需要時執行既有 focused integration；不預設 full suite。
- Static：`git diff --check`、受影響正式規格與 `.arch-map` closure。
- 上述 acceptance 全部 `passed` 即停止；環境缺失則精確標示 `blocked`／`not_run`，不得以文件或程式存在冒充完成。

完成證據（2026-09-18）：owner-focused Python tests `172 passed`；Order Workbench／服務日期 Vitest `33 passed`；React production build passed；architecture closure passed；`git diff --check` passed。另有既存 Orders mutation adapter 測試 3 項因舊 fixture 的案件／日期回讀與收據不一致而失敗，與本工作包新增的 `bound_staff` 契約無關，未以該結果取代上述驗收。

## 7. Coverage

| Requirement | Canonical owner | Implementation slice | Oracle |
|---|---|---|---|
| R-TERMS-01 | Orders + Scheduling generation | pre-assignment terms candidate | A-TERMS-01／02 |
| R-VA-01 | Client Finance | virtual-account resolution/projection | A-VA-01／02 |
| R-HIST-01 | Orders adoption + Scheduling | restart readback, stage projection, service dates | A-HIST-01／02 |
| R-BOARD-01 | Orders operational projection | core-stage/group projection + React | A-BOARD-01／02 |
