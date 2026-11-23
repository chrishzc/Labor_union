# Module: payroll-current-issue

## Parent
- domain: `anomalies`
- subsystem: `anomalies`

## Responsibility
`PAYOUT-002`已退出 runtime Anomalies。本 leaf只保留既有 Payroll owner validation／migration evidence
的導覽，不再投影 current issue、不計算delta、不寫Payroll或Staff Payables root。

## Verification
- 固定版未定位本 leaf 的專屬測試目錄。`domains/anomalies/registry.py` 的預設 registry 只登錄 LINE；既有 `PAYOUT-002` 輔助定義不是執行期登錄。這是靜態來源核對，不是測試覆蓋。

## Lifecycle
- `superseded_candidate`: 無 current runtime anomaly consumer；若 source／test retirement完成，移除本 leaf及其 inbound route。
