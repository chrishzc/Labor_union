# Module: file-persistence

## Parent
- domain: `global`
- subsystem: `controlled-files`

## Responsibility
實作既有受控檔案 typed persistence port，保存 staging、opaque object、版本鏈、Apply receipt 與 finalize intent；不擁有業務完成規則，不自行 commit。命令 claim 以 per-file idempotency key 識別，correlation ID 僅供同一外層操作追蹤，允許多份文件共用。

## Implementation
- primary: `infrastructure/db/controlled_file_repository.py`

## Dependencies
- inbound: `subsystems/controlled_files/workflow.py` — typed facts、claims、receipts 與 caller-owned transaction。

## Contracts
- `document/功能開發計畫/NAS_檔案庫與資料中心管理介面正式規範.md` — 受控檔案 opaque identity、Preview/Apply、receipt 與 storage boundary。

## Verification
- layout_status: `custom_current`
- test_root: `tests/test_controlled_file_repository.py`
- provenance: Existing maintained repository tests cover SQL mapping, lock/CAS, command identity and zero hidden commit; no test relocation.

## Change triggers
Reconcile when repository SQL mapping、command claim identity、typed persistence contract or exact test root changes.
