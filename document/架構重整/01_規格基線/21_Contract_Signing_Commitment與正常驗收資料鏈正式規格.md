# Contract Signing、簽約前服務承諾與正常驗收資料鏈正式規格

## 1. 文件狀態

- 狀態：`approved`
- 人工裁決日期：2026-08-10
- 正式收斂日期：2026-08-11
- Owner：Contract Signing Integration
- 跨域協作者：Orders、Assignments／Scheduling、Client Finance、LINE Integration
- 歷史來源與已完成執行包已自工作樹移除；需要時依 `../04_已完成與上線封存/README.md` 從 Git 歷史精準取回。
- 2026-08-21 M3 coordination amendment：customer `accepted` 只代表 matching decision；須經 fresh-effects
  check 與 Assignment typed conversion/rematch request，不能直接形成 contract、assignment 或 Payroll obligation。

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

2026-08-24 人工裁決：外部寄送不是唯一途徑。LINE 未綁定、未送達、未回呼，或已使用電話、
紙本、現場等非 LINE 流程完成簽約時，已授權內部操作者可經由 `manual_attested` 路徑，以
已簽回的不可變 evidence 形成 `staff_signed_received`。此路徑不是 `staff_contract_sent`、不是
LINE delivery success，也不是 target-status 修改；必須一併保存目前核准模板／版本、實際簽回
evidence、confirmation method、非空 reason、actor、事件時間、matching plan／segment snapshot
與 idempotency identity。當 waiting-deposit lock 尚未建立時，現行 `proposed` plan 必須另有最新
customer acceptance root；已取得 lock 的 `accepted` plan 可直接驗證。沒有可驗證的簽回 evidence
或 customer acceptance 時，人工入口固定拒絕。

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
- 自動寄送路徑的簽回只接受與目前有效 sent document、commitment 與案件相符的不可變版本；
  `manual_attested` 路徑則以同交易新建的目前核准模板版本與實際簽回 evidence 對應，兩者都不得
  接受任意未受控文件或偽造 sent event。
- 同一裁決下，客戶可在有效 commitment 已建立後，以 `manual_attested` 路徑提供實際簽回
  evidence，直接形成 `client_signed_received` 與 Contract Completion；必須保存核准模板／版本、
  evidence、confirmation method、reason、actor、commitment snapshot、Preview fingerprint 與
  receipt。此路徑不建立或宣稱 LINE delivery，也不得以口頭勾選取代必要 evidence。
- `official_service_dates_incomplete` 保留為 stable blocker 名稱；在 conversion 前，其完整性由
  有效 commitment 的精確服務日判斷，不要求先建立 execution schedule。
- 服務中仍須 actual start、有效 execution schedule、訂金與契約完成；不得只看 Orders label。

### 4.3 服務中代班的文件例外（2026-08-27 人工裁決）

服務中已有至少一筆 assignment-owned actual service fact 時，代班屬 Scheduling 的受影響日期
substitution，不開啟新的整案 Contract Signing round：

- 正常代班不要求代班月嫂獨立服務契約或簽回；客戶不需要追加確認或簽署變更文件。既有有效
  commitment、客戶契約與不受影響日期的文件／簽回仍是 current facts，不能因代班而被
  supersede 或重建。
- 代班月嫂 identity、受影響服務日、原／新 assignment 與 Payroll impact 由 Scheduling／Payroll
  的 substitution lineage 擁有。Contract Signing 不得把「代班無新簽回」投影成 contract blocker，
  也不得要求 client completion report 才能讓 substitution、排班 lineage 或薪資成立。
- 工會人員可選擇追加人工 `substitution_supplement` 文件／證據。它是 optional、可稽核的補充
  evidence，不是獨立契約、簽回或客戶接受事件；無附件、未上傳或 archive 暫時不可用均不阻擋
  代班與薪資。若補充文件宣稱改變條款、日期或金額，仍須另經 Orders／Scheduling／Client
  Finance 的正式 owner command，附件本身不能改寫根事實。
- 文件選配入口仍須沿用既有 actor、reason、method、digest／版本、Preview／Apply（若為納管
  文件）與 immutable receipt；不可用口頭勾選或文件存在反推 signed／delivered／customer-
  accepted。代班本身也不得偽造任何 provider delivery 或簽署事件。

## 5. Commands、Queries 與 typed views

Commands：

- `GenerateContractDocumentVersion`
- `SendStaffContract`
- `UploadReturnedContractDocument`
- `RecordStaffSignedContract`
- `PreviewManualStaffContractAttestation`／`RecordManualStaffContractAttestation`
- `SendClientContract`
- `RecordClientSignedContractAndCompleteContract`
- `PreviewManualClientContractAttestation`／`RecordManualClientContractAttestation`
- `CancelOrSupersedeCommitment`
- `ConvertCommitmentToExecution`

每個 mutation 必須包含 actor、reason、correlation id、`expected_status_version`、idempotency key
與 canonical command fingerprint。自動寄送路徑的簽回命令另必須帶目前 sent document 的
`expected_document_version_id`；人工補登則必須帶 Preview fingerprint、confirmation method 與
實際簽回 evidence；任一快照不同一律回 stale typed error。文件 bytes 只由 upload/archive port
接受，不能穿透 Domain。

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
- `manual_contract_evidence_missing | manual_contract_confirmation_method_invalid | manual_contract_reason_missing | manual_contract_preview_stale | manual_contract_customer_acceptance_required`
- `commitment_service_days_invalid | commitment_not_effective`
- `official_service_dates_incomplete | service_time_terms_incomplete`
- `contract_signature_idempotency_conflict`
- `commitment_execution_mismatch | assignment_occupancy_conflict`
- `contract_signing_unavailable | transaction_failed`

Alerts 涵蓋長時間未寄送／未簽回、delivery exhausted、archive/digest failure、stale plan、承諾
日期不守恆、identity conflict、conversion mismatch 與 orphan archive。Alert resolve 不得改變根因。

人工 UI 必須提供模板與版本、產生／預覽、寄送、上傳簽回、紀錄簽署、delivery 狀態、blocker、
receipt 與 repair navigation；每個 staff segment 與有效 commitment 後的 client contract，另必須
提供人工簽約證據 Preview → 明確確認 → Apply → receipt/readback。該入口必填 confirmation
method、非空 reason 與實際簽回檔，清楚標示「未建立 LINE 寄送任務」；不提供 status 直接
修改或 SQL/data-browser patch。

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
- 依 2026-08-26 最新人工裁決，本機 DB 驗收皆屬測試版本；名稱通過 `lu_test_*` allowlist 且
  environment／host／database／credential class 已精確回讀後，可直接建立或重建 disposable DB、寫入
  去識別代表性測試資料、執行 Query／Preview／Apply、receipt readback 與只清理本次 scenario owned rows，
  不需逐次請示。這項授權不涵蓋 `union_db`、production、全庫 cleanup、source replacement、`--switch`、
  未核准 schema／migration 或其他不可逆外部效果。

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

5. 服務中代班不建立新的必需契約／簽回或客戶變更簽署；無 optional substitution supplement
   仍可完成 Scheduling substitution、排班 lineage 與 Payroll，補充文件若存在則只作 evidence。

Global：每個 UI scenario 具 versioned fixture/expected、command lineage、DB verifier JSON、
disposable-MySQL pytest、typed API contract、UI 截圖或人工驗收、Repair/Re-observe/Replay receipt；
preserved migration 另具 source/target digest、projection rebuild 與 legacy immutability 證據。

完成不得只以 schema、route、測試檔或最終資料存在判定。production DB、外部 LINE、部署與
cutover 必須另有明確授權及 release receipt。

2026-08-25 runtime 狀態：內部人工補登簽回已在 fresh lifecycle 案由 Chrome 完成雙方
Preview／確認／Apply／receipt/readback，列為 `completed`；外部 LINE 寄送與 provider delivery
仍是獨立未驗收 lane，不得把它反推成人工簽約功能未完成，也不得宣稱 provider 成功。

## 2026-08-25 外部簽約平台 PDF 交接裁決

本節是較新的人工裁決；與前文「系統直接寄送契約」或「受控 HTTPS 文件下載網址」衝突時，
以本節為準。電子簽章仍由工會既有外部平台執行，本系統不整合或模擬該 provider。

正式流程固定為：

```text
系統產生未簽 PDF → 工會人員經已認證後台直接下載 PDF bytes
→ 工會人員將 PDF 移到外部簽約平台
→ 系統以 LINE 提醒月嫂前往外部平台簽約
→ 月嫂用 LINE 回報完成
→ 系統以 LINE 提醒客戶簽約
→ 客戶用 LINE 回報完成
→ 系統提醒工會人員到外部平台下載最終簽署 PDF
→ 工會人員把最終 PDF 放回指定 NAS 投放區或由管理端受控上傳 → Preview／確認／Apply
→ Contract Signing owner 將 NAS object reference、MIME、size、SHA-256、版本、actor、時間與 audit 保存到 DB
```

1. 管理端下載使用 authenticated、case-scoped 的 backend file response 與
   `Content-Disposition: attachment`；不得建立持久、可轉傳或帶身分的 HTTPS 文件網址，也不得把
   presigned URL／archive locator 回傳給一般 UI。下載須記 security audit，但不是簽署完成事實。
2. 外部平台狀態不是本系統根事實。月嫂與客戶的 LINE 回覆必須經 verified binding、目前 document／
   segment／commitment version 與防重放驗證，分別形成 provider-neutral completion report；LINE delivery
   success 不能代替人的回覆。LINE 不可用時保留同等證據要求的人工補登入口。
3. 只有全部月嫂已回報完成，才可建立客戶提醒 intent；客戶回報完成後只建立「最終 PDF 待回收」任務，
   不得在最終檔案上傳、digest 驗證與 DB 保存前形成 Contract Completion。
4. 最終 PDF 納管採 NAS 指定投放區或管理端 staging → zero-write Preview → 明確確認 → Apply →
   receipt/readback。Apply 必須在單一 outer UoW 鎖定 current case、document version、雙方 completion reports
   與 status version，經 typed `ContractDocumentRepository` 保存 immutable NAS object reference 與 metadata；
   route、UI、LINE callback 不得直接 SQL 或自行組合檔案路徑。
5. 依較新的 `00` §2.2 人工裁決，PDF bytes 的正式來源是工會地端受控 NAS，DB 不保存大型 binary；
   DB 只保存 opaque object reference、digest、MIME、size、版本與稽核 metadata。一般 JSON、LINE payload、
   query string、log、receipt 不得暴露 drive letter、UNC path、NAS mount path、base64、raw PDF、SQL statement
   或 storage locator。既有 `storage_key` 只有在被驗證為受控 logical object reference、具 digest／版本契約
   且無 public path leakage 時才能由 adapter 採用；不能只因欄位存在就宣稱完成。若現有 schema 仍不足，
   另立 schema release 並通過 DB change gates；本文件同步本身不授權 DDL、migration 或既有 DB mutation。
6. 必要 commands／queries 至少包含 `DownloadUnsignedContractPdf`、`RecordExternalStaffSigningReport`、
   `RecordExternalClientSigningReport`、`PreviewFinalSignedContractUpload`、`ApplyFinalSignedContractUpload`、
   `QueryContractDocumentReadback`。每條 mutation 都須有 expected version、idempotency、stale／replay、
   timeout outcome reconciliation、人工 recovery 與 receipt。
7. Browser 驗收必須實點下載與上傳，確認 PDF MIME／檔名／digest、LINE 回覆順序、錯序／重播拒絕、
   final readback 與一般 UI 不出現 document URL、fingerprint、raw cursor 或 storage locator。真實 provider
   push 仍需另行授權；未測時標 `blocked`／`not_run`，不得假造。

因此前述 `SendStaffContract`／`SendClientContract` 僅保留 legacy compatibility identity，不再是新 UI 的
正式主路徑；`archive locator` 只可留在 repository 內部相容層，current public contract 必須退出。

Runtime gap 狀態（2026-08-26）：`approved`。人工已授權本機實作、必要的 `lu_test_*` schema gate、
controlled-file adapter 與 LINE sandbox 驗收；current renderer 仍僅產生 XLSX，現有 `media_assets` 與
`contract_document_versions.storage_key` 尚未驗證為 `00` §2.2 的受控 NAS logical object reference／digest／
version adapter，事件模型也只有 legacy `sent`／`signed_received`，尚無外部平台雙方 completion report。
必須先完成 PDF renderer、NAS discovery／read adapter、metadata 對帳與 completion-report contract；若盤點確認
現有 schema 足夠，可不新增 binary 欄位，若不足仍須另立 DB Work Package。不得以 raw NAS path、受控 HTTPS URL
或直接 signed-return 假裝完成。DDL／migration 只限正式 release chain 與 allowlisted `lu_test_*` 驗證；
production／`union_db`、external deployment 與 entry switch 仍需精確 target gate。既有人工補登完成狀態不受影響。

## 2026-08-21 M3 acceptance-effect amendment

M3 Matching Coordination 可保存 customer acceptance decision 與其 criteria／candidate lineage，但 `accepted` 不等於 Contract Completion、contract identity、formal assignment、official service day 或 Payroll obligation。M3 只能在 fresh downstream facts 後產生 typed `AssignmentConversionRequested`／rematch reference；Orders、Assignment／Scheduling 與 Payroll 各自保留 root writer、Preview／Apply、lock 與 receipt。

任何 conversion mismatch、stale service date、leave／availability conflict 或缺少 Assignment conversion receipt 均 fail closed、零 partial write；本 amendment 不授權 production code、schema／DB、LINE provider、deployment 或 cutover。

## 2026-08-31 Full Contract Preview owner projection與public entry裁決

兩份XLSX維持static legal/content/layout baseline。Client target固定exact case＋client scope；Staff target固定
exact case＋exact assignment/segment＋staff scope。Contract Signing／renderer只組合closed typed owner
projections，不擁有動態business facts，也不得新增金額、日期或INFO12公式。

Client Finance、Payroll、Staff Payables各自提供契約需要的current typed money／business-date／payment-destination
projection；Payroll計算obligation，Staff Payables不得重算，renderer也不得跨owner加總成新公式。Client預定
服務日期由Scheduling Commitment projection提供exact commitment identity/version、start/end及owner計算的
service-day count；Staff使用exact assignment/segment Scheduling projection。INFO12欄位只能由其current owner的
typed projection提供，不得讀raw survey、legacy column、UI state或XLSX formula。

每個mapping row requiredness固定為`required | conditional | optional`。required缺值、stale或source unavailable
fail closed；conditional只在owner-defined condition成立時required；optional僅接受owner明確合法absence。
unavailable、unresolved或ambiguous不得當optional null。

核准authenticated internal bounded public API：client preview target為exact case；staff preview target為exact
case＋assignment/segment。Preview零寫入，fresh-read owner snapshots並回target、template version、owner
fingerprint、blockers、preview fingerprint與PDF result。正式document persistence仍走既有Apply/Generate；Download
只讀opaque document version／controlled-file object並重新authorization，不暴露filesystem/NAS locator、raw URL，
也不重新計算business facts。preview與正式download bytes/digest依既有version contract保持一致可追溯。
本裁決解除public-entry及owner-projection blocker，但依Task 96 priority尚未開始此後順位implementation。

### 2026-09-01 客戶契約付款欄位人工裁決

- 客戶契約 D36「服務款項匯款帳號」固定使用 Client Finance 的工會／代收付帳戶 current
  configuration；禁止綁定月嫂或其他 Staff Payables 帳戶。沒有 current configuration 時不得列印。
- 樓層費與訂金一起支付，因此 C37「樓層費入帳日」使用同一筆 Client Finance
  `deposit_due_date`，不得另取實際收款日或建立第二套日期算法。
