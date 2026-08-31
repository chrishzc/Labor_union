# Subsystem: client-profile

## Parent
- domain: `clients`

## Responsibility
編排 verified applicant request 與 authenticated internal review，於單一 Client UoW fresh-lock
binding、request、profile version並保存 immutable event／receipt／bounded outbox。

## Modules
- `profile-change` — exact nine-field Client profile workflow；path: `modules/profile-change.md`

## Verification routing
- default_boundary: Module
- test_root: `tests/domains/clients/subsystems/client-profile/`
