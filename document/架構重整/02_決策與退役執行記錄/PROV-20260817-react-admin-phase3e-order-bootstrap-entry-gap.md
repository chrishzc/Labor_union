---
doc_type: gap-package
declared_status: proposed
identity: PROV-20260817-react-admin-phase3e-order-bootstrap-entry-gap
date: 2026-08-17
owner: Orders / Case Import Architecture Owner
domain: Orders / Case Import
---

# Phase 3E：新建訂單／Case Bootstrap entry 語意缺口

## 0. 結論

React `OrdersPage` 的「新建訂單」不是現有 Case Architecture Bootstrap 的同義入口。bootstrap 是既有來源資料的
受控修復／採用命令；它不能被 UI 包裝成一般人工建單。owner、最小根事實、草稿生命週期與匯入來源關係未裁決前，
按鈕維持原位且 native disabled，不得以 local state、generic CRUD 或 bootstrap 冒充成功。

## 1. 待人工裁決

1. 人工新建是否為正式業務入口，或所有案件都必須來自核准 workbook／source intake。
2. 若允許人工新建，首個 canonical root 是 case、order intake 還是 import review；誰是唯一 owner。
3. 必填欄位、warning-only 欄位、PII 類別、duplicate policy、draft／abandon／submit lifecycle。
4. Query／Preview／Apply、expected version、idempotency、receipt、audit及後續Orders projection。
5. React stable control `orders.create` 的 capability與rollback entry。

## 2. Evidence boundary

- `api/routes/case_architecture_bootstrap.py`與`subsystems/bootstrap/case_architecture_workflow.py`只可作repair/bootstrap evidence。
- `ui_react/src/pages/OrdersPage.tsx`只證明視覺入口存在，不是契約來源。
- 不得復活generic staff/order CRUD、直接寫DB或將bootstrap response改名為create receipt。

## 3. Gap acceptance

產出責任矩陣，逐欄凍結 owner／SSOT／required／warning-only／PII／duplicate policy與命令語意；人工確認後再建立
backend public-contract與React successor兩個獨立exact WPs。在此之前production write set為空。

## 4. DB gate

| Gate | Status | Evidence |
|---|---|---|
| Scope gate | BLOCKED | owner與root fact未裁決 |
| Change inventory | NOT_RUN | 無DB write set |
| Static release gate | NOT_RUN | 無release |
| Descriptor gate | NOT_RUN | 無schema變更 |
| Read-only plan gate | NOT_RUN | 不適用 |
| Engine verification gate | NOT_RUN | 不適用 |
| Developer acceptance gate | NOT_RUN | 不操作資料庫 |

結論：`DB_CHANGE_NOT_READY`。
