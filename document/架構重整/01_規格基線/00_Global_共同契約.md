# Global 共同契約

## 1. Global 的責任

Global 只定義跨 Domain 不得被破壞的不變量與共用技術契約，不擁有特定業務公式，也不形成可任意呼叫的巨大 Service。

共同契約包括：

- `ActorContext`
- `ExpectedVersion`
- `IdempotencyKey` 與 `IdempotencyReceipt`
- `PreviewFingerprint`（只在需要的人工作業 Preview 邊界）
- `TypedResult` 與 `TypedError`
- `UnitOfWork`
- `BusinessClock`
- `CorrelationId`
- transactional outbox／durable job

## 2. 跨 Domain 不變量

1. 正式業務規則只存在後端；UI 不計算日期、狀態、工時、金額或帳務結果。
2. Query 唯讀；Preview 零寫入；Apply 必須 fresh-read／lock current owner facts 後重算 candidate。
3. business mutation 以 owning aggregate／owner version 作主要 concurrency control；只有真正跨 request 的 `Preview → human Confirm → Apply` 才額外使用 Preview fingerprint。
4. 相同 idempotency key＋相同 canonical command 回原 receipt；相同 key＋不同 command 固定拒絕。
5. 正式收款、付款、退款、adjustment、reversal、服務更正與狀態事件採 append-only；既有正式 event 不原地改寫。
6. 所有新金額為整數新台幣；相容 `DECIMAL(...,2)` 不得讓新流程產生小數義務。
7. 客戶與月嫂是獨立帳務；銀行 row／allocation 必須依 owning Finance contract 守恆，不得用跨 owner 差額硬平。
8. `actual_hours = 有效 assignment-owned 正式服務日數 × orders.service_hours_per_day`；不得 fallback 到 `planned_hours` 或 `orders.staff_id`。
9. cancelled assignment 保留歷史，但不得參與 current 排班、日期、工時或薪資。
10. 服務資料鎖、取消限制與完整履約薪資依 Orders／Scheduling／Payroll current spec；Global 只要求 caller 不得旁路 owner predicate。
11. 所有服務日期、完成時刻與到期日政策以 `Asia/Taipei` 解讀；測試注入 clock。
12. Alert／Anomalies 不是 Domain mutation gate；它只投影 owner predicate。
13. 無法從 current root facts 唯一判定原因或修復方式時，停止自動更正，不得猜測 adjustment／reversal／target status。
14. `#anomalies` 只處理 current issue；一般 owner review／work item 留在 owning page。兩者都只能呼叫 owning typed command，不直接寫 Domain root。
15. 人工正式操作遵守 actor／authorization、必要 reason/evidence、fresh owner concurrency token、idempotency、receipt/readback；只有該 workflow 真正包含 human Preview 時才要求 Preview fingerprint。
16. UI 可顯示 draft／loading／pending，但只有 server receipt／owner readback 可表示正式 Apply 成功。
17. Cache、read model、HTTP conditional response、background notification 都不是 SSOT；cache unavailable 只影響速度，不改 current fact。
18. 長任務可回 `202 Accepted`＋durable job identity，但 worker 仍執行同一正式 command semantics；不得把一個原子 owner mutation拆成多個不受控 commit。
19. 自動化、provider callback、排程與 worker 只能追加實際觀察到的 immutable event、durable task 或 derived projection；不得偽造付款、簽章、delivery 或其他根事實。
20. 會影響 business lifecycle 的自動化若存在等價人工路徑，人工路徑只接受能證明相同 root transition 的 evidence；不得退化成任意 target-status editor。
21. 外部 provider effect 必須在核心 transaction commit 後執行；外部失敗不得回滾已提交 Domain root，也不得用 queued／HTTP 200 冒充 provider terminal success。

### 2.1 Durable Job canonical equality（2026-08-21 Option A）

本節是已核准的 Global 契約；production adoption 仍由實際 caller／release Authority 決定。

- business equality 固定為 `command_type + command_version + canonical_payload + submitted_by`；correlation ID 只供觀測。
- canonical payload 只接受 JSON object、string keys 與 finite JSON values；UTF-8 serialization 固定 sorted keys、compact separators、`ensure_ascii=False`、`allow_nan=False`。
- Typed schema 下 `1` 與 `1.0` 是不同 payload；若 persistence 無法保存此差異，對應 caller fail closed。
- canonical idempotency key 必須先符合 `^[a-z0-9][a-z0-9._:-]{0,190}$`；禁止 silent lowercase。
- `submitted_by` 必須是 immutable actor identity，不得用 display username。
- 只有 development/dev/local/test＋明確 local-bypass profile 才可使用 `system:local_bypass`；production 或一般無 ID principal 拒絕。
- terminal receipt/error 使用 closed command discriminator＋schema version；禁止 raw map 穿透 public view。
- repository 不 hidden commit／rollback；application composition 是唯一 outer UoW／commit owner。

### 2.2 地端 NAS 受控檔案與投影契約（2026-08-25 人工裁決）

既有工會 NAS 是契約、月嫂履歷／證明、寶寶日誌附件、餐食照片及其他大型檔案的實體 bytes 來源；MySQL 只保存 Domain 關聯、opaque object reference、content digest、MIME、size、版本、狀態、actor 與時間等 metadata，不保存大型 binary。各 Domain 仍擁有檔案的業務關聯、可見範圍、完成條件與生命週期；共用檔案能力只負責受控探索、完整性核對、版本讀取與傳輸。

- 工會人員可把既有檔案移入已配置的 Domain／subject 投放區。watcher／reconciliation 只有在檔案穩定、類型／大小／digest 與唯一 subject 關聯成立後才建立索引；未知 subject、重名歧義、寫入中、digest drift、mount unavailable 或權限錯誤 fail closed。
- 可變檔名不是 identity。每個接受版本以 opaque object identity＋digest 識別；同內容可 replay，同 object reference 指向不同內容固定 conflict。
- Web／LIFF 只提供去敏 logical projection 與 authenticated download；不得暴露 drive letter、UNC／NAS path、storage locator 或公開下載 URL。
- 修改採「下載 → 外部工具 → 放回投放區／受控 upload 形成新版本」，不提供原地編輯或 OS file browser 模擬。
- owner command 發送文件時鎖定 subject、purpose、version、digest，再建立 committed download receipt／delivery task；worker 重新核對相同 identity／digest。
- metadata 與 NAS bytes 必須有 backup／restore／reconciliation；實體 mount、retention、搬檔、schema、deployment 仍走各自 Authority／DB gate。
- exact management routes、closed owner／purpose registry、staging／cleanup／reconciliation machine contract 由 `document/功能開發計畫/NAS_檔案庫與資料中心管理介面正式規範.md` 單一擁有；本節不複製 machine fields。

### 2.3 Concurrency／Fingerprint simplification（2026-08-31）

1. owner／aggregate version 是 business mutation 的預設 optimistic concurrency control。
2. `PreviewFingerprint` 只用於真正跨 request 的 `Preview → human Confirm → Apply`，且要證明「使用者確認的 candidate」沒有因外部 current-fact change 失效。
3. 同一 outer command／batch coordinator 的合法前序 mutation 是 expected state transition，不是 external stale；後序 internal step 不得要求 command 開始前預算的 child preview fingerprint 永遠不變。
4. Batch／workbook 以使用者實際確認的 aggregate intent 為邊界。內部 row／root processing 應 fresh-read current facts；若多列指向同一 aggregate，優先按 canonical owner/root identity處理 dependency。
5. idempotency fingerprint 只驗 same key／same canonical command；不得兼作 owner version 或 Preview freshness。
6. content digest 只驗 immutable source／artifact bytes，例如 workbook、PDF、controlled file、published release evidence。
7. snapshot token 只有在 owner 沒有單一合法 version、且確實需要證明 multi-root authoritative snapshot 時才可使用。
8. 不得用兩個以上 mechanism 保護同一 stale condition，除非每一個有不同且明確的 failure meaning。
9. 真正 stale 表示 caller 確認 candidate 後，出現「不屬於本 command 預期 state transition」的 external current-fact change，使 candidate 不再合法。
10. stale／version conflict 必須是 closed typed `conflict`（對 HTTP 通常是 409）；不得用 `RuntimeError`／generic 500 表示正常 concurrency conflict。
11. 不得以 blind retry 修 false-stale。先區分 external stale、self-induced state advance、idempotent replay、deterministic derived drift、data-integrity conflict。
12. 新增 fingerprint／digest／snapshot token 前，必須能回答：保護哪個 race、owner version 為何不足、與 idempotency／content digest 的差異、唯一 failure meaning。無法回答就不新增。
13. 本裁決不要求全 repository cleanup；只在 current slice 已證明 false-stale、duplicate protection 或 deterministic drift 時做 bounded simplification。

## 3. 依賴方向

```text
UI / LINE / CLI
  → typed API / transport adapter
    → Application / Subsystem coordinator
      → owning Domain Commands / Queries
        → Domain rules
        → typed ports
          ← persistence / provider / queue / cache adapters
```

- Domain 不 import UI、FastAPI 或 concrete repository。
- 跨 Domain coordination 透過 typed ports／application coordinator。
- 需要原子性的跨 Domain operation 共用一個 outer `UnitOfWork`；內層 adapter 不 commit。
- Alert、通知、provider 透過 outbox／durable task 在 commit 後執行。

## 4. Typed errors

所有管理 API 使用一致的 error envelope：

```text
category
code
message
field_errors
domain_blockers
retryable
correlation_id
current_version
```

`category` 固定為：

- `validation`
- `forbidden`
- `not_found`
- `domain_blocked`
- `conflict`
- `idempotency_mismatch`
- `unavailable`
- `internal`

只有真正 infrastructure／availability failure 可標 retryable。`conflict` 必須重新 Query／Preview，不得自動 Apply。UI 不得依 message 字串判斷流程。

### 4.1 FastAPI 管理端公開邊界

- `/api/v1/**` 與 `/internal/v1/**` 的非 2xx JSON 使用既有 strict typed error boundary；LINE webhook／LIFF／gateway／legacy namespace 維持各自 provider contract。
- request correlation header 為 `X-Correlation-ID`；缺少時 server 產生，非法／重複值 fail closed。
- response-only correlation rebase 不得改 Domain command、receipt、audit、outbox、job 或 persistent correlation。
- unknown／legacy error 必須去敏；禁止 request body、credential、MFA material、raw exception 或 PII 穿透。
- React/shared transport 只採用通過 strict schema 的 typed error；schema drift 不用寬鬆 cast 吞掉。
- 本邊界不是所有 page-slice 的 blanket migration gate；只在 affected current path 套用。

## 5. SSOT 類型

每個欄位／狀態只能歸入一種：

- `root_fact`：經正式 command 或 external event 確認的 current root。
- `immutable_event`：曾發生的命令、付款、服務或 transition。
- `derived_projection`：可由 root facts 重建的 current value。
- `compatibility_projection`：只服務舊 caller，禁止新流程依賴。
- `query_view`：跨 Domain 顯示模型，不具寫入 Authority。

Alert、UI session、Excel、SQL View、cache、compatibility 欄位都不得升格為 root fact。

## 6. Global readiness 與完成宣告

本節不是「開始任何實作前必須全部通過」的 blanket gate。T1／T2 依 current contract 可直接施工；只有本次變更實際碰到的 boundary 才需要相應 evidence。

需要宣稱某個 material cross-domain／release slice terminal 時，至少確認：

- owner／SSOT／public contract 唯一；
- outer UoW／writer／dependency direction 無旁路；
- success、failure、replay、stale／conflict 與必要 partial-failure oracle 已覆蓋；
- DB／Browser／provider／performance 等只有在該 acceptance 明確需要時才必須實跑；
- 任何 required acceptance `blocked`／`not_run` 時不得宣稱整體完成；
- historical／deferred／superseded work 不因 current slice 自動重開。

固定 Domain 數量、完整全專案 writer scan、full suite、真 MySQL、Browser、stress、security、performance 都不得作為每個 task 的固定儀式；它們只在對應風險與 acceptance 存在時執行。

## 7. Human-assisted recovery 共同模式

```text
owner root / immutable event 出現 current issue
→ owner Query / Preview
→ 人員確認（若該 operation 需要）
→ owner Apply
→ receipt / fresh readback
→ durable recheck
→ predicate false 後移除 current issue
```

- 可唯一安全決定的結果可由 owning Domain 自動完成。
- 原因、歸屬或修復動作不唯一時停在 owner review／current issue，不猜答案。
- Anomalies 只組合 current predicate／action descriptor，不擁有帳務、排班、薪資、Orders 或 LINE root correction。
- 每個 current issue 只需定義 owner、subject、active/completion predicate、合法 action 與必要 evidence；不得為所有 code 建立 generic resolve／tracking workflow。
