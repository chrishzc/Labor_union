# Task 96 HCAT Scheduling owner adapter receipt

- bounded package: `PKG-HCAT-ADAPTER-scheduling`
- status: `completed`
- excluded: six-owner composition, real MySQL, projector, API, React and Browser

## Result

- confirmed service dates bind the current version and exact `orders.service_days` collection.
- effective generation binds aggregate, generation and rebuild event/version lineage.
- assignment official dates require one valid assignment owner per effective work day.
- official service becomes terminal only after all official end moments under Asia/Taipei BusinessClock.
- malformed/unhashable rows, missing or invalid staff IDs, cross-case/stale/count drift return typed unavailable.
- query and locked reads use the caller-owned connection without commit/rollback/close.

## Verification

| Gate | Result | Evidence |
|---|---|---|
| Parent regression | `passed` | `85 passed` |
| Fresh Luna/high | `passed` | cross-focused `170 passed`; P0=0, P1=0, P2=0; `changed_files=[]` |
| Adversarial | `passed` | malformed fields, staff IDs, EI/SV, date counts, clock, lock/no-commit |
| Compile/UTF-8/diff | `passed` | py_compile, strict UTF-8, `git diff --check` |
| Real MySQL | `NOT_RUN` | reserved for the six-owner integration gate |

No DB, port, provider or Git mutation was performed by the verifier.
