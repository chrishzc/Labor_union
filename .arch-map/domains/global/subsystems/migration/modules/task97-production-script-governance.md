# Module: task97-production-script-governance

## Parent
- domain: `global`
- subsystem: `migration`

## Responsibility
產生可重播的 Task 97 production-script 與 production-writer inventory，保留 exact script／commit identity、caller／guard evidence 與既有分類；不執行 production effect。Writer call identity 使用跨受支援 Python 版本穩定的 canonical AST fingerprint。

## Implementation
- `scripts/generate_task97_production_script_inventory.py`
- `scripts/generate_task97_commit_dispositions.py`
- `shared_kernel/writer_inventory.py`

## Verification
- test_root: `tests/domains/global/subsystems/migration/modules/task97-production-script-governance/`

## Provenance
- Task 97 production-script inventory ownership — `architecture_declared` — current Task 97 governance package and generator source.
