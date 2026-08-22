---
doc_type: work-package
declared_status: in-progress
identity: PROV-20260820-access-control-mfa-enrollment-success-contract
date: 2026-08-20
owner: Access Control / Streamlit Integration Owner
domain: Access Control
implementation_authorization: user-approved-2026-08-20
base_branch: cloud_run
base_head: b626580fecf919dc908c794a5b1b7211b4dc1e71
---

# Access Control MFA enrollment 成功契約修復工作包

## 0. Business scenario 與裁決

內部管理員第一次以正確帳密登入時，尚未啟用 TOTP factor。系統必須在不建立 Session 的前提下，
把短效 MFA enrollment challenge 與 provisioning URI 交給既有 Streamlit 綁定畫面顯示 QR code。

2026-08-20 人工核准本 exact 修復：password 驗證成功後的 enrollment 是成功結果，固定由
`POST /api/v1/admin/auth/login/challenges` 的 HTTP 200 `data` 回傳；不得再把 challenge token 或
provisioning URI 放入 403／其他非 2xx error。Global typed error boundary 的去敏契約維持不變。

## 1. Scope、owner 與不變量

- Access Control 擁有 password challenge／MFA enrollment challenge 與 factor state。
- API route 是公開 transport owner；Streamlit typed client 是本次唯一 enrollment consumer。
- 回應以 `challenge_type` 明確區分 `factor_verification` 與 `mfa_enrollment`。
- `mfa_enrollment` 必須帶 `provisioning_uri`；`factor_verification` 的該欄位固定為 null。
- 兩種結果都不建立 bearer Session，challenge token 只留在短效記憶體狀態。
- error、log、URL、browser storage、audit detail 均不得出現 provisioning URI 或原 challenge token。

## 2. Exact write set

Production：

- `api/schemas/admin_auth.py`
- `api/routes/admin_auth.py`
- `ui/api_clients/access_control_api_client.py`
- `ui/app.py`

Contract／tests／integration：

- `document/架構重整/01_規格基線/17_External_Integration_LINE_Access正式規格.md`
- `document/架構重整/02_決策與退役執行記錄/README.md`
- 本工作包
- `tests/test_admin_auth_runtime.py`
- `tests/test_global_typed_error_boundary.py`
- `tests/test_access_control_ui_app_test.py`
- `history/work_log.md`（Git ignored；只記本機驗證）

## 3. Out of scope

- 不改 schema、migration、既有 account／factor 資料或 TOTP keyring。
- 不重設密碼、不人工啟用 factor、不建立 bypass。
- 不修改 React enrollment UI；既有 React Phase 2C 對首次 enrollment 繼續 fail closed。
- 不執行正式 Cloud Run deployment、production cutover、commit 或 push。

## 4. Acceptance

1. 一般 active-factor 帳號得到 `factor_verification` challenge，且 provisioning URI 為 null。
2. 首次登入得到 HTTP 200 `mfa_enrollment` challenge，Streamlit 顯示記憶體內 QR code。
3. legacy `/login` 與所有非 2xx error 不含 challenge token／provisioning URI。
4. strict Global `detail.error` 契約與敏感資訊去敏 regression 持續通過。
5. focused API、UI、TOTP 與 auth tests 通過。
6. 本機 API／UI images 重建並重啟後，health checks 通過；最後由使用者輸入真實帳密與 Authenticator
   驗證碼完成 browser acceptance。

## 5. 2026-08-20 execution evidence

- focused regression：
  `.venv\Scripts\python.exe -m pytest tests/test_admin_auth_runtime.py tests/test_global_typed_error_boundary.py tests/test_access_control_ui_app_test.py tests/test_admin_auth_security.py tests/test_access_totp.py -W error -p no:cacheprovider --basetemp .pytest_tmp/mfa-enrollment-success-contract -q`
  → `75 passed in 5.04s`。
- API image `union-api-compat:redisless-local` 與 UI image
  `union-ui-compat:redisless-local` 均重建成功；build context 未包含 `.env`。
- `union-api-compat-local` 與 `union-ui-compat-local` 已使用既有 Docker network 重啟；
  `http://127.0.0.1:18080/health` 回 healthy，
  `http://127.0.0.1:18501/_stcore/health` 回 200／ok，兩個 container 均為 healthy。
- live OpenAPI 已載入 `challenge_type = factor_verification | mfa_enrollment` 與
  `provisioning_uri` 欄位；pending enrollment 每次成功 password challenge 會替換為新的短效 seed、token
  與 expiry，不會被先前過期 challenge 卡住。
- Codex in-app browser 因本機 trusted-code-path 設定無法連線；此項不是 application failure。工作包維持
  `in-progress`，等待帳號本人於 8501 輸入真實帳密、掃描 QR 並驗證第一組 TOTP 後完成 browser acceptance。
