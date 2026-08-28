---
doc_type: work-package
declared_status: approved
date: 2026-08-27
owner: Anomalies / Orders / Scheduling / LINE / Staff Payables
current_item: CUR-ANOMALY-MANUAL-REMEDIATION-01
---

# 異常必要性移轉工作包

## 1. Authority、目標與完成邊界

本包依 2026-08-27 使用者裁決，把 live 42-code inventory 收斂為 33 個 current active anomaly、7 個
owner work items、1 個退役 false-positive、1 個 audit-only successor occurrence。controlling spec 為
`01_規格基線/06_Anomalies_Domain.md`「異常必要性與一般工作項分界」及其
`AnomalyReclassificationDisposition` contract。

完成不是把 UI 隱藏或刪 registry row。必須保留舊 history／occurrence，先證明 owner work item／successor
可讀，再以 immutable disposition＋receipt 將既有 active alert 轉 inactive；所有 target rows 完成後才停止
producer。`codes()` 保留完整歷史 catalog，`active_codes()` 是33-code產品目標，不是migration期間的operational
effective count；effective producer／active-row狀態須由cutover readback另行證明。

本包不建立新的 Orders、LINE 或 Finance work-item state machine，不使用 generic resolve，不操作
`union_db`／production，不發布 provider side effect，也不把健康新流程「不會產生」當作刪除 legacy integrity
detector 的理由。

## 2. Package partition

### ANM-NM-A：Catalog lifecycle 與 immutable migration disposition

- `status`: `in-progress`
- Objective：建立 `catalog | active | work_item | retired | audit_only` definition lifecycle、
  `active_codes()`、typed Query／Preview／Apply、immutable disposition／receipt 與 deterministic bounded runner。
- Write set：`domains/anomalies/registry.py`、`domains/anomalies/maintenance.py`、
  `subsystems/anomalies/maintenance_workflow.py`、`infrastructure/mysql/anomaly_maintenance_repository.py`、
  專用 API schema／route、additive schema part／release／descriptor、focused tests與本文件 evidence。
- Data effect：新增 system metadata；只對本包列出的 alert fingerprints append disposition／receipt 並把
  current predicate轉 inactive。不得修改 source Domain root 或刪除 anomaly history。
- Acceptance：same-payload replay、conflict、stale、missing target、unknown outcome、partial page、cursor repeat、
  request-only batch fingerprint、policy drift、per-item savepoint rollback、完整two-part cursor、completion sweep、
  before/after fingerprint與 immutable trigger全部有證據。
- Current execution：pure Domain catalog slice 已完成，`codes()` 保留42、`active_codes()`精確為33，另有
  `7 work_item / 1 retired / 1 audit_only`。immutable disposition Domain、application Query／Preview／Apply、
  deterministic bounded runner、MySQL repository、Staff successor fresh verifier與additive schema/release均已完成；
  R11 fresh及含代表性既有alert的preserve-data candidate均通過。專用 maintenance API source 已存在，並由
  server-owned `SCHEDULE-005` policy 支援；`tests/test_anomaly_necessity_migration_api.py` API unit tests 已通過。
  `tests/test_anomaly_necessity_migration_disposable_mysql_e2e.py` 的真 MySQL single Q/P/A＋replay、batch／
  completion sweep replay、HTTP Q/P/A＋replay 三項均為 `passed`，但 durable execution receipt 尚未同步，
  故標記為 `execution evidence pending receipt`，不得冒充 developer acceptance。developer acceptance 仍為
  `NOT_RUN`，本package維持`in-progress`而非`completed`。

### ANM-NM-B：六個一般工作項與 `SCHEDULE-005` 退役

- `status`: `in-progress`，依賴 ANM-NM-A。
- Codes：`ORDER-001`～`ORDER-004`、`DOC-SEND-001`、`LINE-002` → owner work item；
  `SCHEDULE-005` → `retired_false_positive`。
- Owner targets：Orders unfinished 11-step projection、Candidate Contact Pool、Matching Plan communication、
  canonical `line_delivery_tasks` Query。`SCHEDULE-005` 無 target，但必須引用 preference-only spec/release evidence。
- Write set：兩個 process-reminder producer、registry lifecycle、Orders stage action links、Anomalies／Orders／
  Scheduling／LINE typed adapters與focused tests；共享 registry與producer只由 integration writer 修改。
- Acceptance：migration 前 target work queue 可讀；migration 後六碼仍在 owner工作區但不在 active anomaly；
  `SCHEDULE-005` 不再新建且既有 alert inactive；Browser可從舊 history導向 owner context；沒有 provider call。
- Current execution：`SCHEDULE-005` 已從 runtime process-reminder scan 移除，pure builder 只留作
  migration／regression fixture；focused cutover regression `23 passed`。既有 alert 的 durable retirement receipt
  尚待同步。六個 work-item code 的 owner queue 存在，但 exact target identity／canonical version／
  same-transaction fresh-lock contract 尚未完成正式裁決，不得用 legacy timestamp、`max(event.id)`、
  `plan.version`或任意 webhook 代替。

### ANM-NM-C：Staff overpayment successor 去重

- `status`: `in-progress`，依賴 ANM-NM-A。
- Objective：consumer 必須先處理 `staff_overpayment_recovery_established`，鎖定 payout difference／recovery
  lineage並讀回 `staff_overpayment_recovery_open` successor，才把 `staff_payout_overpayment` disposition 設為
  `replaced_by_successor`。舊 occurrence留 history，active list只留 successor。
- Current execution：consumer claim 已納入實際 producer 的
  `intent_type=staff_overpayment_recovery_updated` + payload
  `event_type=staff_overpayment_recovery_established`，並以 fresh recovery root 決定 successor active／
  terminal；canonical `finance-import-row:<id>`、stale replay 與 fail-closed regression 由主代理重驗
  `45 passed`。真 MySQL old inactive／successor active／history retained 及 React history 仍為 `NOT_RUN`。
- Write set：Staff payout difference／recovery consumers、root projection、repository、focused／disposable MySQL
  tests與React successor history顯示。
- Acceptance：successor建立失敗、歧義、stale、dead-letter或readback failure時舊 alert保持 active；成功後
  old inactive／successor active；terminal recovery只移除 successor，不刪 occurrence。

### ANM-NM-D：後續 owner-contract／schema packages

- `status`: `blocked`，不阻擋 A／B／C。
- `LINE-004`：合法 customer＋staff dual role 已裁決，但 live `line_identity_bindings(line_user_id PK)` 無法保存
  role-scoped雙 roots；需 additive subject-scoped identity release、preserve-data migration與同-type conflict oracle。
- `SUBSIDYADVANCE-001`：`UNION_ADVANCE_DUE` 已裁決為 Staff Payables work item，但尚無 typed owner Q/P/A；
  必須先定義 funding work item→payable/payout/recovery contract，不能只移除 anomaly。
- `SCHEDULE-002`：只保留 incomplete replacement/substitution lineage，但所有日期 outcome 與 Finance／Payroll
  split terminal readback contract仍需完成；在此之前保留 fail closed。

## 3. Ordered execution

1. ANM-NM-A schema inventory、release chain、descriptor、read-only plan、fresh與preserve-data gates。
2. Domain／Subsystem focused tests後，以 disposable MySQL 驗證 disposition Apply、replay、partial batch與rollback。
3. ANM-NM-B 先驗 owner work queue，再 migration active rows，最後停 producer；不得反序。
4. ANM-NM-C 先修 established consumer與successor readback，再 migration old payout alerts。
5. API／React build與 `lu_test_*` Browser：舊 alert消失、owner工作仍可操作、history/successor可讀。
6. A～C全PASS時的中間 current target 是 `34`（`SUBSIDYADVANCE-001` 仍暫留）；D完成後才達最終 `33`。

## 4. Verification profile

- Module：registry lifecycle、disposition candidate、cursor、LINE cross-role negatives、Staff successor truth table。
- Subsystem：Query／Preview／Apply、single outer UoW、idempotency、fresh target readback、producer admission。
- Domain：正常工作項不屬 anomaly；false-positive／successor semantics；取消／完成 lifecycle gates。
- Global：typed errors、capability、outbox／receipt、migration release、preserve-data、entry contract。
- Runtime：真 MySQL before/after、API list/detail、React owner navigation、Browser old→new工作區→history。

## 5. Database change gate（current）

| Gate | 狀態 | Current evidence／next command |
|---|---|---|
| Scope | PASS | 本 approved Work Package、`06_Anomalies_Domain.md` necessity contract與使用者2026-08-27裁決。 |
| Change inventory | PASS | `schema-only`：新增 disposition／receipt／batch receipt 三個 append-only owned objects；`system-seed`：無；`business-row-backfill`：無，runner mutation 不得藏入 release；`destructive`：無。target 三欄只在 false-positive 全空，該類另綁 rulebook／release evidence。 |
| Static release | PASS | R9.1 `1009_anomaly_reclassification_disposition.sql`已補完整two-part cursor、eligible-code set/fingerprint與effective start-cursor uniqueness；release manifest／descriptor、fresh assembly 136 parts與validation release v15已重算，manifest validator及release build `--check` PASS。 |
| Descriptor | PASS | R11 fresh MySQL與preserve-data candidate均將`1009_anomaly_reclassification_disposition.sql`讀回`exact`；三表欄位數22／20／11，六個immutable triggers存在。 |
| Read-only plan | PASS | R11 preserve-data dry-run列1009為`absent`；artifact SHA-256=`d4c50cafdfeef450ab707707f6b5702582a71eb5adbaaaf1cc2434bc11ff77d5`，plan fingerprint=`2e5fec42f11e9385e5021b2324428e960256caacd4ad4bd435917b11c1fca331`。 |
| Engine verification | PASS | R11 fresh bootstrap及source→candidate backup／restore／Apply／Verify完成；owned object=`exact`、view mismatch=0、backfills=[]。`anomaly_current_alerts` 3 rows與`staff_overpayment_recoveries` 1 row的count／checksum／primary-key fingerprint前後一致；新增三表皆0 rows。證據：`03_追蹤清單與證據/evidence/2026-08-27_anomaly_reclassification_schema_engine_receipt.md`。 |
| Developer acceptance | NOT_RUN | 待 allowlisted local source backup、candidate、replacement receipt與rollback evidence；不得碰 `union_db`。 |

總結：`DB_CHANGE_NOT_READY`。R9.1 schema part `1009_anomaly_reclassification_disposition.sql`／release
`labor-union-anomaly-reclassification-disposition-2026-08-27-v1` 的scope、inventory、static、descriptor、read-only
plan、fresh及preserve-data engine gates均已PASS；ANM-NM-A durable execution receipt 尚待同步，且 developer
acceptance 尚未執行。R11 evidence取代舊R7。
不得執行`--switch`、不得隱藏row backfill、不得碰`union_db`。

## 6. Bidirectional coverage

| Requirement | Package | Direct evidence |
|---|---|---|
| 42→33 necessity partition | A／B／C／D | registry catalog/active partition test與oracle matrix |
| 既有 alert 不永久卡住 | A／B | disposition Apply＋bounded runner＋active-list readback |
| 正常待辦不遺失 | B | Orders/Matching/LINE owner Query與Browser navigation |
| 偏好不形成 hard anomaly | B | SCHEDULE-005 producer absence＋retirement receipt |
| payout只留一個active問題 | C | old inactive／successor active／history retained MySQL oracle |
| dual-role合法 | D | role-scoped roots＋same-type conflict tests＋preserve-data gate |
| advance是Staff工作項 | D | Staff Q/P/A／payout／recovery readback，Anomalies無該碼 |

`package_status`: `SPEC_GAP`（整體）；`execution_ready_packages`: `ANM-NM-A | ANM-NM-B | ANM-NM-C`；
`blocked_package`: `ANM-NM-D`。B 的六碼 owner target 契約仍需收旂；A～C 的其餘既定 scope 可施工，
但不得用其 PASS 宣稱33-code target已全部落地。
