# Domain: knowledge-retrieval

## Responsibility

擁有可審核知識來源、版本、發布／退役 lifecycle、索引 freshness 與引用回答邊界；JSONL／XLSX 僅是 migration input，LINE 與 LLM adapter 不得建立平行可回答來源。

## Subsystems

- `knowledge-retrieval` — intake、review、publication、index job 與 answer orchestration；path: `subsystems/knowledge-retrieval/index.md`

## Contracts

- `document/架構重整/01_規格基線/29_LINE服務說明、客服互動與選單角色正式規格.md` — Knowledge source、治理、published-only retrieval 與 READY index contract。
- `domains/knowledge_retrieval/` — lifecycle、structured content 與 citation rules。

## Verification routing

- layout_status: `custom_current`
- test_root: `tests/domains/knowledge-retrieval/`
