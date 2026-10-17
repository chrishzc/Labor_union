# Module: order-terms

## Parent
- domain: `orders`
- subsystem: `orders`

## Responsibility
編排 Orders Terms 的 Query／zero-write Preview／fresh-lock Apply。Preview 衍生 `requires_formal_apply`：不形成 Scheduling、confirmed dates、Finance、Payroll 或 lifecycle 正式影響的普通保存只更新 Orders aggregate，不建立 command claim、事件或永久 receipt；有正式影響時才以單一 outer Unit of Work 套用跨 owner 影響並產生可追溯 receipt。Terms caller 另比對 current effective assignments 與 candidate 的 identity／人員／日期／區間形狀；形狀未變時不呼叫 Scheduling replacement writer，沿用 current generation 與真實 assignment identity，Terms receipt 的 Scheduling receipt linkage 為 nullable。尚未建立 assignment 時，起始日平移不虛構排班 segment，並以相同天數平移預計結束日；已有 current confirmed service dates 時保留日期間隔、建立新的 immutable current version 取代舊版。

尚未建立 assignment 且沒有既有下游義務時，與付款計算無關的修改只讀 Orders／Scheduling 與下游完整性的最小存在 facts；Finance／Payroll version 與 impact 明確為 nullable。預計開始日、服務天數、每日時數或樓層費異動且已有 Finance root 時，額外讀取 Finance 付款計算 facts，由 owner 重算階段並在日期有變化時同步條款與 immutable event，不建立簽約前義務或新增 Payroll 依賴。已有 assignment 時仍使用完整下游 facts 與版本控制。

客戶名冊使用獨立的 typed `OrderTermsRegistryFacts` 唯讀 projection，只讀 Orders 條件與 Scheduling／Finance／Payroll 版本；不以 Preview 的逐日排班或義務完整性限制查閱。缺少必要 Orders 欄位仍回 not-ready，服務資料鎖只限制編輯；Preview／Apply 的完整性與版本檢查保持原規則。

Terms GET 使用獨立的 typed `OrderTermsQueryFacts`，沿用 registry 的條款／版本讀取並帶回目前指派及確認服務日期；已有客戶應付義務但尚無執行指派時仍可查閱，不執行 Preview／Apply 的下游義務檢查。

已有客戶期款但未建立執行指派的既有案件，付款相關條件異動亦讀取 Finance facts、重算已存在期款及補正條款日期；以 current confirmed／此次替代日期計算，未建立期款保持未建立。缺漏 roots、Payroll 義務與 nonstage 限制仍拒絕；同一 Terms Apply 保存版本、事件與 receipt。

Case Import 唯一來源的 unknown→known 下廚需求補正使用 `OrderCookingRequirementCorrectionRequest` 與最小 Orders cooking facts；沿用 caller-owned UoW，fresh lock／版本檢查後只更新 `requires_cooking` 與 Orders version，不要求逐日排班或讀寫既有帳務。服務資料鎖與既有已知料理條款仍阻擋此受限 command；已知條款的異動沿用一般 Terms Preview／Apply。

Issue #326：同一 Terms command 可承接完整替代日期與明確既有指派分配；原有跨 owner transaction 與 immutable versions 保持不變。

既有歷史案件缺少約定服務開始日／服務天數，且尚未建立 Client Finance、Payroll 或服務資料鎖定時，沿用同一 owner-local Query／Preview／Apply 補齊契約條件；保留歷史 lifecycle、實際開工日與既有歷史排班證據。

待補件／洽談中的受限 intake terms bootstrap 可選擇補齊完整 service-time tuple 與每日時數，仍以 current Orders version、原 Preview／Apply 與 receipt 保存；不擴張歷史案件資格，不建立下游 roots。進件完成 Preview 另回 typed current service time，供 UI 預填與成功回讀比對，姓名／日期／天數的 completion 判定保持原語意。

進件完成 Apply，及洽談中補齊最後一項完整服務條件的 intake Apply，在既有 Orders outer UoW 透過 typed initializer 委派 canonical Case Architecture Bootstrap。待補件的分段保存與歷史修補不初始化；重播原 receipt 不追加初始化。既有 roots 不覆寫，partial roots 拒絕並 rollback，初始付款條款／薪資政策與 Orders receipt 同交易保存，不建立應收應付或正式排班。

## Implementation
- primary:
  - `domains/orders/terms.py`
  - `subsystems/orders/terms_workflow.py`
  - `subsystems/orders/order_intake_terms_bootstrap.py`
  - `subsystems/orders/order_intake_client_name_repair.py` — 既有 intake 姓名缺件 Preview／Apply，沿用版本、備註、冪等及 receipt。
  - `infrastructure/mysql/order_terms_read_model.py`
  - `infrastructure/mysql/order_terms_repository.py`
  - `infrastructure/mysql/order_lifecycle_impact_writer.py` — 將 typed lifecycle impact 寫入 Orders projection、事件、資料鎖與 outbox；沿用外層 transaction。
  - `infrastructure/mysql/order_intake_terms_bootstrap_repository.py`
  - `infrastructure/mysql/order_intake_architecture_initializer.py`
  - `api/dependencies/order_intake_terms_bootstrap.py`
  - `api/schemas/order_terms.py`
  - `api/dependencies/order_terms.py`
- entrypoints:
  - `api/routes/order_terms.py` — Orders Terms Query／Preview／Apply HTTP transport；普通保存允許省略 reason／Idempotency-Key，正式分支仍要求兩者。
  - `ui_react/src/api/orders/order_terms_mutation_client.ts` — strict typed client、conditional command header 與 nullable service-time tuple decoder。
  - `ui_react/src/components/OrderTermsMutationPanel.tsx` — Terms Preview／Apply 操作面板；普通保存不等待永久 receipt，結果不明時改讀回而不盲目重送；未修改的全空服務時段可原樣保存。
  - `api/routes/order_intake_terms_bootstrap.py` — 早期進件及受限歷史案件的服務條件修正，以及進件完成的 Preview／Apply HTTP transport。

## Dependencies
- outbound: `scheduling/schedule-generation` — 由 Scheduling typed candidate 判定排班 generation 影響；Orders 不自行寫入 assignment。
- outbound: `scheduling/matching-coordination` — 正式日期 replacement 使既有 matching schedule snapshot 失效；候選與方案 owner facts 不由 Orders 改寫。
- outbound: `client-finance/client-finance` — 條款變更的客戶應收影響。
- outbound: `staff-payables/payroll` — 條款變更的薪資影響。
- outbound: `case-import/case-architecture-bootstrap` — 完成進件後沿用 canonical 政策與 writer，同一 caller-owned transaction 初始化缺少的 owner roots。

## Contracts
- `document/架構重整/01_規格基線/01_Orders_Domain.md` — Orders Terms 與 Query／Preview／Apply 語意。
- `document/架構重整/01_規格基線/02_Assignments_Scheduling_Domain.md` — Scheduling generation ownership。

## Verification
- layout_status: `custom_current`
- test_root: `tests/test_order_terms_preassignment_correction.py`
- test_root: `tests/domains/orders/subsystems/orders/modules/order-terms/`
- test_root: `ui_react/src/tests/domains/orders/subsystems/orders/modules/order-terms/`
- test_root: `ui_react/src/tests/order_terms_mutation_client.test.ts` — 既有 Terms typed-client 契約測試，沿用現行位置。
- test_root: `tests/domains/orders/subsystems/orders/modules/intake-terms-bootstrap/unit/`
- test_root: `tests/domains/orders/subsystems/orders/modules/intake-terms-bootstrap/integration/`

## Provenance
- Workflow owner and cross-owner transaction boundary — `architecture_declared` — Orders formal spec and current source.
- Preassignment impact-aware read set and nullable downstream version／impact contract — `architecture_declared` — Orders formal spec, Terms workflow, HTTP schema and MySQL adapter.
- Ordinary Terms direct-save／formal-impact split and conditional permanent receipt contract — `architecture_declared` — Orders formal spec, Terms workflow, HTTP／UI adapters and focused regression.
- Terms scheduling-shape comparison、existing assignment identity reuse and nullable Scheduling receipt linkage — `architecture_declared` — Orders／Scheduling formal specs, Terms workflow, migration contract and focused regression.
- Preassignment start-date、confirmed-service-date replacement projection and focused regression — `source_observed` — current workflow, MySQL adapter and test listed above.
- Nullable service-time HTTP／UI preservation and disposable-MySQL round trip — `source_observed` — canonical module and subsystem integration roots listed above.
- Intake terms bootstrap and intake completion owner-local unit regression — `source_observed` — current bootstrap workflow and canonical unit root.

- Intake 姓名／服務條件補件與完成使用選填備註；原版本、Preview、冪等、receipt 與初始化交易不變。自動初始化記錄系統觸發說明，Orders 命令保存原人工備註；正式 Terms 原因要求不變。

## Change triggers
Reconcile when Orders Terms public contract, cross-owner impact, transaction boundary, preassignment generation semantics, receipt, or focused test root changes.
