# Anomalies Query Page-Slice Evidence Matrix（草案）

Status: `DRAFT`／未核准、未 freeze、不可作為完成證據。 
Owner: Anomalies React Page Integration Owner  
Work Package: `PROV-20260817-react-admin-anomalies-query-page-slice`  
Baseline: `main@8615225481c8f72a9629289285516189b270cb36`  
Authority: [page-slice execution decision](../../../../02_決策與退役執行記錄/PROV-20260817-react-admin-page-slice-migration-execution-decision.md)

## 1. Endpoint and response matrix

| Surface ID | Method / endpoint | Success contract source | Required fields / enum | UI disposition | Evidence to collect |
|---|---|---|---|---|---|
| `anomalies.list` | `GET /api/v1/anomalies?include_snapshot=false` | `api/routes/anomaly_registry.py::query_anomalies`; `AnomalySummaryView` | fingerprint, definition_code, source_domain, source_identity, source_version, severity=`warning|blocking`, predicate_active, workflow_status=`open|claimed|resolved`, workflow_version; snapshot null/unavailable | wired list/KPI/filter/card | Network request + response + DOM |
| `anomalies.detail` | `GET /api/v1/anomalies/{fingerprint}` | `query_anomaly_detail`; `AnomalyDetailView` | typed summary scalars; detail raw/unclosed fields never rendered | lazy Drawer detail; unclosed slots unavailable | lazy Network + selected Drawer DOM |
| `anomalies.warning-list` | `GET /api/v1/import-warning-tracking/tasks` | `query_tasks`; `ImportWarningTaskView` | occurrence_identity, owning_lane, logical_code, field_path, masked_subject, issue_codes, tracking_status six-value enum, tracking_version>=1, display_message, nullable evidence/navigation | wired field-level warning cards | Network + DOM |
| `anomalies.warning-referral` | `GET /api/v1/import-warning-tracking/tasks/{occurrence_identity}/referral?expected_version=N` | `query_referral`; `WarningReferralView` | occurrence_identity, expected_version>=1, owning_lane=`hcm`, logical_code, field_path, masked_subject, display_message, navigation=`hcm_import_center`, action_kind allowlist, nullable target_command | lazy warning Drawer referral; no transition | Network + DOM |

## 2. UI slot matrix

| Stable ID / slot | Server path | Disposition | Negative / safety assertion |
|---|---|---|---|
| `anomalies.kpis` | list severity/workflow status | loaded-scope KPI | no global total inference |
| `anomalies.category-filters` | list source_domain | local filter | 0 GET on filter |
| `anomalies.status-filters` | list workflow_status | local filter | generic status not warning tracking |
| `anomalies.card.<fingerprint>` | list fingerprint/definition/severity/status | server identity | no hardcoded case facts |
| `anomalies.card.drawer_open` | selected fingerprint | lazy detail/referral | one GET per identity/generation |
| `anomalies.drawer.detail` | detail.summary typed scalars | wired where closed | missing/wrong/extra fails closed |
| `anomalies.drawer.timeline` | detail.timeline | unavailable unless closed typed view | raw dict never enters renderer |
| `anomalies.drawer.evidence` | detail display/root evidence | unavailable unless closed typed view | no root-cause inference |
| `anomalies.drawer.referral` | warning referral declared fields | wired for typed fields | no corrected payload/action apply |
| `anomalies.card.claim` | none | native disabled | 0 non-GET |
| `anomalies.drawer.resolve-reason` | none | native disabled | no local value/fake success |
| `anomalies.drawer.resolve` | none | native disabled | 0 non-GET |
| warning transition/recovery controls | none | disabled/deferred | no POST/preview/apply/recovery call |

## 3. Query-state and request-budget evidence

| Scenario | Expected request budget | Required evidence |
|---|---:|---|
| mount | 1 anomaly list + 1 warning list | fetch spy and browser Network |
| retry anomaly only | 1 anomaly GET | warning data remains visible |
| retry warning only | 1 warning GET | anomaly data remains visible |
| open anomaly Drawer | 1 detail GET | no warning referral unless warning selected |
| open warning Drawer | 1 referral GET | no anomaly detail N+1 |
| close/switch Drawer | 0; abort old | stale response cannot overwrite selection |
| filter/status/tab navigation | 0 | local/hash-only behaviour |
| disabled controls | 0 | 0 POST/PUT/PATCH/DELETE, 0 alert/confirm/prompt |

## 4. Required negative vectors

- missing required response key; wrong primitive; null violation; extra envelope/nested key;
- invalid severity/workflow/tracking/navigation enum; invalid fingerprint; invalid expected version;
- detail/referral response containing raw/unallowlisted fields must not render as business facts;
- token missing/rotated; 401/403/404/409/422/500/503; timeout/network/abort;
- stale detail after Drawer close or identity switch; duplicate same-identity response;
- sentinel A/B server DTOs produce different DOM values; no `mockData` dependency in page closure;
- every Claim/Resolve/Recovery/Warning transition control remains native disabled and non-mutating.

## 5. Evidence file placeholders (implementation phase only)

| Artifact | Status now |
|---|---|
| `contract-field-matrix.md` | NOT_RUN |
| `candidate-change-inventory.md` | NOT_RUN |
| `verification-receipt.md` | NOT_RUN |
| `browser-smoke-receipt.md` | NOT_RUN |
| `open-findings.md` | NOT_RUN |

No DB engine receipt is required for this query-only slice. Existing DB browser observation must be recorded as
GET-only evidence and must not be relabeled as migration, mutation, or engine verification.
