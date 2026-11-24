# Module: lifecycle-authoritative-facts

## Parent
- domain: `orders`
- subsystem: `orders`

## Responsibility
鎖定並組成 Orders lifecycle／自動完成的 authoritative facts，包含有效正式服務日、actual end 與 completion instant；服務時間三欄皆未設定、且實際迄日與最後正式服務日一致時，依 Orders contract 採台北日終；若只缺其中一部分，則阻擋自動完工。

<a id="completion-catchup-design"></a>

## 過期完工補抓與驗證邊界 ^completion-catchup-design

- 對應 [Orders 過期完工補抓](../../../../../requirements/01_Orders_Domain.md#order-completion-catchup)。既有 `order_auto_completion_job_repository` 依有效班表發現所有已到期案件，`auto_completion_job_dispatch` 將 case、版本及完工時刻交 durable queue；背景 handler 再委派唯一 `AutoCompleteOrderService` fresh-read／lock，不直接執行狀態 UPDATE。
- 服務量與有效班表的一致性由 [Scheduling 契約](../../../../../requirements/02_Assignments_Scheduling_Domain.md)決定，Orders 消費 owner facts，不另以日期筆數重定義服務量；最後服務日與 `actual_end_date`、跨日完整時段均須可核對，不能用昨日日期本身推定已完工。日期回填不排除已到期案件，舊版工作的衝突不能阻止新版本再次被發現。
- `infrastructure/mysql/order_auto_completion_job_repository.py` 的到期查詢使用 `completion_instant <= evaluation_at`，`subsystems/orders/auto_completion_job_dispatch.py` 以案件、目前版本及完工時刻組成 durable command identity；`api/dependencies/private_operations.py` 組裝 worker。讀取到期案件不變更狀態，worker 仍經原 application port 保存完工結果。
- 驗收對應 `ORDER-CATCHUP-01/02`。`test_accounting_change_reconciliation_mysql.py` 從 Terms 新班表與版本，經原 durable discovery／handler，再核對正式完工及看板第 11～13 步；同檔保留原收付及失敗回滾案例。這是實際執行的驗證入口，不由來源位置推定已驗收。
- 背景工作停止、版本衝突或 active blocker 不得被表示為已完工；雙邊待收付不因第 11 步完成而自動結清。「成立後未服務」是零服務終止，lifecycle authoritative facts／自動完工 Query 保留此狀態，不將它推進服務完工。
- 其他既有驗證入口：`tests/test_order_auto_completion_job_dispatch.py`、`tests/domains/orders/subsystems/orders/integration/test_order_auto_completion_workflow.py`、`tests/test_order_auto_completion_disposable_mysql_e2e.py`。

```yaml archmap-impact
- kind: implements_requirement
  source: completion-catchup-design
  target: '.arch-map/requirements/01_Orders_Domain.md#^order-completion-catchup'
```

## Implementation
- primary:
  - `subsystems/orders/service_start_lifecycle.py` — 已正式排班案件至約定開工日才轉為服務中；不重排班或寄新通知。
  - `infrastructure/mysql/service_start_lifecycle_repository.py` — 共用 occupancy mutex／fresh owner facts 與 canonical lifecycle writer；AutoComplete 保留唯一完工權。
  - `domains/orders/lifecycle.py`
  - `infrastructure/mysql/order_auto_completion_repository.py` — 完工同交易同步補助應退、月嫂應付及 Orders 唯一付款日；無 LINE 外部效果。
  - `subsystems/orders/lifecycle_authoritative_facts_loader.py`
  - `subsystems/orders/lifecycle_authoritative_facts.py`
  - `subsystems/orders/lifecycle_control_read_facts.py`
  - `subsystems/orders/order_lifecycle_command_envelope.py`
  - `subsystems/orders/auto_completion_workflow.py`
  - `infrastructure/mysql/order_auto_completion_job_repository.py` — 唯讀到期發現，包含回填至過去的有效完工時刻。
  - `subsystems/orders/auto_completion_job_dispatch.py` — 依目前版本及時刻建立 durable command。
  - `api/dependencies/private_operations.py` — 背景 worker composition，委派原完工 service。
  - `api/dependencies/order_auto_completion.py`
  - `api/routes/order_auto_completion.py` — canonical completion commands and readonly automatic-completion status。
  - `api/schemas/order_auto_completion.py`

## Dependencies
- outbound: `scheduling/scheduling` — 有效 generation、正式 assignment 與 official service dates。
- outbound: `client-finance/client-finance` — deposit settlement root fact，以及當前有效的 typed 未付人工放行；後者只解除訂金進度關卡，不改核銷事實。

- outbound: `payroll/payroll-rebuild` — 正式完工後自動同步薪資與付款日。

## Contracts
- `.arch-map/requirements/01_Orders_Domain.md` — lifecycle completion instant semantics。

## Provenance
- Lock-held facts and auto-completion workflow — `source_observed` — `subsystems/orders/lifecycle_authoritative_facts_loader.py`.

## Verification
- higher_boundary: [Orders order-terms 的帳務更正整合測試](../../../../../../tests/domains/orders/subsystems/orders/integration/test_accounting_change_reconciliation_mysql.py) — 引用該 owner 的解鎖 Terms 縮短班表、昨日到期補抓、正式完工與雙邊結算投影。

## Change triggers
Reconcile when lifecycle root facts, completion instant, effective scheduling readback, or auto-completion blocker semantics change.
