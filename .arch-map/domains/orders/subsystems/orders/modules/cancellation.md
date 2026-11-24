# Module: cancellation

## Parent
- domain: `orders`
- subsystem: `orders`

## Responsibility
組成訂單取消的 Query／Preview／Apply，驗證 fresh Orders、Scheduling、Client Finance 與 Payroll 根事實，並以單一交易產生取消 receipt／outbox。
合法不存在的下游 owner 以 NULL 表達；專用 reader 驗證 partial roots／孤立財務歷史。零服務案件若收取違約金且正式條件齊備，同一交易初始化必要的 Client Finance 主檔與款項。日期-only 開始日不代表已服務。
Query 依注入的台北業務日期排除未來排班，人員核對當日是否服務；未鎖定服務資料可確認為零日。取消及退款／補收全額核銷更新人工 LINE 通知資格，由人員預覽後發送。既有 terminal menu handoff 保留。

<a id="cancellation-unserved-design"></a>

## 零服務取消的實作邊界 ^cancellation-unserved-design

- `domains/orders/lifecycle.py` 的 `OrderEstablishmentEvidence` 與 `zero_service_terminal_status` 產生 typed lifecycle 結果：有正式成立證據的零服務終止為「成立後未服務」，成立前為「訂單取消」。MySQL 狀態契約由 `1081_order_established_unserved_status.sql` 承接。
- 業務裁決見 [Orders 零服務終止](../../../../../requirements/01_Orders_Domain.md#order-zero-service-termination)，金額只使用 [Client Finance 結算](../../../../../requirements/04_Client_Finance_Domain.md#client-cancellation-settlement)。Domain 根據正式成立證據與確認服務量產生 typed 結果，workflow 不從目前狀態字串猜測曾成立。
- 沿用下列取消 UI／API、workflow 與 repositories；由同一 Apply 保存領域結果、帳務影響、版本、receipt 與 outbox。一般取消已確認實際服務不為零時，workflow 回傳 `order_cancellation_has_actual_service`，面板提供既有 Terms 修改入口；歷史既有取消的受限補正仍依原資格處理。
- 零服務時 Payroll／Scheduling 使用明確零量，不回退登記天數或預排日；成立後未服務的退款含全部有效客戶入款，由 Finance 原 ports 處理，UI 不計費。歷史取消分類修正另沿 [historical-adoption](historical-adoption.md#historical-unserved-design)，不重做效果未明的取消結算。
- `CancellationWorkflowRepository` 是應用層 typed port；MySQL read model 提供成立證據及各 owner facts，repository 在原 outer UoW 保存狀態與事件。`automatic_client_accounting.py` 與 Payroll rebuild 入口保留零服務終止 guard，避免後續同步重新依登記服務量建立義務。
- 驗收對應：`ORDER-UNSERVED-01/02`、`ORDER-EARLY-END-02`、`CF-UNSERVED-01/02/03`，沿下列 owner roots 核對回讀、重播與負向案例；DB 升級及真實 MySQL 驗證結果另依實際執行證據判定。

```yaml archmap-impact
- kind: implements_requirement
  source: cancellation-unserved-design
  target: '.arch-map/requirements/01_Orders_Domain.md#^order-zero-service-termination'
```

## Implementation
- primary:
  - `domains/orders/cancellation.py`
  - `domains/orders/lifecycle.py` — 成立證據與零服務終止狀態裁決。
  - `subsystems/orders/cancellation_workflow.py`
  - `infrastructure/mysql/order_establishment_read_model.py` — 正式成立 lifecycle／採納證據的共用唯讀 SQL。
  - `infrastructure/mysql/order_cancellation_read_model.py`
  - `infrastructure/mysql/order_cancellation_repository.py`
  - `api/schemas/order_cancellation.py`
  - `api/dependencies/order_cancellation.py`
  - `db/schema_parts/1081_order_established_unserved_status.sql` — 狀態 ENUM／CHECK successor，資料保留及啟用沿 migration owner。
- entrypoints:
  - `api/routes/order_cancellation.py`
  - `ui_react/src/api/orders/order_cancellation_client.ts`
  - `ui_react/src/components/OrderCancellationPanel.tsx`
  - `ui_react/src/components/OrderWorkbenchV2Drawer.tsx`

## Dependencies
- outbound: `scheduling/scheduling` — 取消有效 generation 與 assignment 重建。
- outbound: `client-finance/client-finance` — 取消退款／義務 impact。
- outbound: `payroll/payroll` — 服務人員薪資 impact。
- outbound: `government-subsidy/government-subsidy` — 取消的 Finance 委派不做中途補助同步；Orders 保存終止狀態後，才在原 outer UoW 委派 `government_period_difference_repository.synchronize_government_case_amount`。成立後未服務使用正式零量，缺少結束日期仍可更正既有凍結金額；保留人工核定金額及整期銀行快照，只追加原 owner 差額，不列入政府核銷報表。補助退還沿 `automatic_client_accounting.synchronize_terminal_subsidy_return` 與既有方案 Preview 判定。

## Contracts
- `.arch-map/requirements/01_Orders_Domain.md` — §3.5 cancellation 與 Preview／Apply typed errors。
- `/api/v1/orders/{case_no}/cancellation/{preview,apply}` — `api/routes/order_cancellation.py`。
- 正式取消視窗先讀全案結算預覽，再由人員確認 Apply。Client Finance 在既有交易關卡建立一般退款或調整款，案件帳務以正式結算識別回讀，銀行核銷沿各原 owner。
- 取消完成及重新讀取已取消案件時提供原案資料帶入非市民新案的導覽入口；只導向 Case Import 手動建案，不自動建案或更動綁定，沿用既有 busy 與未儲存離頁保護。

## Verification
- layout_status: custom_current
- test_root: `tests/domains/orders/subsystems/orders/modules/cancellation/`
- static:
  - `.venv/bin/python -m pytest tests/domains/orders/subsystems/orders/modules/cancellation/ tests/domains/orders/subsystems/orders/integration/test_cancelled_order_reentry_guard.py tests/domains/orders/subsystems/orders/integration/test_order_cancellation_cross_domain_chain.py`
- disposable_mysql: `tests/test_historical_mid_service_cancellation_disposable_mysql_e2e.py`
- disposable_mysql: `tests/domains/orders/subsystems/orders/integration/test_order_cancellation_absent_roots_disposable_mysql.py`
- owner_guard: [Client Finance obligation-planning 的同步守衛](../../../../../../tests/domains/client-finance/subsystems/client-finance/integration/test_automatic_accounting.py) — 引用該 owner 的取消後自動帳務驗證。
- owner_guard: [Payroll payroll-rebuild 的重算守衛](../../../../../../tests/domains/payroll/subsystems/payroll/integration/test_payroll_rebuild_workflow.py) — 引用該 owner 的取消後薪資重算驗證。
- higher_boundary: tests/domains/orders/subsystems/orders/integration/
- higher_boundary:
  - `ui_react/src/tests/orders_page_real_data.test.tsx`
- test_root: `ui_react/src/tests/order_workbench_v2_cancellation.test.tsx`
- test_root: `ui_react/src/tests/order_workbench_v2_reopen.test.tsx`
- test_root: `ui_react/src/tests/order_cancellation_client.test.ts` — 既有 schema 案例區分合法的 `null` 與漏欄，必要欄位不能省略。

## Provenance
- Cancellation workflow ownership — `architecture_declared` — Orders §3.5 and existing Orders subsystem map.
- Already-effective cancellation must be rejected before candidate rebuild, except a historical cancellation-origin row with confirmed service-day facts entering its one-time canonical remediation path — `source_observed` — `subsystems/orders/cancellation_workflow.py` and Orders historical-remediation tests.

## Change triggers
- 取消 eligibility／typed error、cross-domain impact、transaction owner、API entrypoint 或 UI cancellation gating 改變時重新 reconcile。
