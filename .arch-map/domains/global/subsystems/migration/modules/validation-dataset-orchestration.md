# Module: validation-dataset-orchestration

## Parent

- domain: `global`
- subsystem: `migration`

## Responsibility

在明確的 disposable validation schema 中，以各 owner 的現行 workflow 組合可重播 UI 驗收資料；只讀檢查 root、outbox 與 Finance Import manual-review 事實，不旁路 owner command 或復活已退役的 anomaly projection。

## Implementation

- primary:
  - `scripts/seed_ui_validation_dataset.py`
  - `scripts/seed_validation_dataset.py`
  - `scripts/seed_validation_beclass_review.py`
  - `scripts/seed_validation_finance_manual_review.py`
  - `scripts/verify_finance_manual_review_scenario.py`
  - `scripts/prepare_issue218_persisted_browser_fixture.py` — disposable Issue 218 browser fixture；只在指定的 `lu_test_*` schema 建立 line-agent 與合成訂單，並將一次性登入資料寫入 operator-supplied mode-600 file。
  - `subsystems/validation_dataset/inspection.py`
- config:
  - `validation/datasets/dataset_v1_foundation.json`
  - `validation/datasets/README.md`

## Dependencies

- outbound: `case-import` — foundation bootstrap 與 BeClass review root/outbox 由 Case Import workflow 產生。
- outbound: `finance-import` — unresolved bank row 經 canonical intake 形成 owner-managed `manual_review`。
- outbound: `orders` — contract-completion query 僅用於驗證刻意保留的 domain blockers。

## Verification

- layout_status: `custom_current`
- test_root: `tests/test_validation_dataset_scripts.py`
- test_root: `tests/test_verify_finance_manual_review_scenario.py`

## Provenance

- Validation dataset orchestration never bypasses owner commands — `source_observed` — current seed scripts and `infrastructure/mysql/beclass_import_review_writer.py`.
- Issue 218 fixture uses the guarded disposable bootstrap then only creates synthetic browser-acceptance roots — `source_observed` — `scripts/prepare_issue218_persisted_browser_fixture.py`.
- Finance Import manual review is an owning-domain work item, not a current anomaly projection — `source_observed` — `tests/domains/anomalies/subsystems/anomalies/modules/anomaly-registry/test_finance_anomaly_registry_contract.py`.

## Change triggers

Reconcile when disposable-database policy, seeded owner workflow, expected root/outbox readback, or focused validation test location changes.
