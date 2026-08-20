---
doc_type: work-package-amendment
declared_status: proposed
identity: PROV-20260817-react-admin-phase4-scenario-lineage-governance-prerequisite-amendment
date: 2026-08-17
owner: Global Validation Governance Integration Owner
domain: Global Validation Governance / React Phase 4
amends: PROV-20260817-react-admin-phase4-scenario-lineage-governance
source_gap: PROV-20260817-react-admin-phase4-scenario-lineage-governance-gap
authority: awaiting-exact-human-approval
approval_required: 核准此 exact Phase 4 Scenario Lineage Governance prerequisite amendment：Phase 3 只需 PHASE3_SCENARIO_LINEAGE_METADATA_READY；Global typed error boundary 不屬 metadata-only prerequisite；Phase 4 最高輸出維持 PHASE4_SCENARIO_LINEAGE_METADATA_READY，不得宣稱 runtime PASS。
ui_execution_mode: not-applicable
base_branch: main
base_head: 8615225481c8f72a9629289285516189b270cb36
dirty_baseline: preserve-all-user-work
---

# Phase 4 Scenario Lineage Governance prerequisite／browser metadata amendment

## 1. 裁決目的與目前狀態

本文件是對 `PROV-20260817-react-admin-phase4-scenario-lineage-governance` 的**前置條件文字修正提案**，目前為
`proposed`，尚未取得人工核准，不授權任何 production、API、React、DB、provider 或 browser 執行。

目前可追溯事實如下：

- Phase 3 Scenario Lineage Governance 的驗證回執最高輸出為
  `PHASE3_SCENARIO_LINEAGE_METADATA_READY`；其 `10 passed` 只證明 metadata／test-data contract，並明確不構成
  API、DB、browser、provider 或 production runtime PASS。
- Phase 4 Scenario Lineage Governance 本身是 metadata-only 工作包，目的為建立 scenario、fixture、expected、
  receipt registry 與 checklist lineage；它不應等待 Phase 3 的 runtime PASS，因為 Phase 3 工作包並不產生該類
  PASS。
- Global FastAPI Typed Error Boundary 是獨立的 public API contract／runtime 工作包，具有自己的契約、前置條件與
  未決 correlation precedence amendment；它不是 Phase 4 metadata-only lineage artifact 的必要前置條件。

## 2. 精確裁決

核准後，Phase 4 Scenario Lineage Governance 工作包的 prerequisite 應解讀為：

```text
required prerequisite:
  PROV-20260817-react-admin-phase3-scenario-lineage-governance
  output == PHASE3_SCENARIO_LINEAGE_METADATA_READY

not a prerequisite:
  Global FastAPI Typed Error Boundary runtime PASS
  Global FastAPI Correlation Precedence Amendment PASS
```

`PHASE3_SCENARIO_LINEAGE_METADATA_READY` 是本 metadata-only 工作包可接受的 Phase 3 gate；它不能被升格為
`PASS`，也不能解除任何 Phase 3 runtime、DB、API、browser 或 provider gate。

Global typed error boundary 仍須依其自身 Work Package 與 correlation precedence amendment 的核准及驗收流程處理。
Phase 4 scenario metadata 可建立對 Global typed error boundary 的 scenario lineage reference，但不得把該 reference
解讀為 Global runtime 已完成，也不得為了通過 Phase 4 validator 偽造 Global runtime receipt。

Browser metadata固定沿用React主計畫的唯一enum：

```text
browser-required | browser-file-dialog-assisted | browser-blocked | not-applicable
```

原工作包的`not_applicable | controlled_browser_required | blocked`不得建立第二套語彙。若canonical Part checklist
尚不存在，該coverage record必須使用`browser-blocked`、`browser_checklist_step_ids: []`，並在
`missing_artifacts`列出exact path與owning Part；只有checklist path存在且mode不是`browser-blocked`時，step IDs才
必填、非空且全manifest唯一。本metadata包不得代替Part owner建立缺少的checklist。

## 3. Exact integration patch delta（核准後才可執行）

本 amendment 核准後，由唯一 Integration Owner 在最新 integration target 上執行下列最小文件同步；本 amendment
本身不預先修改這些檔案：

1. 在 `PROV-20260817-react-admin-phase4-scenario-lineage-governance-work-package.md` 將 frontmatter
   `prerequisites` 從
   `PROV-20260817-react-admin-phase3-scenario-lineage-governance PASS`
   改為明確的 metadata output gate：
   `PROV-20260817-react-admin-phase3-scenario-lineage-governance PHASE3_SCENARIO_LINEAGE_METADATA_READY`。
2. 將同一工作包的 `Current activation` 文字改為：僅在 Phase 3 metadata output
   `PHASE3_SCENARIO_LINEAGE_METADATA_READY` 可追溯且本工作包取得其 exact 人工核准後，才可啟動 metadata writer；
   Global typed error boundary runtime／correlation amendment 不屬本包 activation prerequisite。
3. 保留該工作包所有 metadata-only、0 runtime、0 DB、0 browser、0 provider、不得偽造 receipt 的限制；不得把
   `completed`、`PASS` 或 `success` 寫入 runtime receipt。
4. 將原工作包的browser enum與missing-checklist條款同步為本修訂的唯一規則；不得修改
   `validation/ui_business_workflows/checklist_manifest.yaml`或新增`phase4/`平行根。
5. 更新 `document/架構重整/02_決策與退役執行記錄/README.md` 的該工作包摘要與 amendment inbound link，明確標示
   本 amendment 的 `proposed`／等待核准狀態。
6. 更新 Phase 4 scenario lineage evidence 的 prerequisite／activation blocker 文字；不得重產或覆寫既有 Phase 3
   receipt、scenario、fixture、expected 或 digest。
7. 對主 React migration plan／dependency matrix 只做精確的 prerequisite wording delta；不得藉此啟動 Phase 4
   runtime bounded work packages。

任何 production writer、backend contract hardening、React mutation、DB seed／migration、browser runner 或 provider
驗證，均不在本 amendment write set 內，且必須另依其 own Work Package、approval 與 gate 執行。

## 4. Out of scope 與 anti-lazy constraints

- 不修改任何 production code、API schema、Domain、Subsystem、React page、Streamlit、DB、schema、seed、migration、
  provider、browser script 或測試程式。
- 不新增或重產 scenario、fixture、expected、receipt、checklist 或 validator；那些是原 Phase 4 工作包的 write set。
- 不把 Phase 3 的 `10 passed` 解釋成 runtime PASS，不把 Phase 4 metadata-ready 解釋成 API／DB／UI／browser PASS。
- 不解除 Global typed error boundary 的獨立 blocker，也不批准其 correlation precedence 行為。
- 不因 Phase 4 metadata prerequisite 修正而解除 HCM、Finance、LINE、Knowledge、Durable Job 或其他 bounded runtime
  工作包的各自 contract／engine／browser gates。
- 不改變任何 scenario identity、revision、source mapping、fixture digest、expected oracle 或 receipt identity。

## 5. Acceptance after approval

只有下列文件性驗證全部通過，才能把本 amendment 標為 `completed`：

1. 原 Phase 4 工作包的 prerequisite、activation、completion boundary 三處文字與本裁決一致。
2. Phase 3 reference 精確使用 `PHASE3_SCENARIO_LINEAGE_METADATA_READY`，未出現要求 Phase 3 runtime `PASS` 的殘留文字。
3. Global typed error boundary 與 correlation amendment 均明確列為非本 metadata-only prerequisite，且沒有被標示為已完成。
4. Phase 4 最高輸出仍是 `PHASE4_SCENARIO_LINEAGE_METADATA_READY`；所有 runtime receipt 初始狀態仍限於
   `missing | not_run | blocked`。
5. README、主計畫、dependency matrix 與 Phase 4 evidence 的 inbound references 可互相追溯，且沒有建立第二份 SSOT。
6. manifest只接受主計畫browser enum；missing checklist固定`browser-blocked`＋空step IDs＋exact missing owner，
   存在的checklist則step IDs非空且全域唯一。
7. scoped `git diff --check`、strict UTF-8／無 BOM 與 exact write-set audit 通過。

## 6. DB gate

本 amendment 為文件性 prerequisite wording 修正，沒有 schema、seed、backfill、migration 或資料列變更。

| Gate | Status | Evidence |
|---|---|---|
| Scope | PASS | 本文件限定為 Phase 4 metadata-only prerequisite amendment |
| Change Inventory | PASS | 0 schema／seed／backfill／destructive；0 production／DB side effect |
| Static Release | NOT_RUN | 不適用；沒有 release artifact |
| Descriptor | NOT_RUN | 不適用；沒有 DB object |
| Read-only Plan | NOT_RUN | 不適用；沒有 DB 操作 |
| Engine Verification | NOT_RUN | 明確禁止啟動資料庫 |
| Developer Acceptance | NOT_RUN | 明確禁止操作既有資料庫 |

結論：`DB_CHANGE_NOT_READY`。
