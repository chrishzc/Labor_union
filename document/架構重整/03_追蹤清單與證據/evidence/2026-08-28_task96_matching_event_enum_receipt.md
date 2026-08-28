# Task 96 Matching event enum alignment receipt

- bounded package: `PKG-HCAT-MATCHING-EVENT-ENUM`
- status: `completed`
- scope: Matching coordination command-to-released-event mapping only

## Result

- `ApplyInitialCriteriaSnapshot` now maps to released `criteria_snapshotted`.
- all eight supported Apply commands map explicitly to values in release 1003.
- Query, Preview and unknown commands fail closed with `MatchingCoordinationPersistenceError`;
  no unknown command falls back to `rematch_required`.
- reader, package lineage, receipt, outbox and source semantics were unchanged.

## Verification

| Gate | Result | Evidence |
|---|---|---|
| Parent regression | `passed` | `71 passed` |
| Fresh Luna/high | `passed` | P0=0, P1=0, P2=0; `changed_files=[]` |
| Released enum probe | `passed` | eight Apply mappings exact; unsupported commands fail closed |
| Compile/UTF-8/diff | `passed` | py_compile, strict UTF-8/header, `git diff --check` |

No DB, schema, port, provider or Git mutation was performed by the verifier.
