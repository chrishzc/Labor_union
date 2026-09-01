# Module: task97-production-script-governance

## Parent
- domain: `global`
- subsystem: `migration`

## Responsibility
產生可重播的 Task 97 production-script inventory，保留 exact script identity、caller／guard evidence 與既有分類；不執行 production effect。

## Implementation
- `scripts/generate_task97_production_script_inventory.py`

## Verification
- test_root: `tests/domains/global/subsystems/migration/modules/task97-production-script-governance/`

## Provenance
- Task 97 production-script inventory ownership — `architecture_declared` — current Task 97 governance package and generator source.
