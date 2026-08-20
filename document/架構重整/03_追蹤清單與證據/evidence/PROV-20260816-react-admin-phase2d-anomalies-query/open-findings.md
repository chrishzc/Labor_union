# Open Findings — Phase 2D Anomalies Query

**Status**: `OPEN_BLOCKERS`  
**Timestamp**: 2026-08-16 fresh independent audit

| ID | Severity | Finding | Required disposition |
|---|---|---|---|
| P2D-01 | resolved-in-candidate | `severity` backend public contract gap | Phase 2D-H以registry enrichment與Pydantic enum修正；待真Chrome200→DOM驗收 |
| P2D-02 | resolved-in-candidate | workflow與Import Warning status原為一般`str` | Phase 2D-H已收斂封閉enum與OpenAPI負向測試；待runtime驗收 |
| P2D-03 | P1 | 全前端 suite 12 failures／3 files | 由 owning Orders 工作包修復；Phase 2D 不得越界修改 |
| P2D-04 | P2 | lint 有 2 個既有 MasterLayout warnings | 由 Foundation/Shell owner 收斂，不得宣稱 0 warnings |
| P2D-05 | expected gap | display snapshot、typed detail／timeline／recovery 尚未開放 | 維持 unavailable；不解析 raw dict |
| P2D-06 | resolved-runtime | 真Chrome初次audit命中舊API程序 | 重啟正確`.venv` FastAPI後兩GET family已進DOM；Shell離線badge另案 |
| P2D-07 | P1 | disposable MySQL E2E因未配置隔離`lu_test_*`而skip | 只在明確隔離資料庫重跑，禁止操作既有`union_db` |

Claim、Resolve、Import Warning transition 與 Repair mutation 仍為 out of scope，控制項保持 native disabled。
