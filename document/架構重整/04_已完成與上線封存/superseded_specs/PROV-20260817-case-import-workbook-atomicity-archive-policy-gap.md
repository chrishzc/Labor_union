---
doc_type: gap
declared_status: superseded
identity: PROV-20260817-case-import-workbook-atomicity-archive-policy-gap
date: 2026-08-17
owner: Case Import Integration Owner
domain: Case Import / Orders Historical Adoption / Staff
approval_required: 人工裁決各workbook atomicity、source archive policy與HCM identity disposition
successor: PROV-20260817-case-import-workbook-policy-decision
---

# Case Import workbook atomicity／archive／identity disposition gap

## Resolution（2026-08-23）

人工已透過successor exact採用推薦值：HCM duplicate identity為`review_only`、HCM Current為
`WHOLE_WORKBOOK + archive_required`，三種historical family為
`ROW_ATOMIC_RESUMABLE + archive_required`。canonical matrix位於
`../03_追蹤清單與證據/evidence/PROV-20260817-case-import-workbook-atomicity-archive-policy-gap/workbook-family-decision-matrix.md`。

本gap因此`superseded`；production能力盤點結果為`DB_SCOPE_REQUIRED`，但本resolution不授權DB或code。

## Business scenario

管理員上傳HCM、Client BeClass、Staff Historical或Historical Orders工作簿後，系統必須可證明來源檔案、
逐列身分解析、root版本、warning/review與terminal receipt屬於同一可重播命令；不能由既有逐列commit或
暫存檔行為反推正式政策。

## 必須人工裁決

1. `exact IP + exact normalized name + existing Client`時，HCM列採`review_only`或
   `create_partial_case_plus_warning`；並明定root、warning、outbox、replay與UI receipt outcome。
2. Client BeClass、Staff Historical、Historical Orders各自採`WHOLE_WORKBOOK`或
   `ROW_ATOMIC_RESUMABLE`；不得以同一答案套用三個family。
3. 每family採`archive_required`或`no_raw_archive_with_formal_port_amendment`；凍結PII class、retention
   owner、read authorization、archive identity、delete/compensation與crash recovery。
4. 若採row-atomic，持久層是否能表達running、row terminal receipts、resume cursor與唯一aggregate receipt；
   不足時必須另立DB successor，不得用log、temp file或缺少final receipt冒充。

## Evidence matrix write set

- `document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-case-import-workbook-atomicity-archive-policy-gap/workbook-family-decision-matrix.md`（new）
- 本gap、`02/README.md`與`15_正式規格索引與裁決總表.md`只由Integration Owner更新。

矩陣至少包含family、source identity、fingerprint inputs、target expected versions、atomicity、terminal
dispositions、PII class、archive policy、receipt selector、replay/stale/conflict、warning/outbox owner與Route A/B
scenario identity。

## Out of scope

0 production、0 API、0 React、0 DB/schema/migration/seed/backfill、0正式資料操作。裁決完成後才可核准
Phase 4A-H與Phase 4A-CW-H。

## DB gate

| Gate | Status | Evidence |
|---|---|---|
| Scope gate | BLOCKED | persistence／retention／atomicity尚未裁決 |
| Change inventory | NOT_RUN | 尚無production write set |
| Static release gate | NOT_RUN | 尚無release |
| Descriptor gate | NOT_RUN | 尚無object contract |
| Read-only plan gate | NOT_RUN | 尚無migration plan |
| Engine verification gate | NOT_RUN | 尚未核准 |
| Developer acceptance gate | NOT_RUN | 不操作既有資料庫 |

結論：`DB_CHANGE_NOT_READY`。
