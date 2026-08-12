# Contract Signing、簽約前服務承諾與正常驗收資料鏈正式規格

## 1. 文件狀態

- 狀態：`approved`
- 人工裁決日期：2026-08-10
- 正式收斂日期：2026-08-11
- Owner：Contract Signing Integration
- 跨域協作者：Orders、Assignments／Scheduling、Client Finance、LINE Integration
- 歷史來源：`document/架構重整/04_已完成與上線封存/superseded_specs/契約整合與正常測試資料鏈_決策草案.md`
- 已完成執行範圍：[`56_Contract_Signing_and_UI_Validation_Work_Package.md`](../04_已完成與上線封存/work_packages/56_Contract_Signing_and_UI_Validation_Work_Package.md)

本規格是第 `01`、`02`、`04`、`07`、`10`、`15`、`17` 份正式規格的契約簽署補充裁決。
若舊條款仍把「客戶簽回」「契約完成」「訂金核銷」「訂單成立」視為同一事件，或要求先建立
execution schedule 才能完成客戶契約，以本規格較新的人工裁決為準。

## 2. Business scenario 與 Global invariants

```text
配對完成
→ 每個月嫂 segment 產生、寄送並回收月嫂契約
→ 全段簽回且精確服務日守恆，建立簽約前服務承諾
├─→ 建立唯一簽約前訂金義務 → 訂金可先核銷 → 訂單成立
└─→ 產生、寄送並回收客戶契約 → 客戶簽回與 Contract Completion 原子完成
→ 訂金與客戶契約均成立
→ commitment exact conversion 為 execution assignment／effective schedule
→ actual start → 月曆、薪資、補助與完成
```

1. 訂金核銷、客戶簽回、Contract Completion 與 execution conversion 是四個可區分事實。
2. 訂金有效即可使 Orders 進入「訂單成立」；這不代表客戶已簽約，也不允許 execution。
3. 客戶簽回前不得建立 execution assignment；commitment 不得被 Calendar、Payroll 或
   Government Subsidy 當成正式服務事實。
4. Query 唯讀、Preview 零寫入；每個 Apply 只有一個 outer Unit of Work 與 commit owner。
5. 外部 LINE 傳送只由 committed durable delivery task 執行；delivery 成功不等於簽署完成。
6. UI、script、fixture 與 migration 不得直接寫契約完成、Orders status、execution schedule、
   finance settled projection、alert 或 receipt。

## 3. Ownership、SSOT 與 non-goals

| Owner | Root facts／責任 | 不擁有 |
|---|---|---|
| Contract Signing Integration | 核准模板引用、不可變文件版本、月嫂／客戶 sent 與 signed-received events、provider-neutral identity、status version、command receipt | Orders lifecycle、應收金額、execution assignment、LINE attempt 結果 |
| Scheduling Commitment | matching plan/version snapshot、segment、月嫂、精確服務日、commitment event／terminal event | execution schedule、薪資、補助、Orders status |
| Client Finance | 簽約前訂金義務、客戶簽回後的剩餘期款、ledger、allocation、settlement | 契約簽署證據、Orders status |
| Orders | Contract Completion event、`contract_identity` projection、lifecycle | 外部簽署 payload、LINE delivery、assignment 日 |
| Assignments／Scheduling | commitment 的 exact conversion、正式 assignment／schedule 與 occupancy | 契約文件、應收、LINE |
| LINE Integration | 綁定身分、delivery task、attempt 與 retry | 契約或 Orders 成功狀態 |

### 3.1 Root facts 與 derived values

- `contract_document_version`：scope、case、segment、template id/version/digest、source snapshot
  digest、MIME、size、SHA-256、archive locator、supersedes id、actor、created-at。
- `contract_signing_event`：case、scope、segment、document version、event type、provider-neutral
  event identity、payload digest、status version、actor、occurred-at、idempotency identity。
- `precontract_service_commitment` 與 days：matching plan/version、segment snapshot digest、staff、
  精確服務日、版本、created／cancelled／superseded／converted events。
- Contract Signing command receipt、document access grant、LINE delivery intent/outbox。
- Client Finance obligation／ledger roots、Orders contract event、Scheduling assignments 仍由各自
  owning Domain 擁有。
- segment sent／signed status、commitment readiness、client contract status、conversion eligibility、
  UI blockers 與 alerts 都是 derived projections，不是 mutation SSOT。

### 3.2 Non-goals

- 不提供任意本機契約檔作為核准模板，也不裁決電子簽章 provider。
- 不在 LINE callback、Streamlit 或 API route 直接推進 Orders／Scheduling／Finance。
- 不支援半日或分時 commitment；同案同日只有一個月嫂 owner。
- 不以人工勾選、delivery success、訂金核銷或 Orders status 偽造簽署事件。
- 不授權 production DB migration、外部傳送、刪除舊資料或 cutover。

## 4. 狀態機

### 4.1 月嫂 segment 與 commitment

```text
draft_generated → staff_contract_sent → staff_signed_received
全部有效 segment signed + 精確日守恆 → commitment_ready
commitment_ready → converted | cancelled | superseded
```

- 全部 segment 的精確服務日不得重疊，合計必須等於 `orders.service_days`。
- `staff_signed_received` 不建立 client receivable、execution、薪資、補助或訂單成立。
- matching plan/version 變更使舊 commitment `superseded`；不得原地改寫日期或月嫂。

### 4.2 客戶契約與 Orders

```text
commitment_ready → client_draft_generated → client_contract_sent
→ client_signed_received → contract_completed

有效訂金核銷 → 訂單成立
訂單成立 AND contract_completed AND commitment_ready
→ commitment converted → execution assignment／schedule
```

- 客戶不得早於全部月嫂簽回。
- 簽回只接受與目前有效 sent document、commitment 與案件相符的不可變版本。
- `official_service_dates_incomplete` 保留為 stable blocker 名稱；在 conversion 前，其完整性由
  有效 commitment 的精確服務日判斷，不要求先建立 execution schedule。
- 服務中仍須 actual start、有效 execution schedule、訂金與契約完成；不得只看 Orders label。

## 5. Commands、Queries 與 typed views

Commands：

- `GenerateContractDocumentVersion`
- `SendStaffContract`
- `UploadReturnedContractDocument`
- `RecordStaffSignedContract`
- `SendClientContract`
- `RecordClientSignedContractAndCompleteContract`
- `CancelOrSupersedeCommitment`
- `ConvertCommitmentToExecution`

每個 mutation 必須包含 actor、reason、correlation id、`expected_status_version`、idempotency key
與 canonical command fingerprint。簽回命令另必須帶目前 sent document 的
`expected_document_version_id`；不同版本一律回 `contract_document_version_stale`。文件 bytes
只由 upload/archive port 接受，不能穿透 Domain。

Queries 提供案件契約進度、每 segment 狀態、目前文件版本、delivery 狀態、commitment 摘要與
blockers。文件下載／預覽必須以案件、角色、文件版本授權並寫 security audit。Query 回傳 typed
view，不得回 raw persistence dict 或觸發狀態轉換。

## 6. Transaction、lock 與 partial failure

### 6.1 Send 與月嫂最後一段簽回

- Send 鎖定案件、plan/segment、status version、文件與 LINE binding；同交易建立 sent event、
  access grant、delivery task/outbox、receipt 與新版本，commit 後才由 worker 傳送。
- 月嫂簽回按 plan、segment id 固定順序鎖定；驗證文件、事件、日期守恆與版本；append event。
- 最後一段簽回同交易建立 commitment header/days、簽約前 deposit obligation、兩端
  receipt/outbox；任一步失敗全部回滾。

### 6.2 客戶簽回

鎖定案件、有效 commitment、目前 client document、Orders aggregate、Client Finance account、
既有 deposit obligation 與 command receipt。單一交易依序：

1. archive 已成功且 digest 相符才 append client signed event；
2. 投影唯一 `orders.contract_identity`；
3. append Orders Contract Completion event；
4. 保留既有 deposit obligation，只補第一、第二期或 policy 定義的剩餘義務；
5. 重評 lifecycle，但不得覆寫已由訂金形成的「訂單成立」；
6. 寫 versions、audit、outbox 與 receipt；單一 commit。

不得以 HTTP 串接兩個 transaction。archive 在 DB rollback 後形成的 orphan object 必須由受控
reaper 依「無 document root 引用」安全清理，不得把 orphan 誤認為可寄送版本。

### 6.3 Execution conversion

鎖定 commitment、Orders、Client Finance settlement、matching plan、所有受影響 staff occupancy
與 assignment aggregate。fresh candidate 的 case、plan/version、staff、日期集合必須與 commitment
完全相同；同交易建立 assignments、schedules、converted event、Payroll impact、outbox、receipt。
任何 mismatch 或 occupancy conflict 零 partial write。

## 7. Idempotency、retry、stale、timeout 與 conflict

- 相同 idempotency key＋相同 fingerprint 回原 receipt，零新增。
- 相同 key 或 provider event identity＋不同 fingerprint 回
  `contract_signature_idempotency_conflict`。
- status、plan、document、Orders、Finance 或 Scheduling version stale 時回 typed conflict，UI
  必須重新 Query／Preview；client 不自動換 key 重送敏感 command。
- UI 對同一份上傳檔與 sent-document version 的使用者重送，必須保存同一 idempotency key；只有
  檔案或版本快照變更、或收到 stale 後重新確認，才建立新 key。
- 使用者選錯文件、驗證失敗與 Domain blocker 不 retry。
- DB／archive／provider unavailable 可 retry，但必須保留同一 identity；timeout 結果未知時先查
  receipt/delivery task，禁止直接建立第二份文件或事件。
- delivery worker 依 durable task policy retry；簽署 root 永不因傳送失敗回滾。

## 8. Typed errors、alerts 與人工入口

Stable errors 至少包含：

- `contract_document_empty | contract_document_too_large | contract_document_type_not_allowed`
- `contract_document_digest_mismatch | contract_document_archive_failed`
- `contract_status_version_conflict | contract_document_version_stale`
- `contract_line_recipient_unbound | contract_line_recipient_subject_mismatch`
- `staff_contract_not_sent | client_contract_not_sent | staff_commitment_incomplete`
- `commitment_service_days_invalid | commitment_not_effective`
- `official_service_dates_incomplete | service_time_terms_incomplete`
- `contract_signature_idempotency_conflict`
- `commitment_execution_mismatch | assignment_occupancy_conflict`
- `contract_signing_unavailable | transaction_failed`

Alerts 涵蓋長時間未寄送／未簽回、delivery exhausted、archive/digest failure、stale plan、承諾
日期不守恆、identity conflict、conversion mismatch 與 orphan archive。Alert resolve 不得改變根因。

人工 UI 必須提供模板與版本、產生／預覽、寄送、上傳簽回、紀錄簽署、delivery 狀態、blocker、
receipt 與 repair navigation；不提供 status 直接修改或 SQL/data-browser patch。

## 9. Ports、Module 與 Adapter 邊界

Ports：TemplateCatalog、ContractRenderer、ImmutableDocumentArchive、DocumentAccessGrant、
SigningEventRepository、CommitmentRepository、OrdersContractCompletionPort、
ClientFinanceObligationPort、SchedulingConversionPort、LineDeliveryTaskPort、SecurityAuditPort、
OutboxPort、BusinessClock 與 outer UnitOfWork。

純 Module：DocumentDigest、SigningSequenceValidator、CommitmentDayConservationValidator、
ContractStatusReducer、CommandFingerprint、RemainingObligationPlanner、
CommitmentExecutionEqualityValidator。Module 不讀 DB、檔案、網路或現在時間。

FastAPI 只驗證 transport 並映射 typed errors；Streamlit 只呼叫 bounded typed client。MySQL、
archive 與 LINE 是 port adapter，不重新判斷狀態機或 commit。

## 10. Preservation migration 與 validation dataset

- 唯一 legacy source 固定為核准的 preserved source；source 永遠唯讀。
- 目標只允許明確確認的 `lu_test_dataset_*`，每次重建使用 current schema，不寫 candidate／正式庫。
- additive schema → preflight/digest → root adapter migration → projector rebuild → replay versioned
  scenario manifests → DB/API/UI verifier。
- 不直接搬運 view、cache、summary、current alert、derived occupancy、mutable status projection、
  receipt 或 outbox；無法唯一映射的資料進 `legacy_unresolved` 人工清單，不猜值。
- legacy 與 validation case number、external event identity、document digest、idempotency key 不得碰撞。
- migration runner 必須使用 table classification allowlist；禁止對所有 base tables做通用
  `INSERT ... SELECT`，也禁止以關閉 FK 作為正常搬移策略。
- rebuild／清空任何 validation DB 前仍需逐次明確確認；本規格不授權 DB mutation。

## 11. Legacy exit

- 可變本機模板管理不得作為核准模板、文件 archive 或簽署證據來源；所有正式 caller 轉至
  TemplateCatalog、ContractRenderer 與 ImmutableDocumentArchive 後，舊入口只讀或退役。
- 任何直接寫 `orders.contract_identity`、契約狀態、precontract commitment、assignment／schedule
  或 Client Finance obligation 的 API、script、fixture 與 repository caller 必須清零。
- generic preserve migration 不得 universal copy base tables；完成 allowlist roots、projector rebuild、
  collision verification 與 focused regression 後才可關閉舊路徑。
- retirement 需依 Entry Point Governance 更新 caller inventory、replacement、focused regression 與
  receipt；找不到 static caller 不能直接刪除。

## 12. 分層驗收與完成條件

Module：模板／digest、日期守恆、sequence、fingerprint、remaining-obligation 與 exact conversion。

Subsystem：send／return、同 key replay/conflict、stale、archive/DB rollback、delivery retry、最後一段
commitment、客戶簽回＋Contract Completion 單一交易、conversion mismatch 零寫入。

Domain：

1. 月嫂先簽後只有 commitment，無 contract identity、execution、薪資或補助。
2. 訂金先核銷時 Orders 為「訂單成立」、契約等待客戶、execution 為零。
3. 客戶後簽只補剩餘期款，deposit 不重建，contract receipt 唯一。
4. 訂金＋客戶契約完成後，只有 exact commitment 可轉 execution。

Global：每個 UI scenario 具 versioned fixture/expected、command lineage、DB verifier JSON、
disposable-MySQL pytest、typed API contract、UI 截圖或人工驗收、Repair/Re-observe/Replay receipt；
preserved migration 另具 source/target digest、projection rebuild 與 legacy immutability 證據。

完成不得只以 schema、route、測試檔或最終資料存在判定。production DB、外部 LINE、部署與
cutover 必須另有明確授權及 release receipt。
