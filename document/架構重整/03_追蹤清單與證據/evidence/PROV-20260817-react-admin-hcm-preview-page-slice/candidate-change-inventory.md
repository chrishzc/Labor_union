# HCM Preview page-slice candidate change inventory

Execution date: `2026-08-17`

Base: `main@8615225481c8f72a9629289285516189b270cb36`

Candidate: shared dirty working tree; unrelated user／agent changes preserved.

## Fresh source disposition

The following production paths were fresh-read and left unchanged because the authorized Preview behavior was already present:

- `ui_react/src/pages/DataImportPage.tsx`
- `ui_react/src/pages/DataImportPage.css`
- `ui_react/src/api/case_import/hcm_workbook_schemas.ts`
- `ui_react/src/api/case_import/hcm_workbook_errors.ts`
- `ui_react/src/api/case_import/hcm_workbook_client.ts`
- `ui_react/src/adapters/case_import/hcm_workbook_adapter.ts`
- `api/routes/hcm_import.py`
- `api/schemas/hcm_import.py`
- `subsystems/case_import/hcm_workbook_import.py`

Observed behavior: immutable workbook bytes, `.xlsx`／non-empty／20 MiB constraints, local SHA-256, one allowlisted multipart Preview path, memory bearer, 30-second timeout, AbortSignal, strict aggregate decoder, source-digest equality, row-outcome conservation, generation guard, unavailable row detail, and native-disabled Apply／other five cards.

## Test-only changes made by this execution

| Path | Pre-edit SHA-256 | Final SHA-256 | Added evidence |
|---|---|---|---|
| `ui_react/src/tests/hcm_workbook_client.test.ts` | `85E3B1F3439730EE515C848D01337472EE58B9D6C54F094A1BF41CB4D3169BDD` | `4962EFC9F1FF3B4F75FA7D6569F57CEB2D575825AEFA0030F64CB5426B9CE124` | pre-aborted external signal → zero fetch + typed abort error |
| `ui_react/src/tests/data_import_hcm_preview_flow.test.tsx` | `5FFA121AC39261765E65BE3878ADF170EB269D5B58D69FA15CE62BE25BBECE66` | `46E5F3CD62130D3D5625690D18E5FF6032D09E65D48BC5E1E478E42271A19E08` | open/select zero request, explicit-click single request budget, Apply zero follow-up, close abort and stale-response discard |

Both test files were pre-existing untracked working-tree artifacts; this execution edited them in place and did not claim ownership of unrelated content.

## Evidence files

- `hcm-preview-page-slice-evidence-matrix.md`
- `candidate-change-inventory.md`
- `verification-receipt.md`
- `browser-smoke-receipt.md`
- `open-findings.md`

## Explicit zero-change inventory

- 0 backend production changes.
- 0 React production changes.
- 0 shared transport／runtime decoder／Auth／App／package／lock changes.
- 0 Apply／ingest／historical／resubmission enablement.
- 0 DB schema／seed／migration／repair／fixture／production-row changes.
- 0 README／main plan／shared index changes.
- 0 commit／stage／push／worktree／reset／clean／stash operations.
