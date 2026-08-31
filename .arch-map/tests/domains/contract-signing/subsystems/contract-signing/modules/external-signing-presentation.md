module: external-signing-presentation
parent_subsystem: contract-signing
architecture: ../../../../../../domains/contract-signing/subsystems/contract-signing/modules/external-signing-presentation.md
layout_status: custom_current
test_root: ui_react/src/tests/contract_external_signing_actions.test.tsx

# Owned verification
- `contract_external_signing_actions.test.tsx` — 保護外部簽約 closed states、歷史簽回 strict lineage、Preview invalidation、未知結果不得重送、final PDF fresh readback 與 business-first closed presentation。
