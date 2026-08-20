---
doc_type: gap-package
declared_status: proposed
identity: PROV-20260816-react-admin-phase4c-line-delivery-public-query-gap
date: 2026-08-16
owner: LINE Delivery / Access
domain: LINE Delivery
subsystem: Delivery Administration Query
successor_proposal: PROV-20260817-react-admin-phase4c-line-delivery-public-query-hardening
---

# Phase 4C-D：LINE Delivery public query／PII gap

`/api/v1/line/tasks` summary/list/detail 目前皆為 `BaseResponse[dict]`；list/detail 暴露 recipient identity、
`payload_json`、provider/error/correlation/source identifiers。cancel/run-now/retry還允許空白reason與server產生
key，並可能喚醒worker造成外部發送。React 不得接線。

Successor 需建立 server-masked Pydantic summary/list/detail views、Global typed errors、pagination/filter/auth tests，
且 Query 0 provider／0 commit；不得釋出 raw payload、recipient/provider/correlation。所有 control mutation另案。

Exact backend-only successor 已提出於
`PROV-20260817-react-admin-phase4c-line-delivery-public-query-hardening-work-package.md`，目前仍為`proposed`。
