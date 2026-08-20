---
doc_type: gap-package
declared_status: proposed
identity: PROV-20260817-react-admin-phase4b-weekly-workbook-authority-gap
date: 2026-08-17
owner: Reporting Architecture Owner
domain: Reporting / Orders / Government Subsidy / Scheduling
---

# Phase 4B：三-sheet週報 workbook authority 缺口

## 0. 結論

React Reports的案件週報、補助sheet與服務中工時sheet目前是presentation mock；現有AP／補助named exports不能被重新命名成完整
週報。沒有正式metric/date/source definitions與單一report contract前，整包XLSX按鈕維持disabled。

## 1. 待人工裁決

每個KPI與欄位的owner、root fact、時間區間、timezone、去重規則、PII/masking、下載權限與是否必須同一workbook；報表是snapshot、
即時query或durable export job；formula/version/artifact digest及重跑語意。

## 2. Gap acceptance

建立三sheet field-authority matrix，逐欄標`KEEP/REPLACE/RETIRE/DECISION_REQUIRED`。人工核准後才立Reporting coordinator
public-contract與React download WPs；UI不得自行join或計算正式KPI。

## 3. DB gate

| Gate | Status | Evidence |
|---|---|---|
| Scope gate | BLOCKED | reporting authority與公式未凍結 |
| Change inventory | NOT_RUN | 本gap不改DB |
| Static release gate | NOT_RUN | 無release |
| Descriptor gate | NOT_RUN | 無schema變更 |
| Read-only plan gate | NOT_RUN | 不適用 |
| Engine verification gate | NOT_RUN | 不適用 |
| Developer acceptance gate | NOT_RUN | 不操作資料庫 |

結論：`DB_CHANGE_NOT_READY`。
