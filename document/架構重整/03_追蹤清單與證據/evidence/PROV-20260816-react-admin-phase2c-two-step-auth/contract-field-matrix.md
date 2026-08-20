# Phase 2C Two-Step Authentication: Contract Field Matrix

**Declared Status**: FROZEN  
**Freeze Timestamp**: 2026-08-16T15:33:00+08:00  
**Authority Reference**: `01_規格基線/17_External_Integration_LINE_Access正式規格.md` (4.2–4.3)  
**Backend Routes**: `api/routes/admin_auth.py`  
**Backend Schemas**: `api/schemas/admin_auth.py`, `api/schemas/base.py`  
**Target Client Write Set**: `ui_react/src/api/auth/two_step_auth_schemas.ts`, `session_client.ts`  
**Target Presentation Write Set**: `ui_react/src/pages/LoginPage.tsx`  

---

## 1. Endpoint & HTTP Contract Overview

| # | Step | Endpoint Path | Method | Auth Header | Content-Type | Success Response Envelope |
|---|---|---|---|---|---|---|
| 1 | Stage 1: Password Challenge | `/api/v1/admin/auth/login/challenges` | `POST` | *None* | `application/json` | `BaseResponse[AdminPasswordChallengeResponse]` |
| 2 | Stage 2: TOTP Verification | `/api/v1/admin/auth/login/challenges/{challenge_id}/verify` | `POST` | *None* | `application/json` | `BaseResponse[AdminSessionResponse]` |
| 3 | Session Info (Validation) | `/api/v1/admin/auth/me` | `GET` | `Bearer <token>` | *None* | `BaseResponse[AdminPublic]` |
| 4 | Session Refresh | `/api/v1/admin/auth/refresh` | `POST` | `Bearer <token>` | *None* | `BaseResponse[AdminRefreshResponse]` |
| 5 | Session Logout | `/api/v1/admin/auth/logout` | `POST` | `Bearer <token>` | *None* | `BaseResponse[dict]` |
| 6 | *Legacy / Forbidden* | `/api/v1/admin/auth/login` | `POST` | *None* | *None* | **FORBIDDEN IN PRODUCTION** |
| 7 | *Legacy / Forbidden* | `/api/v1/admin/auth/development-session` | `POST` | *None* | *None* | **FORBIDDEN IN PRODUCTION** |

---

## 2. Comprehensive Field-by-Field Contract Matrix

| surface_field_id | endpoint | method | request JSON path | response JSON path | Pydantic source | TypeScript / Zod Type | required / nullable | secret handling | disposition |
|---|---|---|---|---|---|---|---|---|---|
| **stage1_username** | `/api/v1/admin/auth/login/challenges` | `POST` | `$.username` | N/A | `AdminPasswordChallengeRequest.username` | `z.string().min(1).max(100)` | Required, Non-nullable | Cleartext username (retained on error) | `READY_TYPED` |
| **stage1_password** | `/api/v1/admin/auth/login/challenges` | `POST` | `$.password` | N/A | `AdminPasswordChallengeRequest.password` | `z.string().min(1).max(256)` | Required, Non-nullable | `INTERNAL_SECRET`: Memory only during request; wiped immediately on Stage 1 success | `READY_TYPED` |
| **stage1_success** | `/api/v1/admin/auth/login/challenges` | `POST` | N/A | `$.success` | `BaseResponse.success` | `z.literal(true)` | Required, Non-nullable | Public boolean | `READY_TYPED` |
| **stage1_message** | `/api/v1/admin/auth/login/challenges` | `POST` | N/A | `$.message` | `BaseResponse.message` | `z.string()` | Optional / Present ("請輸入驗證器代碼") | Public string | `DISPLAY` |
| **stage1_challenge_id** | `/api/v1/admin/auth/login/challenges` | `POST` | N/A | `$.data.challenge_id` | `AdminPasswordChallengeResponse.challenge_id` | `z.string().min(1)` (UUID) | Required, Non-nullable | Memory only; used in Stage 2 URL path; cleared on reset/expiry/success | `READY_TYPED` |
| **stage1_challenge_token** | `/api/v1/admin/auth/login/challenges` | `POST` | N/A | `$.data.challenge_token` | `AdminPasswordChallengeResponse.challenge_token` | `z.string().min(32).max(256)` | Required, Non-nullable | `INTERNAL_SECRET`: Memory only; never in URL/DOM/log/storage; cleared on reset/expiry/success | `READY_TYPED` |
| **stage1_expires_at** | `/api/v1/admin/auth/login/challenges` | `POST` | N/A | `$.data.expires_at` | `AdminPasswordChallengeResponse.expires_at` | `z.string().datetime()` (ISO 8601) | Required, Non-nullable | Expiry timestamp (5 min from issue) | `READY_TYPED` |
| **stage2_path_challenge_id** | `/api/v1/admin/auth/login/challenges/{challenge_id}/verify` | `POST` | Path Param `{challenge_id}` | N/A | URL Path parameter | `encodeURIComponent(challenge_id)` | Required, Non-nullable | Sanitized URL parameter | `READY_TYPED` |
| **stage2_challenge_token** | `/api/v1/admin/auth/login/challenges/{challenge_id}/verify` | `POST` | `$.challenge_token` | N/A | `AdminFactorVerificationRequest.challenge_token` | `z.string().min(32).max(256)` | Required, Non-nullable | `INTERNAL_SECRET`: Sent in body; cleared immediately after attempt | `READY_TYPED` |
| **stage2_factor_code** | `/api/v1/admin/auth/login/challenges/{challenge_id}/verify` | `POST` | `$.factor_code` | N/A | `AdminFactorVerificationRequest.factor_code` | `z.string().regex(/^[0-9]{6}$/)` | Required, Non-nullable | `INTERNAL_SECRET`: 6-digit TOTP; memory only; cleared on error/success | `READY_TYPED` |
| **stage2_success** | `/api/v1/admin/auth/login/challenges/{challenge_id}/verify` | `POST` | N/A | `$.success` | `BaseResponse.success` | `z.literal(true)` | Required, Non-nullable | Public boolean | `READY_TYPED` |
| **stage2_access_token** | `/api/v1/admin/auth/login/challenges/{challenge_id}/verify` | `POST` | N/A | `$.data.access_token` | `AdminSessionResponse.access_token` | `z.string().min(1)` | Required, Non-nullable | `INTERNAL_SECRET`: Bearer token; memory-only in `sessionClient`; never in storage/URL | `READY_TYPED` |
| **stage2_token_type** | `/api/v1/admin/auth/login/challenges/{challenge_id}/verify` | `POST` | N/A | `$.data.token_type` | `AdminSessionResponse.token_type` | `z.string().default('bearer')` | Required, Non-nullable | Fixed string "bearer" | `READY_TYPED` |
| **stage2_expires_at** | `/api/v1/admin/auth/login/challenges/{challenge_id}/verify` | `POST` | N/A | `$.data.expires_at` | `AdminSessionResponse.expires_at` | `z.string().datetime()` (ISO 8601) | Required, Non-nullable | Session expiration timestamp | `READY_TYPED` |
| **admin_user_id** | `/api/v1/admin/auth/login/challenges/{challenge_id}/verify` & `/me` | `POST`/`GET` | N/A | `$.data.admin.id` (or `$.data.id`) | `AdminPublic.id` | `z.number().int().nullable()` | Required field, Nullable | Public user identifier | `READY_TYPED` |
| **admin_username** | `/api/v1/admin/auth/login/challenges/{challenge_id}/verify` & `/me` | `POST`/`GET` | N/A | `$.data.admin.username` (or `$.data.username`) | `AdminPublic.username` | `z.string().min(1)` | Required, Non-nullable | Display username | `DISPLAY` |
| **admin_display_name** | `/api/v1/admin/auth/login/challenges/{challenge_id}/verify` & `/me` | `POST`/`GET` | N/A | `$.data.admin.display_name` (or `$.data.display_name`) | `AdminPublic.display_name` | `z.string().min(1)` | Required, Non-nullable | User display name | `DISPLAY` |
| **admin_role** | `/api/v1/admin/auth/login/challenges/{challenge_id}/verify` & `/me` | `POST`/`GET` | N/A | `$.data.admin.role` (or `$.data.role`) | `AdminPublic.role` | `z.string().min(1)` | Required, Non-nullable | Access control role | `READY_TYPED` |
| **admin_linked_line_user_id** | `/api/v1/admin/auth/login/challenges/{challenge_id}/verify` & `/me` | `POST`/`GET` | N/A | `$.data.admin.linked_line_user_id` | `AdminPublic.linked_line_user_id` | `z.string().nullable().optional()` | Optional, Nullable | LINE user mapping ID | `READY_TYPED` |
| **admin_capabilities** | `/api/v1/admin/auth/login/challenges/{challenge_id}/verify` & `/me` | `POST`/`GET` | N/A | `$.data.admin.capabilities` | `AdminPublic.capabilities` | `z.array(z.string())` | Required, Non-nullable (array) | Security capability set | `READY_TYPED` |
| **admin_is_root** | `/api/v1/admin/auth/login/challenges/{challenge_id}/verify` & `/me` | `POST`/`GET` | N/A | `$.data.admin.is_root` | `AdminPublic.is_root` | `z.boolean()` | Required, Non-nullable | Root status flag | `READY_TYPED` |
| **admin_access_control_version** | `/api/v1/admin/auth/login/challenges/{challenge_id}/verify` & `/me` | `POST`/`GET` | N/A | `$.data.admin.access_control_version` | `AdminPublic.access_control_version` | `z.number().int()` | Required, Non-nullable | Credential version check | `READY_TYPED` |
| **refresh_expires_at** | `/api/v1/admin/auth/refresh` | `POST` | N/A | `$.data.expires_at` | `AdminRefreshResponse.expires_at` | `z.string().datetime()` (ISO 8601) | Required, Non-nullable | Refreshed session timestamp | `READY_TYPED` |
| **logout_logged_out** | `/api/v1/admin/auth/logout` | `POST` | N/A | `$.data.logged_out` | `dict` (`{"logged_out": True}`) | `z.boolean()` | Required, Non-nullable | Logout indicator | `READY_TYPED` |

---

## 3. Error Contract & UI Disposition Matrix

| Stage | HTTP Status | Error Code (`detail.code` or string) | Backend Message | UI Action / Disposition | Secret Handling Rule |
|---|---|---|---|---|---|
| **Stage 1** | `401 Unauthorized` | `invalid_credentials_or_factor` | 帳號、密碼或驗證碼錯誤 | 留在 Stage 1；顯示「帳號或密碼錯誤」；清空密碼欄位；保留 username | 立即清除 state 中的 password |
| **Stage 1** | `403 Forbidden` | `mfa_enrollment_required` | 請完成 MFA 綁定後再登入 | 留在 Stage 1；顯示「此帳號需先完成 MFA 綁定；React 綁定流程尚未啟用」；清空密碼 | **絕對禁止** 洩漏或渲染 error payload 中的 `provisioning_uri`、`token` 或 `secret` |
| **Stage 1** | `429 Too Many Requests` | `login_rate_limited` | 登入嘗試過於頻繁，請稍後再試 | 留在 Stage 1；顯示「登入嘗試過於頻繁，請稍後再試」；清空密碼 | 清除密碼 |
| **Stage 1** | `503 Service Unavailable` | `admin_auth_unavailable` / `admin_session_storage_unavailable` | 管理員登入儲存服務暫時無法使用 | 留在 Stage 1；顯示「系統驗證服務暫時無法使用，請稍後再試」 | 清除密碼 |
| **Stage 2** | `401 Unauthorized` | `invalid_credentials_or_factor` | 帳號、密碼或驗證碼錯誤 | 留在 Stage 2；顯示「驗證碼錯誤或無效」；清空 6 位 TOTP 輸入框；允許重新輸入 TOTP | 清空 TOTP 輸入陣列 |
| **Stage 2** | `401 / 409 / Expired` | `invalid_credentials_or_factor` (due to challenge expiration or replay) | 帳號、密碼或驗證碼錯誤 | 若 challenge 已逾期 (超過 5 分鐘)，自動退回 Stage 1 並提示「驗證階段已過期，請重新輸入帳號密碼」 | 清空 challenge_id, challenge_token, TOTP digits |
| **Stage 2** | `429 Too Many Requests` | `login_rate_limited` | 登入嘗試過於頻繁，請稍後再試 | 留在 Stage 2；顯示「驗證嘗試過於頻繁，請稍後再試」；清空 TOTP 輸入框 | 清空 TOTP |
| **Stage 2** | `503 Service Unavailable` | `admin_auth_unavailable` | 系統暫時無法使用 | 留在 Stage 2；顯示「驗證服務暫時無法使用」；不建立 Session | 保留 challenge 待重試或返回 |
| **Any** | `422 Unprocessable Entity` | `VALIDATION_ERROR` | FastAPI parameter validation failure | 顯示「輸入格式不符規定」 | 不建立 session |
| **Any** | Network / Timeout | `ApiNetworkError` / `ApiTimeoutError` | 網路連線失敗 / 請求逾時 | 顯示「網路連線異常，請檢查網路後重試」 | 不建立 session |
| **Any** | Decode Error | `ApiDecodeError` | 資料結構驗證失敗 | Fail closed；顯示「伺服器回應結構異常」；不建立 session | 丟棄 raw payload |

---

## 4. Frontend State Machine Specification

```text
[Initial / Render]
       │
       ▼
 ┌──────────────┐   handleStage1Submit (validation + API)
 │password_entry│ ──────────────────────────────────────────┐
 └──────────────┘                                           │
       ▲                                                    │
       │ back-to-stage1-btn / challenge_expired             ▼
       │ (wipes challenge, password, totp)        ┌───────────────────┐
       ├───────────────────────────────────────── │ challenge_pending │
       │                                          └───────────────────┘
       │                                                    │
       │                                                    │ API Success (challenge_id, challenge_token)
       │                                                    │ [Wipes password state!]
       │                                                    ▼
       │                                          ┌───────────────────┐
       │                                          │    totp_entry     │
       │                                          └───────────────────┘
       │                                                    │
       │                                                    │ handleStage2Submit (6 digits check + API)
       │                                                    ▼
       │                                          ┌───────────────────┐
       │                                          │  verify_pending   │
       │                                          └───────────────────┘
       │                                                    │
       │ API 401 (challenge expired)                        │ API Success (AdminSessionResponse)
       │                                                    ▼
       │                                          ┌───────────────────┐
       └───────────────────────────────────────── │   authenticated   │
                                                  │ (Shell Unlocked)  │
                                                  └───────────────────┘
```

---

## 5. Secret Hygiene & Defense-in-Depth Invariants

1. **Zero Secret Persistence**:
   - `password`, `totpDigits`, `challenge_token`, `access_token` MUST NEVER be written to `localStorage`, `sessionStorage`, cookies, URL search params, URL hash, or `document.title`.
2. **Immediate Memory Erasure**:
   - `password` is wiped the moment Stage 1 challenge returns.
   - `challenge_token` is wiped upon Stage 2 completion, expiration, or back button press.
   - `totpDigits` are wiped upon verify error, verify success, or back button press.
3. **Error Redaction (`mfa_enrollment_required`)**:
   - Backend 403 detail contains `provisioning_uri` and challenge tokens.
   - Frontend MUST NOT render or log these values. UI must display a sanitized notification: `此帳號需先完成首次 MFA 綁定；React 綁定流程尚未啟用。`
4. **Generation Guard**:
   - Async API requests must use a generation ID or active flag so that if a user clicks back and starts a new login attempt, slow responses from the previous attempt are cleanly ignored.
5. **Session Client Isolation**:
   - In-memory bearer token is stored only in private module variables in `session_client.ts`.
   - All protected requests read `sessionClient.getToken()` just-in-time and inject `Authorization: Bearer <token>`.
