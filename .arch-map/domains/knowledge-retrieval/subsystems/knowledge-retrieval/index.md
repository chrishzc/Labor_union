# Subsystem: knowledge-retrieval

## Parent

- domain: `knowledge-retrieval`

## Responsibility

協調 Knowledge source intake、人工審核／發布／退役、index durable job 與 cited answer；outer Knowledge Unit of Work 是 mutation commit owner。

## Modules

- `reviewable-qa-catalog` — LINE 常見 QA migration、系統內編修、治理狀態與 published-only index projection；path: `modules/reviewable-qa-catalog.md`

## Verification routing

- default_boundary: Subsystem
- test_root: `tests/domains/knowledge-retrieval/subsystems/knowledge-retrieval/`
