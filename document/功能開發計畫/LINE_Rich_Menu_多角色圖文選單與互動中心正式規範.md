# LINE Rich Menu 多角色圖文選單與互動中心正式規範

> 文件性質：正式業務規範  
> 適用範圍：目前正式 LINE Bot  
> 更新日期：2026-09-02

## 一、目的與範圍

LINE 保留四個邏輯使用角色：一般用戶／訪客、客戶、月嫂、工會人員／管理員。角色與其功能入口必須存在，但使用者不得在 LINE 內自行切換角色或 Rich Menu。

目前 Rich Menu provider 設定維持三套主要選單：

1. `default_menu`：一般用戶／訪客與客戶共用。
2. `staff_menu`：月嫂功能入口。
3. `union_staff_menu`：工會人員／管理員功能入口。

一般用戶／訪客與客戶雖為不同業務身分情境，但共用 `default_menu`，因此不另建立第四套 provider menu。

## 二、身分判定與禁止切換規則

1. 後端目前有效的 LINE 身分綁定是身分與權限判定來源。
2. 四角色與其固定指令、功能入口繼續存在。
3. 不提供角色選擇器、`richmenuswitch`、alias switch、`esc` 或其他使用者端自行切換機制。
4. Rich Menu 顯示本身不授權任何 Domain 操作；實際功能仍由後端身分、Session、LIFF Token 與 capability 驗證。
5. 發現重複、錯綁或需要變更身分時，由使用者向工會提出。
6. 工會依當下有效身分，以既有身分維護介面解除、替換或重新綁定；完成前不得由前端猜測或覆蓋身分。

## 三、角色選單與功能入口

### 一般用戶／訪客與客戶：`default_menu`

| 按鈕 | 動作 |
| --- | --- |
| 服務登記 | LIFF `?entry=registration` |
| 修改登記資料 | LIFF `?target=profile_update` |
| 服務說明 | 傳送訊息「服務說明」 |
| 專人客服諮詢 | 傳送訊息「專人客服」 |

### 月嫂：`staff_menu`

| 按鈕 | 動作 |
| --- | --- |
| 訂單查詢 | LIFF `?target=staff_order_search` |
| 排班資訊 | LIFF `?target=staff_schedule` |
| 請假代班申請 | LIFF `?target=staff_leave_apply` |
| 薪資請款明細 | LIFF `?target=staff_payout` |

### 工會人員／管理員：`union_staff_menu`

| 按鈕 | 動作 |
| --- | --- |
| 待確認審核 | LIFF `?target=staff_review` |
| 客服中心 | LIFF `?target=customer_service` |
| 重大異常通報 | LIFF `?target=anomalies_center` |
| 即時營運看板 | LIFF `?target=dashboard` |

只允許已有安全入口或 fail-closed UI 的 target 留在選單。當 owner contract 尚未就緒時，既有 LIFF 必須顯示不可用說明，不得改走其他流程或執行 mutation。

## 四、AI 與固定指令

四角色相關固定指令與 deterministic navigation 保留。AI／QA 只處理未命中固定指令的自然語言，不得把「角色判定」改成由模型猜測，也不得透過回答觸發 Rich Menu switch。

## 五、編輯與發布

正式發布沿用既有認證後台 Preview／Apply 流程：

`Draft → Preview → Queued → Processing → Published / Failed`

- Preview 不寫入 LINE。
- Apply 才可建立發布工作。
- 各角色選單可個別維護與發布。
- 不建立使用者端 switch action。
- 身分變更與 Rich Menu 發布是兩件不同事情，不得互相冒充成功。
- 檔案修改或排入 queue 不等於 LINE 已生效；正式狀態仍以 publication readback 與 provider readback 為準。

## 六、設定與既有介面

- `config/line_menu.json` 是 bootstrap 草稿，保留 `default_menu`、`staff_menu`、`union_staff_menu`。
- 正式 current configuration 仍由既有版本化 runtime 設定與管理端讀回判定。
- LIFF 身分頁、工會身分維護、AI 客服工作室與 Rich Menu 編輯／發布 UI 沿用既有實作。
- Rich Menu 動作只允許 message、URI、postback；不允許 `richmenuswitch`。

## 七、驗收條件

1. 三套主要 provider menu 均存在且 enabled，且恰有 `default_menu` 設為 default。
2. 四個邏輯角色的功能入口仍可由其既有流程到達。
3. 設定、UI 與 provider payload 契約均不能建立 `richmenuswitch` action。
4. 身分衝突可由工會透過既有流程解除、替換或重新綁定。
5. 使用者無 `esc`、alias switch、角色選擇器或其他自行切換入口。
6. 正式 LINE 狀態須另以發布紀錄及 provider readback 驗證。
