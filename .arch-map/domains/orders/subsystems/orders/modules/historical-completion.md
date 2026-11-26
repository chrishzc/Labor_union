# Module: historical-completion

## Parent
- domain: `orders`
- subsystem: `orders`

## Responsibility
依歷史來源服務迄日驅動「歷史訂單－服務中」到「歷史訂單－服務完成」的每日推進，不依賴 Scheduling 可用性。同一 outer UoW 更新完工投影，委派 Payroll 同步歷史月嫂應付，把同步結果與略過原因保存於 lifecycle event、outbox 與工作收據，再由 Client Finance 檢查客戶補助退款。另組合 Orders Step 11 所需的 Orders、Scheduling、Client Finance 與 Staff Payables fresh readback；Query 保持 read-only。當 fresh oracle 證明歷史服務天數完整且雙邊款項均真正結清時，由 bounded Preview／Apply 將 Orders 從「歷史服務完成」推進為「歷史帳務完成」。

## Implementation
- primary:
  - `subsystems/orders/historical_completion_oracle.py`
  - `subsystems/orders/historical_completion_query.py`
  - `subsystems/orders/historical_completion_projector.py`
  - `subsystems/orders/historical_completion_apply.py`
  - `subsystems/orders/auto_completion_job_dispatch.py`
  - `infrastructure/mysql/historical_completion_writer.py`
  - `infrastructure/mysql/order_auto_completion_job_repository.py`
  - `infrastructure/mysql/historical_client_finance_completion_read_adapter.py`
  - `infrastructure/mysql/historical_staff_payables_completion_read_adapter.py` — 從 Staff Payables 取正式結清與來源版本；不由 Orders 或前端重算。
  - `infrastructure/mysql/historical_orders_scheduling_completion_read_adapter.py`
- entrypoints:
  - `api/routes/historical_completion.py`
  - `api/dependencies/historical_completion.py`
  - `api/dependencies/durable_job_handlers.py`
  - `api/schemas/historical_completion.py`
  - `ui_react/src/api/orders/historical_completion_client.ts`
  - `ui_react/src/api/orders/historical_completion_schemas.ts`
  - `ui_react/src/components/HistoricalCompletionPanel.tsx`

## Dependencies
- outbound: `scheduling`、`client-finance`、`staff-payables` — Query 只讀各 owner typed current readback；Apply 鎖定並驗證 exact owner versions/source vector，不改寫這些 owner root。
- Staff Payables completion evidence accepts either canonical bank payout/allocation lineage or exact current historical payout projection/event/link lineage；Apply locks both lineage families before fresh re-read。更正差額及追償讀取見 [Staff Payables historical payment settlement](../../../../staff-payables/subsystems/staff-payables/modules/historical-payment-settlement.md)。
- outbound: Orders canonical lifecycle writer — 追加 lifecycle event/outbox 並以 lifecycle version CAS 更新 Orders projection。
- inbound: `ui_react/src/pages/FinancePage.tsx` — 客戶收款頁選取歷史服務完成案件時，透過 HistoricalCompletionPanel 呈現 owner referral、預覽並確認帳務完成；成功或手動重新整理後重新讀取案件及完成狀態。案件工作台保留完工摘要與同案帳務連結。

<a id="contracts"></a>

## Contracts ^historical-completion-contracts

```yaml archmap-impact
- kind: implements_requirement
  source: historical-completion-contracts
  target: .arch-map/requirements/27_歷史訂單生命週期與服務天數帳務正式規格.md#^historical-accounting-completion
```

### 第 11 步交接

| 負責角色 | 正式約定 | 去哪查 |
| --- | --- | --- |
| Orders／後端 | Query 只讀；由 Orders 組合各 owner 的最新回讀。只有服務天數完整、雙邊款項均真正結清且符合 #27 §7 其餘條件時，才由 Preview／Apply 推進。 | `historical_completion_oracle.py`、`historical_completion_apply.py` |
| Staff Payables | 跨案出款由 Staff Payables 驗整筆分配，不以單案切片推定完整；Orders 和前端不重算。 | `historical_staff_payables_completion_read_adapter.py`、下方 Staff Payables 正式決策 |
| 前端 | 證據缺漏或歸屬不明時呈現不可判定及對應 owner 的轉介，不把第 11 步顯示成已完成。 | `HistoricalCompletionPanel.tsx`、下方 Verification |

- 以 [歷史訂單正式規格 #27 §7](../../../../../requirements/27_歷史訂單生命週期與服務天數帳務正式規格.md#7-帳務完成投影) 判定整案能否結清；API 組裝見 `api/dependencies/historical_completion.py`，UI 的不可判定與轉介見 `HistoricalCompletionPanel.tsx`。
- Staff Payables 來源版本的 [正式決策](../../../../../../document/架構重整/02_決策與退役執行記錄/PROV-20260827-historical-staff-payables-completion-root-spec-gap.md) §2.2–2.3：`owner_source_versions` 列出各正式來源的類型、身分、版本，不取最大版本代表全案。一筆出款跨案時由 Staff Payables 驗整筆分配，不用本案切片推定完整。證據缺漏或歸屬不明回不可判定；Orders 不推進第 11 步，畫面沿 owner 轉介。
- `document/架構重整/02_決策與退役執行記錄/PROV-20260828-historical-payment-and-owner-settlement-spec.md` — payment、owner settlement與Step 11分離。
- `.arch-map/requirements/27_歷史訂單生命週期與服務天數帳務正式規格.md` — 歷史帳務完成 Q/P/A、fresh settlement 與 fail-closed lifecycle transition。

## Verification
- layout_status: `custom_current`
- test_root: `tests/domains/orders/subsystems/orders/modules/historical-completion/`
- integration_root: `ui_react/src/tests/historical_completion.test.tsx` — 既有模擬案例核對儲存只套用一次，完成後才通知上層。
- routing: `.arch-map/tests/domains/orders/subsystems/orders/modules/historical-completion.md`

## Provenance
- Orders Step 11 composition ownership — `architecture_declared` — 現行 #27 §7、Orders subsystem owner 與上述 composition。
- API／React paths and focused tests — `source_observed` — current repository。
- Cross-owner Step 11 oracle／query／projector／API／Apply coverage remains at the Orders subsystem integration boundary declared by the parent map；React presentation另由既有focused test保護。

## Change triggers
Reconcile when historical service-end rollover、Step 11 inputs、owner referral、terminal projection、Apply freshness/idempotency、lifecycle writer、React presentation or focused test roots change。
