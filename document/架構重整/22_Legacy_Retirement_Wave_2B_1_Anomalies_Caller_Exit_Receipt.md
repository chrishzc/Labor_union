# Legacy Retirement Wave 2B-1 Anomalies Caller Exit Receipt

日期：2026-08-03

## 授權範圍與結果

本 Work Package 僅切斷 legacy Finance Alert 三個保留 target module 的 residual caller；三個 target module 均未移除、未修改：

| Target module | SHA-256（前／後） |
| --- | --- |
| `services/finance_alert_detection.py` | `ab74569ff80936906188dbcda0d01c43c0c99024c0d5f0f4879806b936335da4` |
| `services/finance_alert_events.py` | `b86591954a69fa08f2eb02ff7dec2eab9521d0ac0d81fefcaafc0a65f8150a60` |
| `services/finance_alert_workflow.py` | `2470c112f9591b10b4f4f1c84fc11f2fab9f2399ddbd603b5f21bc3b6d6a3a1e` |

External production、UI、worker、outbox 與 maintenance roots 對 target group 的 caller 為 0。`finance_alert_workflow.py → finance_alert_events.py` 是保留 target group 內部依賴，依本階段「不得修改／移除 target modules」限制保留；將於正式 module-removal package 一併消失。

## 變更

- 移除已無外部 production root 的 `services/finance_alert_wiring.py`。
- 移除僅驗證 legacy route 的 `tests/test_finance_alert_router.py`。
- `ui/pages/06_finance_alerts.py` 移除 legacy Finance Alert client、schema 與 dead helper；保留 canonical Anomalies panel。
- `scripts/generate_fake_data.py` 移除 legacy alert workflow 呼叫與 legacy alert table 操作；它不會直接寫 legacy alert table 或 canonical projection table。
- `api/routes/finance_alerts.py` 切斷 legacy workflow import 及 actions。此 route 仍未由 `api/main.py` 掛載，也沒有新增 410 adapter。

## Inventory 不變量例外

刪除 `api/routes/finance_alerts.py` 會使既有 writer inventory 少 1 筆（其 `_run_action` 的靜態 `COMMIT` finding），違反本 Work Package 指定的「662 findings 與 fingerprint 完全不變」。因此 route source 暫留為**未掛載、不可執行的靜態盤點錨點**，且已不再 import 或呼叫 target group。這不是可用的 legacy route，也不是 410 adapter。

後續若授權實際移除此 route，必須在新的 module-removal package 中明確接受 inventory count 變更，並重新計算預期 fingerprint；不可沿用 Wave 2B 原本推定的 657 值。

## 驗證

- `py_compile api/routes/finance_alerts.py ui/pages/06_finance_alerts.py scripts/generate_fake_data.py`：通過。
- 有限 pytest matrix：27 passed、1 個既有 Starlette deprecation warning。
- `rg` caller scan：target group 唯一命中為其內部 `finance_alert_workflow.py` 對 `finance_alert_events.py` 的 import；所有外部 caller 類別為 0。
- Inventory：662 findings，fingerprint `d0a0007df33120d761d82d60707b948b28ccadc9e2e31ecd394762027cae1ddb`，與 Wave 1A 後 baseline 完全相同；未新增 writer。
- `api/main.py`、canonical Anomalies route/workflow/worker/outbox、schema、資料均未修改。

詳細可機械比對資料見 `evidence/legacy_retirement_wave_2b1_anomalies_caller_exit/`。
