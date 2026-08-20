# Phase 4A-P verification receipt

驗證時間：2026-08-16；candidate：current shared working tree。

| Check | Command | Result |
|---|---|---|
| Focused frontend | `npm test -- hcm_workbook_client ... data_import_no_fake_mutation` | PASS：4 files／14 tests |
| Full frontend | `npm test -- --reporter=dot` | PASS：39 files／496 tests；有既有 warnings／network stderr，見open findings |
| Build | `npm run build` | PASS：90 modules；既有 >500kB chunk advisory |
| Lint | `npm run lint` | PASS exit 0；`MasterLayout.tsx` 2個既有 Fast Refresh warnings |
| Focused backend | `.venv\Scripts\python.exe -m pytest ... test_hcm_import_* ...` | PASS：22 tests |
| UTF-8 | strict decoder on 11 source/test files | PASS：11/11 |
| Forbidden scan | `rg` fake/mock/storage/skip/permissive-Zod/Apply paths | PASS：0 matches |
| Whitespace | `git diff --check` | PASS；僅既有 line-ending advisories |

## Claim-specific proof

- Client 只暴露 Preview；沒有 Apply／ingest／historical／resubmission method。
- Multipart field 精確為 `workbook`；fresh memory bearer、30秒 timeout、AbortSignal及server/local digest相等由
  `hcm_workbook_client.test.ts` 驗證。
- Strict envelope/data negative cases與aggregate conservation由client/adapter tests驗證。
- 頁面真File→Preview→DOM aggregate及同名不同bytes清舊preview由flow tests驗證。
- 11個card-level未開放controls與Drawer Apply原生disabled，alert/confirm為0。

本 receipt 不證明 HCM Apply、warning disposition、receipt observation、entry cutover或真browser upload。
