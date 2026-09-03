# LINE Bot 操作 SOP

> 更新日期：2026-09-02  
> 適用範圍：目前正式 LINE Bot、LIFF 與管理端

## 一、訊息入口

LINE Webhook 由既有 runtime 驗證、保存並路由事件。固定身分／角色指令、服務指令、QA／Knowledge、真人客服與客訴各走既有 owner；不建立第二套路由。

固定指令優先於 AI 自然語言判斷。AI 不負責猜測使用者角色，也不負責切換 Rich Menu。

## 二、四個邏輯角色

目前保留四個邏輯使用角色：

1. 一般用戶／訪客。
2. 客戶。
3. 月嫂。
4. 工會人員／管理員。

一般用戶／訪客與客戶共用 `default_menu`，所以 provider 目前使用三套主要 Rich Menu，而不是四套實體選單：`default_menu`、`staff_menu`、`union_staff_menu`。

角色與功能入口存在，但使用者不能自行 switch。任何功能權限都以後端目前有效身分綁定與 capability 判定為準。

## 三、Rich Menu 功能入口

### `default_menu`

- 服務登記
- 修改登記資料
- 服務說明
- 專人客服諮詢

### `staff_menu`

- 訂單查詢
- 排班資訊
- 請假代班申請
- 薪資請款明細

### `union_staff_menu`

- 待確認審核
- 客服中心
- 重大異常通報
- 即時營運看板

選單按鈕只負責開啟既有 LIFF／Web 入口或送出固定訊息／postback；業務 mutation 仍由 owning Domain 後端執行。

## 四、禁止使用者自行切換

- 不提供 `richmenuswitch` action。
- 不提供 Rich Menu alias switch。
- 不提供角色選擇器。
- 不使用 `esc` 作為解除角色或切回其他選單的營運入口。
- 不因使用者輸入一句文字就自動改寫其 authoritative identity。

需要更換身分時，由使用者聯絡工會，工會透過既有身分維護流程解除、替換或重新綁定。

## 五、LIFF 身分與登記

1. 頁面取得 LINE ID Token。
2. 綁定／登記使用既有 typed flow。
3. 需要 mutation 的操作先 Preview，確認後才 Apply。
4. 後端 current binding 是身分判定來源。
5. 審核中或衝突狀態不得由前端自行覆蓋。

主要既有入口：

- `/line-identity`：LINE 身分確認與綁定
- `/line-registration`：服務登記
- `/line-staff-orders`：月嫂案件查詢
- `/line-staff-schedule`：月嫂排班查詢
- `/line-mobile-admin`：工會手機管理

## 六、身分重複或變更

1. 使用者向工會提出。
2. 工會查核當下有效綁定與待審核資料。
3. 工會使用既有介面執行解除、替換或重新綁定。
4. 操作完成前不改用另一角色狀態。
5. 結果以後端 readback 為準。

## 七、AI 客服與 QA

固定身分／角色指令與服務指令先處理；只有未命中固定路由的自然語言才進 QA／Knowledge 流程。

QA runtime 只有 `enabled=true` 與 `enabled=false`：

- `enabled=true`：可供語意比對並回傳題庫內固定答案。
- `enabled=false`：完全排除自動回答。

找不到可用答案時走安全 fallback；使用者明確要求真人、否定答案或提出客訴時，沿用既有客服 ticket／escalation 流程。

## 八、Rich Menu 編輯與發布

1. `config/line_menu.json` 是 bootstrap 草稿，不是正式 current state。
2. 正式設定由既有版本化 configuration 與管理端讀回為準。
3. 發布前 Preview，Apply 後才排入發布工作。
4. 各角色選單可維護，但 action 不允許 switch。
5. 以 publication readback 與 LINE provider readback 判定真正生效。
6. 不使用已退役的 `line/setup_rich_menus.py` 旁路發布。

## 九、驗收

- `default_menu`、`staff_menu`、`union_staff_menu` 均保留。
- 四個邏輯角色的固定指令與功能入口仍存在。
- 使用者端沒有 `richmenuswitch`、alias switch 或 `esc` 切換流程。
- 身分衝突由工會解除／替換／重新綁定。
- QA 只有啟用／未啟用兩態。
- Rich Menu 正式發布需完成 provider readback。
