# Subsystem: access

## Parent
- domain: `external-integration`

## Responsibility
提供 admin authentication/session、enabled actor、audit 與 security-alert boundary；authorization 不得被 UI presence 或 raw session data 取代。

## Dependencies
- outbound: all admin business adapters — supplies ActorContext/security boundary, not business rules。

## Contracts
- `subsystems/access/` — Access workflows
- `api/` — FastAPI auth/dependency adapters
- `document/架構重整/01_規格基線/17_External_Integration_LINE_Access正式規格.md` — Access contract

## Verification routing
- default_boundary: Subsystem
- test_root: `tests/domains/external-integration/subsystems/access/`
- integration_root: `tests/domains/external-integration/subsystems/access/integration/`.
- remaining_layout_gap: selected flat Access tests plus legacy Streamlit rollback coverage; see Test Map.
