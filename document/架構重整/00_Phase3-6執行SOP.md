# React 管理端遷移 Phase 3–6 執行 SOP

狀態：current operational SOP  
適用範圍：React 管理端遷移 Phase 3、4、5、6  
非權威事項：本文件不改變正式業務規格、Work Package scope、人工裁決或 DB／provider 授權。

## 1. 目的與完成定義

本 SOP 用來避免 Phase 間跳轉、重複讀取、重複測試、工具失敗死循環及 evidence 膨脹。每次只推進一個
Phase；同一 Phase 內只有互不依賴且 write set 不重疊的工作才能平行。

Phase 完成必須同時具備：

1. 所有該 Phase 已核准且可施工的 current requirements 已完成 code／contract acceptance；只有 T2／T3
   且確有跨步驟 consumer 時才要求 living Work Package。
2. focused verification 覆蓋每個改動邊界，沒有以舊結果或單一 example 假 PASS。
3. runtime／API／browser gate 為 `PASS`，或有精確 `BLOCKED_TOOLING | BLOCKED_DATA | BLOCKED_AUTHORITY`
   並列出未完成 acceptance；blocked 不得改寫成 completed。
4. DB gate 使用 `PASS | BLOCKED | NOT_RUN`，schema／migration 未完成時固定
   `DB_CHANGE_NOT_READY`。
5. 需要 durable evidence 時只有一份 aggregate final receipt；T1／一般 T2 以 current command 與 source
   state 交付即可。原始成功 log、重複 journal 與 intermediate receipt 不長期保存。

## 2. Phase 狀態機

```text
INVENTORY
  -> IMPLEMENTATION_READY
  -> IMPLEMENTING
  -> CODE_VERIFIED
  -> RUNTIME_BATCH_READY
  -> RUNTIME_VERIFIED
  -> PHASE_COMPLETED
```

允許的旁路狀態：

- `BLOCKED_AUTHORITY`：owner、SSOT、public interface、schema、external side effect 或 scope 需要新人工裁決。
- `BLOCKED_TOOLING`：指定 browser／workflow／runtime 工具不可用；不重複重試，也不改成產品失敗。
- `BLOCKED_DATA`：合法場景根事實不足；記錄缺少的 fixture／rows 與補齊後重測點。
- `CODE_COMPLETE_RUNTIME_PENDING`：code、focused tests、build 已通過，但 runtime batch 尚未能執行。

同一 blocker 不得把 Phase 狀態退回 `INVENTORY`，也不得重開已完成的 Work Package。

## 3. 每個 Phase 的固定流程

### Step 0 — 一次性 preflight

每次開始或恢復 Phase，只做一次：

1. 記錄 branch、HEAD、`git status --short`；保留所有 dirty／untracked 成果。
2. 只讀 AGENTS、正式規格索引、該 Phase 直接 active Work Packages、final receipts 與命中的 current source。
3. 重用一張 living Phase inventory：`identity | status | owner | write set | dependencies | code | focused |
   runtime | blocker | next action`；沒有跨批次 consumer 時只在對話維護，不新增 tracked 文件。
4. completed／superseded 預設排除；只有新鮮 failing evidence 才能進 remediation。

禁止在同一 Phase 內因切換小工作包重做 Step 0。

### Step 1 — 決定可施工批次

依下列順序選取工作：

1. 已核准、dependencies 已達指定 metadata/runtime gate、write set 明確。
2. 優先完成 shared backend/API contract，再一次接完 React clients／handlers／pages。
3. LINE lane 與非 LINE lane分離；LINE 尚未開發完成時，不阻塞非 LINE 模組遷移。
4. 規格缺口若不改變本批 scope，記入既有 WP 的 open finding 後繼續下一個 bounded slice。
5. 只有 T3 的 owner、SSOT、public interface、schema、交易邊界、外部副作用或治理邊界改變時，才更新
   current spec／package；只有 identity 或 Authority 真正改變時才建立 successor。

小型 bug、測試 matcher、tooling blocker、evidence 補充不得建立 successor。

### Step 2 — 實作

1. 凍結 exact write set 與 shared hot spots；Integration Owner 是 shared docs／catalog 的唯一 writer。
2. 先依 [Agent 任務分級與交付規範](./00_Agent任務分級與交付規範.md) 判斷 T0–T3，再獨立判斷 topology。
   T0–T2 預設單 Agent；只有真正需要獨立 verifier、序列交接或至少兩條隔離 lane 時才使用多 Agent。
   子代理數是上限不是目標；共享 hot spot 同批次只有一位 integration writer。
3. 先完成該 Phase 的 API／adapter／action handler 接線，再執行 UI/runtime 測試。
4. UI 顯示「後端未提供」時先分類：
   - endpoint／typed projection 缺失：backend contract gap；
   - endpoint成功但 rows／根事實不足：`BLOCKED_DATA`；
   - payload schema或狀態機不符：contract drift；
   - 純 layout／按鈕變形：UI defect。
5. 只有大幅 UI／JavaScript 視覺重構才使用 Stitch；backend 接線、typed projection 與測試資料問題不得
   轉成 Stitch 工作。
6. completed WP 出現新鮮 failing evidence時，在原 evidence directory新增 remediation section；除非第 1 節
   authority 邊界改變，不建立新 identity。

### Step 3 — 有界驗證

驗證依 `Module -> Subsystem -> Domain -> Global`，但執行次數受限：

1. 每個 bounded write batch 執行一次 focused test command。
2. 失敗後只有取得新證據並完成針對性修正，才能再跑一次；純 matcher 問題先一次修完。
3. 同一 Phase 所有 production edits 完成後只跑一次 TypeScript／production build。
4. React full suite、Python full suite與完整 UI sweep 留到 Phase 3–6 接線完成後各跑一次；不以每個 WP 重跑。
5. non-fatal warning 必須記錄，但不得冒充 failed；failed 也不得被 warning 說明掩蓋。

### Step 4 — Runtime batch

同一 Phase 的 runtime 驗收集中成一次 session：

1. 啟動前回讀 port listener identity、environment、auth profile、host、database與credential class。
2. 只終止／重啟可證明 owned 的 process；未知 process 不動。
3. API 使用 `api-test-workflow` 去重、縮減與計量；workflow 自身錯誤標記 `BLOCKED_TOOLING`，不得反覆換
   adapter或把工具失敗算成 API failure。
4. Browser 只連線一次；失敗後依官方 recovery 做一次重試。外部狀態未改變時不再重試。
5. Browser session 依 inventory 一次跑完該 Phase 所有可驗收 routes／scenarios，再關閉 owned runtime。
6. 測試資料不足記 `BLOCKED_DATA`，列出缺少根事實與重測點；不為了讓 UI 好看合成未授權資料。

### Step 5 — DB gate

1. 0 schema／migration change：不跑 migration chain；Static release、Descriptor、Read-only plan固定
   `NOT_RUN`，總結仍為 `DB_CHANGE_NOT_READY (0 DB change)`。
2. API／UI／Domain runtime 可依
   [Migration 與 Cutover 規格](./01_規格基線/10_Global_保留資料Migration與Cutover_Subsystem.md#9-agent-與開發者-db-變更執行門)
   使用 allowlisted development `lu_test_*`與目前 credential；只操作
   scenario-owned rows，保存before／after／receipt並scoped cleanup。禁止`union_db`與production target。
3. schema／migration變更必須完整執行同一正式規格的七個 gate；既有 DB runtime不可取代fresh與preserve-data
   candidate evidence。
4. HCM仍只做Import Result Review，不合成或上傳測試 XLSX。

### Step 6 — 收斂與移交

1. 只有 release／migration／rollback／incident／外部效果／稽核或明確 consumer 需要時，才保留一份
   aggregate final receipt；不按 slice 建 receipt。
2. Phase inventory 更新一次；completed／superseded不再出現在active execution queue。
3. 刪除無 inbound reference、已被final receipt摘要且不屬migration／rollback／incident的raw logs。
4. Phase只有在 requirement-by-requirement evidence 完整時標 completed；否則使用精確 pending／blocked 狀態。
5. 完成本 Phase 收斂後才切換下一 Phase；工具阻塞項集中放入最終 runtime queue，不回頭穿插施工。

若 current SSOT 明確形成跨 Phase hard prerequisite（例如 Phase 3 consumer依賴Phase 4 owner adoption），不得
假稱 current Phase 可線性完成，也不得自由切換整個 Phase。處理方式固定為：記錄 dependency edge與原 Phase
checkpoint，只執行被點名的 exact prerequisite slice，完成其驗收後立即返回原 checkpoint。若要永久重編 Phase
ownership或解除 dependency，必須取得人工裁決。

## 4. 重試與停止規則

| 情況 | 最大自動處理 | 結果 |
|---|---:|---|
| 同一測試失敗 | 1次針對性修正後重跑 | 再失敗即保留failed evidence並換下一可施工slice |
| Browser連線失敗 | 初次＋1次官方recovery | `BLOCKED_TOOLING` |
| API workflow自身失敗 | 初次＋1次有新證據修正 | `BLOCKED_TOOLING` |
| 測試資料不足 | 1次根事實盤點 | `BLOCKED_DATA`，資料補齊後才重測 |
| 規格／owner／public contract不明 | 0次猜測 | `BLOCKED_AUTHORITY`並請求人工裁決 |
| completed WP無新鮮failure | 0次重開 | 保持completed |

任何失敗都不得無界建立 successor、重跑 full suite、切換 browser surface或建立新的 disposable DB。

## 5. Phase 3–6 固定順序

1. Phase 3：非 LINE action handlers與typed query／mutation contracts全部接線。
2. Phase 4：Import、Finance、LINE高副作用流程；LINE缺口不阻塞可獨立的Import／Finance。
3. Phase 5：entry target control plane、逐entry cutover、dual-run與rollback evidence。
4. Phase 6：immutable artifact hosting、production runtime gate、逐entry retirement；retention未核准到期前不刪
   Streamlit。
5. 最終驗收：一次focused aggregation、一次full suites、一次API batch、一次UI route sweep，再決定Phase 6
   retirement readiness。

上述順序受第3節Step 6的cross-Phase hard-prerequisite例外約束；例外只授權必要slice，不授權整個後續Phase提前。

## 6. 每次進度回報格式

```text
Current phase / state:
Completed this batch:
Evidence:
Blocked (tooling | data | authority):
DB gates: PASS | BLOCKED | NOT_RUN; DB_CHANGE_NOT_READY when applicable
Next single action:
```

不得用「大致正常」、「應該完成」或舊 receipt 替代當前證據。
