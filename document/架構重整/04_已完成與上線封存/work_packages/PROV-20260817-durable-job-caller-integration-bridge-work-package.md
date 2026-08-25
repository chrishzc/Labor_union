---
doc_type: work-package
declared_status: completed
identity: PROV-20260817-durable-job-caller-integration-bridge
date: 2026-08-17
owner: Global Durable Jobs Integration Owner
domain: Global / Jobs
prerequisites: PROV-20260817-durable-job-core-persistence-worker-contract PASS; PROV-20260817-global-fastapi-typed-error-boundary PASS
activation_state: completed-local-validated-2026-08-22
authority: user-approved-in-spec-auto-activation-2026-08-22
approval_required: 核准此 exact Durable Job Caller Integration Bridge Work Package
evidence_directory: document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-durable-job-caller-integration-bridge/
required_receipts: candidate-change-inventory.md; contract-matrix-freeze-receipt.md; verification-receipt.md; open-findings.md
scenario_governance: Part_00_全域測試資料治理與Scenario契約.md
ui_execution_mode: not-applicable
base_branch: main
base_head: 0641ed62d20a85289c82aa5a272b73feff715f59
dirty_baseline: captured-2026-08-22-shared-dirty-preserved-no-production-writer
base_drift_rule: any relevant path drift requires fresh read and re-freeze before edits
---

# Durable Job caller integration bridge工作包

## Scope

在Core no-hidden-commit port完成後，提供六個bounded callers唯一可使用的application／dependency composition。
本包不切換任何caller、不提供public Jobs route、不改worker/repository/DB，也不把JobAccepted升格為Domain成功。

## Exact write set

- `subsystems/jobs/command_application.py`（new）
- `api/dependencies/jobs.py`（existing；只限Bridge composition）
- `tests/test_durable_job_command_application.py`（new）
- `tests/test_jobs_dependency.py`（new）
- 本工作包、`02/README.md`與evidence只由Integration Owner更新。

## Frozen contract

- application以明確outer UoW為唯一commit owner；Core repository port不得commit/rollback。
- command equality只使用Core frozen type/version/canonical payload/actor policy；correlation不影響business equality。
- same key/same fingerprint回同job identity；任一差異回typed idempotency conflict，不得吞成成功。
- dependency以`yield/finally`關閉connection；缺session/DB/storage error經Global typed boundary去敏。
- application只回accepted job identity與replayed flag；terminal outcome必須由後續masked Query取得。

## Acceptance

1. unit test證明commit一次、failure rollback一次、connection close一次；repository hidden commit為0。
2. same-key replay/mismatch、actor/type/version/payload差異與canonical JSON負向測試通過。
3. 任何外部provider、worker wakeup、Domain mutation、public route與DB schema change皆為0。
4. 六個caller尚未採用時本包只能標`bridge-ready`，不能標system adopted。

## DB gate

| Gate | Status | Evidence |
|---|---|---|
| Scope | PASS | 凍結範圍隨前置落地自動啟動；exact write set未擴張 |
| Change inventory | PASS | 0 schema/seed/backfill/destructive；只改transaction composition |
| Static release | NOT_RUN | 無DB release |
| Descriptor | NOT_RUN | 無DB object |
| Read-only plan | NOT_RUN | 不適用 |
| Engine verification | PASS | 六caller代表性`lu_test_*` enqueue／claim／worker／terminal matrix通過並cleanup |
| Developer acceptance | NOT_RUN | 不操作既有資料庫 |

結論：`DB_CHANGE_NOT_READY`。

## Re-freeze record（2026-08-22）

- Base固定為`main@0641ed62d20a85289c82aa5a272b73feff715f59`；保留所有既有dirty／untracked成果。
- Core verification為`completed-local-validated`；Phase4只提供`PHASE4_SCENARIO_LINEAGE_METADATA_READY`，未升格runtime PASS。
- `subsystems/jobs/command_application.py`與兩份focused tests尚未建立；本次只重凍結governance，不啟動production writer。
- exact write set、outer UoW、no-hidden-commit與六caller後置邊界不變；任何相關base drift須再次fresh-read。
