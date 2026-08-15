# WP86 Independent Worker Local Credential Receipt

Date: 2026-08-15  
Scope: local development credential loading only; no schema, data, external provider, or production mutation.

## Finding and repair

An independently launched incident worker returned
`503 internal_service_authentication_unavailable`. The FastAPI composition loads Git-ignored
`.env`, but the worker and monitor CLIs did not. `PrivateOperationsClient` now reads only an
allowlist of Private API settings from the project `.env` when an explicit process value is absent;
it does not mutate `os.environ`, so DB credentials cannot be reintroduced after worker startup
clears them. Explicit deployment values retain precedence. The local shared key remains excluded
from logs, URLs, responses, and Git.

## Evidence

- `.venv\Scripts\python.exe -m pytest -W error -p no:cacheprovider --basetemp
  .pytest_tmp\wp87-runtime-security-final tests\test_private_runtime_operations.py` —
  `28 passed`.
- Coverage includes local key fallback, process-value precedence, DB credential non-injection,
  correct/wrong Google issuer, bounded retry, and every Worker／Monitor `--once` failure exit.
- No worker cycle, DB operation, external provider, or production side effect was invoked.

## Remaining operator action

Existing API and worker processes must be restarted once to read the newly configured local `.env`.
