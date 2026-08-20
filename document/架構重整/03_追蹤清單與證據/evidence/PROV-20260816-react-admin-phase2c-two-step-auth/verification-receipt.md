# Phase 2C 最新正式工作區驗證回執

日期：2026-08-16；HEAD：`8615225481c8f72a9629289285516189b270cb36`。

使用者已明確回覆「採用」。production flow 為 password challenge → TOTP verify → volatile memory
Bearer Session；未使用 combined login、dev token、localStorage、sessionStorage、cookie 或 URL。

| Gate | 狀態 | Fresh evidence |
|---|---|---|
| G0 Authority/scope | PASS | specification approved；Work Package approval evidence=`採用` |
| G1 Auth contract | PASS | Pydantic↔Zod strict alignment；UTC offset transport regression added |
| G2 Auth client | PASS | challenge/verify 分離；Session 僅 verify 後建立 |
| G3 Login presentation | PASS | StrictMode mounted guard；Stage 1/2 真接線；無 fake alert |
| G4 Automated integration | PASS WITH WARNINGS | `npm test -- --reporter=dot`：16 files / 196 tests；既有 React `act(...)` warnings 未隱藏 |
| G5 Static/backend | PASS | lint 0 diagnostics；build 75 modules；Auth focused pytest 27 passed |
| G6 Runtime browser | PASS | 真 Chrome；challenge 200、verify 200、Orders summary 200、Shell 顯示在線與 50 筆案件 |
| G7 Evidence | PASS | Browser receipt、verification receipt、open findings 與 index 已同步 |

已知非阻擋事項：production build 仍有單一 bundle >500 kB warning；部分既有 component tests 有
React `act(...)` warnings；`git diff --check` 仍被未授權且既存的 `DataImportPage.tsx` trailing whitespace
阻擋。本工作未掩蓋或越界修改該檔。

結論：Phase 2C 帳密 Challenge → TOTP → memory Session 已完成本機真瀏覽器驗收。
