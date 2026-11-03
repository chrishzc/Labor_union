# Module: authentication-session

## Owner

- source: `subsystems/access/authentication_session.py`

## Responsibility

Owns admin authentication/session persistence orchestration, including the absolute session deadline, revocation guard, and enabled-admin guard.

## Implementation

- `ui_react/src/pages/LoginPage.tsx` — login and MFA enrollment presentation.
- `ui_react/src/pages/LoginPage.css` — flowing enrollment layout without footer overlap.
- `ui_react/src/api/auth/session_client.ts` — typed authentication client.
- `ui_react/src/api/auth/two_step_auth_schemas.ts` — password challenge discriminant and provisioning data.

- `subsystems/access/authentication_session.py` — shared password hashing and account/session orchestration.
- `api/dependencies/admin_auth.py` — authenticated principal and bounded registry read/write capability guards.
- `api/routes/admin_auth.py` — password challenges, TOTP enrollment confirmation and session transport; distinct safe keyring/schema failures, no session from enrollment.
- `subsystems/access/incomplete_root_reset.py` — offline Query/Apply for the sole unused, unbound root at initial security version 1; local target/id/version and business-reference guards, fresh locked recheck after confirmation, atomic bounded deletion and retained audit.
- `scripts/reset_incomplete_root_setup.py`、`scripts/launchers/reset_incomplete_root.bat` — default read-only preview and exact interactive confirmation for local incomplete-root reset; no HTTP entry or credential arguments.
- `scripts/configure_initial_totp_key.py`、`scripts/launchers/configure_initial_totp_key.bat` — offline explicit initial key setup; valid keys remain unchanged, missing/invalid keys require empty local account/auth tables and exact confirmation; atomic ignored .env write, no database mutation or secret output.
- `subsystems/access/totp.py` — shared environment/persisted keyring validation and factor encryption.
- `api/schemas/account_center.py` — account creation/reset transport constraints.
- `api/routes/admin_setup.py` — shared first-root progress/create API for standard and NAS management entries; same-origin HTTPS (HTTP only for a loopback Host and peer). `bootstrap_root_admin` atomically commits root plus pending enrollment and returns `RootBootstrapResult`; 201 returns a typed enrollment challenge, not a login redirect. Root designation closes recreation; active TOTP completes setup. `/setup` redirects to React; LINE public entry does not attach setup.
- `ui_react/src/api/auth/setup_client.ts` — bounded first-root status/create transport using the shared public-prefix handling.
- `ui_react/src/pages/FirstRootSetup.tsx`、`ui_react/src/pages/FirstRootSetup.css` — one setup gate/form mounted by `main.tsx` before the application and session handling; no environment-based account creation.

## Current contract
- `/me` 回應僅可更新發出請求的同一 token 所屬快取；晚到回應不得覆寫已登出或換人的 Session。Registry deletion UI 借用此既有 read boundary 即時確認 root。

- Session expiry is bounded by the existing absolute deadline (maximum eight hours from issuance).
- There is no idle-session expiry or idle renewal.
- Revoked sessions and disabled admin users remain invalid.
- Existing stored sessions are evaluated by the absolute deadline; refresh does not extend that deadline.
- Creating or resetting an admin password requires at least 10 characters, including root bootstrap; existing password hashes remain valid.
- All management entries use one flow: create root → QR → TOTP confirmation → recovery codes → fresh two-step login. Setup and enrollment issue no session. Root/pending factor/challenge commit together; encryption or persistence failures roll back creation. Existing recovery rules and the unique root fact are unchanged.
- `has_root_admin` gates the sole first-install form. The automatic unfinished-root continuation state/entry is retired; expired initial enrollment stops and names the offline reset tool. Missing encryption configuration and schema failures have distinct safe errors; legacy development credentials never create accounts at startup.

## Verification

- test_root: `ui_react/src/tests/session_client_two_step_auth.test.ts` — existing session client contract.
- test_root: `ui_react/src/tests/login_enrollment.test.tsx` — enrollment presentation and successful binding without a login session.
- test_root: `ui_react/src/tests/LoginPage.test.tsx` — two-step login, TOTP failure presentation and secret-safe handling.
- test_root: `ui_react/src/tests/fixtures/auth/two_step_auth_contract_fixtures.ts` — existing authentication contract fixtures.

- layout_status: `custom_current`
- layout_basis: Existing Access public account contract remains in the canonical subsystem `contract/` root; it verifies the API projection/request boundary together with the shared authentication policy. Session lifecycle integration remains in the existing sibling `integration/` root.
- `tests/domains/external-integration/subsystems/access/integration/test_access_session_expiry_policy.py`
- test_root: `tests/domains/external-integration/subsystems/access/contract/test_access_account_center_public_contract.py` — account request boundaries, safe public projection and shared password policy.
- test_root: `ui_react/src/tests/FirstRootSetup.test.tsx` — create→QR→TOTP→recovery→login order, expired initial setup stops, no session before login, password clearing, public prefix, unavailable state and concurrent closure.
- test_root: `tests/domains/external-integration/subsystems/access/contract/test_incomplete_root_reset_cli.py` — preview/confirmation/cancellation, remote and production refusal, safe errors.
- test_root: `tests/domains/external-integration/subsystems/access/contract/test_initial_totp_key_cli.py` — preview/cancellation, persistent valid-key preservation, existing account refusal, environment/file changes and failed-write cleanup without secret output.
- test_root: `tests/domains/external-integration/subsystems/access/integration/test_incomplete_root_reset_mysql.py` — legacy/pending root reset and all other table contents preserved; full database hashes verify no writes on cancellation, wrong target/id/version, changed security state during confirmation and used/enrolled/business-referenced account refusal, including the real CLI entry.
- test_root: `tests/domains/external-integration/subsystems/access/contract/test_nas_setup_contract.py` — shared API composition, secure same-origin transport, secret-safe errors, single-use closure, typed races and database/schema failure.
- test_root: `tests/domains/external-integration/subsystems/access/regression/test_development_root_admin_connection_lifetime.py` — legacy development credentials cannot bootstrap root at startup.
- test_root: `tests/domains/external-integration/subsystems/access/regression/test_admin_auth_runtime.py` — retained TOTP, session, rate-limit and local-bypass regression contracts; the retired startup-bootstrap oracle is replaced by the shared setup contract and web-MFA integration test.
- test_root: `tests/domains/external-integration/subsystems/access/integration/test_development_root_mfa_enrollment_mysql.py` — fresh disposable MySQL verification of missing-key rollback, explicit persistent key setup without DB writes, fresh-process factor decryption, web enrollment/login and existing-account/key preservation.
