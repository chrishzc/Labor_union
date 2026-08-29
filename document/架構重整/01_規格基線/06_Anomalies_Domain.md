# Anomalies Domain

狀態：`current_projection_contract_approved`；`runtime_cutover_blocked_spec_gap`

最新人工裁決：2026-08-29 current-state 異常瘦身

執行邊界：2026-08-29 Task 97 最新人工裁決授權本機 current-only typed Domain／
Application contract、bounded recheck／intent transaction contract 與 focused tests。Runtime cutover、
source replacement、刪檔、schema／DB migration、entry retirement、provider effect 與 deployment 仍不在授權內。
因 current schema 尚缺 `current_anomaly_issues` 與 durable recheck-intent contract，新 contract 只可
fail closed，不得透過 placeholder adapter 或 anomaly-specific claim／delivery state 偽裝 cutover 完成。

## 1. Domain 定位與最新裁決

Anomalies 是各 owning Domain 根事實之上的 current-state protection projection，不是
其他 Domain 的控制中心、歷史事件庫、通用待辦系統或 generic root editor。

2026-08-29 人工裁決固定：

1. 異常只表達當下仍成立的問題；Anomalies 不永久保存 occurrence、workflow、tracking、
   reclassification 或 reopen history。
2. 每次 owner 狀態改變後以 fresh owner facts 重查 predicate。predicate 不成立時
   直接刪除 current row，不寫 resolved row 或 auto-resolve event。
3. claim、resolve、tracking close 不是 root repair，且不得作為 current issue 的生命週期。
4. 需要人工判斷的 current issue 必須有 owner-specific Query → Preview → Confirm →
   Apply → fresh readback → recheck 閉環。
5. 新輸入的格式錯誤由 LIFF／backend validation 阻止；既有或歷史資料留在 owner
   review／work queue，不轉成永久 anomaly occurrence。
6. 只有結果唯一、安全、可重播且使用同一 owner predicate 的流程才可自動化。
   自動化能力不存在時可標 `blocked_capability`，但人工閉環不可缺席。
7. `#anomalies` 只顯示 15 個 current issue，並在 Drawer 內透過 bounded typed owner
   clients 完成人工操作。25 個一般 owner work item 只顯示在各自 owner page。
8. UI、route、worker、detector 都不得直接讀寫 current table 或旁路 owning Domain。

本節完整取代本文較早 revision 的 finance immutable occurrence、generic claim／resolve workflow、
import-warning 六狀態 tracking、necessity reclassification disposition 與 historical-baseline umbrella
契約。舊 source、schema 與測試仍是 live-drift evidence；在後續 cutover gate 完成前不得刪除。

## 2. SSOT 與產品分類

Anomalies 只擁有：

1. 15 個 current issue definition 的 code、owner、subject schema、severity、blocking、details contract
   與 owner action descriptor。
2. 可由 owner facts 完整重建的 `current_anomaly_issues` current projection。
3. bounded recheck 與 current-only Query 契約。

異常條件、金額、日期、identity mapping、assignment lineage、payment／allocation、delivery
與 correction 仍由各 owning Domain 根事實及正式事件擁有。Anomalies 的 details、severity、
blocking 與 UI state 不得成為 Domain command gate。

### 2.1 Runtime 分類

- 15 current issue codes：`SCHEDULE-006`、`PAYOUT-002`、`GOVSUB-001`～`GOVSUB-005`、
  `GOVSUB-007`、`IMPORT-003`、`IMPORT-006`、`BECLASS-001`、`SCHEDULE-002`、
  `SCHEDULE-003`、`LINE-006`、`LINE-004`。
- 25 owner work item／validation results：`PAYOUT-001`、`PAYOUT-003`、`GOVSUB-006`、
  `client_over_refund_recovery_open`、`client_refund_underpayment`、
  `staff_overpayment_recovery_open`、`staff_payout_underpayment`、`IMPORT-001`、
  `finance_import_manual_review`、`CLIENTREFUND-001`、`IMPORT-004`、`HISTORICAL-ORDER-001`、
  `ORDER-001`～`ORDER-004`、`DOC-SEND-001`、`RECEIVABLE-001`、`CLIENTPAYABLE-001`、
  `RETURN-001`、`SUBSIDYADVANCE-001`、`SCHEDULE-001`、`LINE-001`、`LINE-005`、`LINE-002`。
- 3 retire／merge codes：`staff_payout_overpayment`、`HISTORICAL-BASELINE-ROOTS-001`、
  `SCHEDULE-005`。

這是產品目標，不是 live runtime 已 cut over 的證據。在 15-code action map、25-item
replacement map、3-code replacement／absence readback 與 destructive migration gates 通過前，不得
停止舊 writer、隱藏舊 row、刪 registry code 或退役入口。

### 2.2 Case Import 方向

- `BECLASS-001`：HCM 已存在，但沒有唯一且一致的 Client BeClass counterpart。
- `IMPORT-003`：Client BeClass 已存在，但沒有 HCM counterpart。
- 兩者只在 owner 驗證後形成唯一、一致、可追溯的 accepted mapping 時解除。
- 異常頁不得任意挑選候選資料、用姓名／電話模糊比對、merge roots 或直接修改
  mapping／root。人工入口只能送交 owner 能驗證的 evidence 與 typed command。

## 3. Public current-issue contract

### 3.1 Subject identity 與 issue key

`subject_identity` 是每個 definition code 的 closed typed object。下列欄位順序是 canonical：

| Code | Subject identity |
|---|---|
| `SCHEDULE-006` | `case_no + generation` |
| `PAYOUT-002` | `obligation_identity + source_event_identity` |
| `GOVSUB-001` | `bank_fact_identity` |
| `GOVSUB-002` | `bank_fact_identity + batch_id` |
| `GOVSUB-003` | `batch_id + integrity_revision` |
| `GOVSUB-004` | `reversal_bank_fact_identity + source_receipt_id` |
| `GOVSUB-005` | `assignment_id + batch_id + claim_item_id` |
| `GOVSUB-007` | `payable_identity` |
| `IMPORT-003` | `entity_kind + review_item_id` |
| `BECLASS-001` | `case_no` |
| `IMPORT-006` | `batch_id` |
| `SCHEDULE-002` | `assignment_id` |
| `SCHEDULE-003` | canonical sorted `assignment_id_a + assignment_id_b` |
| `LINE-006` | `case_no + notification_reason` |
| `LINE-004` | `subject_type + line_user_id` |

`issue_key` 固定為 `ci_` 加上對
`{"v":1,"definition_code":...,"subject_identity":...}` 的 UTF-8、sorted-key、compact JSON，
使用專用、可注入測試的 `issue_identity_key_v1` 取 HMAC-SHA-256 lowercase hex。
不得 fallback 成可枚舉低熵 identity 的無密鑰 hash。API 不回傳 raw `subject_identity`、
HMAC input 或 key version，只回各 code 的 closed redacted subject view。
2026-08-29 人工裁決：同一 canonical code＋subject 跨多次 episode 永遠使用同一 key；
一般 key rotation 不得改變公開 identity，需更換時必須另有保持舊 key 穩定性的
exact migration contract 與 Authority。每次重新成立仍建立新 current episode。

### 3.2 Current projection

`CurrentIssueProjection` 至少包含：

- `issue_key`、`definition_code`、`owner_domain`、closed `subject_identity`；
- `owner_snapshot_token`、`severity`、`blocking`；
- `details_version=1` 與以 definition code 為 discriminator 的 closed typed details；
- `episode_started_at`、`last_verified_at`；
- closed manual-action descriptors 與 automation availability。

episode timestamps 只隨 current row 存在；predicate false 刪除 row 後不另行保存。
未知 code／version、缺欄、額外欄位、PII 穿透或 malformed subject 固定 fail closed。

### 3.3 API 與 React

- `GET /api/v1/anomalies`：只回 current rows。可用 filters 限
  `definition_code | owner_domain | blocking | limit | cursor`。
- `limit` 預設 50、上限 100。排序為 blocking 優先、severity 由高到低、
  `episode_started_at` 舊到新、`issue_key` ascending。cursor 是有 version、不可竄改的
  opaque token，必須綁定相同 filters、limit 與最後排序 tuple。malformed、簽章
  錯誤、版本不支援或 binding 不符回 `anomaly_cursor_invalid`。
- 2026-08-29 人工裁決為 live best-effort pagination：cursor 不綁 snapshot，每頁
  讀取當下 current rows。翻頁期間 insert、delete 或排序欄位變動可導致漏列或重複；
  client 以 `issue_key` 去重，需最新 authoritative view 時從第一頁重查。UI 不得
  將一次翻頁結果表示為 snapshot-complete。
- `GET /api/v1/anomalies/{issue_key}`：回 current details、owner evidence、blocking effect 與
  manual-action descriptors；無 occurrence／timeline／claimed／resolved fields。
- `#anomalies` 只渲染 15 個 current issue。Drawer 依 closed action descriptor 呼叫單一
  bounded owner client；不接 raw endpoint、raw dict 或 generic mutation payload。
- action 成功但 recheck 失敗時，UI 只顯示「owner 操作已提交、目前狀態待重新查詢」；
  不得先移除 issue。

Stable errors 沿用 Global typed error envelope，至少包含：
`anomaly_not_found`、`anomaly_definition_not_found`、`anomaly_version_conflict`、
`anomaly_projection_stale`、`anomaly_projection_data_integrity_violation`、
`recovery_action_not_available`、`recovery_action_contract_version_mismatch`、
`recovery_source_binding_incomplete`、`owner_snapshot_unavailable`、`transaction_failed`。
cursor 邊界另固定 `anomaly_cursor_invalid`。

## 4. Owner action contract

每個 current issue 必須在 owning Domain 正式規格與 15-code source map 同時固定：

1. owner predicate 使用的 root facts、subject identity、blocking effect 與 completion predicate；
2. typed Query、Preview、Apply 的 exact operation、version 與 closed input／output；
3. actor capability、reason、evidence、fresh owner version、preview fingerprint、idempotency 與 receipt；
4. 合法 outcome、禁止 outcome、stale、timeout、partial failure 與 outcome-unknown reconciliation；
5. Apply 後 owner readback、durable recheck intent 與 Drawer renderer。

navigation-only、Query-only、projector retry、generic resolve、`available_actions=[]` 或「尚未支援」都不是
terminal-ready manual action。只有 automation 可以 `blocked_capability`；manual action 缺漏時該 code
與整體 cutover 都保持 `SPEC_GAP`。

## 5. Bounded recheck 與 transaction

Recheck 固定依下列步驟執行：

1. 建立 canonical bounded scope，明確列出 definition codes、subject type 與 canonical sorted
   unique subject IDs。
2. 每個 definition 將 subject 映射為 closed `owner_lock_keys`，key 為
   `(owner_domain, owner_root_type, canonical_owner_root_id)`；依 tuple 的 canonical UTF-8 byte
   ordering 取得 owner／scope lock。不同 code／subject type 只要指向同一 owner root，必須產生
   相同 lock key。映射不完整固定 `SPEC_GAP`；不得只鎖現有 current rows。
3. 取得 lock 後讀取 owner facts，並取得覆蓋整個 scope 的 monotonic owner version 或
   snapshot token。
4. 只使用該 snapshot 計算完整 candidate set，並回報 `authoritative_complete`。
5. 寫入前在同一 outer transaction 重新驗證 owner token；過期時整批零寫入。
6. token 仍 current 且 scope 完整時，才對精確 scope 執行 present upsert、absent
   delete，再一次 commit。
7. 重疊 scope 使用相同 lock ordering 與 token validation。duplicate candidate、non-canonical
   subject 或 ordering 固定 fail closed。
8. 每個改變 owner root 的 transaction 在同一 commit 寫入通用 durable recheck intent。
   intent append 失敗時 owner mutation 整體零提交；只有已 committed intent 的後續處理失敗或
   結果不明才由 replay 及 bounded maintenance repair 補回。
9. maintenance subject universe 是 owner 可枚舉 candidate-relevant subjects 與 current projection
   已有 subjects 的 canonical union；兩側各用 deterministic bounded cursor／watermark。只掃一側、
   任一側 incomplete 或無法 authoritative readback 時都不得宣稱 complete，且零 delete。
10. repair 只重查目前 owner facts，不從舊 alert snapshot 復原，不建立 anomaly
   occurrence／workflow／tracking／reclassification history。

`authoritative_complete=false`、timeout、owner unavailable、schema drift、stale token、duplicate
candidate、重疊 scope lock failure 或 durable intent processing failure 都不得刪除 current row。
Repository 不得 commit／rollback；route、worker、detector 不得直接寫 projection。

## 6. Cutover、entry 與 migration gate

API、DB 與 entry cutover 必須等到：

- 15-code action source map 全部 terminal-ready；
- 25 owner replacements 的 exact Query／typed response／owner UI／completion／readback 全部可達；
- 3 retire／merge replacements 與 absence readback 通過；
- Task 97 正式 tracked identity、revision、WP、receipt 與 terminal gate 已精確映射；
- 99-path dependency inventory 每列具備 exact successor、caller、owner、readback、deletion／
  rewrite gate、focused tests 與 final zero-reference oracle；
- entry caller inventory 完成。證明只有內部 caller 且 replacement 完成者可直接 removed；
  外部或未知 caller 先回 typed `410 Gone`。

任何 preserve-data target 要 drop legacy anomaly tables 前，必須先建立加密、限時、
可驗證且具 rollback owner 的 source backup，並實際驗證 schema／data／source-version
一致還原。無 backup、expiry、restore evidence 或 exact target Authority 時固定
`DB_CHANGE_NOT_READY`。不得由舊 alert snapshot backfill 新 current rows；只能以 fresh owner recheck
重建。production、`union_db`、provider、deployment、entry switch 與實際 destructive target
均不在本文 Authority 內。

Task 97 conflict precedence（2026-08-29 人工裁決）：本 Domain 規格收旂與本機當前
Task 97 若在 public contract、owner／SSOT、transaction、writer、entry disposition、shared
write set 或驗收基線重疊，一律以 Task 97 優先，Anomalies 重疊 lane 固定
`blocked_by_task97_priority`。此優先序不代表 untracked Task 97 已成為 canonical dependency 或完成證據。

## 7. Acceptance 與 convergence

規格重新收旂前，read-only review 必須證明：

1. 15／25／3 分類精確，Case Import 方向與 `#anomalies` UI 邊界無衝突。
2. 15 個 manual action 與 25 個 replacement 無 `SPEC_GAP`、generic resolve、navigation-only 或
   ownerless outcome。
3. issue identity、pagination、details version、episode timestamps、typed errors 與 PII redaction 可機械驗證。
4. Recheck 覆蓋 stale insert、absent row、incomplete scope、overlap、duplicate、timeout、intent loss、
   repair 與 atomic rollback，不誤刪 current row。
5. Task 97 dependency、99-path inventory、entry caller disposition 與 destructive rollback 契約完整。
6. strict UTF-8、governance validator、reference scan 與 `git diff --check` PASS。

```yaml
spec_route:
  status: SPEC_GAP
convergence:
  status: NOT_READY
  blockers:
    - 15-code owner action source map incomplete
    - 25 owner replacements incomplete
    - 15-code subject scalar normalization and public redaction views incomplete
    - recheck owner-lock and maintenance subject-universe mappings incomplete
    - Task 97 canonical dependency unavailable in base
    - dependency inventory lacks executable successor gates
    - destructive migration remains unauthorized
```

只有上述 blocker 全部解除且 read-only review PASS，才可依 2026-08-29 人工條件式授權
將規格與執行計劃恢復為 `approved`。
