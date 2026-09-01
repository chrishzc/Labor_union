module: finance-import-correction
parent_subsystem: finance-import
architecture: ../../../../../../domains/finance-import/subsystems/finance-import/modules/finance-import-correction.md
layout_status: custom_current
test_root: ui_react/src/tests/finance_import_correction_client.test.ts

# Owned verification
- `finance_import_correction_client.test.ts` — strict correction Preview、durable Apply identity、terminal outcome receipt與malformed payload fail-closed。
