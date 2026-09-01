# Module: api-composition

## Parent
- domain: `global`
- subsystem: `controlled-files`

## Responsibility
將受控檔案七個 public management routes 接至既有 workflow，維持 authenticated persisted
admin actor、typed errors、opaque projections、digest/readback 與 download response 邊界。

## Implementation
- primary: `api/routes/controlled_files.py`
- dependency: `api/dependencies/controlled_files.py`

## Contracts
- `document/功能開發計畫/NAS_檔案庫與資料中心管理介面正式規範.md` §9.1、§9.3–§9.5

## Verification
- layout_status: `custom_current`
- test_root: `tests/domains/global/subsystems/controlled-files/`
- higher_boundary: `tests/test_entrypoint_review_queue.py`

## Change triggers
Reconcile when public route identity, request/response schema, auth dependency, typed error mapping,
download headers or API test placement changes.
