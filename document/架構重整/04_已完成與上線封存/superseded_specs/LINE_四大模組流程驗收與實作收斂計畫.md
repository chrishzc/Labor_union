---
doc_type: feature-plan
declared_status: completed
status: archived
identity: LINE-four-module-flow-acceptance-and-implementation-convergence
date: 2026-08-20
updated: 2026-08-23
priority: P1
owner: LINE Integration Architecture Integration Owner（待人工確認）
domain: LINE Integration / Customer Service / Access / Runtime Monitoring
business_scenario: 管理員、LINE使用者、客服與runtime operator能沿四個模組完成可追溯的identity、客服fallback、LINE publication/delivery與異常人工處理流程；每個外部副作用均可由receipt/outbox/retry/recovery證明
scope: Eraser current diagram 與正式規格、live implementation、evidence 的模組1～4對照；建立可驗收的流程完整性矩陣與互不重疊的後續工作包
out_of_scope: 外部 Eraser 寫入、production/provider rollout、React/UI cutover（M4 backend以外）、M3-E schema/DB mutation、Knowledge direct authorization、03 evidence與非本 lane README／catalog mutation
dependencies: 17_External_Integration_LINE_Access正式規格.md；20_LINE客服與月嫂自助服務正式規格.md；23_LINE身分管理與解除正式規格.md；00_Global_共同契約.md；現有LINE authorization normalization、Phase4C backend WPs；其他模組的current DB migration recovery（非 M3 gate）
write_set:
  - document/功能開發計畫/LINE_四大模組流程驗收與實作收斂計畫.md
acceptance: 圖中每個模組與跨模組箭頭均能對應正式SSOT、actor/trigger、state、transaction/UoW、outbox/provider、typed errors、retry/stale/conflict、manual recovery與entrypoint；每一項implementation claim均有current evidence，未完成或未授權固定標記gap/blocked；模組1～4均通過Module→Subsystem→Domain→Global驗收後才可標completed
required_tests: 文件與diagram completeness matrix review；各後續WP的focused contract／route／UoW／redaction／retry／stale／manual-recovery tests；current DB migration依update_local_database preserve-data gate；需要時才做controlled browser/provider acceptance
approval_required: Eraser title/module mapping、Module 1 ownership、Module 2 deterministic-vs-AI router、Module 4 alert target contract 已人工確認；本文件不授權 rollout、provider 或 current DB，僅記錄另行核准的 staged implementation slices
decision_links: 17_External_Integration_LINE_Access正式規格.md；20_LINE客服與月嫂自助服務正式規格.md；23_LINE身分管理與解除正式規格.md；PROV-20260820-line-liff-binding-ownership-reconciliation.md；PROV-20260820-line-runtime-alert-target-admin-contract.md；PROV-20260817-line-knowledge-authorization-normalization-work-package.md
evidence_links: PROV-20260817-react-admin-phase4c-line-delivery-public-query-hardening/verification-receipt.md；PROV-20260817-react-admin-phase4c-line-notification-rules-mutation/verification-receipt.md；2026-08-20_rich_menu_option_b_schema_gate_receipt.md；PROV-20260820-line-configuration-typed-redacted-query-hardening/verification-receipt.md；PROV-20260817-line-knowledge-authorization-normalization/verification-receipt.md
external_diagram:
  provider: Eraser.io
  workspace_url: "multiple；M1／M3=https://app.eraser.io/workspace/87vWpXgxRJMD2prPgXgO；M2／M4=https://app.eraser.io/workspace/bzK8Pm9tVCOFa5VHLeRu"
  authority_scope: workspace；四模組圖面為需求輸入與流程驗收推導，不是單一 diagram ID 的正式SSOT
  current_diagram_id: null
  current_diagram_url: "null；以 module_diagrams 各自 diagramUrl 為準"
  title: four module diagrams；workspace file title is not a module identity
  module_diagrams:
    - module: M1
      id: 9vI_ssJZUHa59Yw7LXc0d
      title: 模組一：LINE LIFF 表單架構與身分升級切換全流程圖
      url: https://app.eraser.io/workspace/87vWpXgxRJMD2prPgXgO?diagram=9vI_ssJZUHa59Yw7LXc0d&layout=canvas
    - module: M2
      id: xS5rOAuuQCUL139Tp4RA
      title: AI Agent 路由與 Harness
      url: https://app.eraser.io/workspace/bzK8Pm9tVCOFa5VHLeRu?diagram=xS5rOAuuQCUL139Tp4RA&layout=canvas
    - module: M3
      id: IXLp95YCVlOmYlkS1gBkl
      title: 模組三：雙向智慧協調與派案博弈全流程圖
      url: https://app.eraser.io/workspace/87vWpXgxRJMD2prPgXgO?diagram=IXLp95YCVlOmYlkS1gBkl&layout=canvas
    - module: M4
      id: bYdfiEJlAm-XhTLuLoJ-
      title: 管理端、異常與轉真人
      url: https://app.eraser.io/workspace/bzK8Pm9tVCOFa5VHLeRu?diagram=bYdfiEJlAm-XhTLuLoJ-&layout=canvas
  read_mode: workspace and module diagrams read-only audit；圖面是需求輸入，acceptance項目是依正式SSOT推導；不執行外部寫入
  previous_diagram_id: 0dXMFM1JaK-mi8Ayl_sB（obsolete link；只保留追溯）
---

# LINE 四大模組流程驗收與實作收斂計畫

## 1. 結論先行：四個 backend 目標不等於四個模組完成

目前可以先完成的是「流程與責任的可驗收化、漂移盤點、後續工作包切分」；不能把四個 backend 目標的局部通過數字直接升格為四個模組完成。

目前證據支持的範圍如下：

| 模組 | current disposition | 可先完成／仍缺少 |
|---|---|---|
| M1. LIFF 表單與身分升級 | `M1-A backend completed / sandbox E2E user-waived` | Alternative A、canonical binding與已知legacy guarded／410已完成focused驗證；真實LIFF sandbox E2E由使用者略過，日後有問題另開任務 |
| M2. AI Agent 路由與 Harness | `M2-A backend completed / module partial` | production full AI rejected；deterministic Tier 1、durable manual fallback與direct provider exit已完成；Tier 2 AI、provider與QA gates deferred／blocked |
| M3. 雙向智慧協調與派案博弈 | `approved backend scope completed / real E2E user-owned` | Query／Preview／Apply、owner adapters、fresh-lock、criteria/willingness/recontact、leave canonical receipt與service-date rematch均已收斂；`accepted` 仍只產生 typed Assignment conversion/rematch request，不寫 Orders、Assignment 或 Payroll。真實 DB/API／跨域 UI 驗收不宣稱 PASS |
| M4. 管理端、異常與轉真人 | `M4-A backend completed / module partial` | singleton／typed API／closed masked audit與human escalation create→claim→handling→resolve完成；React presentation、provider與完整human E2E仍 deferred |

因此，現階段可平行施工的是已核准的 M1-A、M2-A、M3-A、M4-A exact slices；M1 sandbox E2E 只能使用受控 LINE sandbox。這些 slice 仍不得升格為四模組整體完成；未完成分支、provider、rollout、current DB 與 cross-module evidence 仍保留原 gate。

## 2. Authority、diagram與解讀規則

### 2.1 Eraser current diagram identity

- Workspace authorities：M1／M3 圖面位於 `https://app.eraser.io/workspace/87vWpXgxRJMD2prPgXgO`；M2／M4 圖面位於 `https://app.eraser.io/workspace/bzK8Pm9tVCOFa5VHLeRu`。
- 四模組總圖不使用任何單一 module diagram URL；每一 URL 只代表其所屬圖面，不得互相代替。
- Current titles：M1 `模組一：LINE LIFF 表單架構與身分升級切換全流程圖`；M2 `模組二：AI Agent 語意路由器與確定性 Harness 控制流程圖`；M3 `模組三：雙向智慧協調與派案博弈全流程圖`；M4 `模組四：工會管理端、異常通報與客訴轉真人全流程圖`。
- Current diagram identity（2026-08-21 Eraser MCP fresh-read）：M1 `9vI_ssJZUHa59Yw7LXc0d`；M2 `xS5rOAuuQCUL139Tp4RA`；M3 `IXLp95YCVlOmYlkS1gBkl`；M4 `bYdfiEJlAm-XhTLuLoJ-`。
- Previous local mappings `1XwrLwQvzREt3gYfwac2`（M1）與 `A9x4TWcBBN1l6Ppn0-ot`（M3）在 current Eraser workspace 查無 diagram，已視為 stale identity，不再作為 authority。
- 舊連結：`0dXMFM1JaK-mi8Ayl_sB` 已標為 obsolete；本計畫只保留其追溯 identity。

Eraser 圖面是需求輸入；圖面上的 acceptance 是依 `15`～`24`、current evidence與人工裁決推導的流程 completeness evidence，不是正式規格、授權、SSOT、migration plan 或 provider rollout。若圖與正式SSOT或人工最新裁決矛盾，圖上的箭頭必須標 `conflict`／`human-decision-required`，不能以圖覆蓋正式 owner。

### 2.2 Canonical repository references

- Formal LINE boundary：[17 External Integration LINE Access](../../01_規格基線/17_External_Integration_LINE_Access正式規格.md)、[20 LINE Customer Service](../../01_規格基線/20_LINE客服與月嫂自助服務正式規格.md)、[23 LINE Identity](../../01_規格基線/23_LINE身分管理與解除正式規格.md)。
- Module 1 decision candidate：[LIFF binding ownership reconciliation](../../02_決策與退役執行記錄/PROV-20260820-line-liff-binding-ownership-reconciliation.md)。
- Module 2 blocked plan：[LINE QA knowledge contract](../../../功能開發計畫/LINE_QA客服知識契約收斂計畫.md)；authorization boundary的歷史identity為 `PROV-20260817-line-knowledge-authorization-normalization-work-package`，原路徑在封存時已不存在。
- Cross-module infrastructure evidence（不是 M3 canonical evidence）：Delivery query、Notification Rules與LINE Configuration的歷史receipt路徑在封存時已不存在；仍可追溯的[Rich Menu Option B gate receipt](../../03_追蹤清單與證據/evidence/2026-08-20_rich_menu_option_b_schema_gate_receipt.md)保留連結。
- Module 4 decision candidate的歷史identity為 `PROV-20260820-line-runtime-alert-target-admin-contract`，原路徑在封存時已不存在；current裁決以正式規格索引為準。

### 2.3 每個模組的 diagram completeness gate

Eraser 圖上的每一個 module box 至少要補齊以下節點或明確標註 `not-applicable`：

1. actor、入口／trigger、precondition、canonical root fact／SSOT；
2. Query／Preview／Apply 或 ingress／worker command 的 typed input、output、stable errors；
3. state machine、fresh-read／lock／outer UoW／commit owner；
4. idempotency、fingerprint、replay、stale、conflict、timeout、retry與backoff；
5. outbox／inbox／durable job、provider side effect與「何時不得呼叫 provider」；
6. failure、anomaly、dead-letter、manual recovery、operator receipt與redaction boundary；
7. public/private/LIFF entrypoint、caller與legacy exit；
8. 與其他模組的箭頭，逐條標明 source owner、target owner、資料形狀、交易邊界與是否同一 commit。

圖完成不代表程式完成。每一條箭頭都要能連到正式規格段落與 current code／test／receipt，否則只算 `diagram-only`。

2026-08-21 Eraser MCP fresh-read 的 diagram-to-current-byte disposition：M1 圖仍包含直接 clients lookup、role promotion 與 dual-role 結果，與正式 23 的 binding/projection boundary 衝突，故只採 canonical typed projection 解讀，LIFF E2E 仍 `BLOCKED`；M2 圖明列 Tier 2 AI、confidence、admin UI 與 feedback loop，但最新裁決只核准 deterministic Tier 1＋manual fallback，full AI/provider 為 `DEFERRED`；M3 圖的四條 exact flow（refusal groups、willing pool、zero-pool compromise、leave/date coordination）是需求輸入，現行 M3-A 只完成 typed foundation，完整流程 `PARTIAL / NOT_READY`；M4 圖包含 alert singleton、客訴三步驟與手機審核，但圖面原有姓名／電話／完整摘要標示不符合正式去敏契約，現行只採 masked typed projection，完整 provider／React／persistence E2E 仍 `NOT_READY`。

## 3. M1：LIFF 表單與身分升級

### 3.1 Canonical flow contract

| 面向 | 驗收內容 |
|---|---|
| Actors／triggers | LINE end user／LIFF；server-side verified LINE ID token；首次身份先行、customer/staff/admin claim、舊客 rebind claim；真人 reviewer 處理 pending review |
| SSOT／root facts | `line_identity_bindings` 與 binding events 是LINE identity root；customer／staff／admin root facts仍由各 owning Domain擁有；owner columns只是projection；`provisional_client_registrations`的owning Domain仍需人工確認 |
| State | flow open／validated；binding pending／active；review pending→approved/rejected/cancelled；revocation pending→revoked；不得以LIFF直接role promotion或直接覆蓋既有LINE ID |
| Transaction／outbox | verified claim由LINE Identity application擁有outer UoW；owner projection adapters在同一command內更新；成功後才建立stable delivery／Rich Menu binding intent；route不得直接SQL或同步provider |
| Provider | LINE ID-token verification與已提交outbox worker；provider failure不回滾已提交binding root，必須保存retry／manual recovery |
| Errors／retry／stale | invalid token／ambiguous proof／cross-subject claim／binding collision／stale expected version／idempotency mismatch固定typed fail closed；可重試的delivery／provider failure只能由durable worker bounded retry |
| Manual recovery | reviewer只能依masked current binding、proof fingerprint、expected version與receipt作approve/reject；不直接改projection、不重播webhook、不用舊helper猜測身份 |
| Entrypoints／legacy | canonical `api/routes/line_identity.py`、`api/routes/line_identity_management.py`與typed applications；`/api/line/bind`、舊`client_binding_application.py`、舊approve writer與`bind.html`需逐項`retain-readonly`／`410`／adapter／remove裁決 |

### 3.2 Current evidence與gap

- Formal authority：`23_LINE身分管理與解除正式規格.md`、`20_LINE客服與月嫂自助服務正式規格.md`、`17_External_Integration_LINE_Access正式規格.md`。
- Current code evidence：`api/routes/line_identity.py`已走server-side token與typed application；`subsystems/line/identity_application.py`、`identity_review_application.py`與owner adapters已存在canonical boundary。
- Current decision package：`PROV-20260820-line-liff-binding-ownership-reconciliation.md` 已為 `approved-for-specification-freeze`；Alternative A 已裁決，舊direct writers、provisional registration owner與legacy exit仍待 implementation evidence。
- Current tests/evidence：identity／review focused tests與route retirement characterization存在，但現有 evidence 明確指出沒有受控真實LIFF browser／verified-token registration／binding／Rich Menu end-to-end acceptance。

### 3.3 Module 1 acceptance

`Module PASS` 必須同時證明：diagram completeness；verified-token→typed flow→fresh binding root→owner projection→receipt/outbox 的正常路徑；same-subject rebind、cross-subject rejection、collision、stale、replay、rollback與provider retry；browser/network/DOM不洩漏完整LINE ID／phone；所有舊writer有唯一退出裁決。未完成前狀態固定 `partial / human-decision-required`。

## 4. M2：AI Agent 路由與 Harness

### 4.1 Canonical flow contract

| 面向 | 驗收內容 |
|---|---|
| Actors／triggers | customer LINE inbound message、已驗證identity/group context、service-help intent、unknown／ambiguous intent；Customer Service reviewer與Knowledge reviewer |
| SSOT／root facts | Customer Service擁有客服ticket、conversation與人工處理狀態；Knowledge Retrieval擁有source provenance、item version、publication與index job；QA workbook只能是input evidence，不是SSOT |
| State | `identity → group → service help → knowledge fallback → manual customer service`；published item/index需可追來源與version；missing source、stale index、unowned answer固定manual-only／unavailable |
| Transaction／outbox | inbound先進durable inbox；routing只建立typed service-help result、ticket intent或delivery intent；Knowledge publish/reindex是自己的versioned UoW；回答不得直接觸發Domain mutation |
| Provider | 目前不授權AI model或provider；若未來採AI，只能在已核准 deterministic guard、citation、confidence與manual fallback後接入，不能由Eraser設計稿自行升格 |
| Errors／retry／stale | unknown／ambiguous intent、無approved source、stale/failed index、provider unavailable與citation mismatch分別輸出typed fallback／manual ticket／bounded retry；禁止幻覺答案 |
| Manual recovery | Customer Service確認人工回覆與ticket；Knowledge reviewer核准source／answer／automation boundary；unresolved owner/category/source留在review queue |
| Entrypoints | `subsystems/line/service_help_application.py`、`subsystems/line/knowledge_question_application.py`、`subsystems/knowledge_retrieval/answer_query.py`、`api/routes/knowledge_retrieval.py`；所有route與worker仍受Access normalization與formal spec boundary約束 |

### 4.2 AI router漂移與current evidence

`LINE_運營與智能管理中心視覺化工作台規範.md`描述「AI客服事件與意圖規則管理」與即時模擬器，但這是設計／功能計畫，不是核准的AI router architecture。`LINE_QA客服知識契約收斂計畫.md`目前是 `blocked`：artifact-tool loader不可用，尚無本輪workbook locator、owner、category、source或approved answer evidence。已完成的 `PROV-20260817-line-knowledge-authorization-normalization-work-package.md`只處理linked LINE admin compatibility projection；Knowledge direct authorization、Knowledge lifecycle、AI/provider rollout明確不在範圍。

最新裁決已核准 M2-A 的 deterministic slice，但沒有核准 production full AI。現況證據為：

- `subsystems/line/ai_router_contracts.py`、`subsystems/line/deterministic_ai_router.py` 已提供 closed、provider-free Tier 1 outcome；
- `subsystems/line/service_help_application.py` 已把回覆導向 durable delivery／manual ticket，不在 commit 前呼叫 `reply_provider`；
- focused `test_deterministic_ai_router.py`、`test_service_help_manual_fallback.py`、`test_line_customer_service_first_release.py` 共 `28 passed`（以 `pytest -p no:capture` 執行；僅有既有 cache permission warning）。

因此 M2 現況為 **M2-A partial / implementation evidence available**；QA workbook、Knowledge direct authorization、Tier 2 AI、AI/provider、production rollout 仍是 `blocked / deferred`。不得把 Eraser 或工作台上的「AI 語意路由」直接當作 full AI 已核准，也不得以 M2-A 的 28 個 focused tests 宣稱 Module PASS。

### 4.3 Module 2 acceptance

`Module PASS` 必須證明每個routing branch都有canonical owner、closed output、source/version citation、manual fallback與zero mutation on answer；unknown/stale/unapproved/ambiguous branches fail closed；若採AI，還需獨立architecture approval與provider test evidence。現在固定 `partial / NOT_READY`：M2-A 已可驗證，Tier 2／AI／provider／QA evidence 仍未就緒。

## 5. M3：雙向智慧協調與派案博弈

本節以 Eraser M3 的真實業務語意為準。matching notification、postback、schedule confirmation與leave substitution只能作為 partial implementation evidence；Delivery／Rich Menu等LINE external-interaction能力是 cross-module infrastructure，不是 M3 的 canonical flow、完成條件或 migration gate。圖面需求仍不得直接升格為正式 owner、schema或approved architecture。

### 5.1 Canonical flow contract

| 面向 | 驗收內容 |
|---|---|
| Actors／triggers | customer／order、原員工與候選員工、coordinator／人工reviewer；條件或歷史變更、接受／拒絕、請假、預產期／服務日期變更、可用性變更與重新媒合事件 |
| SSOT／root facts | formal recommendation identity、criteria snapshot/diff與歷史拒絕原因；candidate pool lineage；Orders／Assignment／Payroll各自的root facts與conversion reference；Scheduling、Staff availability與Staff Payables各自的Domain root facts；不得以通知或圖面取代 owner |
| State | recommendation `pending→resent/reviewing→accepted/rejected/expired`；candidate pool可動態重算；零候選必須落到具體折衷／人工決定；`accepted` 只進 fresh-effects check，產生 Assignment conversion/rematch typed request；M3 不寫 Orders、Assignment 或 Payroll；請假延展或緊急替補、日期／可用性變更均由 owning workflow 重新評估 |
| Transaction／consistency | 以 criteria diff × history 精準重送而非整批重播；Apply 前 fresh-read／lock recommendation、candidate與Order根事實；接受後的 Orders、Scheduling、Staff Payables projection／receipt 必須可追溯且不可部分偽成功；provider／通知只在已提交邊界後執行 |
| Errors／retry／stale | criteria diff、歷史拒絕原因、stale expected version、candidate pool changed、zero candidate、acceptance conflict、leave/date availability conflict均須typed fail-closed；重送只允許精準差異範圍，禁止猜測或覆蓋新決定 |
| Manual recovery | reviewer依recommendation identity、criteria diff、candidate lineage與歷史拒絕原因選擇延展、替補、具體折衷或重新媒合；不得直接改 Orders／Scheduling／Staff Payables或重播舊通知冒充接受 |
| Entrypoints／partial evidence | matching notification、postback、schedule confirmation與leave substitution已有 A–E internal typed behavior focused evidence；concrete owner adapters、public coordination Query／Preview／Apply entrypoint、caller／worker receipt與cross-domain consistency仍 pending，不能當作 M3 已完成 |

### 5.2 Current evidence與DB boundary

- Formal recommendation identity、criteria diff／歷史拒絕原因精準重送、candidate pool lineage、zero-candidate resolution與 `accepted` effect（decision→fresh-effects→typed Assignment conversion/rematch request）已規格凍結；目前已有 13 個 source-version typed projections 與 A–E internal typed behavior evidence，M3 不寫 Orders、Assignment 或 Payroll。concrete owner adapters、public coordination Query／Preview／Apply entrypoint與完整 cross-domain E2E仍 pending，不能宣稱 Module PASS。
- leave defer／substitute、matching notification、postback與schedule confirmation均已有 internal focused evidence，但不能取代 recommendation／assignment owner或cross-domain consistency；目前 M3 focused regression evidence 為 `82 passed`，仍不等於 full Module PASS。
- Delivery／Rich Menu與其他LINE external-interaction測試可作 cross-module infrastructure evidence，不能作 M3 完成條件；其自身 migration／provider gate另依各自正式範圍處理。
- M3 Phase E 目前僅有 candidate inventory／spec planning，Scope gate **PASS**；DDL、schema implementation、release、seed、backfill、destructive 與資料庫操作均未授權。Static／Descriptor／Read-only plan／Engine／Developer gates 均 `NOT_RUN`，總結固定 `DB_CHANGE_NOT_READY`。

### 5.3 M3 acceptance

`Module PASS` 必須同時凍結：recommendation identity；criteria diff × 歷史拒絕原因的精準重送；動態意願池與candidate lineage；零候選的具體折衷；`accepted` 後 fresh-effects、Assignment conversion/rematch request；請假延展／緊急替補；預產期／服務日期變更與原員工可用性／重媒合；Scheduling／Orders／Staff Payables一致性；typed stale／conflict／manual recovery與receipt。M3 不寫 Orders、Assignment 或 Payroll；Phase E schema candidate 不得偽造 implementation PASS。

## 6. M4：管理端、異常與轉真人

### 6.1 Canonical flow contract

| 面向 | 驗收內容 |
|---|---|
| Actors／triggers | authenticated enabled internal admin；runtime monitor health event；客服急件／identity conflict；LINE group registration；admin reset/enable command |
| SSOT／root facts | `line_alert_notification_targets`的`target_type='group'`、`group_id`、`enabled`與delivery intent lineage；客服ticket／review root由Customer Service／LINE Identity擁有；不新增或假定`alert_group_id` root fact |
| State | group target `active↔disabled`，最多一筆active group；health event→durable intent/task→sent/retry/failed/exhausted；ticket pending→human handling→closed；singleton violation/orphan/receipt ambiguity固定operational finding |
| Transaction／outbox | Query zero-write；reset/enable在single outer UoW fresh CAS lock target→update projection→audit→admin receipt→commit；runtime health只由已提交event投影delivery intent；command本身不呼叫provider |
| Provider | LINE alert delivery worker／provider；provider unavailable與retry exhausted保存attempt/anomaly，不偽造delivered、不回滾target command |
| Errors／retry／stale | not_found、version_conflict、idempotency_mismatch、group_already_active、version_unavailable、persistence_unavailable、contract_invalid均typed；不猜測另一群組、不自動disable另一active target |
| Manual recovery | operator先查masked target／receipt，再以同一contract reset/enable；不得直接SQL、清physical group_id、重播webhook或用UI local toast冒充成功 |
| Entrypoints | current `api/routes/runtime_health.py`、`subsystems/line/runtime_alert_application.py`、`infrastructure/mysql/runtime_monitor_repository.py`、Streamlit runtime manager；後續React entry需另案治理，不得以local capability menu當授權 |

### 6.2 Current gap

`PROV-20260820-line-runtime-alert-target-admin-contract.md` 已為 `approved-for-specification-freeze`；沿用既有`line_alert_notification_targets.group_id` compatibility projection，reset為disable active target並保留歷史row。current-byte evidence 已涵蓋 active singleton、opaque CAS、same-key replay、new-key no-active=`not_found`、typed API 與 manual recovery；provider／React／完整 human E2E 仍另有 gate。

目前 M4-A 已落在 `api/routes/runtime_health.py`、`api/schemas/runtime_health.py`、`subsystems/line/runtime_alert_application.py` 及其 target application／repository，並完成 Customer Service concrete repository／UoW、durable masked handoff／outbox lineage、escalation API projection與Streamlit typed client；本輪涵蓋singleton、target API/client、去敏、create／claim／handling／resolve與hold release的focused regression為`66 passed`。這證明backend typed slice與handoff evidence，仍未涵蓋provider failure/recovery、React presentation或真實commit human E2E。

`LINE_LIFF_工會手機管理中心規範.md`自稱approved並描述`alert_group_id = NULL`，但這與current schema、formal owner與approved-for-specification-freeze alert contract衝突。其管理端／alert流程不能直接作實作授權。Current target route/client已改為closed typed view／receipt，PATCH具expected_version、reason、idempotency與correlation；health-status／health-events也掛上既有closed response model，額外runtime details不再穿透HTTP boundary。`alert_group_id = NULL`方案仍不得實作。

### 6.3 Module 4 acceptance

`Module PASS` 必須在上述 freeze 後完成typed read/reset/enable backend、CAS/replay/singleton conflict、receipt/audit/outbox、provider failure/recovery與masked UI/client contract；任何`alert_group_id` schema或physical-null方案另立approved DB WP。現在固定 `M4-A partial / NOT_READY`：singleton target、typed API、masked escalation handoff、Streamlit typed client與backend focused evidence已完成，但provider failure/recovery、React presentation與完整human E2E尚未完成。

## 7. Cross-module acceptance matrix

| Cross-module edge | Required owner／invariant | Current status |
|---|---|---|
| LIFF verified identity → binding／owner projection | LINE Identity root；owner Domain projection adapter；同一command receipt/outbox | partial；ownership successor仍需人工裁決 |
| Binding success → Rich Menu／delivery intent | committed outbox；provider failure不回滾binding | backend evidence存在；browser/real provider未驗收 |
| Inbound message → Service Help／Knowledge fallback | identity/group precedence；answer有source/version；unknown manual；業務失敗整筆rollback後另交易記錄失敗 | deterministic/manual backend與failure isolation PASS；QA/Tier 2 AI/provider deferred |
| Notification rule → intent → delivery task | configuration owner → notification intent → delivery owner；single UoW cancellation | backend focused PASS；React/manual replay out-of-scope |
| Rich Menu publication → fan-out binding intents | publication owner固定provider menu ID；published與fan-out原子 | code evidence PASS；DB replacement incomplete |
| Runtime health → alert target → LINE delivery | alert target projection owner；command no provider；durable retry | singleton／typed target backend與masked client PASS；provider failure/recovery E2E pending |
| Admin auth → all LINE modules | all enabled internal users same business capability result；root-only Account Center | authorization normalization G0-G6 PASS；does not complete modules |

## 8. 可平行處理的後續工作包與依賴

只有 exact write set 不重疊且 owner 明確的工作可平行；M3 不承接其他模組的 metadata-lock recovery hot spot：

| Work package | scope／write set摘要 | dependency | status／gate |
|---|---|---|---|
| M1 LIFF identity successor | `line_identity_bindings`唯一writer；Case Import擁有provisional registration；legacy direct writers guarded/410並逐caller退出；onboarding是binding projection outcome，不是role promotion | Alternative A、owner split與legacy exit已凍結；真實LIFF E2E仍需sandbox config | M1-A implementation-authorized／partial；B/C與provider rollout deferred |
| M2 AI Agent／Harness decision與contract | reject production full AI；M2-A deterministic harness＋durable manual fallback；Phase 2 proposed；explicit human/wrong precedence over all auto-routing | direct `reply_provider`已由durable delivery task取代；dispatch失敗時業務UoW整筆rollback，再以獨立UoW保存failure completion；M2→M4 typed handoff已完成 | M2-A backend completed／module partial；AI/provider與Tier 2 deferred |
| M3 雙向協調／派案 successor | 13 個 source-version typed projections、A–E internal typed behavior；`accepted`→fresh-effects→Assignment conversion/rematch；B–D 經typed ports整合leave/assignment owner；Phase E schema另案 | recommendation/candidate/zero-candidate與conversion boundary已凍結；不寫 Orders、Assignment、Payroll；concrete adapters與public coordination Query／Preview／Apply entrypoint仍 pending | M3-A／B–D implementation in progress；overall partial；Phase E schema deferred |
| M4 管理端／異常／轉真人 backend successor | runtime target registration/reset/enable/disable同一0-schema advisory serialization boundary；active singleton、opaque CAS、same-key replay、new-key no active=`not_found`、lock fail=0 write、unknown commit查原key receipt | Runtime Monitoring／LINE operator為target owner；escalation不競寫 runtime target | M4-A implementation-authorized／partial；React/provider/rollout deferred |
| Cross-module UI／browser acceptance successor | 各模組 typed client/UI、diagram completeness、controlled browser/provider acceptance與redaction evidence；不改正式owner | 對應 M1～M4 backend／decision gates完成；React migration／route registry另由integration owner | proposed；只可規劃，不授權cutover |

依賴關係：`M1 decision → M1 implementation → M1 browser acceptance`；`M2 human router decision → M2 contract → M2 provider（若核准）`；`M3 successor contract → recommendation／assignment implementation → Scheduling／Orders／Staff Payables consistency → targeted acceptance`；`M4 contract decision → M4 backend → human escalation acceptance`；Cross-module UI／browser work只能在對應 backend gate後進行。M1/M2/M4的文件與decision工作可平行；M3 不得綁定 Rich Menu／Option B 或其他模組 migration recovery。

## 9. Human decisions required

1. 確認Eraser workspace title與四個module ID／名稱mapping；workspace總圖不得使用 M1 URL 代替。
2. Module 1：採用`line_identity_bindings`唯一writer／owner projection split；指定`provisional_client_registrations` owner；裁決舊writer／`bind.html`退出方式。
3. Module 2：採 deterministic routing，或另立AI router architecture；在裁決前禁止AI provider、prompt、seed、Knowledge publish與自動回答。
4. Module 4：接受`reset = disable active group target`兼容投影方案；確認singleton、CAS、replay與manual recovery owner；拒絕偷偷新增`alert_group_id`。
5. Module 3：確認「雙向智慧協調與派案博弈」的 recommendation／candidate／zero-candidate／acceptance-rematch／leave-date-availability contract與五個工作包邊界；若後續需要 schema，另立 approved DB Work Package；不得以 Rich Menu／Option B evidence 代替 M3 決策。

## 10. Status與下一個可交付結果

本計畫目前為 `approved-for-specification-freeze`，不是 `completed`。四模組仍須完成各自 implementation、schema／DB、provider／browser 與 evidence gates；不得把本次文件裁決或局部 backend evidence 當作流程完成。

下一個安全可交付結果是各 lane 依本次 freeze 建立獨立 implementation successor；LIFF sandbox、schema implementation、production/provider approval與真實 E2E 仍是 unresolved。此計畫不授權任何外部 Eraser 寫入、provider call、React cutover 或新的 DB schema。

## 11. 2026-08-21 人工裁決同步與 freeze 邊界

本節將人工批准的 M1–M4 decision identity 與 staged implementation authority 同步至本計畫。production approval 僅限下列 exact slices；不包含 rollout、provider、current DB 或外部平台寫入。

- M1 採 Alternative A：`line_identity_bindings` 是唯一 writer；Case Import 擁有 provisional registration；legacy direct writers 必須 guarded／410 並逐 caller 退出。onboarding 只是 binding projection outcome，不是 role promotion。Customer Service 擁有 `binding_failed_assistance`，但 dual-role 與 two-failure trigger 尚未實作，需 M4 escalation；真實 verified-token／LIFF／Rich Menu E2E 仍受 sandbox config 阻擋。
- M2 reject production full AI now；approve Phase 1 deterministic harness＋durable manual fallback；Phase 2 維持 proposed。explicit human／wrong 優先於所有自動路由；只有不含 human／wrong marker 的 exact protected identity alias 才能進 identity。direct `reply_provider`已退出webhook transaction，Service Help只建立durable delivery task；業務dispatch失敗時原UoW整筆rollback，再以獨立UoW保存本次failure completion。current implementation 已由 Service Help application 透過 typed `CreateHumanEscalation`／escalation gateway 交接 M4；保留 M2 `service_help` sole-writer、M4 Customer Service owner 與 typed-port boundary，不宣稱 M2 overall PASS。
- M3 approve Scheduling Matching Coordination subsystem 與 Phase A–D；Phase E schema 未授權。accepted 僅是 decision→fresh-effects→Assignment conversion/rematch typed request；M3 不寫 Orders、Assignment 或 Payroll。Phase D 只能透過 typed ports 整合 leave／assignment owner，不接管 root writer。
- M4 target approve history-preserving disable、active singleton、opaque CAS、same-key replay、new-key no-active=`not_found`、Runtime Monitoring／LINE operator，以及 registration/reset/enable/disable 共用 0-schema MySQL advisory serialization boundary。取得 lock 失敗固定 0 write；commit 後 release unknown 視為可能已提交，API 不回 success，依原 key 查 receipt。runtime target owner sole-writes `runtime_alert_application`；M4 escalation 不競寫。
- M4 escalation approve Customer Service owner、Anomaly 只作 source；HIGH 只存在 escalation。candidate inventory 僅兩張 additive tables，0 seed／backfill／destructive；M2 owner sole-writes `service_help` 並接 `TicketReferral`，escalation 只走 typed port；runtime target owner sole-writes `runtime_alert_application`，escalation 只產生 committed masked intent；Scheduling 不在 escalation transaction。

### 11.1 Latest implementation authority (2026-08-21)

- `M1-A`：核准 canonical binding ownership／legacy guarded-or-410 implementation；真實 LIFF／verified-token E2E 只可在受控 sandbox，B/C、two-failure、dual-role、retirement successor 與 provider rollout 不在本 slice。
- `M2-A`：核准 deterministic Tier 1 precedence、typed closed outputs、durable manual fallback 與已確認的 `reply_provider` drift 修正；0 AI provider、0 Knowledge direct authorization、Tier 2 AI deferred。
- `M3-A`：核准 Matching Coordination foundation／typed contract slice；M3 Phase B–D 已核准並依 exact write set in progress；不授權 M3-E DDL 或任何 Orders／Assignment／Payroll root write。
- `M4-A`：核准 runtime target singleton／typed API／opaque CAS／masked escalation application slice；React presentation、AI/provider、rollout與其他 schema change deferred。`M4-DB` 已通過 disposable qualification，並依 2026-08-22 最新人工裁決以 fast local in-place 路徑套用 current `lu_test_dataset_contract_signing_v4`；post-apply descriptor `exact`、兩張 owned tables 皆 0 rows，DB 狀態為 `DB_CHANGE_READY_LOCAL_APPLIED`。production／cutover仍未授權。
- Current integration disposition：M1-A 的 `identity_application.py`／`line_identity.py`／registration test 已修正「新 provisional registration 不得依賴既有 customer lookup」分支；M1 identity／legacy-surface／registration／cutover focused suite `74 passed`，並補上 `/api/line/config`、`client-info`、`register`、`bind-page`、`register-page` 與 `/api/line/bind` 在 canonical runtime 的 410／零 DB 寫入 characterization；受控 LIFF sandbox E2E 為 `3 skipped`（未提供 sandbox config），真實 verified-token browser flow 仍未完成，故維持 `partial / NOT_READY`。M2-A deterministic router／manual fallback／M2→M4 escalation gateway本輪 focused suite為 `31 passed`；full AI/provider、Tier 2 與 QA evidence 仍 deferred，故 M2 維持 `partial / NOT_READY`。M3 current evidence包含13個source-version typed projections、A–E internal typed behavior、初始criteria public Preview／Apply與focused regression；其餘11個owner adapters／完整public coordination entrypoints、cross-domain receipt／E2E仍 pending，故 M3 維持 `partial / NOT_READY`。M4-A application focused evidence保留；M4-DB current local apply已完成且descriptor `exact`，DB狀態為 `DB_CHANGE_READY_LOCAL_APPLIED`；因immutable tables無法兼得commit E2E與scoped cleanup，本輪API閉環`NOT_RUN`，provider failure/recovery、React/client與完整human E2E仍未完成，故M4仍為`partial / NOT_READY`。
- M3-A current-byte amendment：customer `accepted` 的 fresh conversion 只有在 request 明確指定 package 內 `eligibility=eligible` 且 `willing=willing` 的 candidate 時才建立；缺少 candidate 或 fresh effects 仍相符但 willingness／eligibility 不符固定輸出 typed error，fresh effects 已不相符則只建立 `rematch_required` reference；此 guard 不新增 persistence、outbox 或 Orders／Assignment root write。
- M3 focused-count correction：current A–E internal focused regression evidence 為 `82 passed`；此數字只代表 typed internal behavior／contract coverage，不代表 concrete owner adapters、public coordination entrypoint、cross-domain E2E、M3 overall PASS或Phase E schema授權。
- 所有 slice 在 focused tests、receipt／redaction／replay／manual-recovery evidence 完成前維持 `partial / NOT_READY`；不得以 implementation started 或單一測試宣稱 Module PASS。

### DB gate（本次只凍結候選盤點／規格 planning）

| Lane | Scope / Change inventory | Static | Descriptor | Read-only plan | Engine | Developer acceptance | Summary |
|---|---|---|---|---|---|---|---|
| M3 Phase E | **PASS**：candidate inventory／spec planning only；無 DDL、seed、backfill、destructive | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | `DB_CHANGE_NOT_READY` |
| M4 escalation | **PASS**：local-only schema apply已人工核准；0 seed／backfill／destructive | PASS | PASS | PASS | PASS | PASS | `DB_CHANGE_READY_LOCAL_APPLIED` |

### Unresolved

LIFF sandbox config／真實 E2E、M3 B–D、schema implementation 與 canonical release／descriptor（M4-DB disposable artifacts除外）、production/provider/external-side-effect rollout、M4 escalation threshold／trigger catalog 與所有 focused acceptance 均保留為後續 gate。

## 12. 2026-08-22 M3 Query current-byte同步

M3 initial criteria Preview／Apply之外，13-source Query composition已接入現有 typed owner reads，並新增
closed `POST /api/v1/matching-coordination/{case_no}/query`；current focused evidence為 `28 passed`。這只完成
read-only Query slice，不代表 matching package、criteria-diff resend、zero-candidate、rematch、leave/date或
Apply fresh-lock完成。

第 14 節人工裁決已取代本文件較早的「Phase E未授權」文字：M3 additive artifacts與 disposable fresh／
preserve qualification可執行，但仍禁止套目前 DB、production、source replacement、seed、backfill、
destructive與provider。Current DB未套M3 schema，所以 real API workflow固定 `NOT_RUN`。

新的 anti-drift blocker為 business policy未閉合：正式規格只有「單人完整覆蓋優先；否則2–4連續無重疊
segments」不變量，尚未指定candidate ranking、segment combination與zero-candidate soft-criteria policy。
在人工裁決前不得把current generic／identity-ignoring workflow包成public endpoint；M3維持
`partial / NOT_READY`。

## 13. 2026-08-22 M3 人工選擇 policy 同步

人工已裁決三項 blocker：候選依姓名穩定排序即可，最終由工會人員選擇；多段服務由工會人員自行組合；
zero-candidate 的放寬 criteria 由工會人員自行選擇。Server 不新增推薦分數、自動 segment optimizer 或
自動 soft-criteria relaxation。

Current implementation 已新增 closed matching-package Preview 與 zero-candidate Preview：前者驗證
eligible＋willing、coverage、1 或 2–4 segments、sequence 與服務日期守恆；後者驗證 explicit selection
屬於 current criteria snapshot，並把 policy/version、selection、source tuple 納入可重現 fingerprint。
兩者皆為零寫入，且不寫 Orders／Assignment／Scheduling root、不呼叫 LINE provider。

Current focused evidence為 `103 passed`，AST/import PASS。未套 current DB，real API workflow `NOT_RUN`；
criteria-diff persistence、Apply fresh-lock後的完整跨域閉環及其他 M3 branches仍需後續小工作包，故 M3
維持 `partial / NOT_READY`。

## 14. 2026-08-22 M3 criteria history current-byte同步

既有 M3 criteria snapshot immutable lineage 已接入 read composition：history 必須非空、版本唯一遞增、
case identity一致，且末筆與 current snapshot 精確相同，否則 fail closed。全部 M3 focused regression為
`132 passed`。

這不代表 criteria-diff branch 完成。candidate-contact 現有事件只持久化 willingness 與文字 reason，缺少
規格要求的 affected criteria、original willingness 與 pain-resolved evidence，不能精確分流 G1／G2／G3。
在後續獨立 persistence 小包獲核准前，不暴露 public criteria-diff Preview、不修改 schema，也不從 current
projection 推測歷史。M3 維持 `partial / NOT_READY`。

## 15. 2026-08-23 M3 willingness／recontact current-byte同步

依 2026-08-22 人工裁決，M3 Scheduling Matching Coordination 擁有「哪些 candidate 因 criteria diff
受影響」的判定；LINE 只接收 committed exact recipient intents 並負責 delivery／retry，不新增一個跨流程
的 LINE business state machine。Willingness／recontact closed states 固定為
`unconfirmed → pending → willing|unwilling|expired → stale → recontact_previewed →
recontact_queued → pending`，或 `stale → silent_excluded`；其他 transition 固定 fail closed。

Current implementation 已完成下列 staged slice：

- candidate willingness 與 immutable event state 均為 closed enum；event 綁定 candidate／staff、criteria
  snapshot、完整 source tuple、stable reason 與 affected criteria。snapshot source mismatch、candidate-staff
  identity drift、同 candidate／snapshot 重複事件、legacy refusal 與新 lineage 重複代表同一 candidate 均
  fail closed。
- criteria diff 依 before snapshot 的 explicit lineage deterministic 分流 G1 reconfirm、G2 reprobe、G3
  silent exclude；只有 current eligible G1／G2 可被工會人員選入 Apply。每筆 committed recontact intent
  保存 opaque staff reference、route/action/reason、before／after snapshot、diff fingerprint、source tuple與
  optional package lineage；receipt JSON 與 LINE outbox payload均可 typed round-trip，G3不建立 intent。
- non-initial Apply 沿用既有 outer UoW：claim/replay → M3 root lock → typed owner preflight lock set → 所有
  owner facts/history `for_update=True` read → candidate-pool locked readback → fresh recompute → immutable
  lineage／receipt／outbox → single commit。M3 repository不鎖或寫 Orders／Assignment／Leave／Payroll root；
  optional leave/conversion reference沒有 locked port時固定 fail closed。
- Public API current routes包含 Query、initial criteria Preview／Apply、package Preview、criteria-diff
  Preview／Apply、zero-candidate Preview／Apply、rematch Preview／Apply、service-date-rematch Preview、caregiver-selection Apply與
  customer-decision Apply。actor由
  authenticated admin derivation；Apply要求 Idempotency-Key／X-Correlation-ID；client不得指定route group、
  provider payload或Orders mutation欄位。service-date request的assignment ID僅引用既有owner fact，production
  composition會以同一request connection唯讀核對assignment／staff／原日期，再讀shifted-date availability。
- package fingerprint 會由完整 candidate criteria／coverage／notification lineage、segments、snapshot與
  source tuple重算；persisted JSON fingerprint與`package_digest`欄任一漂移皆 fail closed。Malformed
  receipt／event JSON統一轉成 typed persistence error，不漏出raw parser exception。

Current全部 `test_matching_coordination_*.py` scoped regression為 `154 passed`。另外，M2 webhook failure
isolation與deterministic／manual fallback精確測試為`21 passed`；M4 closed masked audit／target／human
escalation backend精確測試為`67 passed`。本 slice為0 SQL schema、
0 seed、0 backfill、0 destructive、0 current DB apply、0 provider。package JSON fingerprint與column digest
tamper hardening、rematch Preview／Apply與service-date專用Preview已完成；尚未完成的是leave專用public API、
service-date Apply fresh-lock、canonical owner receipt composition／saga閉環與具M3 schema的real DB/API E2E。leave typed preview核心雖已存在，
production composition目前沒有canonical leave-receipt owner port；只加fake可過的route不算完成。因此 M3
維持 `partial / NOT_READY`，不得宣稱四條 Eraser business flow全部完成。

## 16. 2026-08-23 backend closeout 與封存裁決

本節取代前文較早的 M3 pending/current-byte 敘述。本次最後兩個小包已完成：

- service-date Apply 在既有 outer UoW 內鎖定 M3 root，fresh-read owner service dates、assignment 與 shifted-date availability，重算 preview；stale fingerprint 在 lineage／receipt 前 fail closed。
- leave Preview／Apply 已接入 Scheduling-owned immutable canonical receipt。Preview 唯讀核對 case、package、criteria、leave version、original staff 與完整 source tuple；Apply 在同一 outer UoW 重新讀 receipt，將 canonical leave identity/version/fingerprint 綁入 M3 source tuple，過期或不一致即 rollback。M3 不寫 Leave、Orders、Assignment、Payroll 或 LINE provider 根事實。
- closed public routes包含 `preview/leave-impact`、`apply/leave-impact`、`preview/service-date-rematch` 與 `apply/service-date-rematch`；Apply要求 client-supplied idempotency與correlation。
- 全部 scoped `test_matching_coordination_*.py` regression為 `165 passed`；OpenAPI readback包含兩支 leave routes。pytest cache permission warning不影響測試結果。

依最新人工裁決，本計畫以 backend 收斂完成封存；不把下列外部項目虛報為 PASS：M1 sandbox LIFF E2E由使用者略過、M2 Tier 2 AI／provider未採用、M3 real DB/API／跨域 UI E2E由使用者自行驗收、M4 React／provider E2E延期。若日後發現問題，應另開新任務，不重新啟用本計畫或擴張本次 owner／schema／provider範圍。

