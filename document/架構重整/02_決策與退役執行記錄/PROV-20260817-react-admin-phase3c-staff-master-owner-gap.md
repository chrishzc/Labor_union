---
doc_type: gap-package
declared_status: proposed
identity: PROV-20260817-react-admin-phase3c-staff-master-owner-gap
date: 2026-08-17
owner: Staff Domain Architecture Owner
domain: Staff
---

# Phase 3C：Staff master 建立／編輯 owner 缺口

## 0. 結論

現有Staff summary、matching preference、availability與retirement contracts不等於staff master CRUD。React「新增人員」、基本資料編輯、
證照附件及銀行資料更新沒有已確認canonical mutation owner，全部維持disabled。

## 1. 待裁決

- staff identity與版本根、duplicate identity、PII／銀行／證照的分離owner與可見權限。
- create、profile correction、certificate evidence、bank payout destination是否為四個bounded commands。
- Preview／Apply、CAS、receipt、audit、document bytes/digest、retention與retirement consumer guard。
- 不得復活retired generic `/staff` CRUD或用Data Browser source correction旁路。

## 2. Gap acceptance

產出field/owner/classification matrix與人工裁決；若分屬不同owners，建立多個successor WPs而非單一Staff CRUD。React保留現有卡片、
Drawer與stable IDs，但未有contract的保存按鈕原生disabled且0 fake success。

## 3. DB gate

| Gate | Status | Evidence |
|---|---|---|
| Scope gate | BLOCKED | canonical owner／root未決 |
| Change inventory | NOT_RUN | 無DB write set |
| Static release gate | NOT_RUN | 無release |
| Descriptor gate | NOT_RUN | 無schema變更 |
| Read-only plan gate | NOT_RUN | 不適用 |
| Engine verification gate | NOT_RUN | 不適用 |
| Developer acceptance gate | NOT_RUN | 不操作資料庫 |

結論：`DB_CHANGE_NOT_READY`。
