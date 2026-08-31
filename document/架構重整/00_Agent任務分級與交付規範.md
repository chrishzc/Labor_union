# Agent 任務分級與交付規範

狀態：current governance  
適用：本 repository 的人工與 Agent 工作  
邊界：本文件只決定執行路由、工程 guard 與最小 durable artifacts；業務語意仍由 owning current spec 與最新人工裁決擁有。

## 1. 先判斷是否改變契約

先問兩件事：

1. 這次工作是否只是依既有 observable contract 實作／修正？
2. 是否會改 owner、SSOT、root fact、public contract、schema／migration、external effect、transaction boundary、governance 或 cross-domain invariant？

- 既有契約足夠：直接實作與 focused 驗證，不重寫規格。
- observable contract 缺失、衝突或不唯一：停止該方向，回同一份 current spec 收斂。
- 改變重大邊界：T3，需人工 Authority。

任務級別、風險、驗證範圍、Agent topology 與研究深度分開判斷；不得因風險高就自動增加文件／Agent，也不得因工作小就省略必要安全驗證。

## 2. T0–T3

| 級別 | 判定 | 最小交付 | 不應建立 |
|---|---|---|---|
| T0 | 唯讀回答、查詢、無 tracked mutation | 回答或 tool result | spec、Work Package、receipt |
| T1 | 單一 owner、依既有契約、局部可逆，不改公開／資料／副作用邊界 | code／tests 或必要文件 | 新 spec、逐 slice package、永久 receipt |
| T2 | 依既有規格的 material implementation，跨 layer／state／integration／handoff | 重用 current spec；必要時一份 living parent package；direct verification | 每個子步驟各自建 spec、package、receipt |
| T3 | 改 owner／SSOT／public contract／schema／migration／external effect／transaction／governance／跨域不變量 | current spec、bounded package、必要 aggregate final receipt | 平行重複規格、intermediate receipt 長期保存 |

同一任務符合多級時，以最高實際變更邊界為準。檔案數、行數、耗時、失敗次數或模型名稱不決定級別。

## 3. P0 engineering guards

這些 guard 立即套用所有 current 工作，但不形成新的全 repository cleanup 任務。

### 3.1 Scope

- 只完成 current observable behavior、acceptance 與必要 write set。
- 不順便重構、統一相鄰模組、補未來 abstraction 或修不阻塞 acceptance 的技術債。
- 新 generic abstraction 必須是目前 contract 所必需，不能只因「之後可能會用」。

### 3.2 Concurrency／Fingerprint

- owner／aggregate version 是 mutation 的主要 concurrency control。
- `PreviewFingerprint` 只屬真正跨 request 的 `Preview → human Confirm → Apply` 邊界。
- idempotency fingerprint 只驗 same-key/same-command；content digest 只驗 immutable source/artifact。
- 同一 outer command／batch 的合法前序 mutation不是 external stale；不得用舊 child-preview fingerprint製造 self-conflict。
- snapshot token 只有在單一 owner version不足以表示 authoritative multi-root snapshot 時才可新增。
- 新增 fingerprint／digest／snapshot 前，必須能說明具體 race、現有 version 為何不足及唯一 failure meaning。
- 正常 stale／version conflict必須是 closed typed conflict，不得漏成 generic exception／500；不得以 blind retry 遮蔽 false-stale。
- 不主動清理全 repo；current slice 有實際 false-stale／duplicate protection 才做 bounded simplification。

### 3.3 Living artifact drift

合法 canonical change 若使仍在使用的 test、validator、current manifest、Arch Map／inventory 等 deterministic drift，可在同一 bounded slice 做最小 synchronization，不需重開 completed work。

只允許對齊 current fact，不得改 business oracle、owner、SSOT、public contract、schema scope 或 external effect。Historical receipt、published/applied immutable artifact、hash-bound historical evidence 與 archive 不改寫。

## 4. Durable artifacts

Tracked artifact 必須有 current consumer、owner、關閉條件，且不能被較小產物取代；否則用對話、test output 或 ignored `scratch/<task-slug>/`。

- spec：只保存跨執行仍需共享的 observable contract、Authority、acceptance。
- Work Package：只在 material work 需要跨步驟 coverage／handoff／effect ceiling／safe stop 時建立。
- final receipt：只在 release／migration／rollback／incident／external effect／audit 或明確 consumer 需要時保存。
- Current register：只保留 owner、status、blocker、next material gate。
- intermediate plan、stdout／stderr、HTTP dump、candidate receipt、cache：放 scratch；無 inbound consumer 後刪除。

Migration release、hash-bound artifact、source backup、rollback receipt、current incident evidence、受保護 fixture 不適用一般精簡。

## 5. 驗證與完成

驗證從最低受影響邊界開始：`Static → Module → Subsystem → Domain → Global`。只有跨整合邊界或 failure model 明確要求時才擴大到 full suite、真 DB、Browser、stress、concurrency、security、performance。

驗證結果只用 `passed | failed | blocked | not_run`。必要 acceptance 仍 `blocked／not_run` 時不得宣稱 umbrella 完成；但單一 package blocked 不代表整個 goal 必須停止，若存在獨立、已授權且不違反 dependency 的 current item，繼續執行。

環境缺失、服務未啟動、合法 DB target 不存在屬 execution/environment blocker，不得重新包裝成架構裁決。

## 6. Drift／失敗分類

先分類再處理：

- `NONCOMPLIANCE`：contract足夠但實作未遵守；原 Authority 內最小修正。
- `PACKAGE_OMISSION`：既有 material package 漏掉必要 path／oracle／handoff；只補同一 living package。
- `SPEC_GAP`：observable contract 缺失／衝突／不唯一；停止該方向並回 current spec。

`BOUNDARY_REQUIRED`、`AUTHORITY_REQUIRED`、`ENVIRONMENT_BLOCKED` 可作回報的 blocker type，但不是新的 repository status／Domain enum。

不得因一次 failure 新建 successor spec、另一份 package、重複 receipt 或 generic framework。只有 Authority、owner、contract identity、scope 或 release identity 真正改變才建立 successor。

## 7. 快速例子

- typed client 單一 mapping bug、contract 明確：T1。
- 已有正式 spec，接 API＋repository＋React＋同一 UoW：T2。
- 新資料表／migration／public entry／external provider effect：T3。
- workbook 已做整體 human Preview，Apply 內 row 1 合法 mutation 使 row 2 舊 fingerprint失效：不是 external stale；修 batch execution model，不加 blind retry。
- 查詢／架構回答：T0。

本文件由 `scripts/validate_agent_governance.py` 做最小 routing marker 檢查；validator 只防止治理連結漂移，不判業務正確性，也不得要求歷史文件補件。
