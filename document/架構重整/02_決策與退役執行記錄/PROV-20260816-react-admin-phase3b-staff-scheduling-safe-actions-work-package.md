---
doc_type: work-package
declared_status: blocked
identity: PROV-20260816-react-admin-phase3b-staff-scheduling-safe-actions
date: 2026-08-16
owner: Integration Owner
domain: Scheduling / Staff
subsystem: Preferences / Availability / Lifecycle / Leave Substitution / React Presentation
specification: PROV-20260816-react-admin-phase3b-staff-scheduling-safe-actions-specification
approval_required: human-must-reply-核准此-exact-Phase-3B-Work-Package
approval_evidence: user-replied-exact-text-2026-08-16
base_branch: main
base_head: 8615225481c8f72a9629289285516189b270cb36
---

# React 管理端 Phase 3B：Staff／Scheduling 安全 actions 工作包（防偷懶版）

> Fresh G1 status：`blocked-contract-amendment-required`。詳見Phase3B evidence `open-findings.md`；原exact
> write set缺Staff selector client且禁止必要backend hardening，故production writers尚未開工。修訂候選為
> `PROV-20260816-react-admin-phase3b1-staff-contract-hardening-selector-amendment.md`。

## 0. Activation gate

本文件已於2026-08-16取得使用者 exact 核准。核准文字：

> 核准此 exact Phase 3B Work Package

本包production/test write set已被核准。本包可與已核准的3A平行，但兩包的 Integration Owner、shared hotspots、
full-suite時段必須協調；未核准不得因3A已核准推定3B授權。

核准後先記錄branch/HEAD/status及每個write-set path collision inventory，將本包改為approved/in-progress。
禁止reset/clean/stash/checkout/worktree/stage/commit/push。

## 1. Contract-first gate

Integration Owner建立唯一：

`document/架構重整/03_追蹤清單與證據/evidence/PROV-20260816-react-admin-phase3b-staff-scheduling-safe-actions/contract-field-matrix.md`

每列欄位同Phase3A，並為四flow另列：root facts、versions、fingerprint、idempotency、lock order、outer UoW、
cross-domain impacts、outbox、receipt、privacy、request budget。每條flow獨立freeze/status；沒有matrix不得開工。

## 2. Lane topology 與 exact write set

### Lane A — Contract Scout（Luna，read-only）

盤點四flow route/Pydantic/application/domain/tests、UI controls、base drift；不寫檔。

### Lane B — Preferences Client/Adapter Writer

- `ui_react/src/api/staff_preferences/staff_preferences_schemas.ts`
- `ui_react/src/api/staff_preferences/staff_preferences_errors.ts`
- `ui_react/src/api/staff_preferences/staff_preferences_client.ts`
- `ui_react/src/adapters/staff/staff_preferences_adapter.ts`
- `ui_react/src/tests/fixtures/staff/staff_preferences_contract_fixtures.ts`
- `ui_react/src/tests/staff_preferences_client.test.ts`
- `ui_react/src/tests/staff_preferences_adapter.test.ts`

### Lane C — Availability/Lifecycle Client/Adapter Writer

- `ui_react/src/api/staff_availability/staff_availability_schemas.ts`
- `ui_react/src/api/staff_availability/staff_availability_errors.ts`
- `ui_react/src/api/staff_availability/staff_availability_client.ts`
- `ui_react/src/api/staff_lifecycle/staff_lifecycle_schemas.ts`
- `ui_react/src/api/staff_lifecycle/staff_lifecycle_errors.ts`
- `ui_react/src/api/staff_lifecycle/staff_lifecycle_client.ts`
- `ui_react/src/adapters/staff/staff_availability_adapter.ts`
- `ui_react/src/adapters/staff/staff_lifecycle_adapter.ts`
- `ui_react/src/tests/fixtures/staff/staff_availability_contract_fixtures.ts`
- `ui_react/src/tests/fixtures/staff/staff_lifecycle_contract_fixtures.ts`
- `ui_react/src/tests/staff_availability_client.test.ts`
- `ui_react/src/tests/staff_lifecycle_client.test.ts`
- `ui_react/src/tests/staff_availability_lifecycle_adapter.test.ts`

### Lane D — Leave/Substitution Client/Adapter Writer

- `ui_react/src/api/leave_substitution/leave_substitution_schemas.ts`
- `ui_react/src/api/leave_substitution/leave_substitution_errors.ts`
- `ui_react/src/api/leave_substitution/leave_substitution_client.ts`
- `ui_react/src/adapters/scheduling/leave_substitution_adapter.ts`
- `ui_react/src/tests/fixtures/scheduling/leave_substitution_contract_fixtures.ts`
- `ui_react/src/tests/leave_substitution_client.test.ts`
- `ui_react/src/tests/leave_substitution_adapter.test.ts`

### Lane E — Staff Presentation Writer

Lane B/C freeze後開始：

- `ui_react/src/pages/StaffPage.tsx`
- `ui_react/src/pages/StaffPage.css`
- `ui_react/src/tests/staff_page_real_data.test.tsx`
- `ui_react/src/tests/staff_preferences_flow.test.tsx`
- `ui_react/src/tests/staff_availability_flow.test.tsx`
- `ui_react/src/tests/staff_lifecycle_flow.test.tsx`
- `ui_react/src/tests/staff_no_fake_mutation.test.tsx`

### Lane F — Scheduling Presentation Writer

Lane D freeze後開始：

- `ui_react/src/pages/SchedulingPage.tsx`
- `ui_react/src/pages/SchedulingPage.css`
- `ui_react/src/tests/scheduling_leave_substitution_flow.test.tsx`
- `ui_react/src/tests/scheduling_no_fake_mutation.test.tsx`

### Lane G — Backend Regression Writer

只可補tests，不改production backend：

- `tests/test_staff_matching_preferences.py`
- `tests/test_staff_availability_routes.py`
- `tests/test_staff_retirement_workflow.py`
- `tests/test_leave_substitution_workflow.py`
- `tests/test_react_phase3b_public_contracts.py`（新增）

若public contract無法閉合，回 `BACKEND_PUBLIC_CONTRACT_GAP`並阻擋該flow，不得自行改route/schema。

### Lane H — Fresh Verification Auditor（Luna，read-only）

不寫receipt、不修code，只回傳raw commands、exit codes、counts、diff findings與write-set audit。

## 3. Shared hotspots與禁止範圍

禁止修改 shared transport/runtime decoder/Auth/App/Drawer/MasterLayout/package/lock/Vite/TS config、backend
production、DB、其他頁面、holiday、staff master、quick lock、leave intake、Phase2 artifacts。各client只屬單一
bounded domain；不得建立 `staff_api.ts` 或 `scheduling_api.ts` 巨型client。

## 4. Anti-laziness execution rules

除Phase3A規則外，增加：

1. 四flow各自status；任何一條blocked不得用總tests綠洗成complete。
2. 不得前端計算 overlap、coverage、end date、buffer、hours、payroll或retirement eligibility。
3. 不得把 availability local array splice、Staff local state或MOCK_STAFF改名後繼續使用。
4. `orders.staff_id/name`不得作leave assignment owner；只用typed assignment query。
5. Cancel availability是append-only intent，不可DELETE。
6. receipt_received與observed分開；re-query failure不得稱Apply failure。
7. Leave batch exact replay、payload mismatch與partial/corrupt snapshot需後端證據；unit mock不可代替。
8. lifecycle復職控制必須由server state出現，不可因UI缺現成按鈕而永遠漏做或自行推status。

## 5. G0–G8 gates

| Gate | PASS condition |
|---|---|
| G0 Scope | exact approval、baseline/collision inventory、0 write-set violation、0 DB |
| G1 Contract | 四flow逐欄matrix、owner/SSOT/versions/fingerprint/UoW/privacy/error全部freeze |
| G2 Backend | live route/application/domain/tests證明zero-write、stale、replay、rollback與各flow不變量 |
| G3 Clients | strict decoder負向tests、current memory token、method/path/header/request budget exact |
| G4 Presentation | 既有tabs/Drawers可見、四flow exhaustive state、其餘controls native disabled |
| G5 Negative safety | sentinel divergence、unexpected network=0、fake mutation=0、mock dependency closure=0 |
| G6 Static suites | focused→full Vitest、lint、build、focused pytest、UTF-8/header/secret/PII/diff/skip全部PASS |
| G7 Runtime | 真FastAPI＋Vite＋帳密→TOTP＋四組controlled data的Network→DOM→re-query evidence |
| G8 Fresh audit | Integration Owner讀完整diff/raw output；四flow status、receipt、findings、index一致 |

G2/G5/G7必須按四flow分列：

- Preferences：Preview zero-write、stale、replay、definition/version lineage。
- Availability：overlap/occupancy/waiting-lock/buffer、append-only cancel、replay。
- Lifecycle：retired consumer guards、confirmed future assignment preservation、reactivation不恢復舊facts。
- Leave/Substitution：service conservation、batch replay/corruption、lock order、cross-domain conflicts、atomic outbox。

G7需要真FastAPI＋Vite＋TOTP與四組去敏controlled data。任何資料集缺失只阻擋該flow，但整包仍為blocked。
不得在既有營運案例執行 mutation；只可使用明確標識的disposable/validation cases。

## 6. Required commands

```powershell
cd D:\project\Labor_union\ui_react
npm test -- src/tests/staff_preferences_client.test.ts src/tests/staff_availability_client.test.ts src/tests/staff_lifecycle_client.test.ts src/tests/leave_substitution_client.test.ts
npm test -- src/tests/staff_page_real_data.test.tsx src/tests/staff_preferences_flow.test.tsx src/tests/staff_availability_flow.test.tsx src/tests/staff_lifecycle_flow.test.tsx src/tests/scheduling_leave_substitution_flow.test.tsx
npm test -- src/tests/staff_no_fake_mutation.test.tsx src/tests/scheduling_no_fake_mutation.test.tsx
npm test
npm run lint
npm run build
```

```powershell
cd D:\project\Labor_union
.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest_tmp/phase3b-staff-scheduling -q tests/test_staff_matching_preferences.py tests/test_staff_availability_routes.py tests/test_staff_availability_workflow.py tests/test_staff_retirement_workflow.py tests/test_staff_retirement_consumer_guards.py tests/test_leave_substitution_workflow.py tests/test_react_phase3b_public_contracts.py
git diff --check
```

## 7. Evidence and status

Integration Owner唯一寫入與Phase3A同名七份evidence，落在本包專屬目錄。每份receipt分列四flow、raw
counts與open blockers，禁止只有總PASS。Production write set沒有DB變更；DB gate固定依最終表揭露，
不得把`DB_CHANGE_NOT_READY`誤寫成React code失敗或DB已驗證。
