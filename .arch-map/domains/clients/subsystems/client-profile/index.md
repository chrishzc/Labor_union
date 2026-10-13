# Subsystem: client-profile

## Parent
- domain: `clients`

## Responsibility
編排 verified applicant request 與 authenticated internal review，於單一 Client UoW fresh-lock
binding、request、profile version並保存 immutable event／receipt／bounded outbox。

## Modules
- `profile-change` — Client profile allowlisted workflow；管理端含 HCM email，申請人欄位維持既有範圍；path: `modules/profile-change.md`

## Verification routing
- default_boundary: Module
- test_root: `tests/domains/clients/subsystems/client-profile/`
