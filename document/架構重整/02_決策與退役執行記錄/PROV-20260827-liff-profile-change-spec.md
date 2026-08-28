# LIFF 資料異動申請與管理核准：規格收斂紀錄

- `doc_type`: `specification`
- `declared_status`: `proposed`
- Current item: `CUR-LIFF-PROFILE-01`
- Current terminal: `AUTHORITY_REQUIRED`
- Controlling authority: `20_LINE客服與月嫂自助服務正式規格.md` §6.1

## 已確認的 observable contract

1. 只有 server 驗證的 LIFF ID token 與 current binding 可以決定 applicant、subject 與 target；query-string
   `userId` 不具授權效果。
2. 申請固定走 applicant `Preview → Confirm → Apply pending request → scoped receipt/readback`；建立 request
   不代表 owner root 已修改。
3. 核准固定走 owner-specific `Preview → Confirm → Apply`。Apply 必須在單一 outer UoW fresh-lock request、
   binding、subject 與 owner version，再由 owning repository 更新 root、append event／receipt／outbox。
4. 核准後管理端與 applicant LIFF 必須重新 Query owner projection，顯示相同業務值與
   `approved_applied`；readback 不可用時只能 reconcile，不能盲目重送。
5. stale、終結 request、same-key different payload、未綁定、subject mismatch、欄位未允許、validation 或
   transaction failure 全部 fail closed；same-key same-payload replay 回原 receipt。
6. LINE Integration 只擁有 intake 與 binding evidence；不得直接寫 Client／Staff root，也不得借用 LINE
   身分審核、歷史 Staff adoption、Scheduling matching preference 或 raw table route 當 profile writer。

## 必須由 owner 規則書裁決的事項

### 2026-08-27 人工裁決（本段優先）

1. 首個交付切片固定為 `Client`；Staff 於後續獨立 package 交付，不與 Client schema／驗收綁成同批。
2. Client 與 Staff 都可對「屬於本人且由對應 owner 擁有」的一般個人資料提出修改申請；exact field
   allowlist 不由 live schema 推定，須先依正式規則書整理候選清單，再逐欄取得人工裁決。
3. Staff 的媒合偏好與不可排班日期也可提出修改申請，並非永久排除於自助服務；所有申請都只建立
   pending request，人工確認後才由 Staff／Scheduling owner 寫入正式根事實。
4. 不可排班日期若與既有有效訂單 assignment／正式排程衝突，Preview 與管理端必須顯示 exact case、日期與
   assignment blocker／warning。人員若具權限並明確強制核准，既有訂單排程仍優先：不得因此取消、縮短或
   標記既有 assignment 為不上班；衝突日期保存為`committed_schedule_exception` lineage，不可排班事實只
   約束未來媒合／尚未承諾時段，既有服務異動仍須另走substitution／leave／cancellation正式流程。

### Client 欄位候選（待人工逐欄裁決）

| 等級 | 候選欄位 | 邊界／限制 |
|---|---|---|
| 建議第一批 | `name`、`gender`、`phone`、`city`、`address`、`residence_type`、`delivery_type`、`baby_info`、`notes` | 只更新Client profile root；地址、生產方式與寶寶資訊不得自動推進Orders／Scheduling或財務。`residence_type`與`delivery_type`現有enum存在live-drift，實作前必須先確認字彙。 |
| 條件式第二批 | `due_month`、`line_id` | `due_month`只可作profile資料；若影響服務日、排班或薪資，改走Orders command。`line_id`只是聯絡文字，不得等同或變更`line_user_id`綁定。 |

每個允許欄位共用verified LIFF identity、current/requested diff、owner version、reason、idempotency、
receipt/readback與最小揭露／遮罩證據。`phone`目前規則為`^09[0-9]{8}$`，不是唯一身分key；
`city`必須為central valid city；`name`必填且trim。其餘exact length／enum／masking必須在task pack前固定。

Client generic profile明確排除：`id`、`case_no`、所有created/updated技術時間、`ip_address`、
`seq_num`、`reject_reason`、`admin_notes`、`identity_status`、`service_time`、`service_start_date`、
`service_days`、`service_type`、`line_user_id`、Finance／Orders／Scheduling／Contract／Anomalies根事實與
BeClass退款帳戶／raw source欄位。

### Staff 欄位候選（待人工逐欄裁決）

| 類別 | 候選欄位 | 邊界／限制 |
|---|---|---|
| 一般個人資料 | `name`、`phone`、`tel`、`tel_ext`、`email`、`birthday`、`city`、`zip_code`、`address` | 申請後人工確認才由Staff owner寫入；exact validation、masking、profile root/version尚待技術package確認。 |
| 媒合偏好 | range `minimum`／`maximum`；set `values` | 沿用Scheduling typed preference definition／value與profile version；偏好只影響媒合排序與說明，不是硬性異常或排除。 |
| 不可排班 | `kind`、`start_date`、`end_date`、`reason` | `kind`=`long_leave | paused_service`。衝突日顯示exact case／assignment；人工強制核准後既有訂單排程優先，另存`committed_schedule_exception` lineage，新媒合仍受不可排班約束。 |

Staff generic profile明確排除：`identity_card`、`line_user_id`、lifecycle `status`、技術時間、
銀行／薪資／Payables資料，以及所有assignment／leave／substitution根事實。媒合偏好與不可排班
由Scheduling owner核准Apply，不因由Staff本人申請就轉移owner。

因此下表的 `STAFF-SCOPE` 與 `DELIVERY-SLICE` 已裁決；Client／Staff exact fields 及 owner root/version
仍須以規則書候選清單與技術 package 收斂，不能由本段直接生成任意 JSON patch。

| Decision ID | 必要裁決 | 為何不能由 live schema／UI 推定 |
|---|---|---|
| `LIFF-PROFILE-CLIENT-FIELDS` | Client 可人工與 LIFF 申請修改的 exact field allowlist、每欄 validation、遮罩與 evidence | `clients` 欄位存在不代表可由 profile mutation 改；部分欄位屬 Orders、Finance、LINE binding 或歷史 projection。 |
| `LIFF-PROFILE-CLIENT-ROOT` | Client profile canonical root identity、aggregate version 與 repository contract | 現行 `clients` 沒有正式 profile aggregate version；直接使用 row timestamp／任意欄位會破壞 stale contract。 |
| `LIFF-PROFILE-STAFF-SCOPE` | `RESOLVED`：一般個資、媒合偏好與不可排班日期都可申請；後兩者仍由 Scheduling owner套用，且既有有效訂單排程優先。exact fields待規則書清單逐欄裁決。 | 不把 Scheduling aggregate錯當Staff master；衝突時不得由profile request旁路取消既有assignment。 |
| `LIFF-PROFILE-STAFF-ROOT` | Staff profile owner、root identity、aggregate version、typed commands 與 transaction boundary | 歷史 adoption writer 是 restricted historical source，不能升格為 current profile owner。 |
| `LIFF-PROFILE-DELIVERY-SLICE` | `RESOLVED`：第一階段只交付 Client；Staff 後續獨立 package。 | 避免兩個 owner 的 schema、測試資料與驗收拓撲互相阻擋。 |

在上述決策完成前，現有 `profile_update.html` 保持 fail-closed 待建狀態是正確行為；不得建立 generic
`corrected_fields`、直接 SQL、任意 JSON patch 或只更新 request/tracking status 的假流程。

## Acceptance IDs

- `LIFF-PROFILE-A1`: verified LIFF 使用者只能讀寫自己的 bounded request，且不能以 URL identity 越權。
- `LIFF-PROFILE-A2`: applicant Preview 零寫入，Apply 只建立 immutable pending request。
- `LIFF-PROFILE-A3`: 管理端顯示 owner current/requested diff、版本、遮罩 evidence 與 blocker。
- `LIFF-PROFILE-A4`: owner approval Apply 成功後，DB、管理端與 LIFF readback 一致。
- `LIFF-PROFILE-A5`: reject、stale、replay、permission、rollback、receipt committed/readback unavailable 均有
  typed outcome，且不會重複 mutation。
- `LIFF-PROFILE-A6`: 每個允許欄位均引用 owner 規則書與 validation；不存在「因資料表有欄位所以可改」。

## DB change gates

| Gate | 結果 | 證據／原因 |
|---|---|---|
| Scope gate | `BLOCKED` | 首個 delivery slice 已固定Client，但Client exact owner fields與root/version尚未裁決，無法形成 bounded write set。 |
| Change inventory | `BLOCKED` | request/decision persistence 與 Client／Staff aggregate version 的 target objects 仍取決於上述裁決。 |
| Static release gate | `NOT_RUN` | 尚無合法 release candidate。 |
| Descriptor gate | `NOT_RUN` | target object contract 尚未確定。 |
| Read-only plan gate | `NOT_RUN` | 尚無 release artifact 可列入 plan。 |
| Engine verification gate | `NOT_RUN` | 尚未進入 schema implementation。 |
| Developer acceptance gate | `NOT_RUN` | 前置 gates 未通過。 |

總結：`DB_CHANGE_NOT_READY`。本文件不授權任何 DDL、migration、seed、backfill、reset、replacement 或
`union_db` 操作。

## DDH 動態執行紀錄

本輪 discovery 以 E4 三條互斥唯讀 lane 分別盤點 Client、Staff、LINE／LIFF／管理端契約；子代理全部為
`gpt-5.6-luna`／`high`，零 workspace effect。DDH native reconciliation 為 `passed`，plan digest
`24660b4f210425b22cb4be87abf616a4763aeca093e4ca574a6dfdd612037281`，terminal receipt digest
`d61ab15cce90d3857c1a3428063a20c831b6f2443d119f23b2a2406d8744144d`。發現 owner authority 缺口後，運作模式
由 E4 discovery 收斂為主代理單一規格 integration writer；沒有派發 implementation writer。

## Convergence

```yaml
convergence:
  status: NOT_READY
  blockers:
    - LIFF-PROFILE-CLIENT-FIELDS
    - LIFF-PROFILE-CLIENT-ROOT
    - LIFF-PROFILE-STAFF-ROOT
    - LIFF-PROFILE-CLIENT-FIELD-CANDIDATE-REVIEW
    - LIFF-PROFILE-STAFF-FIELD-CANDIDATE-REVIEW
```

結果：`AUTHORITY_REQUIRED`。在 owner 規則書完成上述裁決後，才可編譯 task pack 與執行 DB gates。
