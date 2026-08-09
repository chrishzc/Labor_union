---
doc_type: gap-package
---

# Global E2E Acceptance Gap Package

## 1. Evidence rule

A Domain test, a mocked unit test, or several tests that happen to exercise
adjacent components does not prove a Global scenario.  Each approved scenario
needs one traceable isolated-MySQL E2E test with its root facts, API/UI entry
point where applicable, transaction boundary, expected receipt, outbox state
and recovery assertion named in the test or its companion evidence.

Source hashes bind the manifest to the exact source snapshot that was executed.
They are historical evidence rather than a claim about a later dirty worktree:
any changed referenced source requires a new isolated-MySQL run and refreshed
hashes before its scenario can again be called current.

The current completion matrix identifies four business scenarios only in
summary form (cancellation settlement, completed-service payroll retention,
government subsidy allocation, and ambiguous batch → human review).  Their
test-to-scenario mapping is not yet a stable Global acceptance manifest, so
they remain `candidate-existing-coverage`, not counted as completed here.

## 2. Required scenario manifest

| ID | Required Global invariant | Current evidence disposition |
|---|---|---|
| G01 | Terms change rebuilds Scheduling, Client Finance, Payroll and lifecycle consistently; coverage anomaly ownership remains in Scheduling. | proven: real MySQL covers direct canonical transaction/replay plus `test_g01_terms_panel_uses_real_http_preview_and_apply`, which drives the actual Streamlit panel through typed HTTP Preview/Apply. Service-day-count changes fail closed without an approved assignment reallocation plan. Terms Apply does not directly create an alert; any real post-rebuild coverage risk is detected by the existing Scheduling coverage scan. |
| G02 | Actual Start correction is all-chain atomic. | proven: real MySQL covers the canonical transaction/replay trace and `test_g02_actual_start_panel_uses_real_http_preview_and_apply`, which drives the actual Streamlit panel through typed HTTP Preview/Apply with request-scoped dependencies. Complete service-time gating, Orders/Scheduling/Client Finance/Payroll/Lifecycle writes and source outboxes each remain atomic and exactly once. |
| G03 | Mid-service multi-staff cancellation preserves independent client-refund and staff-payable settlement tracks. | proven: real MySQL covers the canonical transaction/replay trace and `test_g03_panel_uses_real_http_preview_and_apply` drives the actual Streamlit panel through typed HTTP Preview/Apply. Only actual completed service days are retained; the resulting client refund and staff payable obligations remain independent rather than being incorrectly auto-netted. |
| G04 | Cancellation after complete service leaves full staff payroll unchanged and performs zero invalid writes. | proven: isolated MySQL `test_g04_full_service_cancellation_is_blocked_without_writes` uses a completed order with two established service-pay obligations and proves the blocker, no writes, and unchanged payroll projection. |
| G05 | Leave/substitution competes safely with completion time. | proven: isolated MySQL real-workflow E2E covers both orders. AutoComplete first makes the true stale Leave Apply return `stale_version` without Scheduling／Client Finance／Payroll／outbox／leave-outcome writes; Leave first makes the old completion conflict, then allows only a recomputed completion instant. |
| G06 | Service-data lock is not removed by refund/reversal. | proven: isolated MySQL `test_g06_refund_and_reversal_preserve_the_immutable_service_data_lock`; manifest `evidence/global_e2e_manifest.json` |
| G07 | API timeout retry replays exactly one full cross-domain command. | proven: isolated MySQL `test_g07_timeout_retry_enqueues_and_applies_one_cross_domain_command`; manifest `evidence/global_e2e_manifest.json` |
| G08 | Injected failure at every cross-domain persistence point leaves no partial commit. | proven: isolated MySQL `test_g08_each_finance_correction_persistence_failure_rolls_back`; manifest `evidence/global_e2e_manifest.json` |
| G09 | Streamlit and direct typed API obtain the same result without UI business fallback. | proven: isolated MySQL `test_g09_ui_client_and_direct_typed_preview_have_the_same_result`; manifest `evidence/global_e2e_manifest.json` |
| G10 | Paused/recovered anomaly projector does not alter committed Domain facts. | proven: isolated MySQL `test_g10_failed_then_recovered_anomaly_projector_never_changes_committed_refund`; manifest `evidence/global_e2e_manifest.json` |
| G11 | Ordinary Finance Import review rows enter finance once and do not duplicate `IMPORT-006`. | proven: isolated MySQL `test_g11_ordinary_finance_review_projects_once_without_integrity_alert`; manifest `evidence/global_e2e_manifest.json` |
| G12 | Correction/post failure rolls back classification, ledger, allocation, receipt and alert resolution; retry is exact. | proven: isolated MySQL `test_g12_failed_correction_rolls_back_then_retries_exactly_once`; manifest `evidence/global_e2e_manifest.json` |
| G13 | Concurrent operations that change the same caregivers' schedules must acquire scheduling access in one fixed caregiver order. If the facts change first, the later operation must return a typed conflict; it must not deadlock or create duplicate same-caregiver, same-day occupancy. | proven: isolated MySQL `test_g13_leave_and_cancellation_serialize_shared_occupancy_write` executes real Leave/Substitution and Orders cancellation workflows concurrently. Exactly one Apply succeeds, the other returns a typed error, no thread remains blocked, one effective generation remains, and no duplicate same-caregiver, same-day occupancy exists. |
| G14 | Deposit reversal before/after service has distinct lifecycle result and invalidates stale actual-start reconfirmation. | proven: isolated MySQL reversal/reconciliation traces prove canonical reversal, exact replay, Client Finance obligation reopening, Orders reconfirmation control and no `client_payments` write. `test_g14_panel_uses_real_http_preview_and_apply` further proves the Order Finance Streamlit panel uses the typed API Preview/Apply flow to create that canonical reversal. |
| G15 | Cache is limited to non-authoritative read projections. Every formal Apply reads fresh locked facts without a cache dependency; a stale Preview returns a typed conflict. | proven: `test_g15_cache_boundary_contract` proves command workflows have no cache dependency and the only TTL cache is the read-only holiday projection. Isolated MySQL `test_auto_completion_first_rejects_the_real_stale_leave_apply_without_writes` proves stale Preview returns `stale_version` with zero writes. |
| G16 | Durable-job duplicate delivery, worker crash and notification loss cannot duplicate a command. | proven: isolated MySQL `test_g16_durable_worker_crash_recovery_and_duplicate_delivery_apply_once`; manifest `evidence/global_e2e_manifest.json` |
| G17 | UI shows pending, never false success, and uses the same idempotency identity after timeout. | proven: isolated MySQL `test_g17_panel_shows_pending_until_the_independent_worker_succeeds`; manifest `evidence/global_e2e_manifest.json` |

## 3. Build order

1. Complete Client Refund, Finance Import reprocess and durable-job data/workflow
   foundations first; G06, G07, G11, G12, G16 and G17 otherwise cannot be honest
   tests.
2. Add a Global E2E fixture which creates an isolated MySQL schema, starts only
   required canonical worker/projector components, and records the schema
   identity and cleanup receipt.
3. Implement G01–G05, G13–G15 as named scenarios.  Reuse existing
   Domain fixtures only where they expose real MySQL constraints and the same
   typed API/application boundary.
4. Add the Finance Import and durable-job scenarios after their respective
   implementation packages pass subsystem tests.
5. Produce `global_e2e_manifest.json` with scenario ID, test node id, isolated
   schema identity, source hashes and receipt/outbox assertions.  A scenario is
   `proven` only after that manifest and the corresponding test pass together.

## 4. Non-negotiable isolation

All 17 scenarios use disposable MySQL databases under the dedicated test
principal.  They must not run against `union_db`, a current operational
database, or a fixture that elides transaction/foreign-key behavior.

## 5. Authority boundary

This gap package authorizes no code, schema or data change.  The actual Global
E2E implementation should be split only after the dependency packages have
their data contracts approved, to avoid tests locking in temporary behavior.
