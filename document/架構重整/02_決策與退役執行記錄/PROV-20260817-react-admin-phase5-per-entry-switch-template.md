---
doc_type: work-package-template
declared_status: proposed
identity: PROV-20260817-react-admin-phase5-per-entry-switch-template
date: 2026-08-17
owner: Global Entry Point Governance / Integration Owner
domain: Global / Entry Point Governance
activation_prerequisites: Phase5A PASS; Phase5B PASS; navigation-switch-decision PASS; target entry readiness candidate PASS
approval_required: 依目標entry另立並核准exact per-entry switch successor；本template不可直接執行
runtime_profile: required-one-of-local-dual-run-or-production-same-origin
---

# Phase 5 單一entry runtime switch工作包範本

## 0. Execution boundary

本template不是production授權。Integration Owner必須在latest base上為**一個**entry late-bind新identity、exact paths與
人工核准文字。任何writer直接以此template施工，固定`BLOCKED_TEMPLATE_NOT_EXECUTABLE`。

## 1. Required frozen inputs

- legacy entry identity、React target identity、business scenario與canonical owner。
- Phase5A frozen registry/rollback manifest revision；per-entry writer唯讀，不得改expected manifest。
- Phase5B current runtime profile與React/Streamlit artifact identities。
- 該entry的readiness receipt、真TOTP browser receipt、dual-run oracle及mutation forward-data receipt（若適用）。
- exact Streamlit rollback URL、observation budget、operator與rollback trigger。

`runtime_profile`是required closed enum：

- `local-dual-run`：只驗`http://127.0.0.1:5173/#<route>`與Phase5B runtime；最多產生switch rehearsal，
  禁止宣稱production cutover或生成`phase5_navigation_switch_production_receipt`。
- `production-same-origin`：必須另有Phase6B-HOST PASS、Phase6B-RUN PASS、immutable artifact manifest與獨立
  release-approval receipts，forward route固定`/admin/#<route>`。缺任一即
  `BLOCKED_RUNTIME_PROFILE_ARTIFACT_MISMATCH`。

缺任一項固定`BLOCKED_ENTRY_NOT_READY`；預期改動Phase5A frozen manifest固定
`BLOCKED_EXPECTED_MANIFEST_MUTATION`。

## 2. Exact successor contract

每個successor必須凍結且只擁有：

1. canonical admin entry map中該一筆target；禁止bulk update。
2. `expected_manifest_revision` CAS、before/after target與new manifest revision。
3. operator、reason、correlation、artifact version/digest、forward URL與exact rollback URL。
4. closed Preview（0 write）→Apply→typed switch receipt→re-query observed狀態機。
5. stale/conflict/artifact unavailable/runtime unhealthy/unknown outcome的typed處置。
6. observation window、健康／業務SLO、automatic alert與人工rollback trigger；不得回滾Domain data。
7. immutable audit receipt；same key/same fingerprint回同receipt，不同payload typed 409。

## 3. Exact write-set rules

- production write set只能是navigation decision所選canonical routing owner及其focused tests。
- queue、readiness matrix與evidence只由Integration Owner在所有驗證PASS後串行回寫。
- `validation/scenarios/react_admin_entrypoints.json`是唯讀輸入。
- 不得修改目標React page、bounded API、Streamlit business page、DB/schema/migration、provider或其他entry。
- 若需要上述任一路徑，退回原bounded successor或新WP，不得擴張switch包。

## 4. Acceptance gates

- G0 exact human approval、fresh base/write-set collision、全部前置fresh PASS。
- G1 one-entry Preview 0 write，CAS stale與unknown identity fail closed。
- G2 Apply只改一筆runtime target並回typed receipt；same-key replay與mismatch conflict成立。
- G3 route依runtime profile驗證；local只可用5173 rehearsal，production才可用`/admin/`並產生switch receipt；
  exact Streamlit rollback、reload/new-tab/session expiry全通過。
- G4 真browser在受控資料上完成forward→observe→rollback→observe；mutation entry另驗forward-written-data。
- G5 artifact/runtime unhealthy時不切；觀測期trigger可切回但不回滾API/schema/Domain data。
- G6 queue/manifest/readiness before/after差異只限該entry disposition，expected manifest bytes不變。
- G7 focused/full tests、strict UTF-8、diff、secret/PII、write-set與fresh independent auditor全PASS。

完成狀態只能是該entry的`switched-observation`或`rolled-back`；不得順便retire Streamlit。退役仍屬Phase6逐entry
工作包，且必須等觀測期與rollback保留條件滿足。

## 5. DB gate

| Gate | Status | Evidence |
|---|---|---|
| Scope gate | BLOCKED | template不可執行；需另立exact successor與人工核准 |
| Change inventory | NOT_RUN | successor預設0 DB，仍需fresh確認 |
| Static release gate | NOT_RUN | 無DB release |
| Descriptor gate | NOT_RUN | 無DB object |
| Read-only plan gate | NOT_RUN | 不適用 |
| Engine verification gate | NOT_RUN | 不適用 |
| Developer acceptance gate | NOT_RUN | 不操作既有資料庫 |

結論：`DB_CHANGE_NOT_READY`。
