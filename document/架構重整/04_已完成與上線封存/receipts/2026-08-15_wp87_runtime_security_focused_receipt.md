# WP87 Runtime Security Focused Receipt

Date: 2026-08-15  
Scope: Private Operations authentication, Worker credential isolation, and one-shot failure semantics.

## Result

- Google OIDC accepts only `accounts.google.com` and `https://accounts.google.com` after audience
  validation; a wrong issuer returns typed 401 without exposing verifier details.
- Local `.env` fallback reads only Private API settings and never injects DB credentials into the
  Worker process environment.
- Durable, LINE, Knowledge, Incident, and Monitor one-shot processes all return non-zero on a
  retryable failed cycle.

## Evidence

```text
.venv\Scripts\python.exe -m pytest -W error -p no:cacheprovider
  --basetemp .pytest_tmp\wp87-runtime-security-final
  tests\test_private_runtime_operations.py
28 passed in 5.39s
```

No Dockerfile, deployment, schema, existing database, or external provider was modified. Launcher
smoke and developer local-service acceptance remain `NOT_RUN`; WP87 remains `in-progress`.
