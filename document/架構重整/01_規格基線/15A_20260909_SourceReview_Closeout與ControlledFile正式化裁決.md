# 15A — 2026-09-09 Source Review Closeout 與 Controlled File 正式化裁決

## 1. 文件狀態

- 狀態：`approved-current-index-amendment`
- 生效日期：2026-09-09
- 被補充文件：`15_正式規格索引與裁決總表.md`
- 目的：只更新 2026-09-02 之後的 `document/功能開發計畫/` source-review 處置與 Controlled File Storage Authority；不重寫 `15` 保存的其他歷史裁決。

本文件日期晚於 `15` 內先前的 source-review 恢復／待搬移文字。若兩者衝突，以本文件及其指向的 current formal spec 為準。

## 2. Current formal baseline 增補

自本裁決起，正式規格基線另納入：

- `30_Controlled_File_Storage_NAS正式規格.md`

`30` 單一擁有 Controlled File Storage／NAS 的 exact machine contract，包括：

- `FILE_PURPOSE_REGISTRY`
- closed management routes
- Query／Preview／Apply／idempotency／receipt
- metadata／typed download
- storage readiness／backup readiness／restore gate
- Freeze-Before-Send
- staging／cleanup
- reconciliation
- Data Center 管理 UI boundary
- repository-local／browser／NAS／backup／production acceptance 分層

`00_Global_共同契約.md` 只保留跨 Domain 不變量，exact machine fields 與 routes 改由 `30` 擁有。

## 3. `功能開發計畫` source-review closeout

以下三份來源文件已完成逐條 disposition，不再是 current working-tree source：

### 3.1 Rich Menu 多角色規格

`LINE_Rich_Menu_多角色圖文選單與互動中心正式規範.md`

- `17`／`23`／`29` 已承接：versioned menu configuration、audience、current role、typed action、draft／Preview／Apply／provider readback、revocation／default-menu reset。
- 舊來源中的「三套 provider menu」「訪客與客戶共用 default」「使用者不得明確選 role」「禁止 richmenuswitch」與硬編 endpoint／page／component 等內容，已被較新的 formal contract 否定，不搬移。
- 文件退出 working tree，由 Git history 保存。

### 3.2 Rich Menu 本機視覺模擬規格

`LINE_Rich_Menu_本機視覺比對與互動模擬工作室正式規範.md`

- `17`／`29` 已承接：canvas／area／action validation、before／after diff、role preview context、零 provider 外送、零 publication task、Preview 不等於 publish、terminal provider readback。
- 舊 UI layout、示例 wording、特定 screenshot／component／假資料展示只作歷史設計，不建立 formal Authority。
- 文件退出 working tree，由 Git history 保存。

### 3.3 NAS／Data Center 規格

`NAS_檔案庫與資料中心管理介面正式規範.md`

- 仍有效的 §9 machine contract 已遷移至 `30_Controlled_File_Storage_NAS正式規格.md`。
- 舊 UI 排版、NAS 型號／環境假設、歷史實作敘述與不再 current 的 hard-coded storage layout 不建立 Authority。
- 文件退出 working tree，由 Git history 保存。

## 4. Source-review disposition artifact

`document/功能開發計畫/SOURCE_REVIEW_DISPOSITION.md` 的任務已完成；它是 migration 過程記錄，不是產品 Authority，已退出 working tree。其最終裁決由本文件、`17`、`29`、`30` 與 `document/功能開發計畫/README.md` 承接。

因此 `15` 內任何仍描述上述三份 source 文件為「已恢復」「current source-review」「仍有效待搬移」「不得退役」的較舊文字，均視為已被本 2026-09-09 amendment supersede。

## 5. 仍保留的功能開發文件

本裁決不退役下列 current 文件：

- `LINE_四大模組_詳細測試手冊與前置條件.md`：current 操作／手機 E2E 手冊，非 SSOT。
- `LINE_QA客服知識契約收斂計畫.md`：current blocked implementation-gap tracker，正式語意仍由 `29` 擁有。
- `Cloud_Run_單一Cloud_VPN_部署測試計畫.md`：proposed。
- `Durable_Job_Worker_Supervision_延後開發計畫.md`：proposed／deferred。

Blocked／deferred 不等於 retired；只有完成、被 successor 承接或人工明確取消後才退出 working tree。

## 6. Acceptance／Authority boundary

本次文件遷移只收斂規格 Authority，不代表：

- production NAS mount 已驗收；
- enabled human Session browser 正向 list／download 已通過；
- backup／restore drill 已通過；
- LINE provider publication／手機 E2E 已自動完成；
- production DB、credential、deployment、外部送出或 destructive action 已獲授權。

未完成 acceptance 仍依各 owning formal spec、current plan／tracker 與 evidence 判定，不得由 source-review closeout 推定成功。