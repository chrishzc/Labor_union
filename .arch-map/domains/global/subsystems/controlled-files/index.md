# Subsystem: controlled-files

## Parent
- domain: `global`

## Responsibility
提供管理端受控檔案 staging、zero-write Preview、Apply、list/detail/download 與 immutable
receipt/readback 的 public API composition。共用 storage 不擁有業務生命週期；owner/purpose
pairing、subject existence、digest、opaque identity 與單一 outer UoW 由既有 controlled-file
workflow／repository／storage port 保護。

## Implementation
- primary: `api/routes/controlled_files.py`
- dependency: `api/dependencies/controlled_files.py`
- workflow: `subsystems/controlled_files/workflow.py`
- finalize runtime: `subsystems/controlled_files/reference_finalize.py`,
  `infrastructure/mysql/controlled_file_finalize_worker.py`
- repository: `infrastructure/db/controlled_file_repository.py`
- storage port adapter: `infrastructure/file/controlled_file_storage.py`

## Modules
- `api-composition` — authenticated public route and typed projection composition；path:
  `modules/api-composition.md`
- `finalize-runtime` — bounded 1015 finalize-intent worker and storage integrity checkpoint；path:
  `modules/finalize-runtime.md`

## Contracts
- `document/功能開發計畫/NAS_檔案庫與資料中心管理介面正式規範.md` §9 — exact seven
  `/api/v1/storage` routes, authenticated management boundary, opaque projection and
  Preview/Apply/receipt contract.
- `document/架構重整/01_規格基線/10_Global_保留資料Migration與Cutover_Subsystem.md` §9 —
  additive schema and developer DB change gates.

## Verification routing
- default_boundary: Subsystem
- module verification: `modules/api-composition.md`
- workflow_tests: `tests/test_controlled_file_workflow.py`
- storage_tests: `tests/test_controlled_file_storage.py`
- schema_tests: `tests/test_controlled_file_schema_contract.py`
- finalize_tests: `tests/domains/global/subsystems/controlled-files/integration/test_controlled_file_finalize_runner.py`

## Change triggers
Reconcile when controlled-file public route identity, auth dependency, typed projection/error,
workflow/repository/storage ownership, schema/release dependency, or canonical test routing changes.
