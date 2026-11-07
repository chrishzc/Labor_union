# Module: file-persistence

## Parent
- domain: `global`
- subsystem: `controlled-files`

## Responsibility
實作既有受控檔案 typed persistence port，保存 staging、opaque object、版本鏈、Apply receipt 與 finalize intent；不擁有業務完成規則，不自行 commit。命令 claim 以 per-file idempotency key 識別，correlation ID 僅供同一外層操作追蹤，允許多份文件共用。

## Implementation
- primary: `infrastructure/db/controlled_file_repository.py`
- Production-only physical locators use current case/date/kind/sequence or Staff number/name display facts and immutable version/digest; opaque IDs and canonical business object keys remain unchanged. New non-photo registrations enqueue the existing finalize intent in the caller's transaction; Scheduling photos retain their attachment-owned enqueue. No legacy locator rewrite or hidden commit.
- `get_committed_apply_evidence(file_id)` exposes the exact immutable per-file Apply receipt/provenance through the existing reconciliation read model. It checks object/staging FK identity and original JSON snapshot; ContractSigning may consume this on the same connection for a legacy member's own original command, never as generic proof of signing or external delivery. Missing/corrupt evidence stays unavailable; no backfill or borrowed primary hash.

## Dependencies
- inbound: `subsystems/controlled_files/workflow.py` — typed facts、claims、receipts 與 caller-owned transaction。

## Contracts
- `document/架構重整/01_規格基線/30_Controlled_File_Storage_NAS正式規格.md` — 受控檔案 opaque identity、Preview/Apply、receipt 與 storage boundary。

## Verification
- layout_status: `custom_current`
- test_root: `tests/test_controlled_file_repository.py`
- test_root: `tests/domains/global/subsystems/controlled-files/modules/file-persistence/`
- focused_read_evidence: `tests/domains/global/subsystems/controlled-files/integration/test_committed_apply_evidence.py` — pure original-serializer projection and bounded statement checks; no SQL execution.
- provenance: Existing maintained repository tests cover SQL mapping, lock/CAS, command identity and zero hidden commit; no test relocation.

## Change triggers
Reconcile when repository SQL mapping、command claim identity、typed persistence contract or exact test root changes.
