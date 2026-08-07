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

The current completion matrix identifies four business scenarios only in
summary form (cancellation settlement, completed-service payroll retention,
government subsidy allocation, and ambiguous batch → human review).  Their
test-to-scenario mapping is not yet a stable Global acceptance manifest, so
they remain `candidate-existing-coverage`, not counted as completed here.

## 2. Required scenario manifest

| ID | Required Global invariant | Current evidence disposition |
|---|---|---|
| G01 | Terms change rebuilds Scheduling, Client Finance, Payroll, lifecycle and anomaly consistently. | partial: isolated MySQL `test_terms_workflow_recovery_applies_one_canonical_cross_domain_change` proves a safe same-day-count change with one UoW, version advances, source outboxes and exact replay. Service-day-count changes fail closed without an approved assignment reallocation plan; Anomalies projection and typed API/Streamlit trace remain required. |
| G02 | Actual Start correction is all-chain atomic. | partial: isolated MySQL `test_g02_actual_start_correction_updates_each_domain_once` proves complete service-time gating, atomic Orders/Scheduling/Client Finance/Payroll/Lifecycle persistence, source outboxes and exact replay. Typed API and Streamlit loading trace remain required. |
| G03 | Mid-service multi-staff cancellation preserves independent client-refund and staff-payable settlement tracks. | partial: real MySQL `test_g03_mid_service_multi_caregiver_cancellation_updates_each_domain_once` proves one UoW, replay, version/outbox boundaries, closing prior unpaid staff obligations and creating independent client refund/staff payable obligations. The prior “both sides to zero” wording was invalid because it would wrongly auto-net separate cash flows. |
| G04 | Cancellation after complete service leaves full staff payroll unchanged and performs zero invalid writes. | proven: isolated MySQL `test_g04_full_service_cancellation_is_blocked_without_writes` uses a completed order with two established service-pay obligations and proves the blocker, no writes, and unchanged payroll projection. |
| G05 | Leave/substitution competes safely with completion time. | missing traceable Global E2E |
| G06 | Service-data lock is not removed by refund/reversal. | proven: isolated MySQL `test_g06_refund_and_reversal_preserve_the_immutable_service_data_lock`; manifest `evidence/global_e2e_manifest.json` |
| G07 | API timeout retry replays exactly one full cross-domain command. | proven: isolated MySQL `test_g07_timeout_retry_enqueues_and_applies_one_cross_domain_command`; manifest `evidence/global_e2e_manifest.json` |
| G08 | Injected failure at every cross-domain persistence point leaves no partial commit. | proven: isolated MySQL `test_g08_each_finance_correction_persistence_failure_rolls_back`; manifest `evidence/global_e2e_manifest.json` |
| G09 | Streamlit and direct typed API obtain the same result without UI business fallback. | proven: isolated MySQL `test_g09_ui_client_and_direct_typed_preview_have_the_same_result`; manifest `evidence/global_e2e_manifest.json` |
| G10 | Paused/recovered anomaly projector does not alter committed Domain facts. | proven: isolated MySQL `test_g10_failed_then_recovered_anomaly_projector_never_changes_committed_refund`; manifest `evidence/global_e2e_manifest.json` |
| G11 | Ordinary Finance Import review rows enter finance once and do not duplicate `IMPORT-006`. | proven: isolated MySQL `test_g11_ordinary_finance_review_projects_once_without_integrity_alert`; manifest `evidence/global_e2e_manifest.json` |
| G12 | Correction/post failure rolls back classification, ledger, allocation, receipt and alert resolution; retry is exact. | proven: isolated MySQL `test_g12_failed_correction_rolls_back_then_retries_exactly_once`; manifest `evidence/global_e2e_manifest.json` |
| G13 | Reversed staff-set ordering obeys canonical mutex order or returns a typed conflict without deadlock/duplicate occupancy. | partial: isolated MySQL `test_g13_reverse_staff_sets_lock_in_one_canonical_order_without_deadlock` proves two reverse-order transactions serialize through the canonical ascending mutex with no deadlock and no mutex-side data writes. The competing leave/substitution-plus-completion occupancy-write trace remains required. |
| G14 | Deposit reversal before/after service has distinct lifecycle result and invalidates stale actual-start reconfirmation. | partial: isolated MySQL reversal E2E proves canonical reversal, exact replay, Client Finance obligation reopening, canonical projection change, Orders intent and service-preserving post-service anomaly. A second isolated MySQL E2E proves immutable Finance Import classification → real Client Receipt reconciliation workflow → Client Finance outbox → active Orders reconfirmation control, without a `client_payments` write. API/UI flow remains required. |
| G15 | Cache hit, miss and unavailable produce identical Apply result; stale Preview conflicts. | missing traceable Global E2E |
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
