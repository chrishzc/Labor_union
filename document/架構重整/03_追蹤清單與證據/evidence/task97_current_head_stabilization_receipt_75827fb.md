---
artifact_role: validation_receipt
owner: architecture-governance / integration-writer
consumer: Task 97 current register / bounded finishing-lane operators
source_of_truth: hash-bound validation evidence; not architecture Authority
close_condition: superseded by a later exact-head stabilization receipt after material source, workflow, or artifact change
retention: bounded_retain
invalidation: validated HEAD, CI workflow, canonical roots, artifact generators, or acceptance gates materially change
replacement_or_absorption: task97_repository_local_closeout_receipt_a48caa8.md
date: 2026-08-30
validated_branch: main
validated_head: 75827fbcc139e87d16a3f753c4478fc9e82910f1
---

# Task 97 current-head stabilization receipt

> Historical stabilization evidence only. Task 97 current terminal result is owned by
> `task97_repository_local_closeout_receipt_a48caa8.md`; the production and DB statements below remain
> historical provenance and must not be reused as the current completion gate.

## 1. Bound identity and conclusion

- branch：`main`
- validated HEAD：`75827fbcc139e87d16a3f753c4478fc9e82910f1`
- 97B formal baseline：`5dfa3b9f9224c544182b5b84f9485dc4d9934968`
- bounded execution start：`42ea17e3a221655a189808a748a3655a4e025beb`
- GitHub Actions run：[33298062001](https://github.com/chrishzc/Labor_union/actions/runs/33298062001)
- stabilization：`TASK97_STABILIZATION_CONFIRMED`
- overall architecture：`ARCHITECTURE_COMPLIANCE_NOT_CONFIRMED`

本 receipt 只關閉 97B current-head stabilization。它不授權 writer exits、entry／script retirement、DB engine、Access T3、external provider、deployment、runtime cutover、destructive cleanup 或 WP8 terminal acceptance。

## 2. Bounded changed paths

本 package 相對 execution start `42ea17e...` 只變更下列 19 paths：

- CI／API／runtime：`.github/workflows/python-app.yml`、`api/routes/anomaly_registry.py`、`infrastructure/mysql/anomaly_runtime.py`
- bounded runners：`scripts/run_contract_signing_normal_chain.py`、`scripts/run_task96_hob_route_a.py`
- artifact generators：`scripts/generate_task97_commit_dispositions.py`、`scripts/reconcile_writer_inventory_v3_dispositions.py`
- focused tests：`tests/test_finance_import_disposable_mysql_e2e.py`、`tests/test_wp77_disposable_mysql_e2e.py`、`tests/test_global_typed_error_boundary.py`、`tests/test_task97_anomaly_current_query.py`、`tests/test_task97_commit_dispositions.py`、`tests/test_writer_inventory_v3_dispositions.py`
- regenerated evidence：`task97_production_script_inventory_v1.json`、`task97_repository_commit_dispositions_v1.json` 與 `writer_inventory_v3` candidate／disposition 的四個 tracked artifacts

沒有新增 schema part、migration release、descriptor、fresh assembly scope、Domain owner、compatibility layer、production effect 或 physical deletion。

## 3. GitHub CI result

GitHub Actions run `33298062001` 對 validated HEAD 的 workflow conclusion 為 `success`：

- build：`PASS`；fatal Flake8 與 warning-only Flake8 均完成。
- Agent governance：`PASS`；validator step 實際執行且成功，不再因前置 lint 結果被 skipped。
- cross-domain workflow boundaries：`PASS`。
- 12-owner canonical matrix：全部 `PASS`。

12-owner 本機同 HEAD exact results：

| Owner | Result |
|---|---:|
| orders | 346 passed |
| scheduling | 225 passed, 1 skipped |
| client-finance | 84 passed |
| staff-payables | 66 passed |
| anomalies | 149 passed |
| payroll | 21 passed |
| finance-import | 116 passed |
| government-subsidy | 44 passed |
| case-import | 18 passed |
| access | 17 passed, 1 skipped |
| line | 520 passed |
| contract-signing | 190 passed |

cross-domain 本機同 HEAD result：`18 passed`。

## 4. Local acceptance

- fatal Flake8 `E9,F63,F7,F82`：`PASS`，finding count `0`。
- Agent governance：`PASS`，輸出 `agent_governance: PASS`。
- full Python collection：`4924 tests collected`。
- non-engine Python full suite：`4768 passed, 141 skipped, 3 xfailed`。
- artifact focused regression：`20 passed`。
- React：`183` test files、`1219 passed`；build `PASS`；lint `PASS`，保留 7 個非 fatal current warnings。
- `git diff --check`：`PASS`；validated HEAD 工作樹 clean。

non-engine suite 明確排除三個需要 disposable MySQL engine 的檔案：`test_background_job_repository_mysql.py`、`test_durable_job_disposable_mysql_e2e.py`、`test_durable_job_payload_equality_disposable_mysql_e2e.py`。其餘 skip 不被提升為 engine acceptance。

## 5. Regenerated artifacts

| Artifact | Exact result | SHA-256 |
|---|---|---|
| entrypoint review queue | 683 entries；514 active、75 operator-only、61 retired-410、33 review-required | `9a73e3554d12b233299ba053aaff519e0125ea94efd94fb9d612943d62340783` |
| Task 97 entry governance | 683 records；31 blocked-external、2 rewrite-to-canonical；0 generic placeholders | `0ab70876d939fd2e60ea5373fcb36eb8969ab054caea12d4d05b1b0645020533` |
| production-script inventory | 86 entries；37 keep、38 test-only、2 rewrite、6 delete、3 blocked-caller | `fdffb994887fa7684d28a2270149bc2696f9916f9e8968cc5f14c445796f2510` |
| repository commit dispositions | 308 identities；terminal status `passed` | `c6127c5bdcce29d72e1aa7960f5d53f79888e2d457772af3495475e47f09fd5a` |
| writer candidate findings | 1320 identities；0 unresolved | `82424f7d1f6e55c3ab1d4f2e775031e81f19d446563f0270c4689bb852413221` |
| writer disposition records | 1320 records；1085 retain-canonical、232 retain-restricted、3 migrate-then-remove、0 needs-decision | `0e030057eca6c73825f04f8b2e0580f529d47038de63ffdba2c41d708f607a80` |

repository commit dispositions 的 exact scanner-input revision 為 `44f3349bf476c3e7e0f57d4c7c7eaf05c8da7dc6`，scan fingerprint 為 `c610c2ce6e06c575fac3857100f2c939c75fb17a07449bcc34024df75f2eb9ca`。evidence-only commit 不改 scanner inputs；generator 現在 fail closed 於 dirty scanner inputs，且 artifact commit 後仍保持 idempotent。

## 6. DB engine and remaining blockers

DB engine status：`BLOCKED_ENGINE_EVIDENCE`。驗收環境沒有 `LABOR_UNION_TEST_MYSQL_*` credentials 或 `MYSQL_TEST_CONTAINER`，因此沒有執行或猜測任何 engine target；未連接 `union_db`、production，也未執行 DDL、backfill、reset、switch 或 destructive cleanup。

Stabilization 關閉後仍存在的 Task 97 finishing blockers：

- writer disposition 的 3 個既有 `migrate_then_remove` exits；本 package 未執行。
- entry queue 的 31 個 `blocked_external_evidence` 與 2 個 `rewrite_to_canonical`。
- production-script inventory 的 2 個 rewrite、6 個 delete 與 3 個 caller-evidence blockers。
- schema 1015～1018 的 disposable fresh／preserve engine evidence。
- Access T3 sink、external/runtime/deployment/cutover gates與 WP8 terminal acceptance。

```text
TASK97_STABILIZATION_CONFIRMED
ARCHITECTURE_COMPLIANCE_NOT_CONFIRMED
```
