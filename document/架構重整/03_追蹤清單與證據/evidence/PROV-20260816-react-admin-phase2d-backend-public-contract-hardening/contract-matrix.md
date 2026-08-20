# Phase 2D-H Public Contract Matrix

日期：2026-08-16  
基線：`main@8615225481c8f72a9629289285516189b270cb36`  
狀態：frozen-for-candidate；此矩陣是驗收證據，不是新的業務授權。

| Surface | Canonical owner | Python public type | JSON values | Required / nullable | Invalid handling |
|---|---|---|---|---|---|
| Anomaly summary severity | `AnomalyDefinition.severity` | `AnomalySeverity` | `warning`, `blocking` | required / non-null | Pydantic validation failure；repository placeholder不穿透 |
| Anomaly summary workflow | projection workflow | `AlertWorkflowStatus` | `open`, `claimed`, `resolved` | required / non-null | Application data-integrity failure或Pydantic validation failure |
| Anomaly workflow receipt status | workflow receipt | `AlertWorkflowStatus` | 同上 | required / non-null | Pydantic validation failure |
| Recovery context severity | registry definition | `AnomalySeverity` | `warning`, `blocking` | required / non-null | Pydantic validation failure |
| Recovery context workflow | projection workflow | `AlertWorkflowStatus` | `open`, `claimed`, `resolved` | required / non-null | Pydantic validation failure |
| Import Warning task status | Import Warning aggregate | `ImportWarningTrackingStatus` | `open`, `awaiting_external_confirmation`, `response_recorded`, `reimport_requested`, `closed`, `auto_resolved` | required / non-null | Pydantic validation failure |
| Import Warning preview result | Import Warning transition | `ImportWarningTrackingStatus` | 同上 | required / non-null | Pydantic validation failure |
| Import Warning request target | operator command boundary | existing allowlist pattern | `awaiting_external_confirmation`, `response_recorded`, `reimport_requested`, `closed` | required / non-null | HTTP 422；不開放 `open`／`auto_resolved` |

## Application enrichment

- `AnomalyApplication.query_summaries()` 與 `query_detail()` 共用 `_enrich_summary()`。
- severity只由 `default_anomaly_registry().require(definition_code).severity` 衍生。
- persisted `source_domain` 與 definition不一致，或 workflow status不是 canonical enum時，固定
  `anomaly_projection_data_integrity_violation`；不得略過壞列或回200空清單。
- repository、資料表與交易邊界均未變更。

## Schema evidence

`AnomalySummaryView.model_json_schema()`、`AnomalyWorkflowReceiptView.model_json_schema()` 與
`ImportWarningTaskView.model_json_schema()` 的 `$defs` enum由 focused tests逐值驗證；blank、unknown及
extra field仍 fail closed。
