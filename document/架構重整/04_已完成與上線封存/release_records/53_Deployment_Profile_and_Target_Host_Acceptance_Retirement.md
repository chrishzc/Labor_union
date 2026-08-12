# 53. Deployment Profile 與 Target-host Acceptance 退役決策

## 決策

- 決策日期：2026-08-09
- 決策者：系統業務負責人
- 對應規格：`01_規格基線/18_Global_Deployment與治理正式規格.md`

使用者決定移除 deployment profile 與 target-host acceptance 設定。系統不保存
`local-primary`、`hybrid-app-host`、target host、edge vendor、RTO/RPO、host ownership 或
target-host acceptance evidence，也不以它們作為程式 release gate。

## 保留邊界

本決策不放寬產品安全與資料不變量：MySQL 不公開、secret 不進 Git、公開 HTTP 必須受控、
以及 preserve-data release 的 backup／candidate／manifest contract 仍有效。實際部署方式由
部署者在系統外處理，不能透過設定改變 Domain 行為。

## 退役範圍

- `50_Target_Host_Deployment_Acceptance_Runbook.md` 改列歷史文件，不再是操作前置條件。
- target-host Scheduler／TLS／HTTP2／latency evidence 不再是產品的 completion 或 release gate。
- Windows Task Scheduler worker 機制保留，但不是 deployment profile。
