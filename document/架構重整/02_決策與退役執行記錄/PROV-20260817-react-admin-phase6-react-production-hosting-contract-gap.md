---
doc_type: gap-package
declared_status: proposed
identity: PROV-20260817-react-admin-phase6-react-production-hosting-contract-gap
date: 2026-08-17
owner: Global Deployment / Runtime Monitoring
priority: P0
successor: PROV-20260817-react-admin-phase6b-production-hosting
---

# Phase 6：React production hosting／artifact contract 缺口

## Business scenario

Streamlit final retirement前，React必須有非Vite-dev的正式same-origin runtime，具備immutable artifact
identity、health、CSP、API compatibility與rollback identity。現在只有5173 dev server及`/api` proxy，沒有可
取代8501的production UI contract。

## Current gaps

- FastAPI沒有validated `ui_react/dist` mount、`/admin/` hash-route static serving／reload或React artifact health。
- 沒有reverse-proxy／static-hosting架構裁決，也沒有production deployment manifest。
- 沒有build version/digest、CSP、cache policy、API compatibility或rollback artifact identity。
- current CORS fallback只列8501；直接把5173加入不等於production hosting。
- Cloud Run文件仍以Streamlit為UI，但目前不是已核准deployment，不能直接改寫成已上線React。
- Current 18號Deployment SSOT明確退役target-host／vendor deployment profile；Phase6B若未限定為
  application artifact contract就會直接衝突，狀態固定`BLOCKED_DEPLOYMENT_SSOT_CONFLICT`。
- API compatibility expected目前沒有獨立canonical source，build script不得用live routes/OpenAPI自我生成。

## Required decision／successor

人工需在獨立public-interface／deployment Work Package裁決：

1. FastAPI static mount、reverse proxy或獨立React service的唯一production topology。
2. same-origin `/admin/` hash-route static serving／reload、health、CSP、cache、artifact digest/version與API
   compatibility；禁止root wildcard，且不得攔截`/api`、`/health`或LINE routes。
3. immutable previous artifact及rollback selector；rollback只切UI artifact，不回滾Domain data。
4. monitor、release receipt、observation window、rollback trigger及operator runbook。
5. 保留18號規格「不綁定target host／vendor」語意，只新增application artifact owner與selector。
6. checked-in API compatibility manifest、owner、freeze receipt及mismatch fail-closed contract。

未閉合前固定為`BLOCKED_REACT_PRODUCTION_HOSTING_CONTRACT`，不得退役Streamlit。

Proposed successor已收斂為FastAPI same-origin `/admin/` static-mount topology規格與exact Work Package；
只有人工核准successor後才算架構確認，本gap本身仍不授權實作或部署。
