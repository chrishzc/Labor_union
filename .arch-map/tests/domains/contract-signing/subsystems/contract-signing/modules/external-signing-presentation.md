module: external-signing-presentation
parent_subsystem: contract-signing
architecture: ../../../../../../domains/contract-signing/subsystems/contract-signing/modules/external-signing-presentation.md
layout_status: custom_current
test_root: ui_react/src/tests/contract_external_signing_actions.test.tsx

# Owned verification
- `ui_react/src/tests/contract_external_signing_actions.test.tsx` — closed states、歷史簽回 lineage、Preview invalidation、未知結果不得重送與 final PDF readback。
- `ui_react/src/tests/contract_external_signing_client.test.ts` — typed React transport 與 schema decode。
- `tests/domains/contract-signing/subsystems/contract-signing/integration/test_full_contract_preview.py` — exact target、typed owner mappings、conditional applicability 與零寫入 Preview。
- `tests/domains/contract-signing/subsystems/contract-signing/integration/test_contract_external_signing_api.py` — authenticated API contract。
