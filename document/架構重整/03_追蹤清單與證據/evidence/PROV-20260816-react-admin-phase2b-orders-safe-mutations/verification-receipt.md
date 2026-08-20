# Phase 2B 最新正式工作區驗證回執

日期：2026-08-16；HEAD：`8615225481c8f72a9629289285516189b270cb36`。

## 修復後不變量

- Reopen 使用 live 中文 lifecycle enum；Preview 驗三版本，Receipt 只驗 live schema 的 order version。
- Service-date receipt 不虛增 order/scheduling version。
- receipt 指紋不符時保留 receipt 並進 `observation_failed`，不誤稱 Domain mutation 失敗。
- 新 business attempt 產生新 idempotency key；只有 `outcome_unknown` 重放沿用同 key/payload。
- receipt/requery/observed/error DOM 互斥；Apply pending/unknown 時無二次 Apply，Drawer 不可關閉。
- Reopen observation 重新查詢 summary 與 selected detail。
- 既有媒合、取消與其他 mutation 維持原生 disabled；無 fake success。

| Gate | 狀態 | Fresh evidence |
|---|---|---|
| G2/G3/G4 frontend flow | PASS | Phase 2A/2B combined focused：7 files / 51 tests |
| Full frontend | PASS | 16 files / 195 tests |
| Lint | PASS | 0 diagnostics |
| Build | PASS | 75 modules；exit 0 |
| Backend Auth + Phase 2B | PASS | 6 exact test files：51 passed in 13.29s |
| Strict fake/storage scan | PASS | Orders production paths 0 matches |
| Global diff check | BLOCKED | 非本波 `DataImportPage.tsx` 既有三處 trailing whitespace |
| G6 Runtime | BLOCKED | 真登入頁已開；尚無人工 TOTP 與獲准可寫 Orders test cases |

結論：G1–G5 的 code/test candidate 已收斂；G6 固定為
`BLOCKED_AUTH_TEST_CREDENTIAL`、`BLOCKED_REAL_BROWSER_EVIDENCE`，兩條 Apply 另受
`BLOCKED_TEST_DATA` 約束。不得宣稱 Phase 2B completed 或 Victory Confirmed。
