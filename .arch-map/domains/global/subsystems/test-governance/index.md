# Subsystem: test-governance

## Parent
- domain: `global`

## Responsibility
維護 repository executable entrypoint inventory、pytest suite audit 與可重現的
Task 97 governance evidence；不授予 production operator authority，也不重定義各
business Domain 的 owner contract。

## Modules
- `entrypoint-and-test-suite-governance` — discovery、exact owner/caller mapping、tracked evidence 與 CI audit；path: `modules/entrypoint-and-test-suite-governance.md`

## Verification routing
- default_boundary: Module
- test_root: `tests/domains/global/subsystems/test-governance/`
