---
doc_type: work-package
declared_status: proposed
date: 2026-08-16
owner: Access Control / Global Security
domain: Internal Access
subsystem: Production cutover and external security alert
implementation_authorization: requires-new-human-confirmation
predecessor: Access Control TOTP Account Management 歷史 Work Package（原文已自工作樹移除）
---

# Access Control：Production Cutover 與 External Security Alert 工作包

> 狀態：`proposed`。本工作包由已封存的本機驗證工作包移交未部署範圍而來；目前沒有 production
> target、operator、provider 或 secret 操作授權，因此不得施工或部署。

## 1. 業務場景與範圍

本包在取得新的人工確認後，才處理真正 production cutover 與 external security alert。它承接：

1. `AC-P3-04` 的 production bypass attempt、root offline-recovery attempt、audit rollback 外部告警；
2. `AC-P3-05` 的真實 MySQL concurrent row-lock／stale-version／outbox partial-failure 驗收；
3. `AC-P6-01` 的 browser-level 帳號建立、本人 enrollment、MFA login、跨頁與 logout；
4. `AC-P6-07` 的所有既有管理頁 Bearer-only、同權驗收，以及 root-only 帳號中心 thin-UI 邊界；
5. `AC-P7-01` 至 `AC-P7-06` 的 target deployment、雙人 MFA enrollment、keyring／時鐘／migration
   preflight、維護窗 smoke、machine identity scan 與相容 rollback。

正式語意以 [`25_Access_Control_Production_Cutover與External_Security_Alert正式規格.md`](../01_規格基線/25_Access_Control_Production_Cutover與External_Security_Alert正式規格.md)
為準；本文件不重複定義 account、MFA 或 human authorization 的根事實。

## 2. 現在明確排除的寫入與副作用

在取得後續人工確認前，本包的實際 write set 為 **無**。特別排除：

- production database、Cloud／OIDC／IAM、DNS、container deployment、external alert provider；
- keyring、password、TOTP seed、recovery code、Bearer、machine key 與任何 production credential；
- 對 configured target 的 schema apply、切換、rollback 或 user enrollment。

不得把本機 `.env`、Docker `mysql_db`、developer-local replacement 或 disposable `lu_test_*` database
視為 production target。

## 3. 啟動前人工確認項目

後續啟動必須明確確認：target identity、operator、維護時窗、release／rollback owner、external alert
provider 與 recipient、資料／keyring backup owner、至少兩位 enrollment 管理員，以及精確 code／schema／
runbook／test write set。任一項缺失，狀態固定為 `BLOCKED_SCOPE`，不得猜測或自動探索外部資源。

## 4. 驗收矩陣

| Gate | 必要證據 | 目前狀態 |
|---|---|---|
| External alert contract | provider-neutral delivery、attempt／failure fact、去敏 payload、人工處理入口 | `NOT_RUN` |
| MySQL concurrency | 真實 MySQL concurrent row-lock、stale-version、outbox partial failure | `NOT_RUN` |
| Browser Global flow | create → enrollment → MFA → cross-page → logout；Bearer-only 同權頁面 | `NOT_RUN` |
| Cutover preflight | target、release chain、schema no-drift、keyring backup／restore、clock、雙人 MFA | `NOT_RUN` |
| Deployment / rollback | 維護窗 smoke、去敏 receipt、相容 rollback；不重啟 legacy key／bypass | `NOT_RUN` |

## 5. 來源與完成條件

前身已完成的本機實作、schema release、fresh／preserve-data MySQL 與 developer-local replacement 證據
只可作為起點，不是本包的 completion receipt。本包僅在所有 gate 有 target-specific 去敏證據且人工確認
completion 後，才能標為 `completed` 或封存。
