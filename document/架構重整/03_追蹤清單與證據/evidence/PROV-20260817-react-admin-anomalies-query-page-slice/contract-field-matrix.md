# Anomalies Query Page-Slice Contract Matrix

Status: `candidate-frozen-local`; browser gate is still `NOT_RUN`.
Work Package: `PROV-20260817-react-admin-anomalies-query-page-slice`
Baseline: `main@8615225481c8f72a9629289285516189b270cb36`

This matrix records only the four approved GET families. Backend files are read-only contract evidence; no
backend file was modified by this slice.

| Surface | Method/path | Contract source | Required / enum | UI handling |
|---|---|---|---|---|
| anomaly list | `GET /api/v1/anomalies?include_snapshot=false` | `api/routes/anomaly_registry.py:52`; `api/schemas/anomaly_registry.py:57` | fingerprint, definition_code, source_domain, source_identity, source_version, predicate_active, workflow_version; severity=`warning|blocking`; workflow=`open|claimed|resolved`; snapshot null | list/card/KPI/filter; loaded scope only |
| anomaly detail | `GET /api/v1/anomalies/{fingerprint}` | `api/routes/anomaly_registry.py:80`; `api/schemas/anomaly_registry.py:71` | typed summary, timeline event scalars, typed action metadata; raw/non-closed snapshot fields fail closed | lazy Drawer; timeline/action slots unavailable when decoder rejects raw shape |
| warning task list | `GET /api/v1/import-warning-tracking/tasks` | `api/routes/import_warning_tracking.py:31`; `api/schemas/import_warning_tracking.py:17` | six `tracking_status` values; `tracking_version>=1`; nullable evidence/navigation | separate field-level warning cards; no generic anomaly KPI merge |
| warning referral | `GET /api/v1/import-warning-tracking/tasks/{occurrence_identity}/referral?expected_version=N` | `api/routes/import_warning_tracking.py:40`; `api/schemas/import_warning_tracking.py:57` | owning_lane=`hcm`; navigation=`hcm_import_center`; action kind allowlist; nullable target command | lazy warning Drawer; neutral `#data-import` navigation only |

## Strict decoder rules

- Schemas are `.strict()` and reject missing required keys, wrong primitive, extra nested/envelope keys, invalid enums and null violations.
- No `z.any`, `z.unknown`, `z.record`, `.passthrough()`, `.catch()`, `.default()`, `.coerce()`, `.preprocess()`, `.transform()`, `as any` or `unknown as`.
- `source_identity`, fingerprints, raw snapshot, action bindings, actor, reason and correlation are not rendered as business facts.
- Claim, Resolve, Recovery and Warning transition remain disabled/deferred; no non-GET is allowed.
