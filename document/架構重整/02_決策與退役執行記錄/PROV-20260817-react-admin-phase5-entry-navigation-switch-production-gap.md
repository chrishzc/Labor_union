---
doc_type: gap-package
declared_status: proposed
identity: PROV-20260817-react-admin-phase5-entry-navigation-switch-production-gap
date: 2026-08-17
owner: Global Entry Point Governance / Runtime Integration
domain: Global Presentation Routing
prerequisite: PROV-20260817-react-admin-phase5-entry-navigation-switch-decision PASS
---

# Phase 5 Entry navigation switch production缺口

## Current gap

Phase5 navigation decision工作包只凍結owner與語意，不修改runtime。Current source沒有application-owned
entry-target manifest、one-entry CAS command、audit receipt或可將canonical admin entry從Streamlit切到React再切回的
production control plane。Queue disposition、React hash route、Streamlit rollback URL或local dual-run都不是
production switch。

## Required successor after decision

人工採用Option A後，另立exact production Work Package，至少凍結：

- checked-in requirement schema與runtime持久manifest的canonical owner、revision及artifact binding；
- single-entry Preview／Apply、expected revision、idempotency、audit、typed receipt與same-key replay；
- current target=`react`、previous target=`streamlit`及entry-specific rollback URL；
- 10 legacy identities與一對多React replacement group的原子映射；
- authenticated operator、unknown/stale/bulk switch、artifact unavailable及manifest/queue drift的fail-closed行為；
- Phase6B-HOST/RUN release identity、health與same-origin `/admin/` prerequisite；
- switch-back rehearsal、完整post-switch observation window與production receipt。

Exact production write set只能在Option A owner/topology正式核准、Phase5A/5B及Phase6B runtime契約freeze後
late-bind。未達成前不得假設`api/main.py`、launcher、Streamlit shell或edge proxy為owner，也不得新增DB/schema。

## Downstream gate

每個Phase5 entry readiness與Phase6A/6C都必須取得自己的
`phase5_navigation_switch_production_receipt`及`phase5_observation_receipt`。Docs-only decision、candidate tests、
queue row、HTTP 200或截圖不能替代；缺少時固定`PHASE5_ENTRY_SWITCH_MISSING`或
`PHASE5_ENTRY_SWITCH_OBSERVATION_INCOMPLETE`。

## DB gate

Scope `BLOCKED`（owner/topology decision與exact production WP未核准）；Change inventory與其餘gates
`NOT_RUN`；`DB_CHANGE_NOT_READY`。
