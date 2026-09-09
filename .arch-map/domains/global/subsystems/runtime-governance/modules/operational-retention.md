# Module: operational-retention

## Parent

- domain: `global`
- subsystem: `runtime-governance`

## Responsibility

以 positive registry 分類技術 log、技術紀錄與營運觀測來源，統一執行 30-day expiry、
configured high／low-water pressure cleanup、capacity readback 與 fingerprinted Manual
Preview／Apply。永久 denylist、production enablement、schema migration 與 physical DB compaction
不屬本 module 的隱含權限。

## Architecture status

- provenance: `architecture_declared`
- contract_revision: `18-retention-amendment-2026-09-09`

## Implementation

- primary:
  - `subsystems/runtime_governance/__init__.py`
  - `subsystems/runtime_governance/operational_retention.py`
  - `infrastructure/runtime/operational_retention.py`
  - `infrastructure/knowledge/chroma_gateway.py`
  - `api/dependencies/maintenance_operation.py`
  - `ui_react/src/pages/StorageManagementPage.tsx`
  - `ui_react/src/pages/StorageManagementPage.css`
- entrypoints:
  - `api/routes/operational_retention.py`
  - `api/schemas/operational_retention.py`
  - `api/dependencies/operational_retention.py`
  - `ui_react/src/api/system/operational_retention_client.ts`

## Direct dependencies

- Knowledge Retrieval：只提供 observation graph／index artifact typed adapter。
- Controlled Files：提供 owned-root 與 business-artifact protection facts；不把受控業務檔案交給 retention owner。
- Application Shell：只呈現「稽核與系統 → 儲存空間管理」typed API projection。

## Verification

- layout_status: `custom_current`
- test_root: `tests/domains/global/subsystems/runtime-governance/`
- integration_root: `ui_react/src/tests/domains/global/subsystems/runtime-governance/`
- default_boundary: Subsystem
- mandatory_oracles: `RET-AC-01..07`

## Change triggers

Reconcile when requirement `RET-001..010`、allow／deny classification、capacity semantics、public
surface、outer commit owner、reconciliation boundary or test root changes.
