# WP56 UI ORD Contract 001 v6

- Date: 2026-08-12
- UI: `http://127.0.0.1:8501`
- Scenario: `UI-ORD-CONTRACT-001`
- Case: `WP56-5C3EBFD2D8FB`
- Replay receipt: `validation/receipts/UI-ORD-CONTRACT-001-UI-043.json`

Chrome selected the scenario case through the Orders editor and re-observed
the formal contract panel: staff signed `1/1`, precontract commitment created,
client signed, immutable archived document versions, and completed contract
state. The controlled UI selected archived document version `88` for the
audited download surface.

Signed-return is a terminal immutable-file operation. The normal UI therefore
does not expose an uploader after completion, preventing a different file from
being submitted with a prior idempotency key. The validation runner instead
replayed each exact typed API command with the same immutable bytes and keys:
staff return `89/86` and client return `91/88` returned their original receipt.

The scenario-specific normal-chain verifier passed all archive, signature,
commitment-conversion, deposit, assignment and five-service-day checks.
