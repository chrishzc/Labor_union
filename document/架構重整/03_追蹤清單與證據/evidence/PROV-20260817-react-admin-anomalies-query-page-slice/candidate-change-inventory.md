# Anomalies Query Page-Slice Candidate Inventory

Status: `candidate-frozen-local`; no commit or browser run.
Work Package: `PROV-20260817-react-admin-anomalies-query-page-slice`

## Candidate write set

| Area | Paths |
|---|---|
| Client/schema | `ui_react/src/api/anomalies/anomaly_query_client.ts`; `ui_react/src/api/anomalies/anomaly_query_schemas.ts` |
| Adapter/page | `ui_react/src/adapters/anomalies/anomaly_query_adapter.ts`; `ui_react/src/pages/AnomaliesPage.tsx` |
| Tests/fixtures | `ui_react/src/tests/anomaly_query_client.test.ts`; `ui_react/src/tests/anomaly_query_adapter.test.ts`; `ui_react/src/tests/anomalies_page_real_data.test.tsx`; `ui_react/src/tests/anomalies_no_fake_mutation.test.tsx`; `ui_react/src/tests/anomalies_detail_referral_flow.test.tsx`; `ui_react/src/tests/fixtures/anomalies/anomaly_query_contract_fixtures.ts` |
| Evidence | this directory |

`AnomaliesPage.css` was inspected and not changed because the existing layout styles cover the new inline Drawer
slots. No backend, shared transport/runtime decoder, Auth, README, main plan, package manifest, DB or Streamlit path
was modified.

## Scope audit

- New production calls: only `GET /api/v1/anomalies/{fingerprint}` and the warning referral GET.
- Existing list/tasks calls remain unchanged and remain GET-only.
- New controls: `anomalies.warning.drawer_open` (presentation) and `anomalies.warning.transition` (native disabled).
- Existing `anomalies.card.claim`, `anomalies.drawer.resolve-reason`, and `anomalies.drawer.resolve` remain native disabled.
