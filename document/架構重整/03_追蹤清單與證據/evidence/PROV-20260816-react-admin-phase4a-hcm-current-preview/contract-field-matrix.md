# Phase 4A-P HCM Current Workbook Preview contract matrix

## Freeze scope

唯一 HTTP action：`POST /api/v1/case-import/hcm/workbooks/preview`。本矩陣凍結於
`main@8615225481c8f72a9629289285516189b270cb36` 的 current dirty working tree；base SHA 不覆蓋 dirty source。

| surface/control | method/path | transport | Pydantic authority | constraint | disposition | UI slot |
|---|---|---|---|---|---|---|
| HCM file | local | File bytes | `api/routes/hcm_import.py::_persist_uploaded_workbook` | `.xlsx`, nonempty, <=20MiB | READY_LOCAL_BOUNDARY | file input |
| Preview | POST `/api/v1/case-import/hcm/workbooks/preview` | multipart `workbook`; current memory bearer | `api/routes/hcm_import.py::preview_hcm_workbook` | one explicit click = max one request | READY_TYPED_PREVIEW | Preview button |
| source digest | response data | strict envelope | `HcmWorkbookPreviewView.source_content_digest` | lowercase 64-hex, equals local bytes SHA-256 | READY_TYPED_PREVIEW | summary |
| row count | response data | strict envelope | `HcmWorkbookPreviewView.source_row_count` | integer >=0 | READY_TYPED_PREVIEW | summary |
| ready | response data | strict envelope | `HcmWorkbookPreviewView.ready_count` | integer >=0 | READY_TYPED_PREVIEW | summary |
| ready with warning | response data | strict envelope | `HcmWorkbookPreviewView.ready_with_warning_count` | integer >=0 | READY_TYPED_PREVIEW | summary |
| review required | response data | strict envelope | `HcmWorkbookPreviewView.review_required_count` | integer >=0 | READY_TYPED_PREVIEW | summary |
| fingerprint | response data | strict envelope | `HcmWorkbookPreviewView.preview_fingerprint` | lowercase 64-hex | READY_TYPED_PREVIEW | summary |
| per-row details | none | none | no public typed view | no inference from counts | BACKEND_GAP | unavailable table message |
| current Apply | POST exists but forbidden | multipart+headers | `HcmWorkbookReceiptView` | warning/UoW/observation gates open | OUT_OF_SCOPE_LOCKED | disabled Apply |
| historical HCM | retired 410 | none | route retirement | no React call | RETIRED_LOCKED | disabled card |
| other import families | not in wave | none | separate bounded domains | no React call | OUT_OF_SCOPE_LOCKED | disabled cards |

## Error/status matrix

| status/failure | UI disposition |
|---|---|
| 401 | clear/deny session through existing auth composition; no raw payload |
| 403 | unavailable; no retry loop |
| 409 | not expected for Preview; fail closed as bounded contract error |
| 422 known `detail.code` | file/contract error; never render raw detail |
| timeout/network/5xx | known Preview failure; user may explicitly retry same snapshot |
| schema/digest mismatch | contract drift; clear preview and fail closed |

## Locked controls

`imports.hcm-current.open-apply`、`imports.hcm-current.apply`、HCM historical preview/apply、Client BeClass
preview/apply、Staff historical preview/apply、Historical Orders preview/apply、Bank Statements preview/apply。
