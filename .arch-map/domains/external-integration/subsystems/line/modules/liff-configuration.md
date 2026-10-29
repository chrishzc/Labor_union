# Module: liff-configuration

## Parent
- subsystem: `external-integration/line`

## Responsibility
Owns current LIFF page/theme configuration through the existing versioned LINE configuration owner. Public registration, binding and gateway projections, management updates, history and rollback all read the database; JSON is fresh-bootstrap input only. Rollback appends a new revision and does not rewrite history. No delivery or menu publication is created. Page presentations apply the saved theme and copy while receipt status and identifiers remain authoritative. Unused customer-service configuration is retired: only empty definitions may be applied, bootstrap skips it and legacy maintenance routes return 410; immutable history and real tickets remain.

## Implementation
- `ui_react/src/api/line_configuration/non_citizen_liff_client.ts`、`ui_react/src/pages/line_management/NonCitizenLiffSettingsPanel.tsx` — LIFF 工作室的非市民頁面選項、明確建立及版本化文案／欄位設定；`/api/config/liff/non-citizen` 經既有 owner Query／Apply，無 provider 效果。
- `subsystems/line/configuration_application.py`
- `subsystems/line/configuration_contracts.py`
- `subsystems/line/ports.py`
- `subsystems/line/liff_models.py` — shared typed validation, no API dependency
- `subsystems/line/liff_configuration_history.py` — database history projection
- `infrastructure/mysql/line_configuration_publication_repository.py`
- `api/routes/line_system_config.py` — existing `/api/config/liff` read/write/history routes
- `api/schemas/line_config.py` — reexports shared LIFF models
- `config/liff_settings.json` — bootstrap only

## Contracts
- `document/架構重整/01_規格基線/20_LINE客服與月嫂自助服務正式規格.md` §6 — LIFF configuration SSOT

## Verification
- test_root: `tests/domains/external-integration/subsystems/line/modules/liff-configuration/`

## Change triggers
Reconcile configuration authority, runtime projection, version checks, history, rollback or verification roots.
