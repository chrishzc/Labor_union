# Order Cancellation UI Client Receipt

## Executed evidence

- Date: 2026-08-08
- Command:
  `.venv\Scripts\python.exe -m pytest tests\test_order_cancellation_api_client.py`
- Result: `1 passed in 0.61s`
- Environment note: the sandbox identity could not load the `pydantic_core`
  DLL. The same focused test passed under the workspace owner's host identity.
- Non-blocking warning: pytest could not create its existing `.pytest_cache`
  path because of `WinError 183`; the test body completed.

## Proven contract

`OrderCancellationApiClient` sends the existing typed API contract without UI
business fallback:

- Query decodes the canonical cancellation facts and caregiver options.
- Preview serializes only confirmed service-day input.
- Apply carries the Preview versions and fingerprint, preserves the confirmed
  service days, and sends the stable idempotency header.

## Not proven by this receipt

- Streamlit rendering and Loading behavior.
- A real HTTP router with authenticated dependencies.
- The isolated-MySQL G03 cross-Domain transaction, replay, outbox, and
  independent client-refund/staff-payable settlement invariants.

This receipt does not change `G03` from `partial` to `proven`.
