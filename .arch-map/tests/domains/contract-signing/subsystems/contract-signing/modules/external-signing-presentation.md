module: external-signing-presentation
parent_subsystem: contract-signing
architecture: ../../../../../../domains/contract-signing/subsystems/contract-signing/modules/external-signing-presentation.md
layout_status: custom_current
test_root: ui_react/src/tests/contract_external_signing_actions.test.tsx

# Owned verification
- `contract_external_signing_actions.test.tsx` — 保護外部簽約 closed states、歷史簽回 strict lineage、Preview invalidation、未知結果不得重送、final PDF fresh readback 與 business-first closed presentation。
- `test_full_contract_preview.py` — 保護 exact target、typed owner mappings、conditional applicability與零寫入 Preview。
- `test_full_contract_preview_ui_client.py` — 保護 authenticated typed client及 browser print mirror只採 cell-keyed typed values、不回退 raw presentation資料。
