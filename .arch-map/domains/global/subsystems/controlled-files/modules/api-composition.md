# Module: api-composition

## Parent
- domain: `global`
- subsystem: `controlled-files`

## Responsibility
將受控檔案 public management routes 與檔案傳輸設定接至既有 workflow，維持 authenticated persisted
admin actor、typed errors、opaque projections、digest/readback 與 download response 邊界。

## Implementation
- primary: `api/routes/controlled_files.py`
- dependency: `api/dependencies/controlled_files.py`
- transfer settings: `infrastructure/runtime/file_transfer_settings.py` — photo/resume byte limits, file timeout and atomic settings JSON; no business DB authority. Public LINE reads private HTTPS policy rather than the management configuration file.
- `GET /api/v1/storage/transfer-settings` — authenticated runtime projection for resume UI; other controlled-document capacities retain their existing behavior.
- settings API: `api/routes/file_settings.py` — root-only `GET/PUT /api/v1/storage/settings`; versioned atomic JSON config for size/timeout only, no DB schema. Container storage path is projected read-only from runtime configuration; path writes are rejected.
- settings UI: `ui_react/src/pages/FileSettingsPage.tsx`, `ui_react/src/pages/FileSettingsPage.css`, `ui_react/src/api/system/file_settings_client.ts` — real read/preview/save/readback for size/timeout, current container path shown as read-only text, no path note or file-category explanation surface.

## Contracts
- `document/架構重整/01_規格基線/30_Controlled_File_Storage_NAS正式規格.md` §4–§9、§11–§13

## Verification
- layout_status: `custom_current`
- test_root: `tests/domains/global/subsystems/controlled-files/`
- test_root: `ui_react/src/tests/domains/global/subsystems/controlled-files/modules/api-composition/`
- higher_boundary: `tests/test_entrypoint_review_queue.py`

## Change triggers
Reconcile when public route identity, request/response schema, auth dependency, typed error mapping,
download headers or API test placement changes.
