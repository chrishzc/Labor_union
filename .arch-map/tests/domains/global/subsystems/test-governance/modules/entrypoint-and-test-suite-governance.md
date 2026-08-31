module: entrypoint-and-test-suite-governance
parent_subsystem: test-governance
architecture: ../../../../../../../domains/global/subsystems/test-governance/modules/entrypoint-and-test-suite-governance.md
layout_status: custom_current
test_root: tests/domains/global/subsystems/test-governance/modules/entrypoint-and-test-suite-governance/contract/

# Owned verification
- `test_entrypoint_review_queue.py` — current discovery、exact mapping 與 terminal disposition queue。
- `test_task97_commit_dispositions.py` — input-bound source revision、stable commit identity 與 exact semantic disposition。
- `test_task97_entry_governance_artifact.py` — tracked entry-governance evidence fresh-clone reproducibility。
- `test_task97_production_script_governance.py` — executable script inventory、classification 與 source digest freshness。
