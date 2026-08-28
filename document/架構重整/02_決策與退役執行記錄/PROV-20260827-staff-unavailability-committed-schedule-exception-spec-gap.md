# Staff unavailability committed-schedule exception 規格缺口

- `spec_gap_id`: `PROV-20260827-staff-unavailability-committed-schedule-exception`
- `declared_status`: `proposed`
- `business_authority`: `CONFIRMED-2026-08-27`
- `owner`: `Scheduling`
- `controlling_spec`: `24_Staff_Matching_Preferences與不可服務期間正式規格.md` §3.3
- `effect_ceiling`: local source、versioned additive schema、`lu_test_*` validation；不含`union_db`或production

## 1. 已確認的業務契約

1. Staff可提出不可排班申請，人工確認後才由Scheduling owner寫入。
2. 與既有有效assignment／正式訂單排程衝突時，Preview顯示exact case、assignment與日期，
   預設拒絕。
3. 具權限人員可以`force_preserve_committed_schedule`明確核准；既有訂單排程固定優先，
   不得因不可排班申請取消、縮短、改派或標示為不上班。
4. 重疊日期必須保存`committed_schedule_exception` append-only lineage；不可排班仍約束未來媒合與
   尚未承諾日期。既有服務如需改變，只能另走leave／substitution／cancellation。
5. Apply必須fresh-read相同衝突集合；衝突集合或任一owner version變動固定stale。

## 2. Live drift

- `db/schema_parts/188_matching_preferences_and_staff_availability.sql`只有availability aggregate、block、
  event與receipt；沒有可機械查詢的case／assignment／conflict-date／owner-version exception binding。
- `domains/scheduling/staff_availability.py`仍將assignment conflict轉成`ASSIGNMENT_CONFLICT`且不可Apply。
- `api/routes/staff_availability.py`、`api/schemas/staff_availability.py`與
  `infrastructure/mysql/staff_availability_repository.py`尚無force capability、fresh conflict fingerprint、
  exception readback與stale contract。
- event／receipt JSON snapshot可作evidence，不能代替可join、可重放、可對帳的canonical lineage。

## 3. Bounded candidate inventory（待架構確認）

| 分類 | Candidate | 資料效果 |
|---|---|---|
| `schema-only` | additive `scheduling_staff_unavailability_committed_exceptions` | 每筆一日、綁定`block_id`、`case_no`、`conflict_source_kind=assignment | waiting_lock`、exact source identity與`conflict_date`，並保存availability／source owner versions、conflict fingerprint與source event identity；append-only。 |
| `schema-only` | availability event／receipt descriptor extension | 保存force flag、capability、reason、conflict fingerprint與exception identities；不把JSON當唯一binding。 |
| `system-seed` | none | 不新增business vocabulary seed。 |
| `business-row-backfill` | none by default | 既有hard-block流程理論上沒有已核准exception；若後續發現legacy rows，另立影響盤點與unresolved review，不猜測回填。 |
| `destructive` | none | 不刪除、改寫或取代既有availability／assignment根事實。 |

## 4. Required implementation contract

- Query／Preview零寫入，回exact conflict identities、dates、current versions、fingerprint與
  `can_apply=false | can_force_preserve=true`。
- Apply需Scheduling force capability、explicit boolean、非空reason、same preview fingerprint、
  expected availability version與衝突owner versions。
- 同一outer UoW鎖occupancy mutex、fresh-read block／conflicts／versions，追加block、event、exception bindings、
  receipt與outbox；不mutation既有assignment。
- same-key same-payload回原receipt；same-key different-payload、conflict-set drift、version drift固定fail closed。
- Calendar同時顯示unavailability與committed service；Matching只排除未來／尚未承諾衝突日。

### 4.1 Exact binding shape

- 唯一性候選：`(block_id, conflict_source_kind, conflict_source_id, conflict_date)`。
- `case_no`必填，不得只由FK推導；Preview／readback必須直接顯示並驗證exact case。
- assignment來源必存`assignment_id`；waiting lock來源必存`lock_id`與逐日`lock_day_id`，
  並以check constraint保證兩種來源二選一。
- assignment owner version來自`scheduling_aggregates.aggregate_version`與effective generation；
  waiting lock不得以timestamp或非canonical event count假補version。
- buffer不屬於`committed_schedule_exception`，不得被`force_preserve_committed_schedule`覆蓋；
  它維持獨立`requires_manual_confirmation`語意。

### 4.2 待人工裁決

1. 是否新增專用capability
   `scheduling.staff_availability.force_preserve_committed_schedule`，並且只由明確grant的內部人員擁有，
   不自動等同`system.administration`或所有enabled users。
2. waiting lock是否新增dedicated aggregate version（建議），而不沿用可與lock變動脫鉤的
   matching-plan version或event sequence。
3. buffer-only衝突經人工確認後，是「保留buffer並拒絕不可排班」，還是「先透過專用
   Scheduling command釋放buffer，再重做availability Preview／Apply」；不得在availability Apply內隱式刪改buffer。

## 5. DB change gates

| Gate | 結果 | 證據／原因 |
|---|---|---|
| Scope gate | `PASS` | 人工業務裁決、Scheduling owner與正式規格 §3.3已確定。 |
| Change inventory | `BLOCKED` | 本文為candidate；exact table／descriptor／write set尚待人工架構確認與approved Work Package。 |
| Static release gate | `NOT_RUN` | 尚無versioned release candidate。 |
| Descriptor gate | `NOT_RUN` | 尚無owned-object descriptor。 |
| Read-only plan gate | `NOT_RUN` | 尚無canonical release artifact。 |
| Engine verification gate | `NOT_RUN` | 未施工fresh／preserve-data validation。 |
| Developer acceptance gate | `NOT_RUN` | 前置gates未通過。 |

總結：`DB_CHANGE_NOT_READY`。本文不授權DDL、migration、seed／backfill、reset、replacement、
`--switch`或任何`union_db`／production操作。
