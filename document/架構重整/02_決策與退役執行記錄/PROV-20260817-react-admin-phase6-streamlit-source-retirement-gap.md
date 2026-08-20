---
doc_type: gap-package
declared_status: superseded
identity: PROV-20260817-react-admin-phase6-streamlit-source-retirement-gap
date: 2026-08-17
owner: Global Entry Point Governance / Integration Owner
priority: P0
successors: PROV-20260817-react-admin-phase6c-per-entry-retirement-readiness-gap; PROV-20260817-react-admin-phase6c-per-entry-retirement-template; PROV-20260817-react-admin-phase6c-final-streamlit-dependency-cleanup-gap
---

# Phase 6：Streamlit source／dependency retirement 缺口

> 此廣泛缺口已被三個更窄的current successors取代：逐entry readiness gap、逐entry exact template與最後
> dependency cleanup gap。本文件只保留歷史parent pointer，不再作平行SSOT、施工授權或完成判定。

## Current blockers

- 10個Streamlit runtime entries沒有任何一筆READY；Phase5 readiness為PARTIAL 4／BLOCKED 6。
- entry queue仍漏Data Import，11個React entries也未登錄。
- launcher、monitor、preflight、ngrok supervisor、migration rehearsal、dependencies與current tests仍使用Streamlit。
- `ui/`包含動態pages、panels、components、typed clients及runtime helpers，不能整個資料夾一次刪除。
- 現有Streamlit tests仍是rollback／compatibility驗收資產，不能用skip或批次刪除偽造綠燈。

## Successor requirements

1. Phase5A/5B完成且10個source entries逐筆有replacement/rollback/forward-data receipt。
2. Phase6B-HOST production hosting與Phase6B-RUN runtime integration均完成並經release核准。
3. Integration Owner建立精確的source retirement manifest；每一檔有caller、replacement、test disposition。
4. 每一個entry分批移除；全量測試、queue validator、launcher/monitor/rehearsal與dependency lock同步通過。
5. 歷史evidence與archive內容保留，不為清除`Streamlit`關鍵字改寫。

## Phase 6C per-entry Work Package contract

Phase6C不能是一個涵蓋`ui/**`的批次工作包。每次只允許一個Streamlit source entry，並在最新base上
late-bind下列exact內容：

- source entry identity、dynamic `PAGE_REGISTRY` caller與所有直接／間接source paths；禁止glob。
- 已active的React replacement identity、正式cutover decision、browser／rollback／forward-data／observation
  receipts與Phase6A validator result。
- 每一個Streamlit test的`retain | migrate_then_remove | remove` disposition及replacement test path。
- queue transition：UI source移除後只能依Entry Governance標`removed`並具replacement／decision；
  `retired_410`僅限HTTP，不得套用UI page。
- current SSOT、README、operator runbook與active index inbound delta；歷史receipt不改寫。
- exact required tests、changed-path whitelist、rollback trigger及release identity。

同一entry完成後先觀測、fresh-run queue/launcher/browser regression，再提出下一entry；不得自動批次推進。
只有最後一個Streamlit runtime／test／rehearsal caller完成正式disposition，才可另立final dependency cleanup
Work Package移除`streamlit`／`streamlit-cropper`與lockfile項目。

### Multi-agent rule

- Luna只做caller／test／docs inventory與fresh audit。
- Terra只處理該entry bounded presentation source與不重疊replacement tests。
- Primary／Integration Owner唯一裁決queue transition、shared launcher／dependency、SSOT、release與刪除授權。
- 任一unknown caller、missing rollback、failed forward-data或base drift固定停止該entry；不得以skip／warning繼續。

未閉合前固定為`BLOCKED_STREAMLIT_SOURCE_RETIREMENT`。
