# Subsystem: registry-deletion

## Parent
- domain: `global`

## Responsibility
編排 root-only 的未簽約案件及 case-owned 關聯資料永久刪除，擁有單一 outer UoW、fresh signing guards 與去個資收據；任一方曾簽回即阻擋，保留月嫂、其他案件與共用來源，不呼叫 provider。

## Modules
- `registry-deletion` — typed eligibility、fresh-lock Apply、receipt replay 與管理端確認；path: `modules/registry-deletion.md`

## Contracts
- `document/架構重整/01_規格基線/33_案件與月嫂整合名冊正式規格.md` RD-1

## Verification routing
- default_boundary: Module
- test_root: `tests/domains/global/subsystems/registry-deletion/`
