# Candidate Change Inventory — Phase 2D Anomalies Query

**Document Code**: `PROV-20260816-react-admin-phase2d-candidate-change-inventory`  
**Milestone**: Phase 2D Anomalies & Import Warning Real Query Integration  
**Integration Owner**: Project Orchestrator  
**Timestamp**: 2026-08-16T20:05:00+08:00

---

## 1. Candidate Write Set & Lane Allocation

| # | File Path | Lane | Type | Status |
|---|---|---|---|---|
| 1 | `tests/test_anomaly_registry_router.py` | Lane B | Backend Test | NEW |
| 2 | `tests/test_import_warning_tracking_api.py` | Lane B | Backend Test | MODIFIED (existing file) |
| 3 | `ui_react/src/api/anomalies/anomaly_query_schemas.ts` | Lane C | Frontend Schema | NEW |
| 4 | `ui_react/src/api/anomalies/anomaly_query_errors.ts` | Lane C | Frontend Error Taxonomy | NEW |
| 5 | `ui_react/src/api/anomalies/anomaly_query_client.ts` | Lane C | Frontend Query Client | NEW |
| 6 | `ui_react/src/adapters/anomalies/anomaly_query_adapter.ts` | Lane D | Frontend Data Adapter | NEW |
| 7 | `ui_react/src/pages/AnomaliesPage.tsx` | Lane E | Presentation Component | MODIFIED (Semantic Merge) |
| 8 | `ui_react/src/pages/AnomaliesPage.css` | Lane E | Presentation Stylesheet | MODIFIED (Preserved + Extended) |
| 9 | `ui_react/src/tests/fixtures/anomalies/anomaly_query_contract_fixtures.ts` | Lane C | Test Fixtures | NEW |
| 10 | `ui_react/src/tests/anomaly_query_client.test.ts` | Lane C | Client Contract Tests | NEW |
| 11 | `ui_react/src/tests/anomaly_query_adapter.test.ts` | Lane D | Adapter Unit Tests | NEW |
| 12 | `ui_react/src/tests/anomalies_page_real_data.test.tsx` | Lane E | Component Tests | NEW |
| 13 | `ui_react/src/tests/anomalies_no_fake_mutation.test.tsx` | Lane E | No-Mutation Safety Tests | NEW |
