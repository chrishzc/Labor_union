# Module: entrypoint-and-test-suite-governance

## Parent
- domain: `global`
- subsystem: `test-governance`

## Responsibility
從 current source discovery 建立 exact entrypoint queue，保存 owner、operator、caller
evidence 與 terminal disposition，並由 CI 執行 read-only pytest suite audit。新增
entrypoint 必須在既有 canonical mapping owner 完整分類後才可更新 tracked evidence。

## Implementation
- primary: `scripts/generate_entrypoint_review_queue.py`
- generators:
  - `scripts/generate_task97_entry_governance.py`
  - `scripts/generate_task97_production_script_inventory.py`
- audit: `scripts/audit_test_suite.py`
- workflow: `.github/workflows/python-app.yml`
- evidence:
  - `document/架構重整/03_追蹤清單與證據/evidence/entrypoint_review_queue_v1.jsonl`
  - `document/架構重整/03_追蹤清單與證據/evidence/task97_entry_governance_v1.json`
  - `document/架構重整/03_追蹤清單與證據/evidence/task97_production_script_inventory_v1.json`

## Verification
- test_root: `tests/domains/global/subsystems/test-governance/modules/entrypoint-and-test-suite-governance/contract/`

## Change triggers
Reconcile when executable discovery、owner/caller mapping、terminal disposition、tracked
evidence schema、suite audit entrypoint 或 CI caller changes。
