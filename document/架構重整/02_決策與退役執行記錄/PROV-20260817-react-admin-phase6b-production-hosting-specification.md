---
doc_type: implementation-specification
declared_status: proposed
identity: PROV-20260817-react-admin-phase6b-production-hosting
date: 2026-08-17
owner: Global Deployment / Runtime Integration
authority: awaiting-exact-human-approval
recommended_topology: fastapi-same-origin-admin-static-mount
approval_required: 核准此 exact Phase 6B Work Package
prerequisites: PROV-20260817-react-admin-phase5b-dual-run-runtime-foundation PASS
base_branch: main
base_head: late-bound-at-approval
dirty_baseline: integration-owner-must-capture-before-writer
base_drift_rule: artifact, static mount, health or previous binding drift requires fresh read and re-freeze
db_change: none
---

# Phase 6B：React `/admin/` Production Hosting 規格

## 1. 目的與邊界

Phase6B只讓FastAPI同源服務一個已驗證、immutable的React `dist` artifact：

```text
/admin/          → index.html
/admin/assets/*  → manifest-listed static assets
/api/*           → existing API routes, never intercepted
/health          → existing API health, never intercepted
/internal/*      → existing private routes, never intercepted
LINE/webhook routes → never intercepted
```

React使用hash navigation，因此`/admin/#orders` reload的HTTP path仍是`/admin/`；不需要任意path SPA
fallback。禁止root wildcard mount。

本包不切任何entry、不改default navigation、不部署target host／Cloud／edge、不改provider、不寫DB、
不retire Streamlit。完成上限為`production-artifact-hosting-validated`。

## 2. Immutable artifact contract

每個artifact位於獨立versioned directory，含`index.html`、assets與`artifact-manifest.json`。Manifest至少包含：

- `artifact_version`：非空immutable release identity。
- `source_ref`與build tool versions。
- `api_compatibility_revision`：只作版本對照，不由runtime重新推導public contract。
- `root_entry=index.html`。
- 每個served file的relative path、byte size與lowercase SHA-256。
- `artifact_digest`：canonical manifest內容的SHA-256。

Manifest缺失、extra unlisted file、missing file、size/digest mismatch、absolute path、`..`、symlink escape、
root marker缺失或artifact directory指向workspace root時，一律fail closed。Build不得覆蓋current／previous
artifact或source tree。

## 3. Current／previous binding

Production profile明確提供：

```text
REACT_ADMIN_CURRENT_ARTIFACT_DIR
REACT_ADMIN_PREVIOUS_ARTIFACT_DIR
REACT_ADMIN_ACTIVE_SELECTOR=current|previous
```

Current與previous都必須在startup前完整驗證，各有不同`artifact_version`／digest。禁止依mtime、目錄排序、
symlink target或「找不到current就用previous」猜選。

Rollback只切active selector並重新載入presentation artifact；不回滾API、schema、Domain data、receipt或outbox。
Previous artifact未經明確替換／retention裁決不得被build或cleanup覆蓋。Unknown selector、missing previous或
previous digest不符固定拒絕rollback。

## 4. Static serving, CSP and cache

- FastAPI只在`/admin`掛載validated active artifact；route registration order與tests必須證明不攔截
  `/api`、`/health`、`/internal`、LINE/webhook及其他existing routes。
- React build使用`/admin/` asset base；API仍是root-relative`/api`，不得產生`/admin/api`或absolute origin。
- `/admin/`與artifact manifest：`Cache-Control: no-store`。
- content-hashed JS／CSS／fonts／images：`Cache-Control: public, max-age=31536000, immutable`。
- Security headers至少包含：
  - `Content-Security-Policy`：`default-src 'self'`、`frame-ancestors 'none'`；禁止remote script、
    `unsafe-eval`與非必要`unsafe-inline`。
  - `X-Content-Type-Options: nosniff`。
  - `Referrer-Policy: no-referrer`或同等更嚴格值。
- MIME type必須與asset一致；unknown／unlisted asset回404，不fallback index。

## 5. Artifact health attestation

原`PROV-20260817-react-admin-phase6b-artifact-health-private-contract-amendment`吸收進本HOST規格，不再作
獨立前置。

HOST提供service-auth protected、read-only private endpoint：

```text
GET /internal/v1/runtime/react-admin/artifact-health
```

它只回目前active mounted artifact的：active selector、artifact version、artifact digest、manifest digest、
API compatibility revision、root marker check、one listed asset digest check與`healthy`。不接受selector/path
參數，不回filesystem path、raw manifest、asset內容、env、token或secret。

Attestation query 0 DB、0 monitor observation、0 LINE intent、0 provider call。Generic API `/health`或
`/admin/` 200不能替代artifact attestation。

## 6. Runtime and browser acceptance

- Startup先驗current/previous，再mount active；invalid artifact不得啟用`/admin/`。
- `/admin/`、至少一個JS與CSS asset、private attestation均對應同一artifact digest/version。
- `/admin/#<known-hash>`與unknown hash reload都返回同一root HTML；unknown hash由React現行route guard處理。
- `/api/...`維持root-relative且不被static mount攔截；`/admin/api/...`不得回API或index fallback。
- Artifact／manifest／headers／receipt不得含token、帳密、TOTP、PII、secret或filesystem path。
- Browser只驗hosting與same-origin request；entry切換與業務流程驗收仍屬Phase5/per-entry工作包。

## 7. Out of scope

Entry routing／CAS、traffic切換、production hostname、reverse proxy、CORS wildcard、Cloud deployment、monitor
persistence、provider、DB/schema/migration/seed/backfill、Streamlit removal、Phase6 retirement。

## 8. Completion gates

| Gate | PASS condition |
|---|---|
| G0 Scope | exact approval、Phase5B PASS、dirty/write-set freeze、0 DB/provider/entry change |
| G1 Artifact | versioned manifest、all-file digests、extra/missing/path escape fail closed |
| G2 Mount | `/admin/`hash static serving且0 root wildcard/API/health/internal/LINE interception |
| G3 Headers | exact CSP/cache/MIME/nosniff/referrer headers |
| G4 Health | service-auth read-onlyattestation與mounted artifact identity一致；0 DB/monitor/provider side effect |
| G5 Rollback | current/previous不同identity、previous完整驗證、selector rehearsal與unknown/missing fail closed |
| G6 Browser | `/admin/#hash` reload、assets、root-relative API、`/admin/api` negative evidence |
| G7 Static | focused/full tests、React build/lint/test、UTF-8/header/diff/secret/write-set PASS |

## 9. DB gate

Scope／Change inventory在exact approval後PASS（0 DB change）；Static/Descriptor/Plan/Engine/Developer acceptance
均`NOT_RUN`。結論`DB_CHANGE_NOT_READY`；不影響純artifact hosting，也不授權任何DB side effect。

