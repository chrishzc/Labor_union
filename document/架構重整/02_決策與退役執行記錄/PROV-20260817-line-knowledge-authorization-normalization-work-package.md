---
doc_type: work-package
declared_status: proposed
identity: PROV-20260817-line-knowledge-authorization-normalization
date: 2026-08-17
base_branch: main
base_head: late-bound-at-approval
dirty_baseline: integration-owner-must-capture-before-writer
base_drift_rule: any relevant path drift requires fresh read and re-freeze before edits
owner: Access / LINE / Knowledge Integration Owner
domain: Access / LINE / Knowledge
source_gap: PROV-20260817-line-access-authorization-normalization-gap
formal_specification: 17_External_Integration_LINE_Access正式規格.md
authority: awaiting-exact-human-approval
approval_required: 核准此 exact LINE / Knowledge Authorization Normalization Work Package
scenario_governance: Part_00_全域測試資料治理與Scenario契約.md
scenario_adoption: AC-CAPABILITY-SESSION-002; LINE-IDENTITY-DELIVERY-001
ui_execution_mode: not-applicable
prerequisites: PROV-20260817-react-admin-phase3-scenario-lineage-governance PASS; PROV-20260817-global-fastapi-typed-error-boundary PASS
---

# LINE／Knowledge authorization normalization 工作包

## 0. 授權邊界

本包只收斂正式 Access 規格與 live capability gate 的漂移。所有 authenticated、enabled internal users
具有相同業務功能能力；capability 名稱保留為 command／audit vocabulary，不得形成 role-based business
authorization。唯一 root-only 例外仍是 Account Center。

只有使用者明確回覆：

> 核准此 exact LINE / Knowledge Authorization Normalization Work Package

才可修改 production。此核准不包含 Account Center、provider rollout、Rich Menu publish、delivery control、
notification rule mutation、Knowledge lifecycle、DB 或 React UI。

## 1. Exact production write set

- `subsystems/access/authentication_session.py`
- `subsystems/access/integration_capabilities.py`
- `subsystems/line/capabilities.py`
- `api/dependencies/admin_auth.py`

不得逐 route 大量改寫 dependency、不得移除 actor／audit permission scope，也不得把 unknown capability
默認放行。若 fresh matrix 證明某 route 使用獨立 role 判斷，固定回 `WRITE_SET_AMENDMENT_REQUIRED`，不能
在本包順便擴張。

## 2. Exact test／integration write set

- `tests/test_admin_auth_security.py`
- `tests/test_capability_grant_policy.py`
- `tests/line/subsystems/test_line_application_contracts.py`
- `tests/line/domain/test_line_order_group_stage6.py`
- `tests/line/subsystems/test_contract_knowledge_applications_stage8.py`
- `tests/test_enabled_admin_business_capability_matrix.py`（new）
- `tests/test_line_knowledge_authorization_route_matrix.py`（new）
- `document/架構重整/01_規格基線/17_External_Integration_LINE_Access正式規格.md`（Integration Owner only）
- `document/架構重整/01_規格基線/15_正式規格索引與裁決總表.md`（Integration Owner only）
- `document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-line-knowledge-authorization-normalization/`（new）

Evidence目錄至少包含`capability-route-matrix.md`、`candidate-change-inventory.md`、
`verification-receipt.md`與`open-findings.md`；matrix必須由live route dependency inventory產生，不能只列writer挑選的
happy-path routes。

`capability-route-matrix.md`至少完整涵蓋`line_identity.py`、`line_identity_management.py`、
`customer_service.py`、`line_tasks.py`、`line_configurations.py`、`line_rich_menus.py`、
`line_notification_rules.py`、`line_order_groups.py`、`knowledge_retrieval.py`及所有直接呼叫
`line_capabilities_for_role()`／integration capability helper的subsystem guard。矩陣逐route記錄dependency、
registered capability、root-only與0-subsystem-call結果；不得只掃FastAPI routes而漏掉direct subsystem caller。

矩陣另必須包含`line_system_config.py`（`/api/config`）與`line_admin.py`，並將`line_identity.py`逐endpoint分成
`admin-session | external-LIFF | page-static`；外部LIFF/public identity flow未使用admin session是protocol設計，
不得被誤報成auth bypass。每筆另標side-effect class：`none | wakeup-only | durable-provider-worker`。

## 3. Frozen contract

1. 每個 enabled principal 對所有 registered business capabilities 得到相同 allow 結果；role、legacy grant與
   menu label不得改變該結果。
2. unknown capability固定拒絕；disabled、expired、revoked、無session仍由`require_admin` fail closed。
   `require_capability`必須先驗capability已登錄，再對所有runtime profiles（含local bypass）執行
   `has_required_capability`；local bypass不得提前return而跳過unknown或
   `DEVELOPMENT_BYPASS_DENIED_CAPABILITIES`。
3. `require_root`只能保護 Account Center；route matrix若發現其他 business route使用root gate固定失敗。
4. `ActorContext.permission_scope`仍包含被執行command的registered capability，供audit與現有
   subsystem guard使用；normalization不是移除已存在的第二層guard。Knowledge 現況
   沒有direct subsystem capability guard；本包只驗證current production caller inventory等於guarded
   router/factory allowlist。新增in-process direct caller固定`WRITE_SET_AMENDMENT_REQUIRED`，不得宣稱任意Python
   import已被阻擋，也不得憑空新增Knowledge guard或擴寫set。長期owner記錄於
   `PROV-20260817-knowledge-direct-authorization-boundary-gap.md`。
5. capability grant資料不得縮小或擴大business access；若仍保留管理入口，只能作compatibility／audit view，
   不能讓React形成差異選單。
6. 客服、identity、delivery、configuration、Rich Menu、Knowledge與order-group query／command均用同一
   principal matrix；不得只挑一條happy-path route自證。

## 4. Acceptance／anti-fake gates

- G0：exact approval、dirty baseline與route dependency inventory frozen。
- G1：registered capability、route dependency、root-only exception逐項矩陣完成。
- G2：四種live role enum與至少兩個enabled principal對所有registered business capabilities結果一致；unknown拒絕。
- G3：disabled／revoked／expired／missing token為401/403且0 subsystem call；root-only Account Center維持。
- G4：現有LINE direct subsystem guard與經FastAPI dependency的結果一致；Knowledge current production
  caller inventory只允許guarded router/factory，新增direct caller即fail closed。
- G5：既有Phase3A、Phase4C Query、Access security focused tests與完整auth regression通過。
- G6：0 DB/schema/provider/React變更；strict UTF-8、檔頭、diff與secret scan通過。

G2～G5不得只用mock principal直接呼叫helper；至少一組FastAPI dependency測試必須從session token進入，並以
不同legacy role／grant的兩組sentinel principal證明結果相同。測試禁止`.skip`、`.todo`、`.only`、刪除既有403
assertion或以`expect/assert True`替代逐capability矩陣。

四種live role enum（`line_viewer`、`line_agent`、`line_manager`、`system_admin`）及至少兩個
不同enabled principal必須覆蓋
全部registered business capabilities；fixture以`AC-CAPABILITY-SESSION-002`與
`LINE-IDENTITY-DELIVERY-001`為oracle。Knowledge reader／manager／publisher／reindexer也必須進同一矩陣，
不能只驗LINE identity happy path。

上述role僅是live compatibility inputs，不是新業務授權模型。禁止為測試`root_admin/admin/
accountant/dispatcher`而修改DB enum、schema、migration或seed；本包固定0 DB change。

只證明「某一個角色剛好有 capability」、只改React menu、只把403測試刪除、或讓unknown capability通過，
一律不算完成。

Denied request必須在application與wakeup前停止。Authorized mutation測試只能在替代wake publisher下證明durable
command／wakeup intent；不得mock或宣稱LINE provider成功。Global typed envelope assertion只適用
`/api/v1/**`；`/api/config/**`維持legacy status並列open finding，不能用Global package虛假覆蓋。

## 5. Required commands

```powershell
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider `
  --basetemp .pytest_tmp\line-knowledge-auth-normalization -q `
  tests\test_admin_auth_security.py `
  tests\test_capability_grant_policy.py `
  tests\test_enabled_admin_business_capability_matrix.py `
  tests\test_line_knowledge_authorization_route_matrix.py `
  tests\line\subsystems\test_line_application_contracts.py `
  tests\line\domain\test_line_order_group_stage6.py `
  tests\line\subsystems\test_contract_knowledge_applications_stage8.py
```

另執行route inventory、unknown/local-bypass、0 provider、strict UTF-8、scoped diff/secret與exact write-set掃描。

## 6. DB gate

| Gate | Status | Evidence／reason |
|---|---|---|
| Scope gate | BLOCKED | 本包尚未取得exact approval；核准後限定0 schema |
| Change inventory | PASS | 0 schema/seed/backfill/destructive；只改capability helpers/dependency |
| Static release gate | NOT_RUN | 無release |
| Descriptor gate | NOT_RUN | 無schema object變更 |
| Read-only plan gate | NOT_RUN | 不適用 |
| Engine verification gate | NOT_RUN | 不適用 |
| Developer acceptance gate | NOT_RUN | 不操作既有DB |

結論：`DB_CHANGE_NOT_READY`。
