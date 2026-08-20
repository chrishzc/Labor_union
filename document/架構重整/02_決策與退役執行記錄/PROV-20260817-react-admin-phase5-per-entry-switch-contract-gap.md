---
doc_type: gap-package
declared_status: superseded
identity: PROV-20260817-react-admin-phase5-per-entry-switch-contract-gap
date: 2026-08-17
owner: Global Entry Point Governance / Integration Owner
domain: Global / Entry Point Governance
source_decision: PROV-20260817-react-admin-phase5-entry-navigation-switch-decision
successor: PROV-20260817-react-admin-phase5-entry-navigation-switch-production-gap
---

# Phase 5 per-entry runtime switch contract缺口

> 本文件已由
> `PROV-20260817-react-admin-phase5-entry-navigation-switch-production-gap`完整承接。保留本檔只作歷史
> inbound reference，不再作active gap、production write set或核准入口；後續一律以successor為唯一SSOT。

## Business scenario

營運者需要一次只把一個legacy Streamlit entry導向已驗證的React replacement，並能在觀測期間以同一entry
identity立即切回精確Streamlit rollback URL。現有Phase5 per-entry工作包只驗證candidate readiness、雙UI oracle與
rollback URL可用性；它們沒有canonical routing owner、manifest revision、one-entry CAS、switch audit receipt或
observation window，因此不能產生真正cutover授權。

## Gap

- queue status、React hash route與測試PASS都不是runtime router。
- 沒有一個已核准owner可以原子地把單一entry的target由`streamlit`切為`react`，或反向rollback。
- 沒有switch receipt可證明before/after manifest revision、operator、reason、artifact identity與rollback target。
- 沒有觀測期、rollback trigger、stale/conflict、artifact unavailable及bulk-switch fail-closed規則。
- 現有名稱含`entry-cutover`的工作包最高只可交付`query-candidate`／`readiness-candidate`。

## Required successor decision

先完成`PROV-20260817-react-admin-phase5-entry-navigation-switch-decision`並選定canonical admin entry map owner；
之後每次只為一個已通過readiness的entry建立獨立exact switch successor。不得建立一次切全部entry的通用Apply。

## Out of scope

本gap不修改production、queue、manifest、launcher、DB、Streamlit或React source，也不授權任何切換。

## DB gate

| Gate | Status | Evidence |
|---|---|---|
| Scope gate | PASS | docs-only gap，0 DB change |
| Change inventory | PASS | schema/system-seed/business-row-backfill/destructive皆無 |
| Static release gate | NOT_RUN | 無DB release |
| Descriptor gate | NOT_RUN | 無DB object |
| Read-only plan gate | NOT_RUN | 不適用 |
| Engine verification gate | NOT_RUN | 不適用 |
| Developer acceptance gate | NOT_RUN | 不操作既有資料庫 |

結論：`DB_CHANGE_NOT_READY`。
