---
doc_type: gap-package
declared_status: proposed
identity: PROV-20260817-form-template-catalog-owner-public-contract-gap
date: 2026-08-17
owner: undecided (Orders / Contract Signing / Staff / Reporting)
scope: Form Management owner, template lifecycle, document/export public contract
decision_required: canonical owners and React entry identity
---

# Form Management owner／template catalog／public contract缺口

## 為何不能直接施工

現有Streamlit entry同時混合：Orders case/read statistics、一般表單template catalog、Contract Signing文件、
questionnaire/resume與Reporting。它會直接讀寫／刪除本機JSON、允許raw table/column binding，並可下載含PII文件；
React目前也沒有`#form-management`。把`#orders/#staff/#reports`拼成replacement或先寫generic Form API都是錯誤。

目前只有Orders `/form-management-statistics`與`/{case_no}/form-management-context`是可保留的typed read facts；
不得為了新頁複製成第二個Form client。Contract Signing只承認核准template引用與不可變document version，
不接受任意local file成為正式template。

## Exact gap write set

- 本文件
- `document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-form-template-catalog-owner-public-contract-gap/capability-owner-contract-matrix.md`
- `document/架構重整/01_規格基線/15_正式規格索引與裁決總表.md`（Integration Owner only；只登記gap）

Owner未決前禁止預先命名production API/schema/React paths；那會是假exact write set。

Current matrix：
`../03_追蹤清單與證據/evidence/PROV-20260817-form-template-catalog-owner-public-contract-gap/capability-owner-contract-matrix.md`。

## 人工必裁決矩陣

1. 分別裁決：(a) Orders context/stats、(b) general template catalog、(c) Contract Signing approved templates/doc versions、
   (d) questionnaire/resume、(e) Reporting。
2. 每塊凍結owner/SSOT、template id/version/digest/lifecycle與semantic placeholder registry；禁止raw table/column binding。
3. 凍結PII class、redaction、preview/download authorization、security audit、retention與physical-delete policy。
4. Preview 0 write；publish使用CAS/idempotency/replay；retire與physical delete分離。
5. renderer escaping/sandbox/CSP、MIME/bytes/digest與document version authorization完整。
6. 人工選dedicated `ui-react:#form-management`或明確one-to-many identity/rollback。

裁決前：Streamlit仍current；React mutation/export全部disabled；不得以local JSON/file成功作Domain receipt。

| DB Gate | Status |
|---|---|
| Scope | BLOCKED（persistence owner/retention未決） |
| Change inventory | BLOCKED |
| Static/Descriptor/Plan/Engine/Developer acceptance | NOT_RUN |

結論：`DB_CHANGE_NOT_READY`。
