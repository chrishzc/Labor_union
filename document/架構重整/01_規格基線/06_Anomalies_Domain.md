# Anomalies Domain

狀態：`current_projection_and_additive_successor_approved`；`runtime_cutover_pending_db_and_runtime_evidence`

最新人工裁決：2026-08-31 business-reachability pruning。

## 1. Domain 定位與最新裁決

Anomalies 只表達「目前確實可能發生、而且狀態成立後需要工會人員介入」的業務異常。它不是程式 correctness dashboard、資料庫 invariant monitor、migration repair queue、一般 owner 待辦或自動 retry 狀態頁。

2026-08-31 人工裁決固定：

1. 純系統公式、deterministic projection、aggregate、季別加總、金額 reducer、transaction invariant 或資料結構一致性若出錯，視為 implementation／test／migration correctness failure，不建立日常 runtime recovery product。
2. 正式 owner Apply 已以 fresh validation、single outer UoW、constraint 或 deterministic reducer 保證不可產生的狀態，不得再為「如果程式自己寫壞」建立第二套人工 anomaly repair。
3. 正常等待、來源先後到達、automatic retry、replay in progress、readback temporarily unavailable、maintenance scan incomplete 都不是業務異常；它們分別留在 owner work queue、durable job 或 operational health。
4. 只有外部真實世界效果、外部資料或 identity 狀態可能合法越過系統預防邊界，而且發生後不能由 deterministic 自動流程安全完成時，才進 `#anomalies`。
5. current issue predicate false 時直接刪除 current row；不保存 anomaly-owned occurrence、claim、resolve、tracking、reopen 或 reclassification history。
6. Anomalies 不修改 owner root。人工處理仍由 owning Domain 的 typed Query／Preview／Apply／receipt／fresh readback 完成。
7. customer＋staff 同一 LINE User ID 是合法雙角色，不是異常；同一 customer 因每年新案件不建立新的 LINE customer identity，LINE customer binding 綁 Client root，不綁 case number。
8. 本裁決 supersede 本檔、`15_正式規格索引與裁決總表.md` §16、Task 96、current-state anomaly execution plans，以及各 owner spec 中仍把下列 retired codes 當 runtime current issue 的較早文字。較早條文只保留 provenance／test evidence，不再形成 current product requirement。

## 2. Current 產品分類

### 2.1 Runtime current issues：只保留 2 碼

| Code | 為何實際可發生 | 需要人工的原因 |
|---|---|---|
| `GOVSUB-007` | 系統外實際政府退款可能由會計匯出超過既有 government refund payable remaining；這是外部真實付款結果，不是 reducer 算錯 | 已發生的超額出款不能靠重算消失，需要 Government Subsidy owner 明確處置 |
| `LINE-006` | LINE recipient／binding／configuration 或 provider delivery 是外部邊界；自動 delivery 可能在 bounded retry 後仍 terminal failed | 只有 automatic path 已無法繼續且需要人修正 recipient／binding／configuration 或執行人工 replay 時才成立 |

### 2.2 移出 Anomalies、保留為 owner work item

- `BECLASS-001`：HCM 先到、Client BeClass 尚未到是兩條合法 intake lane 的正常先後順序，不是異常。若業務流程到了需要 BeClass 資料但仍缺少，顯示在 Case Import／Client owner follow-up queue，由工會聯絡客戶或引導完成正常資料流程；不得建立 anomaly recovery lineage。

### 2.3 從 runtime anomaly 退役的 12 碼

| Code | 退役理由 | 正式承接方式 |
|---|---|---|
| `PAYOUT-002` | 「付款到期很久後才形成薪資義務」不是目前實際業務流程；薪資以正式服務天數為根 | Payroll／Scheduling correctness tests；正常服務日更正走既有 owner command |
| `GOVSUB-001` | 季別／批次判定屬 deterministic owner／Finance Import reconciliation | 正常 reconciliation 或 Finance owner review；不建立 anomaly |
| `GOVSUB-002` | item allocation ambiguity 不作為獨立 anomaly product | owner Preview／manual allocation 若真的需要；不進 `#anomalies` |
| `GOVSUB-003` | receipt／allocation／projection 自己不一致只可能是 implementation／migration integrity failure | deterministic validation、tests、migration readback |
| `GOVSUB-004` | reversal target／amount validation 由正式 Preview／Apply 阻止非法結果 | Government Subsidy normal owner operation；不建立第二套 recovery |
| `GOVSUB-005` | frozen claim 與 service facts 的合法變更應走正常 revision；非法 drift 是 correctness failure | owner revision／validation tests |
| `IMPORT-003` | Client BeClass 與 HCM 可合法獨立先後到達；不存在 HCM「補件解除 anomaly」產品流程 | HCM 正常 intake；客戶資料修改走 Client owner profile change |
| `IMPORT-006` | bank import batch integrity、parser、aggregate、fingerprint correctness 應在上線前與每次 Apply 由 deterministic contract 驗證 | Finance Import tests／validation／operational failure；不做 runtime recovery workbench |
| `SCHEDULE-002` | 正式 replacement／substitution transaction 應原子保存 successor、daily outcome 與跨域 impacts | Scheduling transaction／migration tests；非法 partial lineage 不作日常產品情境 |
| `SCHEDULE-003` | effective assignment overlap 應在 Preview／Apply occupancy validation 與 constraint 前被阻止 | Scheduling validation；若 legacy migration 發現則走 migration correction，不進日常 anomaly |
| `SCHEDULE-006` | coverage、hours、official dates、ownership 等都是 canonical Apply invariant | module／subsystem／migration correctness oracle |
| `LINE-004` | same-type duplicate 的 current business rule 已固定為合法 same-type replacement；customer＋staff 雙角色合法 | LINE Identity normal replacement／role-selection contract；不建立 anomaly lifecycle |

以上退役是「退出 runtime anomaly product」，不代表刪除 owner 正式 business events、receipts、validation 或 migration evidence。任何舊資料 cleanup、schema drop、entry retirement 仍受各自 DB／cutover Authority 約束。

## 3. Current issue identity 與 projection

### 3.1 Subject identity

| Code | Subject identity |
|---|---|
| `GOVSUB-007` | `payable_identity` |
| `LINE-006` | `case_no + notification_reason` |

`issue_key` 固定為 `ci_` 加上對 `{"v":1,"definition_code":...,"subject_identity":...}` 的 UTF-8、sorted-key、compact JSON 使用 `issue_identity_key_v1` HMAC-SHA-256 lowercase hex。不得 fallback 成可枚舉低熵 identity 的無密鑰 hash。API 不回傳 raw HMAC input 或 secret。

### 3.2 Current projection

`CurrentIssueProjection` 至少包含：

- `issue_key`、`definition_code`、`owner_domain`、closed `subject_identity`；
- `owner_snapshot_token`／owner version；
- `severity`、`blocking`；
- closed typed details；
- `episode_started_at`、`last_verified_at`；
- closed owner action descriptor。

predicate false 後直接刪除 row；同一 canonical subject 日後再次成立時可使用同一 stable `issue_key` 建立新 current episode。不存在 claimed／resolved／reopen history。

## 4. `GOVSUB-007` current contract

Active predicate：canonical outgoing government refund bank fact 已唯一對應既有 `government_overpayment_return` payable，且實際出款大於該 payable 當時可合法核銷的 remaining。

這個狀態來自實際外部付款，因此即使發生機率低仍是可達的業務異常。Anomalies 只呈現 source bank fact、payable identity、超額結果與 Government Subsidy owner action；不得部分核銷、建立虛構 claim receipt、直接改 payable amount 或自動 offset。

Completion：Government Subsidy owner 以另行核准的正式處置完成超額出款 disposition，fresh owner readback 明確證明原 `GOVSUB-007` predicate 不再成立。若正式 disposition command 尚未完成，issue 保持 current；不得用 tracking／receipt-only／projection rebuild 關閉。

## 5. `LINE-006` current contract

### 5.1 只有需要人工時才建立 issue

`LINE-006` 不再把 automatic retry／replay lifecycle 本身當異常。以下狀態單獨存在時不得建立新的 current issue：

- delivery `pending`／`processing`；
- retryable failure 尚在 bounded retry；
- manual replay 已建立且仍在正常處理；
- owner readback temporarily unavailable／incomplete；
- maintenance scan incomplete；
- source 已不再 applicable。

Operational／readback failure 需由 durable-job／runtime health 處理；若 DB 內已存在一筆真正 business `LINE-006`，readback 不完整時可以 fail closed 保留舊 row，但不得因「readback incomplete」本身合成新的業務 issue。

### 5.2 Active predicate

對目前仍 applicable、確實需要通知的 source，只有下列至少一項成立才為 current issue：

1. exact recipient／current binding／required configuration 缺失或無效，automatic delivery 無法合法繼續，需要人修正；
2. automatic delivery 的 bounded retry 已耗盡並得到 terminal failed，需要人工 replay／處置；
3. provider outcome 經既有 bounded reconciliation 後仍無法確定，且已進入正式人工處理邊界。

人工修正設定或 binding 後不得直接刪 issue；owner 必須 fresh 驗證 source仍 applicable、recipient／binding／configuration 都合法，並由正式 delivery／manual replay 取得 terminal success，或 authoritative owner facts 證明該通知已不再需要。

## 6. LINE Identity 非異常規則

1. `customer + staff` 雙角色合法；需要時使用既有 role selection，不投影 `LINE-004`。
2. customer binding 的 `subject_reference` 是 Client root identity，不是 `case_no`。同一 Client 每年新增案件不改 LINE identity binding。
3. 若 legacy／匯入資料真的把同一人形成兩個 customer roots，LINE Identity 依人工裁決使用 same-type replacement：確認 current／新 Client root 後，以正式 replacement command 讓新 root 取代舊 root，並清除舊 owner projection；不刪舊案件／Client history。
4. staff role 若同時存在，customer replacement 不影響 staff binding。
5. replacement ambiguity 若無法由 owner identity evidence 唯一決定，停在 LINE Identity owner review；它不是 Anomalies lifecycle。

## 7. Bounded recheck 與 transaction

保留既有 current-only successor原則：

1. owner mutation與 bounded `anomaly.recheck` intent 必須在同一 owner outer UoW commit。
2. worker只在 commit 後 fresh 讀 owner facts。
3. 對 authoritative complete scope 計算 present set；只有完整 readback 才能 delete absent current row。
4. stale token、timeout、owner unavailable、duplicate candidate、schema drift時零 delete。
5. repository不得 hidden commit；route／worker／detector不得直接寫 owner root。
6. maintenance recheck只為兩個 current issue及其 current projection服務；不得重新掃描已退役12碼並建立 runtime issue。

## 8. API／React

- `GET /api/v1/anomalies` 只回 `GOVSUB-007`、`LINE-006` current rows。
- `GET /api/v1/anomalies/{issue_key}` 只回 current details、owner evidence、blocking effect與合法 owner action descriptor。
- `#anomalies` 不再顯示 12 個 correctness／invariant codes，也不顯示 `BECLASS-001`。
- owner work item、normal review、retry／job狀態留在 owning page。
- 不提供 generic resolve、claim、tracking close、raw mutation payload或直接 SQL action。

## 9. Cutover 與退役邊界

本裁決授權的是正式產品語意與規格／計劃修正；不因文件修正自動授權 production source deletion、schema migration、configured DB Apply、entry switch、provider實送或 destructive cleanup。

Repository-local後續最小工作只需：

1. registry／typed union／React mapping收斂到2碼；
2. `LINE-006` predicate排除 automatic in-progress／retry/readback-only 狀態；
3. `GOVSUB-007`保留 current detector與 owner action boundary；
4. `BECLASS-001`改接 Case Import owner follow-up；
5. 12碼 producer／consumer／tests逐項判斷為 delete、owner-validation keep或 migration-only keep，不建立 replacement recovery framework；
6. fresh owner recheck只重建2碼 current rows。

舊 schema／source若已發布且必須作 migration provenance，可保留 artifact，但不得再形成 current runtime requirement。

## 10. Acceptance

完成本輪 anomaly pruning 必須證明：

- runtime current issue exact set = `{GOVSUB-007, LINE-006}`；
- `BECLASS-001`只存在 Case Import／Client owner follow-up，不出現在 `#anomalies`；
- 12 個退役碼不再有 runtime producer／public current definition／React current mapping；
- Scheduling、Payroll、Government aggregate／allocation、Finance Import integrity等 correctness仍由 focused tests、fresh validation、transaction rollback與migration readback保護；
- `LINE-006` pending／processing／retryable／readback-incomplete本身不產生 issue，只有需要人工介入才產生；
- legal customer＋staff dual-role與同一Client多案件不產生 `LINE-004`；same-type replacement走 LINE Identity normal operation；
- predicate false且authoritative complete時 current row實際刪除；
- strict UTF-8、focused tests、governance／reference scan與`git diff --check`通過後，才可宣稱repository-local anomaly product alignment完成。
