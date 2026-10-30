# Module: file-storage

## Parent
- domain: `global`
- subsystem: `controlled-files`

## Responsibility
實作受控檔案 filesystem port 的 readiness、探索、驗證讀取與 staging；不擁有業務附件生命週期。
共用 NAS 根目錄下的資料庫備份專區由 Global migration 維護，不供一般業務附件探索或讀取。

## Implementation
- primary: `infrastructure/file/controlled_file_storage.py`
- shared layout: `infrastructure/file/storage_layout.py` — one production `CONTROLLED_FILE_STORAGE_ROOT`, fixed 01–05 and `_staging`, write-time child creation, no missing-root creation or local fallback. Explicit development archive/media roots remain unchanged.
- New staging uses `_staging`; the legacy hidden staging directory is read/replayed without migration, and both staging namespaces plus the SQL backup area are excluded from business discovery/direct reads. Finalized staff files create resume/certificates/health_and_police siblings.
- `DATABASE_BACKUP_DIRECTORY` is defined by storage_layout and re-exported by the storage adapter for `scripts/nas_database_maintenance.py`.
- Explicit Windows UNC roots also enable the unified layout in the manager's source-mode APP_ENV=development process. Only local, non-NAS development roots retain legacy archive/media precedence; existing bytes are not migrated.

## Contracts
- `document/架構重整/01_規格基線/30_Controlled_File_Storage_NAS正式規格.md` §13B — shared root, backup subtree exclusion, no SQL attachment download.
- `subsystems/controlled_files/contracts.py` — typed storage port results and errors.

## Verification
- layout_status: `custom_current`
- test_root: `tests/domains/global/subsystems/controlled-files/modules/file-storage/`
- legacy_regression: `tests/test_controlled_file_storage.py` — existing readiness, path isolation, staging and integrity checks remain in place.

## Change triggers
Reconcile when storage port ownership, reserved backup namespace, runtime root or verification roots change.
