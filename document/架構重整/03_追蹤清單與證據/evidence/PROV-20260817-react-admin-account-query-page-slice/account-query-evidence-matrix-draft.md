# Account Query Page-Slice Evidence Matrix（Draft）

Status: `DRAFT` / awaiting exact approval. This is not a freeze receipt or PASS evidence.

Work Package: `PROV-20260817-react-admin-account-query-page-slice`

## 1. Endpoint/auth matrix

| Page lane | Method/path | Auth | Current disposition | Required candidate |
|---|---|---|---|---|
| accounts | `GET /api/v1/admin/accounts` | sole enabled root | typed but over-broad `AccountCenterUser/AdminPublic` | minimal six-field list view |
| audit | `GET /api/v1/admin/audits` | enabled internal principal | typed page; current underlying/raw detail policy too broad | closed masked list-only view |
| audit detail | `GET /api/v1/admin/audits/{id}` | enabled internal principal | raw `details` union | not called; UI unavailable |
| jobs | `GET /api/v1/jobs/{job_id}/observation` | `system.administration` capability (`require_system_admin`) | new additive view required | safe metadata only; no receipt/error |
| job cancel | `POST /api/v1/jobs/{job_id}/cancel` | enabled internal principal | mutation | disabled/not called |

## 2. Field matrix

### Accounts

| Field | Type | UI disposition |
|---|---|---|
| `id` | positive integer | card identity |
| `username` | non-empty string | display |
| `display_name` | non-empty string | display |
| `enabled` | boolean | status badge only |
| `is_root` | boolean | root indicator, not business menu authorization |
| `access_control_version` | integer >= 1 | version display/CAS lineage only |
| email/IP/session/last-login/MFA/LINE/role/capabilities | absent | unavailable; no fake value |

### Masked audit

| Field | Type | UI disposition |
|---|---|---|
| `audit_id` | positive integer | stable row identity |
| `occurred_at` | ISO datetime | display |
| `actor_label_masked` | string/null | masked display |
| `action_family` | closed enum | badge/filter |
| `target_label_masked` | string/null | masked display |
| `ip_address_masked` | string/null | server mask only |
| `outcome` | closed enum | badge/filter |
| `reason_code` | bounded string/null | safe code, not raw note |
| raw details/path/resource/token/full IP | absent | never renderer input |

### Job observation

| Field | Type | UI disposition |
|---|---|---|
| `job_id` | non-empty string | submitted identity and response match |
| `command_type` | eight-value enum | safe job type label |
| `status` | queue-state enum | queue status only, not Domain outcome |
| `attempt_count` | integer >= 0 | display |
| `max_attempts` | integer >= 0 | display |
| receipt/error/result/provider/payload | absent | unavailable; never renderer input |

## 3. UI/control/request matrix

| Stable ID | Disposition | Budget / safety |
|---|---|---|
| `account.tab.users` | lazy accounts query | first visit 1 GET |
| `account.tab.audit` | lazy masked audit query | first/filter/page/refresh each 1 GET |
| `account.tab.jobs` | manual lookup workbench | first visit 0 GET |
| `account.jobs.lookup|refresh` | safe observation query | each explicit action 1 GET |
| `account.tab.totp` | explanation/unavailable | 0 GET, no QR/secret/code |
| `account.user.create|enable|disable|password-reset|session-revoke` | native disabled | 0 request |
| `account.mfa.enroll|reset|verify` | native disabled | 0 request |
| `account.audit.detail` | unavailable/disabled | 0 detail GET |
| `account.jobs.cancel|retry|run` | native disabled | 0 request |

## 4. Mandatory negative evidence

- Account: non-root 403, missing/extra/wrong/null/version/duplicate-id payloads;
- Audit: raw details/full IP/token/email/PII injection, invalid filters/page, duplicate IDs, stale filter/page response;
- Jobs: unknown command/status, raw receipt/error/provider injection, identity mismatch, missing job, status not treated as Domain success;
- All: missing/rotated memory bearer, 401/403/404/422/500/503, timeout/network/abort, tab stale response;
- UI: no fake email/IP/MFA/session/audit/job health, `Date.now`, local success, `alert/confirm/prompt` or non-GET;
- Browser: real account→TOTP session, root/non-root auth, Network↔DOM, existing DB GET only.

## 5. Evidence placeholders

| Artifact | Initial status |
|---|---|
| `contract-field-matrix.md` | NOT_RUN |
| `candidate-change-inventory.md` | NOT_RUN |
| `verification-receipt.md` | NOT_RUN |
| `browser-smoke-receipt.md` | NOT_RUN |
| `open-findings.md` | NOT_RUN |

No DB engine/migration evidence is created by this query-only draft.
