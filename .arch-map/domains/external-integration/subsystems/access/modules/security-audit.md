# Module: security-audit

## Parent
- domain: `external-integration`
- subsystem: `access`

## Responsibility
提供管理員操作紀錄的去識別查詢及既有兩年保留期歸檔。NAS 歸檔委派固定程序，原始紀錄及 archive 的內容核對仍由此工作流要求；不賦予查詢者直接刪除權限。

## Implementation
- primary: `subsystems/access/security_audit_query.py`
- API: `api/routes/admin_audit.py`
- schema: `db/schema_parts/151_admin_security_audit_retention.sql`

## Contracts
- 既有 authenticated、enabled 工會人員可看去識別紀錄，不新增人員業務角色差異。
- 逾兩年才由 maintenance profile 執行 archive 程序；不清除 archive，不自行改 transaction owner。
- 正式規格：17 的 NAS-AUTH-01、NAS-DB-01/02 及既有 audit contract。

## Verification
- layout_status: `custom_current`
- layout_basis: 既有 policy 檔案直接驗證這個唯一 query／retention owner，保留其當前位置及 discovery；本次將直接 SQL oracle 更新至同一 owner 的固定程序委派。
- test_root: `tests/test_admin_security_audit_policy.py`

## Provenance
- source_observed: 現有 query／API／policy tests。
- architecture_declared: 本次核准 P09 歸檔功能及 runtime 權限限制。

## Change triggers
Reconcile when audit projection、retention、procedure boundary 或 test root changes。
