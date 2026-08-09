---
scope: 18_Global_Deployment與治理正式規格
status: verified-local-release-contract
verified_at: 2026-08-09
---

# Global Deployment／治理重新驗證收據

## 追溯依據

- 規格基線：`01_規格基線/18_Global_Deployment與治理正式規格.md`；
- worker supervision：`41_Durable_Job_Worker_Supervision_Deployment_Decision.md`；
- retired target-host runbook：`50_Target_Host_Deployment_Acceptance_Runbook.md`；
- deployment setting retirement：`53_Deployment_Profile_and_Target_Host_Acceptance_Retirement.md`；
- preserve-data closure：`51_Preserve_Data_and_Historical_Reprocess_Closure_Work_Package.md`。

## 本次 release-chain 修復

- Access／Knowledge schema 原先能由 fresh bootstrap 載入，但未加入 preserve-data release
  chain；既有 candidate database 因而可能漏套用 dynamic grant、reviewed Knowledge schema。
- 新增 additive release `labor-union-2026-08-09-v3`，嚴格依序套用
  `149_admin_authorization_version.sql`、`147_access_capability_grants.sql`、
  `148_knowledge_retrieval.sql`；每個 artifact 都有 SHA-256、dependency、owned-object
  descriptor、statement-resume policy 與 candidate restore rollback policy。
- `authorization_version` 已從 fresh base schema 移為 release artifact，讓 fresh bootstrap
  與 preserve-data candidate 都走同一 DDL authority；既有環境可用
  `scripts/migrate_admin_capability_grants_schema.py` 做同等、可重跑 upgrade。
- 後續 v4 納入 Rich Menu server-side preview receipt 與管理員 session absolute expiry；v5 納入
  `admin_audit_log_archive`，將超過兩年的管理稽核紀錄移出線上查閱表而不自動刪除 archive。
  它們同樣有 additive artifact、SHA-256、dependency 及 owned-object descriptor。

## 驗證

- release metadata／preserve-data runner／cutover contract：`82 passed, 1 skipped`；
- disposable MySQL 8.4 fresh bootstrap 成功，依序載入 149、147、148 與完整 schema parts；
- 此驗收未連線正式 DB、未改 `.env`、未執行任何外部 deployment mutation。

## Retired deployment setting

使用者已於 2026-08-09 移除 deployment profile 與 target-host acceptance 作為產品設定及
release gate。Decision 50 僅保留歷史追溯；本收據不以 host、edge、RTO/RPO 或外部驗收資料
判斷程式 release 是否完成。

## Current-source policy verification

基線已將 HTTP/2／HTTP/3／connection reuse 明確列為部署者可選的外部優化，保留 HTTP/1.1
application transport compatibility，且不把任一協定當作產品 release gate。

```text
deployment-retirement and migration-release metadata suite
7 passed in 0.27s
```
