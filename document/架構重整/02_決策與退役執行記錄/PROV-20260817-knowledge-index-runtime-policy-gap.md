---
doc_type: gap-package
declared_status: proposed
identity: PROV-20260817-knowledge-index-runtime-policy-gap
date: 2026-08-17
owner: Knowledge Runtime / Deployment Architecture Owner
domain: Knowledge Retrieval / Runtime
---

# Knowledge reindex／runtime artifact policy缺口

現行reindex/retry與local Chroma path不能直接成為production contract。需人工裁決artifact target、immutable version/digest、atomic publish／
current switch、worker crash recovery、previous artifact rollback、retention、provider credentials與deployment owner；job accepted不等於index ready。
未決前React `line.faq.reindex`／job retry維持disabled，4C-KL-H不得擴張到index worker/provider。0 production write set。

DB Gate：Scope BLOCKED，其餘NOT_RUN；`DB_CHANGE_NOT_READY`。

| Gate | Status | Evidence |
|---|---|---|
| Scope gate | BLOCKED | runtime artifact/provider/rollback未裁決 |
| Change inventory | NOT_RUN | 0 DB |
| Static release gate | NOT_RUN | 無release |
| Descriptor gate | NOT_RUN | 無schema |
| Read-only plan gate | NOT_RUN | 不適用 |
| Engine verification gate | NOT_RUN | 不適用 |
| Developer acceptance gate | NOT_RUN | 不操作DB |
