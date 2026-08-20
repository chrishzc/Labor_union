---
doc_type: gap-package
declared_status: proposed
identity: PROV-20260817-react-admin-phase3d-data-browser-part-identity-gap
date: 2026-08-17
owner: React Validation Governance / Data Browser Integration Owner
domain: Global Validation Governance / Data Browser
source_work_packages: PROV-20260817-react-admin-phase3-scenario-lineage-governance; PROV-20260817-react-admin-phase3d-db-query-public-contract-hardening
approval_required: 人工裁決 Data Browser 的 canonical UI Part identity 與驗收 owner
prerequisites: none (docs-only gap)
base_branch: main
base_head: late-bound-at-approval
dirty_baseline: integration-owner-must-capture-before-writer
base_drift_rule: any relevant path drift requires fresh read and re-freeze before edits
ui_execution_mode: not-applicable
---

# Phase 3D Data Browser UI Part／Scenario Identity 缺口

## 0. Business scenario

維運人員需要以React Data Browser查詢核准的masked canonical sources、開啟typed detail並追溯source
identity。驗收必須能追到一個唯一UI Part、scenario、fixture、expected與browser checklist；不能因後端已有
query route，就把整個Data Browser entry判成完成。

## 1. Current gap

- `UI真實業務流程測試資料與驗收主計畫.md`目前沒有Data Browser的canonical Part identity。
- Phase 3 Scenario Lineage只允許建立`react_admin_data_browser_query.json`，明確禁止writer自行建立臨時Part目錄。
- 現行Data Browser尚有raw payload／PII與source-correction mutation邊界；query、repair與entry cutover不是同一能力。
- 若不同writer自行使用Part編號、頁面名稱或既有相近Part，將形成雙SSOT並讓browser receipt無法對齊。

## 2. Required human decision

人工必須裁決下列其中一種，並凍結唯一identity：

1. 建立dedicated Data Browser UI Part，owner為Data Browser masked query／detail；source correction另由owning
   domain recovery Part承接。
2. 將Data Browser作為既有維運／異常Part的明確子scenario，但必須提供一對一scenario path與entry identity，
   不得只用文字說「歸在異常」。

不建議把Data Browser塞進Import Part，因為唯讀source查詢與Import Preview／Apply具有不同owner、交易與PII
邊界。

## 3. Closure acceptance

- canonical Part ID、title、owner、entry route與rollback entry均有唯一值。
- `react_admin_data_browser_query.json`、fixture、expected、UI checklist、result summary與receipt manifest能互相引用。
- query／detail的success、empty、401、403、typed error、timeout、abort、stale、PII redaction與pagination有oracle。
- source correction維持獨立gap；沒有owning-domain command前不得被此Part吸收或啟用。
- 本gap關閉只授權後續scenario metadata／exact Work Package，不授權production、DB、entry switch或retirement。

## 4. DB gate

| Gate | Status | Evidence |
|---|---|---|
| Scope | PASS | docs-only identity gap |
| Change inventory | PASS | 0 schema／seed／backfill／destructive |
| Static release | NOT_RUN | 無DB release |
| Descriptor | NOT_RUN | 無DB object |
| Read-only plan | NOT_RUN | 無migration |
| Engine verification | NOT_RUN | 後續bounded query package |
| Developer acceptance | NOT_RUN | 不操作既有DB |

結論：`DB_CHANGE_NOT_READY`。
