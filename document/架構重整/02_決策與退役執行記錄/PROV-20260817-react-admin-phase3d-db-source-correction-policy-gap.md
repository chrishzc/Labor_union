---
doc_type: gap-package
declared_status: proposed
identity: PROV-20260817-react-admin-phase3d-db-source-correction-policy-gap
date: 2026-08-17
owner: Access / Owning Domains
scope: Data Browser source-correction Preview/Apply disposition
decision_required: retire generic mutation or delegate to owning-domain commands
---

# Data Browser source-correction owner／退役政策缺口

## 現況

`api/routes/data_browser_admin.py`仍暴露raw-dict source-correction Preview／Apply，request以開放updates map傳入，
Apply可直接改`clients`、`staff`與`beclass_records`並commit。這與Data Browser只做去敏查詢、不得擁有正式
來源資料mutation的邊界衝突；React不得接線。

## 人工裁決

- **Option A（recommended）**：退役generic source-correction routes；Data Browser只保留query與owner deep-link。
- **Option B**：各owning Domain建立獨立typed Query→Preview→Apply→receipt/re-query，Data Browser只導航，
  不傳任意updates、不擁有transaction。

裁決前：React controls native disabled；現行Preview/Apply不得被標READY，不得用raw Zod adapter包裝冒充typed。
若採A或B，需另立exact public-interface/entrypoint WP並同步正式規格、queue、tests與rollback。

DB Gate：Scope PASS（gap only）；其餘NOT_RUN；`DB_CHANGE_NOT_READY`。
