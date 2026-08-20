---
doc_type: gap-package
declared_status: proposed
identity: PROV-20260816-react-admin-phase4c-knowledge-public-query-gap
date: 2026-08-16
owner: Knowledge Retrieval / Access
domain: Knowledge Retrieval
subsystem: FAQ Catalog Query
successor_proposal: PROV-20260817-react-admin-phase4c-knowledge-public-query-hardening
---

# Phase 4C-K：Knowledge／FAQ public query／read-commit gap

Knowledge list/detail/jobs/indexes/questions routes沒有 typed response model，會暴露全文、source URI、question／
answer／citations、correlation與LINE task identity；`KnowledgeApplication.list_*`／query還在讀取後 `commit()`，
違反 Query 唯讀。React FAQ 不得接線。

Successor 需先移除 query commit，建立只含 `id/title/lifecycle/version/updated_at` 的 masked catalog typed view、
Global errors與auth/zero-write tests。ingest/review/publish/retire/reindex/question/retry及外部index／LINE side effect
全部另案。

Exact backend-only successor 已提出於
`PROV-20260817-react-admin-phase4c-knowledge-public-query-hardening-work-package.md`，目前仍為`proposed`。
