# Anomalies Domain

## 1. 文件邊界與所有權

- 狀態：`current-spec`
- Owner：Anomalies Domain
- 單一負責範圍：current business issue 的身分鍵、projection、recheck 邊界與 `LINE-006` 唯一 runtime anomaly predicate；不擁有各業務 Domain 的資料修復、排班或帳務規則。
- 關聯引用：見 [Global 共同契約](00_Global_共同契約.md)、[External Integration / Access Control](17_External_Integration_LINE_Access正式規格.md)、[LINE Gateway 與通知投遞](17A_LINE_Gateway_Inbox與通知投遞正式規格.md)

## 2. 核心定位與不變量

Anomalies 只表達「目前確實可能發生、而且狀態成立後需要工會人員介入」的業務異常。它不是程式 correctness dashboard、資料庫 invariant monitor、migration repair queue、一般 owner 待辦或自動 retry 狀態頁。

1. 純系統公式、deterministic projection、aggregate、季別加總、金額 reducer、transaction invariant 或資料結構一致性若出錯，視為 implementation／test／migration correctness failure，不建立日常 runtime recovery product。
2. 正式 owner Apply 已以 fresh validation、single outer UoW、constraint 或 deterministic reducer 保證不可產生的狀態，不得再為程式寫錯建立第二套人工 anomaly repair。
3. 正常等待、來源先後到達、automatic retry、replay in progress、readback temporarily unavailable、maintenance scan incomplete 都不是業務異常；它們分別留在 owner work queue、durable job 或 operational health。
4. 只有外部真實世界效果、外部資料或 identity 狀態可能合法越過系統預防邊界，而且發生後不能由 deterministic 自動流程安全完成時，才建立 current anomaly。
5. current issue predicate false 時直接刪除 current row；不保存 anomaly-owned occurrence、claim、resolve、tracking、reopen 或 reclassification history。
6. Anomalies 不修改 owner root。人工處理仍由 owning Domain 的 typed Query／Preview／Apply／receipt／fresh readback 完成。
7. `customer + staff` 同一 LINE User ID 是合法雙角色，不是異常；同一 customer 因每年新案件不建立新的 LINE customer identity，LINE customer binding 綁 Client root，不綁 case number。

## 3. Current 產品分類

### 3.1 Runtime current issues：只保留 1 碼

| Code | 為何實際可發生 | 需要人工的原因 |
|---|---|---|
| `LINE-006` | LINE recipient／binding／configuration 或 provider delivery 是外部邊界；自動 delivery 可能在 bounded retry 後仍 terminal failed | 只有 automatic path 已無法繼續且需要人修正 recipient／binding／configuration、執行人工 replay 或人工略過時才成立 |

### 3.2 非 Anomalies 之既有 owner work item

- `BECLASS-001`：HCM 先到、Client BeClass 尚未到是兩條合法 intake lane 的正常先後順序，不是異常。若業務流程到了需要 BeClass 資料但仍缺少，顯示在 Case Import／Client owner follow-up queue，由工會聯絡客戶或引導完成正常資料流程；不得建立 anomaly recovery lineage。

### 3.3 退役代碼歸屬對照（不進 runtime current issues）

| Code | 正式承接方式 |
|---|---|
| `PAYOUT-002` | Payroll／Scheduling correctness tests；正常服務日更正走既有 owner command |
| `GOVSUB-001` | 正常 reconciliation 或 Finance owner review；不建立 anomaly |
| `GOVSUB-002` | owner Preview／manual allocation 若需人工判斷留於 owner queue；不建立 anomaly |
| `GOVSUB-003` | deterministic validation、tests、migration readback |
| `GOVSUB-004` | Government Subsidy normal owner operation；不建立第二套 recovery |
| `GOVSUB-005` | owner revision／validation tests |
| `IMPORT-003` | HCM 正常 intake；客戶資料修改走 Client owner profile change |
| `IMPORT-006` | Finance Import tests／validation／operational failure；不做 runtime recovery workbench |
| `SCHEDULE-002` | Scheduling transaction／migration tests；非法 partial lineage 不作日常產品情境 |
| `SCHEDULE-003` | Scheduling validation；若 migration 發現則走 migration correction |
| `SCHEDULE-006` | module／subsystem／migration correctness oracle |
| `LINE-004` | LINE Identity normal replacement／role-selection contract；不建立 anomaly lifecycle |

## 4. Current issue identity 與 projection

### 4.1 Subject identity

| Code | Subject identity |
|---|---|
| `LINE-006` | `case_no + notification_reason` |

`issue_key` 固定為 `ci_` 加上對 `{"v":1,"definition_code":...,"subject_identity":...}` 的 UTF-8、sorted-key、compact JSON 使用 `issue_identity_key_v1` HMAC-SHA-256 lowercase hex。不得 fallback 成可枚舉低熵 identity 的無密鑰 hash。API 不回傳 raw HMAC input 或 secret。

### 4.2 Current projection

`CurrentIssueProjection` 至少包含：

- `issue_key`、`definition_code`、`owner_domain`、closed `subject_identity`；
- `owner_snapshot_token`／owner version；
- `severity`、`blocking`；
- closed typed details；
- `episode_started_at`、`last_verified_at`；
- closed owner action descriptor。

predicate false 後直接刪除 row；同一 canonical subject 日後再次成立時可使用同一 stable `issue_key` 建立新 current episode。不存在 claimed／resolved／reopen history。

## 5. Government Subsidy owner validation

Government Subsidy 的正常 claim、receipt、allocation、reversal、review 與必要 owner correction 由其自身 owner 承接；非法 reducer／projection 狀態由 deterministic validation、focused tests 與 migration readback 保護，不建立第二套 Anomalies recovery。

## 6. `LINE-006` current contract

### 6.1 只有需要人工時才建立 issue

`LINE-006` 不把 automatic retry／replay lifecycle 本身當異常。以下狀態單獨存在時不得建立新的 current issue：

- delivery `pending`／`processing`；
- retryable failure 尚在 bounded retry；
- manual replay 已建立且仍在正常處理；
- owner readback temporarily unavailable／incomplete；
- maintenance scan incomplete；
- source 已不再 applicable。

Operational／readback failure 由 durable-job／runtime health 處理；若 DB 內已存在一筆真正 business `LINE-006`，readback 不完整時可以 fail closed 保留原 row，但不得因 readback incomplete 本身合成新的業務 issue。

### 6.2 Active predicate 與人工略過

對目前仍 applicable、確實需要通知的 source，只有在未保存同一 exact owner snapshot 的人工略過 audit，且下列至少一項成立時才為 current issue：

1. exact recipient／current binding／required configuration 缺失或無效，automatic delivery 無法合法繼續，需要人修正；
2. automatic delivery 的 bounded retry 已耗盡並得到 terminal failed，需要人工 replay／處置；
3. provider outcome 經既有 bounded reconciliation 後仍無法確定，且已進入正式人工處理邊界。

所有目前警示均可逐筆確認略過（包含 `LINE-006`），詳細人工略過契約由 [LINE Gateway 與通知投遞](17A_LINE_Gateway_Inbox與通知投遞正式規格.md) 擁有。同一 exact owner snapshot 已保存人工略過 audit 時不再需要人工提醒（不宣稱 delivery 成功，不改通知來源或任務結果；來源／結果變更後可重新成立）。

人工修正設定或 binding 後不得直接刪 issue；owner 必須 fresh 驗證 source 仍 applicable、recipient／binding／configuration 都合法且已取得 terminal success，或已保存該 exact owner snapshot 的人工略過 audit，或 authoritative owner facts 證明該通知已不再需要。

## 7. LINE Identity 非異常規則

1. `customer + staff` 雙角色合法；需要時使用既有 role selection，不投影 `LINE-004`。
2. customer binding 的 `subject_reference` 是 Client root identity，不是 `case_no`。同一 Client 每年新增案件不改 LINE identity binding。
3. 若匯入或既有資料將同一人形成兩個 customer roots，LINE Identity 使用 same-type replacement：確認目前有效的 Client root 後，以正式 replacement command 讓新 root 取代舊 root，並清除舊 owner projection；不刪案件／Client history。
4. staff role 若同時存在，customer replacement 不影響 staff binding。
5. replacement ambiguity 若無法由 owner identity evidence 唯一決定，停在 LINE Identity owner review；不進 Anomalies lifecycle。

## 8. Bounded recheck 與 transaction

1. owner mutation 與 bounded `anomaly.recheck` intent 必須在同一 owner outer UoW commit。
2. worker 只在 commit 後 fresh 讀 owner facts。
3. 對 authoritative complete scope 計算 present set；只有完整 readback 才能 delete absent current row。
4. stale token、timeout、owner unavailable、duplicate candidate、schema drift 時零 delete。
5. repository 不得 hidden commit；route／worker／detector 不得直接寫 owner root。
6. maintenance recheck 只為唯一 `LINE-006` current issue 及其 current projection 服務；不得重新掃描已退役 13 碼並建立 runtime issue。

## 9. API 與管理端入口邊界

- `GET /api/v1/anomalies` 只回 `LINE-006` current rows。
- `GET /api/v1/anomalies/{issue_key}` 只回 current details、owner evidence、blocking effect 與合法 owner action descriptor。
- 管理端不設獨立「異常審核」頁、側欄入口或專用鈴鐺入口；未知 hash 沿用 App 預設待辦看板。既有後端 API、current projection、owner Q/P/A、audit／receipt 與資料保留。
- 13 個 correctness／invariant codes 與 `BECLASS-001` 均不進 current projection。
- owner work item、normal review、retry／job 狀態留在 owning page。
- 不提供 generic resolve、claim、tracking close、raw mutation payload 或直接 SQL action。

## 10. 驗收標準

- runtime current issue exact set = `{LINE-006}`；
- Government Subsidy 的正常 claim／receipt／allocation／reversal validation 保留；
- `BECLASS-001` 只存在 Case Import／Client owner follow-up，不出現在 current anomaly projection；
- 退役 13 碼不再有 runtime producer／public current definition／React current mapping；
- `LINE-006` pending／processing／retryable／readback-incomplete 本身不產生 issue，只有需要人工介入才產生；
- 同一 exact owner snapshot 記錄人工略過 audit 後，fresh owner readback 證明 predicate false 並刪除 current row；來源／結果變更後可重新成立；
- legal `customer + staff` dual-role 與同一 Client 多案件不產生 `LINE-004`；same-type replacement 走 LINE Identity normal operation；
- predicate false 且 authoritative complete 時 current row 實際刪除。
