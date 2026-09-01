# Test module: safe-review-link

## Owner

- module: `external-integration/line/safe-review-link`
- test routing is declared by the owning Module leaf; canonical roots are tests/domains/external-integration/subsystems/line/modules/safe-review-link/ and ui_react/src/tests/safe_review_link_workbench.test.tsx.

## Oracle

Protects digest-only persistence and the issued → redeemed/expired/revoked
state machine, including wrong actor, stale target, replay, and idempotency
fail-closed behavior.
