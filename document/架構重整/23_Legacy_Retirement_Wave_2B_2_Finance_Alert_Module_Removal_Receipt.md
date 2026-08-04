# Legacy Retirement Wave 2B-2 Finance Alert Module Removal Receipt

日期：2026-08-03

## 退役結果

已移除 legacy Finance Alert route 與三個 service module：

- `api/routes/finance_alerts.py`
- `services/finance_alert_workflow.py`
- `services/finance_alert_events.py`
- `services/finance_alert_detection.py`

同時移除五個僅直接驗證上述 legacy modules 的測試。共用 `tests/_finance_alert_mock_support.py` 未移除，因為它仍被三個 Finance Import 整合測試使用；它不 import 或呼叫任何已退役 module。

## 移除前 Source Lock

| Path | SHA-256 |
| --- | --- |
| `api/routes/finance_alerts.py` | `b5516c88f8e907315c1ca0f6ba2d6d06ccad43cd552549db3fe5f5cd27296e44` |
| `services/finance_alert_workflow.py` | `2470c112f9591b10b4f4f1c84fc11f2fab9f2399ddbd603b5f21bc3b6d6a3a1e` |
| `services/finance_alert_events.py` | `b86591954a69fa08f2eb02ff7dec2eab9521d0ac0d81fefcaafc0a65f8150a60` |
| `services/finance_alert_detection.py` | `ab74569ff80936906188dbcda0d01c43c0c99024c0d5f0f4879806b936335da4` |

Branch 為 `codex/refactor-api-streamlit-architecture`，HEAD 為 `4081a9b40c91a030c64f1d488411287ec6c01bdc`。工作樹本來即為 dirty；本包只碰上列 source 與五個 direct legacy tests。

## Caller 與替代鏈

移除前的 production、UI、worker、outbox、maintenance external caller manifest 均為 0。唯一 source 依賴為 legacy group 內的 `finance_alert_workflow → finance_alert_events`，隨 group 一起退役。

Canonical 替代鏈未修改：

- API：`api/routes/anomaly_registry.py`
- workflow：`subsystems/anomalies/alert_workflow.py`
- worker：`services/architecture_outbox_worker.py`
- Finance Import source-domain consumer：`services/finance_import_anomaly_consumer.py`
- UI：`ui/pages/06_finance_alerts.py`

`api/main.py` 未修改；legacy finance/system alert routes 保持未掛載、沒有新增 410 adapter。

## 驗收

- syntax compile：canonical API、workflow、worker、consumer 與 UI 通過。
- canonical finite matrix：40 passed，1 個既有 Starlette deprecation warning。
- caller scan：無可執行 reference；唯一文字命中是共用 mock helper 的 docstring。
- Inventory：由 662 降至 656，新的 fingerprint 為 `5f37096d0b4b62df38f3a5d01a653c9598a1e367d3174372fcf6099aec2532e6`。
- 允許的 6 筆消失為三個 service modules 的 5 個 writer finding，加上 legacy route `_run_action` 的 1 個 `COMMIT` finding；未新增 writer。

未 stage、commit、push、部署，亦未修改 schema 或資料。

## Rollback

若日後發現 caller、canonical behavior 或 Inventory 差異不正確，只恢復本收據列出的四個 production source 與五個 direct legacy test paths；不可覆蓋任何其他既有 dirty path。恢復後應重新驗證 caller scan、canonical finite matrix 與 Inventory。

詳細 machine-readable receipt 位於 `evidence/legacy_retirement_wave_2b2_finance_alert_module_removal/`。
