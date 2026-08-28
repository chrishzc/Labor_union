# Agent 任務分級與交付規範

狀態：current governance
適用範圍：本 repository 的人工與 Agent 工作
權威邊界：本文件只決定執行路由與最小 durable artifacts；業務語意仍由正式規格與人工裁決擁有。

## 1. 先判斷是否改變契約

先問：這次工作是依既有契約實作，還是要改 owner、SSOT、根事實、public contract、schema／migration、
外部副作用、治理規則或跨 Domain 不變量？

- 依既有契約實作：直接讀 current spec 與 code，以最低足夠層級驗證；不要為每個 slice 重寫規格。
- 契約未唯一、互相衝突或缺少必要行為：回到同一份 current spec 收斂，不能用 code／test 代替裁決。
- 改變上述重大邊界：必須有人工 Authority，並依 T3 管理。

任務級別、行為風險、驗證範圍、Agent topology 與研究深度是五個獨立判斷；不得因風險高就自動增加
Agent 或文件，也不得因任務小就省略實際需要的安全驗證。

## 2. T0–T3 任務級別

| 級別 | 判定 | 最小交付 | 不應建立 |
|---|---|---|---|
| T0 | 唯讀回答、機械查詢、無 tracked mutation | 回答或 tool result | spec、Work Package、receipt |
| T1 | 單一 owner、依既有契約、局部可逆，且不改公開／資料／副作用邊界 | code／tests 或必要文件；focused evidence | 新 spec、逐 slice package、永久 receipt |
| T2 | 依既有規格的 material implementation，跨 layer、狀態、整合或交接 | 重用 current spec；必要時一份 living parent package；direct verification | 每個子步驟各自建 spec、package、receipt |
| T3 | 改 owner／SSOT／public contract／schema／migration／external effect／governance／跨域不變量 | 一份 current spec、一份 bounded package、必要的 aggregate final receipt | 平行重複規格、intermediate receipt 長期保存 |

若同一任務同時符合多級，以最高的實際變更邊界為準。檔案數、行數、經過時間、失敗次數與模型名稱
只能作估算訊號，不能單獨決定級別。

## 3. Durable artifact 必要性

建立 tracked artifact 前，必須能回答它的 current consumer、owner、更新／關閉條件與不可由較小產物取代的
原因。缺一項就不建立，改用對話、code comment、test output 或 ignored `scratch/<task-slug>/`。

- spec：只保存仍需跨執行共享的 observable contract、Authority 與 acceptance。
- Work Package：只在 material work 需要跨步驟 coverage、handoff、effect ceiling 或 safe stop 時建立。
- final receipt：只在 release／migration／rollback／incident／外部效果／人工稽核或明確 consumer 需要時保存。
- Current register：只保留 owner、status、blocker 與下一個 material gate，不重抄完整 spec、commands 與 log。
- intermediate plan、stdout／stderr、HTTP dump、重跑 journal、candidate receipt 與 cache：放 ignored scratch；
  final evidence 已摘要且無 rollback／稽核／inbound consumer 後刪除。

正式 migration release、hash-bound artifact、source backup、rollback receipt、current incident evidence 與受保護
fixture 不適用一般精簡規則。

## 4. 驗證與完成

驗證由變更可影響的最低邊界開始：`Static → Module → Subsystem → Domain → Global`。只有跨越整合邊界，
或 failure model 明確要求時才擴大；完整 suite、真 DB、browser、stress、concurrency、security 與 performance
都必須有對應風險事實，不能作固定儀式。

完成狀態只使用 `passed | failed | blocked | not_run`。T1／T2 可以用 command 與 current source state 在交付
訊息中證明，不必為了留下痕跡再建立 tracked receipt。任何必要 acceptance 為 `blocked`／`not_run` 時，不得
宣稱整體完成；但應精確區分已完成 slice 與尚未完成 gate。

## 5. Drift 與失敗回送

失敗先分類：

- `NONCOMPLIANCE`：契約足夠但未遵守；在原 Authority 內做最小修正並重驗受影響路徑。
- `PACKAGE_OMISSION`：material execution package 漏掉必要 path／oracle／handoff；只補 living package。
- `SPEC_GAP`：observable contract 缺失、衝突或不唯一；停止實作並回 current spec。

不得因一次失敗建立 successor spec、另一份 package 或新 receipt。只有 Authority、契約 identity、owner、
scope 或 release identity 真正改變時才建立 successor。

## 6. 快速例子

- 修正既有 typed client 的單一 schema mapping，契約與 caller 明確：T1，改 code＋focused test。
- 依正式規格接通 API、repository、React 並需同一 UoW 驗收：T2，重用 spec，必要時更新一份 parent package。
- 新增資料表與 preserve-data migration：T3，current spec＋package＋DB gate aggregate receipt。
- 搜尋未使用檔案或回答架構問題：T0；除非使用者另授權 mutation，不建立治理產物。

本文件由 `scripts/validate_agent_governance.py` 做最小靜態一致性檢查；validator 只防止路由漂移，不判定
業務規格是否正確，也不掃描歷史文件要求補件。
