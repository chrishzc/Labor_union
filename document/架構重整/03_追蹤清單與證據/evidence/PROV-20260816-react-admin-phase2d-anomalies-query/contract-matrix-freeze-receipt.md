# Contract Matrix Freeze Receipt — Phase 2D Anomalies Query

**Document Code**: `PROV-20260816-react-admin-phase2d-contract-matrix-freeze-receipt`  
**Milestone**: Phase 2D Anomalies & Import Warning Real Query Integration  
**Integration Owner**: Project Orchestrator  
**Timestamp**: 2026-08-16T19:32:00+08:00  
**Status**: **INVALIDATED**

---

## 1. Freeze Statement
The Contract Field Matrix (`contract-field-matrix.md`) for Phase 2D has been audited against:
- `api/routes/anomaly_registry.py` & `api/schemas/anomaly_registry.py`
- `api/routes/import_warning_tracking.py` & `api/schemas/import_warning_tracking.py`
- `PROV-20260816-react-admin-phase2d-anomalies-query-specification.md`
- `PROV-20260816-react-admin-phase2d-anomalies-query-work-package.md`

## 1.1 Fresh audit invalidation

真實 Chrome 驗證證明 Anomalies payload 的 `severity` 可為空字串；而 Pydantic 將 `severity`、
`workflow_status`、`tracking_status` 宣告為一般 `str`，不是本 receipt 原先假設的封閉 enum。
因此本 freeze receipt 已失效。須由另案 backend public-contract hardening 完成後，重新產生矩陣與
freeze receipt；不得重用本 receipt 宣稱 G1 PASS。

## 2. Invariants Locked
1. Endpoints restricted strictly to `GET /api/v1/anomalies?include_snapshot=false` and `GET /api/v1/import-warning-tracking/tasks`.
2. Zero mutations allowed.
3. Unprovided attributes mapped strictly to `後端尚未提供 typed 顯示摘要` / `後端 typed detail/recovery contract 尚未開放`.
4. Lane write sets frozen and isolated.
