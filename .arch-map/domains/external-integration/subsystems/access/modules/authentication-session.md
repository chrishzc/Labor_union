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
- `api/schemas/account_center.py` — account creation/reset transport constraints.
- `scripts/create_admin.py` — interactive bootstrap adapter using the shared password hasher.

## Current contract

- Session expiry is bounded by the existing absolute deadline (maximum eight hours from issuance).
- There is no idle-session expiry or idle renewal.
- Revoked sessions and disabled admin users remain invalid.
- Existing stored sessions are evaluated by the absolute deadline; refresh does not extend that deadline.
- Creating or resetting an admin password requires at least 10 characters, including root bootstrap; existing password hashes remain valid.

## Verification

- test_root: `ui_react/src/tests/session_client_two_step_auth.test.ts` — existing session client contract.
- test_root: `ui_react/src/tests/login_enrollment.test.tsx` — enrollment presentation and successful binding without a login session.
- test_root: `ui_react/src/tests/fixtures/auth/two_step_auth_contract_fixtures.ts` — existing authentication contract fixtures.

- layout_status: `custom_current`
- layout_basis: Existing Access public account contract remains in the canonical subsystem `contract/` root; it verifies the API projection/request boundary together with the shared authentication policy. Session lifecycle integration remains in the existing sibling `integration/` root.
- `tests/domains/external-integration/subsystems/access/integration/test_access_session_expiry_policy.py`
- test_root: `tests/domains/external-integration/subsystems/access/contract/test_access_account_center_public_contract.py` — account request boundaries, safe public projection and shared password policy.
