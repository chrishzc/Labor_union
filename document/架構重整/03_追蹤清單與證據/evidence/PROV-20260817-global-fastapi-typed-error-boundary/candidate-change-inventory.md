# Candidate change inventory

Production：`api/main.py`、`api/exception_handlers/{__init__,typed_errors}.py`、`api/schemas/{errors,admin_auth}.py`、
`ui_react/src/api/shared/transport.ts`。

Tests：`tests/test_global_typed_error_boundary.py`、兩個既有Admin Auth tests、Order Reopen route regression、
三個既有React transport/auth tests。

0 DB/schema/migration/seed/backfill、0 Domain rule、0 provider call、0 session persistence change。
