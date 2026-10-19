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
- `api/schemas/account_center.py` — account creation/reset transport constraints.
- `api/routes/nas_setup.py` — NAS-only HTTPS/same-origin first-root setup with no installation key or preconfigured URL, delegated to the existing bootstrap transaction; setup closes once the root designation exists. Standard `api.main` does not attach it.

## Current contract

- Session expiry is bounded by the existing absolute deadline (maximum eight hours from issuance).
- There is no idle-session expiry or idle renewal.
- Revoked sessions and disabled admin users remain invalid.
- Existing stored sessions are evaluated by the absolute deadline; refresh does not extend that deadline.
- Creating or resetting an admin password requires at least 10 characters, including root bootstrap; existing password hashes remain valid.
- NAS first-install form follows the shared 10-character minimum; bootstrap does not issue a session or bypass MFA. Existing root/recovery rules and the unique root fact are unchanged. HTTPS remains required; NAS certificate/proxy setup is deferred by the user.

## Verification

- test_root: `ui_react/src/tests/session_client_two_step_auth.test.ts` — existing session client contract.
- test_root: `ui_react/src/tests/login_enrollment.test.tsx` — enrollment presentation and successful binding without a login session.
- test_root: `ui_react/src/tests/LoginPage.test.tsx` — two-step login, TOTP failure presentation and secret-safe handling.
- test_root: `ui_react/src/tests/fixtures/auth/two_step_auth_contract_fixtures.ts` — existing authentication contract fixtures.

- layout_status: `custom_current`
- layout_basis: Existing Access public account contract remains in the canonical subsystem `contract/` root; it verifies the API projection/request boundary together with the shared authentication policy. Session lifecycle integration remains in the existing sibling `integration/` root.
- `tests/domains/external-integration/subsystems/access/integration/test_access_session_expiry_policy.py`
- test_root: `tests/domains/external-integration/subsystems/access/contract/test_access_account_center_public_contract.py` — account request boundaries, safe public projection and shared password policy.
- test_root: `tests/domains/external-integration/subsystems/access/contract/test_nas_setup_contract.py` — HTTPS/same-origin first install without an installation key or fixed URL, shared password minimum, secret-safe errors, single-use closure and typed bootstrap races.
- test_root: `tests/domains/external-integration/subsystems/access/regression/test_development_root_admin_connection_lifetime.py` — development root bootstrap delegation, connection release, existing-account preservation and no automatic TOTP factor provisioning.
- test_root: `tests/domains/external-integration/subsystems/access/integration/test_development_root_mfa_enrollment_mysql.py` — fresh disposable MySQL verification of development bootstrap, random pending factors, confirmation-gated activation/session issuance and restart preservation.
