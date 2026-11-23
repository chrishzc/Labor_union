# Module: admin-entry-target-control

## Parent
- domain: `external-integration`
- subsystem: `access`

## Responsibility
擁有管理端入口 target registry 的 typed Query／Preview／Apply、單筆 CAS、replay、rollback 與 React artifact health gate；不改寫業務 Domain root。

## Implementation
- `subsystems/access/admin_entry_target_control.py`
- `infrastructure/file/admin_entry_target_store.py`
- `api/routes/admin_entry_targets.py` — `query_entry_targets` 的查詢入口宣告 `require_admin` 相依，不據此推論其他入口的行為。
- `scripts/provision_admin_entry_target_state.py`

## Verification
- test_root: `tests/domains/external-integration/subsystems/access/modules/admin-entry-target-control/`

## Provenance
- Entry target owner and canonical contract tests — `source_observed` — current Access subsystem source and focused test suite.
