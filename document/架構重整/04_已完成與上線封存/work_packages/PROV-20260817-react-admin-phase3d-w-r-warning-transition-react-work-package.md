---
doc_type: work-package
declared_status: completed
identity: PROV-20260817-react-admin-phase3d-w-r-warning-transition-react
date: 2026-08-17
owner: Import Warning React Integration Owner
domain: Anomalies / Case Import
prerequisites: PROV-20260817-react-admin-phase3-scenario-lineage-governance PHASE3_SCENARIO_LINEAGE_METADATA_READY; PROV-20260817-global-fastapi-typed-error-boundary PASS; PROV-20260817-react-admin-phase2d-h-closure-gate-amendment PASS; PROV-20260817-react-admin-phase3d-warning-transition-receipt-hardening PASS; PROV-20260817-react-admin-phase3d-r-anomaly-detail-react PASS
authority: 2026-08-22 human exact approval and corrective-patch authorization
approval_required: satisfied
evidence_directory: document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase3d-w-r-warning-transition-react/
required_receipts: candidate-change-inventory.md; contract-matrix-freeze-receipt.md; verification-receipt.md; browser-smoke-receipt.md; open-findings.md
scenario_governance: Part_00_全域測試資料治理與Scenario契約.md
ui_execution_mode: browser-required
base_branch: main
base_head: late-bound-at-approval
dirty_baseline: integration-owner-must-capture-before-writer; preserve-all-user-work
base_drift_rule: any relevant path drift requires fresh read and re-freeze before edits
---

# Phase 3D-W-R：Import Warning Transition React工作包

## 0. Scope

只在既有Anomalies頁原位置接上Import Warning的Query → Preview → Apply → terminal receipt → authenticated
re-query。此transition只改warning tracking disposition，不表示owner root fact已修復，也不解鎖Anomaly Claim／Resolve、
HCM Apply、任意dirty-row override或owner repair/re-import。

Controlled input只消費Phase3 Scenario Lineage凍結的
`validation/scenarios/react_admin_import_warning_transition.json`及其fixture／expected／receipt identity；本包不得
重產scenario或用writer fixture取代browser oracle。

## 1. Exact write set

- `ui_react/src/api/import_warning/import_warning_transition_schemas.ts`（new）
- `ui_react/src/api/import_warning/import_warning_transition_errors.ts`（new）
- `ui_react/src/api/import_warning/import_warning_transition_client.ts`（new）
- `ui_react/src/adapters/import_warning/import_warning_transition_adapter.ts`（new）
- `ui_react/src/pages/AnomaliesPage.tsx`
- `ui_react/src/pages/AnomaliesPage.css`
- `ui_react/src/tests/fixtures/import_warning/import_warning_transition_contract_fixtures.ts`（new）
- `ui_react/src/tests/import_warning_transition_client.test.ts`（new）
- `ui_react/src/tests/import_warning_transition_adapter.test.ts`（new）
- `ui_react/src/tests/anomalies_warning_transition_flow.test.tsx`（new）
- `ui_react/src/tests/anomalies_no_fake_mutation.test.tsx`
- `ui_react/src/components/Drawer.tsx`（corrective amendment：Apply／unknown／re-query期間原生鎖定close）
- `ui_react/src/tests/anomalies_detail_referral_flow.test.tsx`（direct-affected regression）
- `ui_react/src/tests/anomalies_entry_cutover.test.tsx`（direct-affected regression）

`AnomaliesPage.tsx/.css`與no-fake test是shared hot spot，固定在Phase2D query與Phase3D-R detail完成後，由同一
Presentation Integration Writer串行接入。shared transport/Auth、backend、DB、DataImportPage及其他page不在write set。

## 2. Public contract與狀態機

G1必須從已PASS的3D-W-H receipt逐一凍結exact method/path、request、Preview、Apply receipt、receipt/re-query
view、typed errors與header矩陣；production client只允許該network allowlist。backend contract缺任何一欄時固定
`BLOCKED_BACKEND_PUBLIC_CONTRACT`，不得由React自行命名endpoint或從HTTP 200推導成功。

每次call fresh讀memory bearer；無token零fetch。Strict Zod禁止`any/unknown/record/default/passthrough`與unsafe
cast。狀態機固定：

`idle → query_loading → query_ready → editing → preview_loading → preview_ready → apply_pending →`
`receipt_received → requery_loading → observed`。

- edit使preview/fingerprint失效；409只允許re-query後重新Preview。
- Apply timeout/network/正式retryable 503進`outcome_unknown`，保留exact payload與同一idempotency key；只有此狀態
  可same-key retry。
- receipt後re-query失敗進`observation_failed`，保留receipt，不得顯示Apply失敗。
- 只有re-query觀察到server resulting version/status與receipt一致才顯示transition完成。
- Apply／unknown／requery期間selector、inputs、close、tab switch原生disabled；禁止alert/confirm/local business mutation。

## 3. UI controls與語意

保留既有Anomalies filters、cards與Drawer。新增stable IDs至少包含：

- `anomalies.import-warning.transition.open`
- `anomalies.import-warning.transition.action`
- `anomalies.import-warning.transition.reason`
- `anomalies.import-warning.transition.preview`
- `anomalies.import-warning.transition.apply`
- `anomalies.import-warning.transition.retry`
- `anomalies.import-warning.transition.observe`

Owner repair/deep link只能導向正式bounded workflow；不存在時原位顯示unavailable。Claim／Resolve controls仍native
disabled，且不得將warning disposition文案寫成「來源已修復」。

## 4. Lanes與G0–G7

1. Luna Contract Scout唯讀凍結API/DOM/request-budget/control-ID matrix，不寫production。
2. Terra Client Writer只寫bounded client/schema/error/adapter及其tests。
3. Primary Presentation Writer在client freeze後唯一修改page/CSS/no-fake test。
4. Luna Fresh Auditor在latest tree重跑commands，只回raw evidence；Integration Owner唯一更新receipt/index/status。

- G0：全部frontmatter prerequisites fresh PASS、exact approval、dirty preservation、0 unexpected paths。
- G1：exact backend/field/error/header/scenario matrix freeze。
- G2：strict decoder negatives、fresh token、no-token zero fetch、unexpected network zero。
- G3：exhaustive state machine、single-flight、stale、same-key unknown retry、receipt/re-query分離。
- G4：warning disposition不冒充root repair；Claim／Resolve／owner mutation仍locked。
- G5：focused/full React tests、lint、build、UTF-8、diff、secret/PII scan。
- G6：真FastAPI＋Vite＋兩段式TOTP＋controlled scenario的Network↔DOM；缺credential/test data只阻擋G6。
- G7：evidence列出request counts、receipt identity、re-query observation及未解鎖controls，不得宣稱Anomalies全功能完成。

## 5. DB gate

| Gate | Status | Evidence |
|---|---|---|
| Scope gate | PASS | 2026-08-22人工exact核准；3D-W-H與3D-R prerequisites均PASS |
| Change inventory | PASS | React-only，0 schema/seed/backfill/destructive |
| Static release gate | NOT_RUN | 無release |
| Descriptor gate | NOT_RUN | 無DB object |
| Read-only plan gate | NOT_RUN | 不適用 |
| Engine verification gate | PASS | 3D-W-H final focused 39含2支真MySQL；W-R真FastAPI＋Vite browser閉環回讀`lu_test_*` |
| Developer acceptance gate | NOT_RUN | 不操作既有DB |

結論：`DB_CHANGE_NOT_READY`。

## 6. Completion receipt（2026-08-22）

G0–G7已完成。strict client／schema／typed error／adapter與React狀態機維持Query → Preview → Apply →
terminal receipt → authenticated receipt re-query；只有receipt核心欄位與server observation一致才顯示完成。
corrective amendment為`Drawer.closeDisabled`，使ESC、backdrop、header close在Apply／unknown／re-query期間一致原生鎖定。

focused direct-affected為8 files／66 tests PASS；full React為119 files／757 tests PASS；lint exit 0（4個既存非本包
warning）、build PASS、UTF-8/no-BOM/header 14 paths PASS、scoped diff check無錯誤。真瀏覽器使用development
`lu_test_*`唯一scenario `phase3d-wr-browser-20260822195924`，完成Preview 200、Apply 200、receipt GET 200；
receipt `a387d3e2459492b5717a8d37f378f1712373f8033e9266c6b346811d196c6cac`由畫面與DB共同觀察到
`open v1 → awaiting_external_confirmation v2`。Claim／Resolve／owner root repair仍native disabled；未執行provider、
deployment、cutover、schema、seed、backfill或destructive operation。
