# Module: authentication-session

## Owner

- source: `subsystems/access/authentication_session.py`

## Responsibility

Owns admin authentication/session persistence orchestration, including the absolute session deadline, revocation guard, and enabled-admin guard.

## Implementation

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

- layout_status: `custom_current`
- layout_basis: Existing Access public account contract remains in the canonical subsystem `contract/` root; it verifies the API projection/request boundary together with the shared authentication policy. Session lifecycle integration remains in the existing sibling `integration/` root.
- `tests/domains/external-integration/subsystems/access/integration/test_access_session_expiry_policy.py`
- test_root: `tests/domains/external-integration/subsystems/access/contract/test_access_account_center_public_contract.py` — account request boundaries, safe public projection and shared password policy.
