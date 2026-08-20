# Orders Query Page-Slice Verification Receipt

Candidate：2026-08-17 final local state；browser 尚未執行。

| Claim | Command／source | Result | Scope／limit |
|---|---|---|---|
| Focused query/page/adversarial | `npx vitest run` 七個 Orders focused files | PASS：7 files / 78 tests | strict schemas、8 GET、fresh token、StrictMode burst TTL、failure retry、request budget、stale discard、unavailable |
| Phase 2B preservation | `npx vitest run` service dates/reopen/mutation 五檔 | PASS：5 files / 63 tests | 沒有修改 mutation source；證明既有流程回歸全綠 |
| Full React regression | `npm test -- --reporter=dot` | PASS：49 files / 506 tests | stderr 有既有 Route Guard `act(...)` warnings；無 test failure |
| Production build | `npm run build` | PASS：101 modules | 250 ms pending/resolved burst dedupe final source；Vite 有 >500 kB bundle advisory |
| Lint | `npm run lint` | PASS（exit 0） | 2 個既有 `MasterLayout.tsx` fast-refresh warnings，非 write set |
| Allowlist scan | `rg` client exported functions與 endpoint literals | PASS | 8 domain GET functions；factory 不計 endpoint |
| Strict-schema scan | `rg` `.default/.catch/.passthrough/z.any/z.unknown/z.record` | PASS：0 matches | 只掃 Orders query schemas/client/errors |
| No-derivation scan | `rg` Date arithmetic／refund／recommendation generators | PASS | `refundAmount` 僅為 null + unavailable view slot，沒有計算 |
| Mock/storage/fake mutation scan | `rg` mockData/localStorage/sessionStorage/cookie/alert/confirm/innerHTML | PASS：0 matches | production Orders slice |
| Secret scan | 去敏 secret/token/password regex | PASS：0 matches | exact source/tests |

候選在任何後續 relevant edit 後，上述 evidence 必須視為 stale 並重跑。真 Chrome 已曾觀察到 StrictMode duplicate 304；修正後尚待 browser recheck，因此 Orders lane 最高狀態仍為 `implemented-awaiting-browser-evidence`。
