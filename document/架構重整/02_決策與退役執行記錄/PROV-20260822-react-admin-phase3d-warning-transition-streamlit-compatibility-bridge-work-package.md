---
doc_type: work-package
declared_status: proposed
identity: PROV-20260822-react-admin-phase3d-warning-transition-streamlit-compatibility-bridge
date: 2026-08-22
owner: Legacy Streamlit / Anomalies Integration Owner
domain: Anomalies / Case Import
authority: awaiting-exact-human-approval
approval_required: 核准此 exact Phase 3D-W-H Streamlit Warning Transition Compatibility Bridge Work Package
prerequisites: PROV-20260817-react-admin-phase3-scenario-lineage-governance PHASE3_SCENARIO_LINEAGE_METADATA_READY; PROV-20260817-global-fastapi-typed-error-boundary PASS; PROV-20260817-react-admin-phase2d-h-closure-gate-amendment PASS; PROV-20260817-react-admin-phase3d-warning-transition-receipt-hardening exact public contract freeze
bridge_position: W-H final-acceptance/cutover prerequisite; not a W-H public-contract design prerequisite
scenario_governance: ../01_規格基線/00_Global_共同契約.md
ui_execution_mode: streamlit-compatibility-only
evidence_directory: document/架構重整/03_追蹤清單與證據/evidence/PROV-20260822-react-admin-phase3d-warning-transition-streamlit-compatibility-bridge/
base_branch: main
base_head: late-bound-at-approval
dirty_baseline: integration-owner-must-capture-before-writer; preserve-all-user-work
base_drift_rule: any relevant path drift requires fresh read and re-freeze before edits
---

# Phase 3D-W-H Streamlit Warning Transition Compatibility Bridge 工作包

## 0. 定位與目標

現有 Streamlit 異常警示頁仍透過 legacy `ui` client 呼叫 Import Warning Preview／Apply，且將 Apply
結果解碼為 `WarningTransitionPreviewView`。Phase 3D-W-H 將 Apply 收斂為獨立 terminal receipt 並增加
authenticated re-query；若只改 backend，legacy caller 會把舊 Preview payload 當成成功，或在正式
contract 改變後直接失敗。

本 successor 只負責維持這兩個既有 Streamlit caller 的 typed contract compatibility：

```text
Query → Preview → Apply → terminal receipt → authenticated re-query
```

它只記錄 Import Warning tracking disposition，不代表 owning Domain root 已修復、不代表 HCM 已重新匯入，
也不解鎖 Claim／Resolve、HCM Apply、owner repair 或任何 source-domain mutation。

本包必須消費 Phase 3D-W-H 已凍結的 method、path、request、Preview、Apply receipt、re-query view、
headers 與 typed errors；不得由 Streamlit lane 自行命名 endpoint、複製 backend schema 或由 HTTP 200
推導成功。

## 1. Exact write set

### Production

- `ui/api_clients/import_warning_tracking_api_client.py`
- `ui/pages/06_finance_alerts.py`

### Tests

- `tests/test_import_warning_tracking_api_client.py`
- `tests/test_finance_anomaly_recovery_ui.py`
- `tests/test_streamlit_import_warning_transition_compatibility.py`（new）

### Evidence／文件

- 本工作包
- `document/架構重整/03_追蹤清單與證據/evidence/PROV-20260822-react-admin-phase3d-warning-transition-streamlit-compatibility-bridge/contract-compatibility-matrix.md`
- `document/架構重整/03_追蹤清單與證據/evidence/PROV-20260822-react-admin-phase3d-warning-transition-streamlit-compatibility-bridge/verification-receipt.md`
- `document/架構重整/03_追蹤清單與證據/evidence/PROV-20260822-react-admin-phase3d-warning-transition-streamlit-compatibility-bridge/open-findings.md`

`02/README`、active index、Phase 3D-W-H backend paths、React paths、schema、migration、scenario fixture、
Streamlit 其他頁面與 shared transport 不在 write set。shared 文件由 Integration Owner 統一整合。

## 2. Prerequisites與順序

1. Phase 3 scenario lineage 只能解除 metadata dependency；不得被本包升格為 runtime PASS。
2. Global FastAPI typed error boundary、Phase 2D-H closure 與 Phase 2D backend public contract 必須有
   fresh upstream receipt。
3. Phase 3D-W-H 必須先凍結 Apply receipt／authenticated re-query 的 exact public contract；本包不能在
   contract 未知時猜測新欄位或路由。
4. 本包完成後，W-H 才能把 Streamlit compatibility evidence 納入 final acceptance／cutover；React
   `PROV-20260817-react-admin-phase3d-w-r-warning-transition-react` 仍依 W-H backend PASS 解鎖。

因此本包是 W-H final acceptance/cutover 的 compatibility bridge，不是 W-H public-contract design 的
前置條件。若 W-H contract 尚未 freeze，G0 仍 BLOCKED。

## 3. Public caller contract

### API client

- `preview()` 僅解碼 `WarningTransitionPreviewView`。
- `apply()` 僅解碼 W-H 凍結的 `WarningTransitionReceiptView`，不得重用 Preview view。
- `query_receipt()`／同等方法僅使用 W-H 凍結的 authenticated receipt/re-query endpoint 與 view。
- Apply response 缺少 receipt identity、before／after status、resulting version、correlation 或 replayed
  時，固定回 typed contract error；不得把 legacy Preview response 映射成成功 receipt。
- same-key／same-payload replay 必須保留並回傳 server 的 receipt identity 與 `replayed=true`；mismatch
  必須保留 typed conflict。
- transport timeout、5xx 或 unknown outcome 不得換新 idempotency key 盲目重送。

### Streamlit page

- 以 session state 保存本次 Apply 的 exact request、idempotency key 與 correlation ID，避免 rerun 時變更。
- Apply／unknown／receipt observation 期間停用重複操作。
- Apply 成功後先保存 terminal receipt，再 authenticated re-query；只有 re-query 與 receipt 的
  occurrence、status、version、receipt identity 一致才顯示已觀察完成。
- receipt、replayed、before／after status、version 與 correlation 只顯示去敏欄位；不得顯示 raw evidence、
  source snapshot、PII 或 `corrected_fields`。
- 文案只能表示「匯入警示追蹤狀態已記錄」；不得表示來源資料已修復、HCM 已完成 re-import 或正式資料已更正。
- 不新增 HCM workbook 合成／上傳、不新增 owner repair、不新增 Claim／Resolve 控制。

## 4. State machine與失敗語意

```text
idle
 → preview_pending
 → preview_ready
 → apply_pending
 → receipt_received
 → requery_pending
 → observed
```

另有兩個不可混淆的分支：

- `apply_pending → outcome_unknown`：保留 exact payload／同一 key／correlation，只能 same-key retry 或
  authenticated receipt query。
- `receipt_received → observation_failed`：保留 receipt，不得顯示 Apply 失敗，也不得重送新 Apply。

Legacy Preview-shaped Apply response 必須進 `contract_not_ready`／typed invalid-response，而不是
`receipt_received`。

## 5. Acceptance

- API client 與 page 完成 Preview／Apply 型別分離及 terminal receipt／re-query 串接。
- strict negative tests 覆蓋 missing／extra receipt fields、legacy Preview-shaped Apply、same-key replay、
  mismatch conflict、timeout unknown outcome 與 re-query observation failure。
- page source／UI contract test 證明不產生 fake success、不把 tracking disposition 寫成 root repair，且不暴露
  PII／raw evidence。
- Apply 的 idempotency key、correlation ID 與 payload 在 Streamlit rerun／same-key retry 中保持不變。
- receipt 與 re-query 的 identity/status/version 一致時才顯示 observed；replayed 狀態明確標示。
- 未修改任何 backend、schema、DB、React、scenario 或 HCM upload path。
- `git diff --check`、strict UTF-8、no BOM、敏感資訊／PII scan 通過；只留下本包 exact write set。
- 真實 HTTP＋MySQL transition、receipt、outbox、rollback evidence 仍由 Phase 3D-W-H 擁有；本包不得以
  mock 或 Streamlit source assertion 取代 W-H G5。

## 6. Required focused verification

```powershell
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest_tmp\phase3d-warning-streamlit-bridge -q `
  tests\test_import_warning_tracking_api_client.py `
  tests\test_finance_anomaly_recovery_ui.py `
  tests\test_streamlit_import_warning_transition_compatibility.py
```

本命令只驗證 caller contract；不得被解讀為 Phase 3D-W-H backend、DB 或真實 browser acceptance。

## 7. Gates與DB disposition

| Gate | Status | Evidence／reason |
|---|---|---|
| G0 exact approval／W-H contract freeze | BLOCKED | 本 successor 仍 `proposed`，且須先取得 W-H frozen public contract |
| G1 caller contract matrix | NOT_RUN | 核准後由 caller writer 依 W-H contract freeze 產出 |
| G2 strict decoder／legacy fail-closed | NOT_RUN | 未施工 |
| G3 session／same-key／unknown state machine | NOT_RUN | 未施工 |
| G4 redaction／tracking-only semantics | NOT_RUN | 未施工 |
| G5 focused caller verification | NOT_RUN | 未執行測試 |
| G6 true HTTP／MySQL transition evidence | NOT_RUN | 由 W-H 擁有；本包不操作既有 DB |
| G7 evidence／handoff | NOT_RUN | 未施工 |

| DB gate | Status | Evidence／reason |
|---|---|---|
| Scope gate | BLOCKED | 尚未 exact 核准；本包不能代替 W-H approval |
| Change inventory | PASS | 僅 Streamlit client/page/tests；schema-only、seed、backfill、destructive 均為 0 |
| Static release gate | NOT_RUN | 無 schema／migration release |
| Descriptor gate | NOT_RUN | 無 DB object 變更 |
| Read-only plan gate | NOT_RUN | 不適用；本包不執行 DB plan |
| Engine verification gate | NOT_RUN | transition engine evidence 由 W-H 擁有 |
| Developer acceptance gate | NOT_RUN | 禁止既有 DB mutation |

結論固定為 `DB_CHANGE_NOT_READY`；本包不得宣稱 W-H backend、DB、browser 或 React 完成。

## 8. Exact approval phrase

```text
核准此 exact Phase 3D-W-H Streamlit Warning Transition Compatibility Bridge Work Package，
保持上述 scope、write set 與 acceptance；本包只消除 legacy Streamlit caller contract break，
不擴張 Phase 3D-W-H backend、React、HCM Apply、owner repair 或 DB scope。
```
