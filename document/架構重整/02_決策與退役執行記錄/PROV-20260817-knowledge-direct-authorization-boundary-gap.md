---
doc_type: gap-package
declared_status: proposed
identity: PROV-20260817-knowledge-direct-authorization-boundary-gap
date: 2026-08-17
owner: Knowledge Retrieval / Access
domain: Knowledge Retrieval
---

# Knowledge in-process authorization boundary缺口

## Current state

Knowledge HTTP routes具有FastAPI capability dependency，但`KnowledgeApplication`本身沒有direct authorization
port，且dependency factory可被in-process caller取得。Current live caller inventory只有guarded router/factory；
這能證明目前沒有旁路，不能證明未來任意Python direct caller都會受保護。

## Required decision

若未來新增worker、CLI或其他Subsystem direct caller，須先裁決：

- authorization在application port、command actor context或entry adapter哪一層唯一擁有；
- enabled internal users同business capability與root-only Account Center例外如何傳入；
- query/mutation actor、audit、author-reviewer separation及provider/index side-effect gate；
- FastAPI與direct caller使用相同registered capability vocabulary的mechanical proof。

在successor前，Authorization Normalization只凍結current guarded caller allowlist；任何新增direct caller固定
`WRITE_SET_AMENDMENT_REQUIRED`。不得為了關閉本gap在現包臨時把role判斷塞進Knowledge Domain。

## DB gate

Scope `BLOCKED`（owner/port尚未裁決）；Change inventory與其餘gates`NOT_RUN`；
`DB_CHANGE_NOT_READY`。
