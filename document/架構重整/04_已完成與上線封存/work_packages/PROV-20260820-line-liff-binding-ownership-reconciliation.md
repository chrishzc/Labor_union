---
doc_type: work-package
declared_status: completed
identity: PROV-20260820-line-liff-binding-ownership-reconciliation
date: 2026-08-20
owner: LINE Identity / LIFF Onboarding Integration Owner
domain: LINE Integration / Case Import / Customer Identity
subsystem: LIFF identity claim, binding review, and owner projection reconciliation
scope: human decision package for canonical identity ownership and LIFF successor requirements
write_set:
  - document/架構重整/02_決策與退役執行記錄/PROV-20260820-line-liff-binding-ownership-reconciliation.md
acceptance:
  - human confirms one binding-root owner and one successor command/review/receipt/outbox contract
  - all conflicting LIFF plans and legacy writers have an explicit successor or legacy-exit disposition
out_of_scope:
  - production code, tests, schema, migration, provider, role promotion, deployment, and route cutover
approval_required: human decision before any production, schema, migration, provider, or role mutation; latest approval authorizes M1-A exact implementation and controlled M1-E2E only
authority: document/架構重整/01_規格基線/23_LINE身分管理與解除正式規格.md
---

# LINE LIFF 身分綁定 ownership reconciliation gap

## 1. 目的與狀態

本文件只把 LIFF 身分綁定、重新綁定審核及 owner projection 的責任收斂成可交給實作工作包的
裁決與邊界。它不是正式規格的 successor；最新人工裁決僅授權 M1-A exact production implementation
與受控 M1-E2E，不授權 schema、migration、provider rollout、role promotion 或 entry cutover。

目前狀態為 `approved-for-specification-freeze`。Alternative A 已凍結 owner；相互衝突的功能計畫與 live path 仍標記為
`human-decision-required` 或 `live-drift`，不得以現況能執行、既有測試通過或 self-declared
`approved` 取代正式規格 23，也不得直接施工。

## 2. Business scenario

使用者從 LIFF 以 server-side 驗證的 LINE ID token 開始身分流程，輸入最小必要證明後，系統必須：

1. 由 LINE Identity 建立或查詢唯一的 binding root fact；
2. 在沒有衝突時，以同一 application command 建立 binding、更新必要 owner projection、留下 receipt
   與 outbox；
3. 發現既有其他 LINE 身分時，只建立可人工審核的 rebind claim，不直接覆蓋任何 owner projection；
4. 人工 approve／reject 依 expected version、fingerprint、idempotency、actor、reason 與 audit
   決定是否完成同 subject type 的 replacement；
5. 所有外部 LINE 推播、Rich Menu 套用與通知由已提交 outbox／durable worker 執行，不能由 LIFF
   route 或 UI 直接呼叫 provider。

## 3. Current authority and non-negotiable invariants

正式規格 23 是本包的 current authority：

- `line_identity_bindings` 是 LINE User ID 與 customer／staff／admin subject 關係的 SSOT。
- `clients.line_user_id`、`staff.line_user_id`、`admin_users.linked_line_user_id` 只是 owner
  projections；它們不得取代 binding root fact。
- replacement 第一版只允許同 subject type 修正 subject reference；customer 不得由 LIFF 直接變成
  staff 或 admin。
- revocation 先建立 `revocation_pending` root，且在 default Rich Menu provider 成功前保留 owner
  projection；完成後才清除 projection 並轉為 `revoked`。
- Query 必須唯讀、Preview 必須零寫入、Apply 必須鎖定 fresh facts；所有命令都要有版本、冪等、receipt、
  audit 及明確的 outbox／retry／conflict 邊界。
- Streamlit／React／LIFF 都只能使用 typed API；任何 raw table、raw provider payload、完整 PII 或
  legacy role 判斷都不是 binding authority。

相關正式規格 20 另確認 LIFF 只信任 server-side 驗證 ID token 與正式 binding，Rich Menu／per-user
binding 以 wen DB 為 SSOT；已綁定的 internal user 之客服／審核業務能力不因 persisted role／capability
改變。

## 4. Observed contract conflicts and live drift

### 4.1 LIFF 功能計畫與正式規格 23 的衝突

| Source | Observed wording／behaviour | Contract classification | Required disposition |
|---|---|---|---|
| `document/功能開發計畫/LINE_LIFF_舊客快速身分綁定與防冒領規範.md:21` | 首次綁定直接寫 `clients.line_user_id`，並把角色升級為 `customer`。 | `live/spec-conflict`；把 projection 當 writer，且把 role promotion 當業務結果。 | 保留「已核對後可建立 customer binding」的場景意圖，但改寫成 canonical LIFF claim → LINE binding command → owner projection adapter；禁止 route 直接寫欄位或以 role 宣告成功。 |
| 同文件 `:23` | 已有其他 LINE ID 時建立 `client_rebind` review，禁止直接覆蓋。 | `compatible-intent`，但 review owner／root fact 未寫清楚。 | 明確以 `line_identity_bindings`、binding version、old/new LINE ID、proof fingerprint 與 reviewer actor 作 review evidence；approve 僅能走 canonical review command。 |
| `document/功能開發計畫/LINE_LIFF_身分先行與服務登記導流規劃.md:24`、`:34` | 以 `clients`／政府案件分流、建立 provisional registration 與第二次失敗工單。 | `owner-ambiguous`；資料登記、customer identity binding、客服 ticket 三種責任混在 LIFF 導流。 | 人工裁決 provisional registration 的 owner（建議 Case Import），LINE 只提供 verified identity／binding intent；客服 ticket 只能由 Customer Service typed workflow 建立。 |
| `document/功能開發計畫/LINE_LIFF_工會手機管理中心規範.md:1` | self-declared `approved` 的 mobile-admin／alert／rebind 複合範圍，另宣稱 `alert_group_id` 單一 owner 與最高權限重設。 | `human-decision-required`；並非正式規格 23 的 binding contract，且混入 Alert／Access／Scheduling。 | 不把此文件當 binding owner authority；另由各 owning Domain 建 successor。其 LIFF binding 部分只能依本包裁決，alert／role／業務 mutation 不得在此包實作。 |

### 4.2 Live application／API 的現況

目前 canonical path 已大致符合正式方向：

- `api/routes/line_identity.py:129-178` 先驗證 LIFF token，再呼叫 flow open／validate 與 customer
  preview；`api/routes/line_identity.py:186-218` 的 customer apply 交給
  `LineIdentityApplication`，而不是讓 route 直接寫 owner table。
- `subsystems/line/identity_application.py:105-128` 以同一 application workflow 消費 flow、重建
  candidate、建立 binding 或 review，並於結果後排入 LINE delivery task。
- `subsystems/line/identity_review_application.py:145-210` 以 review snapshot、owner adapter、binding
  root、receipt 與 Rich Menu／delivery outbox 完成人工決策；這是後續 successor 應保留的 canonical
  command boundary。
- `infrastructure/mysql/line_identity_owner_adapters.py:35-52`、`:78-99`、`:131-147` 將 customer／staff／admin
  projection 更新包在 typed owner adapters；`line_identity_bindings` 仍由 LINE identity repository
  管理。

但仍有明確 live drift／退出責任：

- `subsystems/line/client_binding_application.py:13-60` 與
  `subsystems/line/identity_review_workflow.py:114-160` 仍保留以 connection/cursor 直接讀寫
  `clients.line_user_id`、建立 `line_confirmation_requests` 與 enqueue legacy task 的舊 writer。
- `line/line_bot.py:316-339` 仍保留 `/api/line/bind` caller；canonical runtime 由
  `line/line_bot.py:253-263` 的 `_require_legacy_line_surface` 回 `410`，因此目前屬 guarded legacy
  path，而非可當作 current writer 的證據。其 helper／tests 仍存在，必須由 successor package 明確
  決定保留為歷史 read／診斷、包成 canonical adapter，或移除。
- `subsystems/line/identity_review_workflow.py:397-479` 的舊 approve path 可直接更新
  `clients.line_user_id`；canonical API 已改用 `api/routes/line_identity.py:365-397` 的
  `LineIdentityReviewApplication`，但 dual implementation 仍造成 owner／replay／receipt／PII 邊界
  不可由檔案存在推定已退出。
- `db/schema_parts/155_line_identity_review_configuration.sql:3-21`、`:59-131` 已建立 canonical
  binding root、immutable event 與 legacy import／anomaly path；`db/schema_parts/186_line_identity_management.sql:1-69`
  已補 revocation pending／completed saga。這是現況證據，不是本包的 schema change 授權。
- `db/schema_parts/146_provisional_client_registrations.sql:3-14` 將 provisional row 以
  `line_user_id` 保存，但未在正式 23 內明確指定其 owning Domain、是否為 binding root、與正式 customer
  claim 的 commit／replay 關係；這是 owner decision gap，不得由 LIFF route 自行補定義。

## 5. Recommended ownership disposition (requires human confirmation)

建議採用 Alternative A：

### A. Canonical split ownership（recommended）

| Responsibility | Recommended owner | SSOT／write rule |
|---|---|---|
| verified LIFF ingress、flow、LINE User ID、binding status/version、binding events | LINE Integration／LINE Identity Management | `line_identity_bindings` 與 `line_identity_binding_events`；只由 typed application command 寫入。 |
| customer／staff／admin 的人員、案件、帳號根事實 | 各 owning Domain（Customer／Staff／Access） | LIFF 不直接改 root fact；透過 typed owner port 更新 projection。 |
| `clients.line_user_id`、`staff.line_user_id`、`admin_users.linked_line_user_id` | 各 owning Domain 的 projection adapter | 只在同一 outer UoW、已驗證 binding command 後更新／清除；不得成為查詢身分唯一來源。 |
| rebind／staff verification／admin binding review | LINE Identity Management | `line_review_requests`、review decision event、expected version、proof fingerprint、actor／reason、receipt；approve／reject 走唯一 typed decision command。 |
| provisional registration row、其 survey／source lineage 與 case bootstrap | Case Import（recommended; human confirmation required） | `provisional_client_registrations` 是暫存／來源 lineage，不是 binding root；需由 Case Import typed workflow 管理 replay、conflict、retention 與轉正式 case。 |
| customer service assistance ticket | Customer Service | binding failure 只發 typed ticket intent／outbox；LINE 不直接持有客服狀態。 |
| Rich Menu publication／per-user binding／external delivery | LINE Integration | provider 只由已提交 outbox／durable worker 執行；provider receipt 不取代 binding／review receipt。 |
| `line_users.role` | compatibility projection only | 不作業務 authorization 或 LIFF success criterion；不得由 LIFF 直接 role promotion。 |

### B. Compatibility adapter（alternative; not recommended）

允許 legacy helper 暫時轉接 canonical claim／review command，但 adapter 必須：

- 不直接改 `clients.line_user_id`、`staff.line_user_id` 或 `admin_users.linked_line_user_id`；
- 不直接建立 legacy review row 作為新 root；
- 保留原 caller 的 410／replacement policy、唯一 idempotency mapping、PII redaction 與退役期限；
- 由獨立 legacy-exit Work Package 建立 caller scan、focused regression、restore trigger 與最終移除裁決。

### C. LIFF owns customer root directly（reject）

不採用。這會讓外部 LIFF 同時擁有 verified identity、customer root、role promotion、客服 ticket 與
provider side effect，違反正式規格 15／20／23 的 Domain ownership、typed command、outbox 與
projection 邊界，也會把 `clients.line_user_id` 錯當成 binding SSOT。

## 6. Successor requirements after approval

後續要實作時，至少需另立一個已核准 successor Work Package，精確寫明：

1. **唯一 ingress**：LIFF 僅接受 server-side verified ID token；query-string `userId` 與
   development fallback 只能依現有 formal／environment boundary fail closed，不能成為 production identity。
2. **唯一 bind command**：customer／staff／admin claim 都由 LINE Identity application 建立；owner adapter
   只處理同一 outer UoW 下的 projection，禁止 route／UI／provider 直接 SQL。
3. **rebind review**：建立 review 前保存 old/new LINE User ID（internal-only）、subject type/reference、
   expected binding／owner version、proof fingerprint、flow ID、idempotency／correlation、actor 與 reason；
   approve 只准同 subject type、fresh lock、collision check、binding event、owner projection update、receipt、
   audit 與 outbox 同步完成；任何 stale／collision／ambiguous source 固定拒絕並要求重新 preview。
4. **provisional registration boundary**：先人工確認 Case Import owner、正式 case bootstrap command、
   binding intent 與 ticket intent 的先後順序；不同 payload replay、未完成 case、duplicate source 與
   unresolved identity 必須有 typed conflict／manual review，不得讓 registration endpoint 猜測或直接寫
   `clients.line_user_id`。
5. **review／revoke separation**：rebind review 不得重用 revocation request；revocation 仍照正式 23 的
   durable saga，provider success 前不得清除 owner projection。
6. **receipt／outbox**：每個 canonical command 產生可重播 receipt；external LINE／Rich Menu 只由 committed
   outbox／worker 執行；provider failure 不回滾已提交 root，但必須保留 retry／dead-letter／manual override
   boundary。
7. **PII／redaction**：完整 LINE ID、phone、identity-card、password、survey payload、provider ID、proof
   snapshot 與 internal note 僅能在明確 restricted storage／typed internal view 使用；URL、log、browser
   storage、一般 DOM、測試 receipt、evidence 與錯誤訊息一律遮罩或不提供。
8. **legacy exit**：對 `/api/line/bind`、legacy `line_confirmation_requests` writer、舊 approve path、
   `bind.html`／`bind-page`、任何 direct SQL helper 做 caller inventory；逐項給出 `retain-readonly`、
   `410`、`adapter` 或 `remove` 的裁決與 focused regression，未完成前不得宣稱 LIFF cutover 完成。

## 7. Human decision points

以下項目已由 2026-08-21 Alternative A 裁決；尚未完成者是 implementation／E2E acceptance，不構成新的 ownership decision：

1. 是否採用 Alternative A，確認 LINE Identity 是 `line_identity_bindings` 的唯一 writer，owner
   projections 由各 owning Domain adapter 在 canonical command 內更新。
2. 是否接受 `provisional_client_registrations` 由 Case Import 擁有；若否，指定唯一 owner、root／projection
   類型、retention、replay、conflict 與正式 case bootstrap boundary。
3. 是否將舊 `client_binding_application.py`／`identity_review_workflow.py` 定位為 guarded legacy-only，
   或核准獨立 compatibility adapter successor；在裁決前禁止讓它們成為新 LIFF writer。
4. 是否把 LIFF onboarding 中的「角色升級為 customer」刪除／改稱為 binding projection outcome；不得把
   `line_users.role` 保留為業務 authorization。
5. 是否由 Customer Service 擁有 `binding_failed_assistance` ticket；若要由其他 Domain 擁有，需另立
   cross-domain decision，不能在 LIFF package 中猜測。

## 8. Dependencies and evidence

### Current dependencies

- `document/架構重整/01_規格基線/00_Global_共同契約.md`：Query／Preview／Apply、UoW、idempotency、typed
  error、receipt、outbox 與 SSOT 類型。
- `document/架構重整/01_規格基線/15_正式規格索引與裁決總表.md`：LINE ownership (`CON-LINE-001`)、
  internal enabled user policy (`CON-AUTH-001`) 與 current authority order。
- `document/架構重整/01_規格基線/20_LINE客服與月嫂自助服務正式規格.md:15-22,120-124`：verified LIFF
  identity、Rich Menu binding、LINE／Domain boundary 與 role-independent mobile-admin contract。
- `document/架構重整/01_規格基線/23_LINE身分管理與解除正式規格.md:12-78`：binding SSOT、projection、
  replacement／revocation／review／receipt／outbox contract。
- `document/架構重整/02_決策與退役執行記錄/PROV-20260816-react-admin-phase3a-line-customer-service-identity-specification.md:43-65,90-113`：
  React 只顯示 typed identity/revocation result，不能直接寫 projection；其 mutation scope 與 browser gate
  仍受原 Work Package 約束。
- `document/架構重整/02_決策與退役執行記錄/PROV-20260817-react-admin-line-query-page-slice-work-package.md:1-9,52-65`：
  React query-only slice 不包含 LIFF binding mutation；不能把 query wiring 當成 LIFF owner decision。
- `document/架構重整/02_決策與退役執行記錄/Import_Entry_and_Legacy_Writer_Retirement_工作包.md:95-107`：
  Client temporary Web→LIFF 與 Staff current LIFF writer 仍 blocked，需獨立 E2E／owner 裁決。
- `document/架構重整/03_追蹤清單與證據/evidence/PROV-20260816-react-admin-phase3a-line-customer-service-identity/open-findings.md:11-17`：
  真 browser／controlled binding evidence 尚未完成；不得把 static tests 升格為 production acceptance。
- `document/架構重整/03_追蹤清單與證據/evidence/2026-08-09_external_integration_line_access_revalidation_receipt.md`：
  canonical review、legacy route 410、temporary registration typed owner 的現況證據；receipt 不取代本包人工裁決。

## 9. Required tests and evidence for successor

此 proposed package 不執行下列測試，也不產生 acceptance receipt；以下是核准 successor 後的必要驗收：

- route／caller inventory：證明所有 current LIFF routes 只通往 canonical application；legacy direct writer
  只回 410、readonly 或明確 adapter，沒有 second writer。
- Domain／Subsystem：customer／staff／admin initial bind、same-subject rebind、cross-subject rejection、
  ambiguous proof、stale version、collision、idempotent replay、payload mismatch、rollback、receipt／audit／outbox。
- provisional registration：same payload replay、different payload conflict、case bootstrap failure、
  binding intent ordering、PII redaction 與 unresolved manual review。
- revocation：`bound → revocation_pending → revoked`、provider success／process crash replay、retryable／
  nonretryable failure、manual override、owner projection timing。
- API／client：strict schema、typed errors、verified token only、no raw dict／full PII in DOM、URL、log 或 receipt；
  React query／mutation packages 只能驗證自身 frozen endpoint budget。
- runtime／browser：使用 disposable controlled LIFF identity and database，驗證 Network → typed result → DOM
  → re-query；不得使用 production LINE ID、phone、provider secret 或正式資料。

### M1 current completion disposition (2026-08-22)

最新人工裁決為「M1 可以跳過驗收，後面有問題另開新任務」。本裁決只記錄目前交付邊界，不改正式規格、owner、provider 或 route cutover：

- `code_closure`: `PASS_BY_FOCUSED_TESTS`；本次 current regression 為 18 tests passed，涵蓋 `tests/test_line_legacy_review_routes_retired.py`、`tests/line/infrastructure/test_line_cutover_boundaries_stage10.py`、`tests/line/infrastructure/test_line_liff_entrypoint.py`。既有 direct evidence 仍以本節既有 backend/static receipt 與 route tests 為準，不重複加總廣泛 suite。
- `real_liff_e2e`: `WAIVED_OR_SKIPPED_NOT_PASS`；不得將 waiver／skip 解讀為 runtime PASS。既有 browser evidence `BLOCKED_REAL_BROWSER_EVIDENCE` 仍有效。
- `provider`: `NOT_RUN / NOT_AUTHORIZED`；本裁決不授權 LINE provider、正式資料或 production operation。
- `future_issues`: 任何後續真實 LIFF、provider、route cutover、legacy caller 或 runtime 問題，另開 successor Work Package／新任務，不回寫為本次 code closure 的 PASS 證據。

## 10. Legacy exit and out-of-scope

### Legacy exit

退出條件是：Alternative A 或人工指定 successor 已核准；每個 legacy caller 有 disposition、owner、replacement、
focused regression、restore trigger；temporary Web→LIFF 有真實 verified-token／registration／binding／Rich Menu
end-to-end evidence；canonical route 與 worker 的 receipt／outbox coverage 完成。未滿足前，legacy helper 可保持
guarded／readonly 以避免資料遺失，但不得再被新功能引用。

### Out of scope

- 不修改正式規格 15／20／23、既有功能開發計畫、02／03 README 或任何 index。
 - 本文件自身不修改 production code、tests、schema／migration／seed／backfill、release metadata 或資料庫；M1-A 的 production implementation 只能由獨立 exact write set 執行。
- 不執行 LIFF／LINE provider call、Rich Menu publish、role promotion、external notification、deployment、
  route cutover、React presentation integration 或 Streamlit retirement。
- 不裁決 Alert `alert_group_id`、Knowledge、Scheduling、Customer Service ticket schema 或其他跨 Domain
  owner；只提出其與 LIFF binding 的 dependency。

## 11. DB and implementation gate

本文件只有既有 live schema evidence，沒有 schema write set；因此本次不執行 DB migration gates、不產生 migration
plan、不操作任何資料庫。任何後續要改 `line_identity_bindings`、`provisional_client_registrations`、legacy review
table 或 owner columns，必須另立 exact Work Package，重新通過 DB change execution gate，並取得人工授權。

| Gate | Status | Evidence／command |
|---|---|---|
| Scope gate | PASS | 人工已核准 Alternative A 與 M1-A exact implementation；schema／provider rollout／role mutation 仍未授權。 |
| Change inventory | PASS | 本次 only-new-document；無 schema／seed／backfill／destructive diff。 |
| Static release gate | NOT_RUN | 無 schema release。 |
| Descriptor gate | NOT_RUN | 無 owned-object 變更。 |
| Read-only plan gate | NOT_RUN | 不適用；未執行 migration plan。 |
| Engine verification gate | NOT_RUN | 不操作 MySQL；既有 schema 僅作 live evidence。 |
| Developer acceptance gate | NOT_RUN | 未執行 launcher／DB upgrade。 |

結論：`DB_CHANGE_NOT_READY` 不適用於本次文件新增，但任何後續 DB mutation 在新的 exact package 通過前均為
`DB_CHANGE_NOT_READY`。

## 12. 2026-08-21 人工裁決：Alternative A specification freeze

本文件狀態為 `approved-for-specification-freeze`（frontmatter `declared_status: approved`）。最新人工裁決在此狀態上增補 M1-A exact production implementation authority；不授權 schema／DB、LINE provider rollout、role promotion、deployment 或 route cutover。

- `line_identity_bindings` 與 binding events 由 LINE Identity application 作唯一 writer；customer／staff／admin root facts 仍由各 owning Domain 擁有，owner columns 僅為 projection。
- `provisional_client_registrations` 的 provisional registration 由 Case Import 擁有；LIFF onboarding 只能產生 binding projection outcome，不得升格 role 或直接寫 customer／staff／admin root。
- legacy direct writers、舊 approve writer 與 `bind.html` 必須 guarded／readonly 或 `410`，逐 caller 建立 disposition、replacement、focused regression 與 restore trigger 後退出；不得被新功能引用。
- Customer Service 擁有 `binding_failed_assistance` 的人工協助入口；dual-role 與 two-failure escalation 尚未實作，須由 M4 escalation successor 接手，不能在本包偷偷增加第二個 binding writer。
- 真實 verified-token／LIFF browser／registration／binding／Rich Menu E2E 仍需 sandbox config 與受控 evidence；本文件不把缺失的真實 E2E 宣稱為 PASS。

### Freeze acceptance and non-authorizations

`same-subject rebind`、cross-subject rejection、collision、stale、replay、legacy exit 與 owner projection 是 M1-A implementation acceptance；受控 verified-token／LIFF／Rich Menu E2E 是獨立 M1-E2E gate。B/C、two-failure、dual-role、retirement successor、schema／DB、provider rollout 與任何外部 production side effect 仍不在本次授權。
