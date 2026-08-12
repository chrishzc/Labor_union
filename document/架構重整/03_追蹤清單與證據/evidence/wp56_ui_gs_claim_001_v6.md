# WP56 UI GS Claim 001 v6

- Date: 2026-08-12
- UI: `http://127.0.0.1:8501`
- API: `http://127.0.0.1:8000`
- Dataset: `lu_test_dataset_contract_signing_v4`
- Scenario: `UI-GS-CLAIM-001`
- Result: verified

This is the executable successor to the v5 static observation. Chrome navigated
to Finance > 補助核銷清冊 > 政府補助申請批次, previewed the 2026 Q3 revision
2 batch, and submitted the UI Apply command. The append-only normal-chain case
`WP56-7B82E214D8E8` contributes assignment `355` and its twelve official
service dates to the displayed candidate.

The typed preview returned batch `2026:Q3:R2` / `2`, thirteen items, total
`462000` NTD, and fingerprint
`13671baae7588d8e2c12d3de6b4f70ba73e9dd5e03a381452aa986972aa7f4fe`.
The UI command returned durable job
`9b7cd883-6b18-417d-93fd-63b918139a25`; the official worker completed it once,
and typed API re-observation returned `succeeded`, attempt count `1`, and
`government_subsidy:2`.

After a Streamlit rerun, Chrome submitted the retained Preview command again.
The UI displayed the same job id, rather than creating a second job or a second
claim batch. This is the scenario's concrete UI repair/re-observe/replay chain.

- Apply/re-observe screenshot:
  `wp56_ui_gs_claim_apply_reobserve_036.png`
- Replay/re-observe screenshot:
  `wp56_ui_gs_claim_replay_reobserve_036.png`
- Machine-readable receipt:
  `validation/receipts/UI-GS-CLAIM-001-UI-036.json`
- Previous DB oracle: `validation/receipts/UI-GS-CLAIM-001_v4.json`
