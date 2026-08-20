# Phase 4A-P open findings

| ID | Severity | Finding | Disposition |
|---|---|---|---|
| 4A-H-01 | P0 | HCM workbook claim、rows、receipt為多重commit，outer UoW未裁決 | Phase 4A-H gap；Apply locked |
| 4A-H-02 | P0 | warning disposition／repair gate未閉合 | Phase 3D／4A-H successor；Apply locked |
| 4A-H-03 | P0 | 無authenticated receipt lookup/observation contract | Phase 4A-H successor；Apply locked |
| 4A-H-04 | P1 | HCM errors仍是bounded `detail.code`，非Global typed envelope | Client去敏fail closed；後端另案 |
| 4A-H-05 | P1 | 無逐列typed Preview | 原表格槽位明確unavailable，不生成假rows |
| 4A-H-06 | P1 | duplicate IP＋name live warning可能違反人工確認政策 | 後端另案，React不推導 |
| REG-01 | P1 | full Vitest中既有Orders test嘗試localhost:3000並輸出ECONNREFUSED，但suite仍pass | 非本波write set；後續全前端test isolation修復 |
| REG-02 | P2 | route guard tests有既有React `act(...)` warnings | 非本波write set；後續test hygiene修復 |
| PERF-01 | P2 | Vite bundle >500kB advisory | 不阻擋Preview；後續chunk治理 |

沒有把任何 finding 寫成 PASS、豁免或 HCM completion。
