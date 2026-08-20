---
doc_type: work-package
declared_status: approved
identity: PROV-20260817-react-admin-phase6b-production-hosting
date: 2026-08-17
owner: Integration Owner
specification: PROV-20260817-react-admin-phase6b-production-hosting
spec_path: PROV-20260817-react-admin-phase6b-production-hosting-specification.md
authority: awaiting-exact-human-approval
approval_required: 核准此 exact Phase 6B Work Package
approval_evidence: user-replied-核准此-exact-Phase-6B-Work-Package
prerequisites: PROV-20260817-react-admin-phase5b-dual-run-runtime-foundation PASS
base_branch: main
base_head: late-bound-at-approval
dirty_baseline: integration-owner-must-capture-before-writer
base_drift_rule: artifact/mount/health/rollback drift requires fresh read and re-freeze
ui_execution_mode: browser-required-static-hosting
db_change: none
absorbs: PROV-20260817-react-admin-phase6b-artifact-health-private-contract-amendment
---

# Phase 6B：React `/admin/` Production Hosting Work Package

## 0. Activation

只有人工明確回覆：

```text
核准此 exact Phase 6B Work Package
```

才可施工。此核准只涵蓋immutable artifact、FastAPI `/admin/`static serving、read-only artifact health與
previous-artifact rollback identity；不授權entry switch、traffic、provider、DB或Streamlit retirement。

原Artifact Health amendment已吸收，不再是獨立activation blocker。

## 1. Exact production write set

- `api/main.py`
- `infrastructure/runtime/react_admin_artifact.py`（new）
- `scripts/build_react_admin_artifact.py`（new）
- `ui_react/vite.config.ts`（只設定`/admin/`asset base）
- `api/schemas/private_operations.py`（只新增closed artifact-health response）
- `api/routes/private_operations.py`（只新增service-auth read-only GET）
- `api/dependencies/private_operations.py`（只重用existing service auth／artifact provider）
- `.env.example`（只記current/previous/selector設定，不放真path或secret）

不得建立Dockerfile、proxy config、第二UI service、新dependency或lockfile變更。需要上述外path時固定
`TOPOLOGY_SCOPE_EXPANSION_REQUIRED`並停止。

## 2. Exact tests and evidence

- `tests/test_react_admin_artifact_build.py`（new）
- `tests/test_react_admin_static_hosting.py`（new）
- `tests/test_react_admin_security_headers.py`（new）
- `tests/test_react_admin_artifact_health.py`（new）
- `tests/test_react_admin_artifact_rollback.py`（new）
- `tests/test_architecture_review_matrix_deployment_retirement.py`（只更新HOST contract assertion）
- 本spec／WP
- `document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase6b-production-hosting/`
  - `contract-matrix.md`
  - `candidate-change-inventory.md`
  - `verification-receipt.md`
  - `browser-runtime-receipt.md`
  - `rollback-rehearsal-receipt.md`
  - `open-findings.md`

README、main plan、shared indexes與正式Deployment SSOT由Integration Owner另行同步，不在production writer
write set。本輪核准也不自動授權這些shared docs。

## 3. Required implementation

### Artifact builder／validator

- Build輸出versioned candidate directory及canonical manifest。
- Manifest列出全部served files path/size/SHA-256與artifact version/digest；extra/missing/mismatch/path escape
  fail closed。
- `--check`唯讀驗證，不修改artifact或source。
- Current/previous兩個artifact都必須驗證且identity不同；不依mtime/symlink/目錄順序猜選。

### FastAPI static mount

- 只mount`/admin`；hash routes靠index HTML，無root wildcard／任意path fallback。
- API、health、internal、docs、LINE/webhook與其他routes保持原response；`/admin/api`不得被代理或fallback。
- Index/manifest no-store；content-hashed assets immutable one-year cache；MIME/CSP/nosniff/referrer headers exact。

### Artifact health

- Service-auth `GET /internal/v1/runtime/react-admin/artifact-health`。
- 回active selector/version/digests/API revision/root/checked-asset/healthy；不接受caller selector/path。
- 0 DB、0 monitor observation、0 LINE intent、0 provider；generic 200不能替代。

### Rollback identity

- Current/previous bindings與digests明確；rehearsal切selector並重新驗healthattestation。
- Unknown/missing/corrupt previous固定fail closed；不回滾API/schema/Domain data。
- Previous artifact不得被下一次build/cleanup覆蓋。

## 4. Forbidden actions

- 不修改launcher/Phase5B monitor、entry registry／queue、navigation、business pages、API/Domain contracts。
- 不建立root wildcard、CORS wildcard、remote script、unsafe-eval、dev-token/no-auth或browser storage捷徑。
- 不部署Cloud／host／edge、不切traffic、不retire或刪Streamlit。
- 不改DB/schema/migration/seed/backfill，不觸發provider。
- 不以`dist`存在、build PASS、TCP open、API health或`/admin/`200單獨宣稱hosting健康。

## 5. Gates

| Gate | PASS condition |
|---|---|
| G0 | exact approval、Phase5B fresh PASS、dirty/write-set collision、0 unexpected paths |
| G1 | immutable manifest/all-file digests及negative path/extra/mismatch tests |
| G2 | `/admin/`mount與API/health/internal/LINE non-interception |
| G3 | CSP/cache/MIME/security headers exact |
| G4 | private read-onlyartifact attestation一致且0 side effect |
| G5 | two-artifact selector rehearsal、previous identity與fail-closed rollback |
| G6 | browser `/admin/#hash` reload/assets/root-relative API與`/admin/api` negative evidence |
| G7 | focused/full pytest、React build/lint/test、UTF-8/header/diff/secret/write-set PASS |

## 6. Required commands

```powershell
.venv\Scripts\python.exe -m pytest -W error -p no:cacheprovider `
  --basetemp .pytest_tmp/phase6b-host -q `
  tests/test_react_admin_artifact_build.py `
  tests/test_react_admin_static_hosting.py `
  tests/test_react_admin_security_headers.py `
  tests/test_react_admin_artifact_health.py `
  tests/test_react_admin_artifact_rollback.py `
  tests/test_architecture_review_matrix_deployment_retirement.py

.venv\Scripts\python.exe -m scripts.build_react_admin_artifact --build --output .pytest_tmp/phase6b/current
.venv\Scripts\python.exe -m scripts.build_react_admin_artifact --check --artifact .pytest_tmp/phase6b/current
npm --prefix ui_react run lint
npm --prefix ui_react run build
npm --prefix ui_react test
git diff --check
```

Browser與current→previous→current rehearsal是必要evidence；沒有previous artifact不得用同一artifact複製冒充。

## 7. Completion semantics

完成狀態只代表`production-artifact-hosting-validated`。它不產生entry switch receipt、不變更canonical
navigation、不開始Phase6C retirement。每個entry仍須Phase5 switch／observation與Phase6獨立核准。

## 8. DB gate

Scope／Change inventory在exact approval後PASS（0 DB change）；Static/Descriptor/Plan/Engine/Developer acceptance
均`NOT_RUN`。結論`DB_CHANGE_NOT_READY`。
