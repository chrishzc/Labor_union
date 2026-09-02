# LINE Bot 操作 SOP

> 更新日期：2026-09-02  
> 適用範圍：目前正式 LINE Bot、LIFF 與管理端

## 一、訊息入口

LINE Webhook 由既有 runtime 驗證、保存並路由事件。固定服務指令、知識回答、澄清、安全 fallback、真人客服與客訴均沿用目前後端處理；本 SOP 不建立第二套關鍵字或回覆流程。

## 二、共用 Rich Menu

正式帳號使用一套共用預設 Rich Menu：

- 服務登記
- 修改登記資料
- 服務說明
- 專人客服諮詢

選單不提供使用者身分或角色切換。月嫂與工會人員功能由既有安全入口及後端權限判定，不以 Rich Menu 顯示狀態授權。

## 三、LIFF 身分與登記

1. 使用者由 Rich Menu 開啟既有 LIFF 身分或登記入口。
2. 頁面取得 LINE ID Token，先建立並驗證身分流程。
3. 綁定或登記先執行 Preview；使用者確認後才執行 Apply。
4. 後端目前有效的 LINE 身分綁定是身分判定來源。
5. 前端不得自行猜測、切換或覆蓋身分。

主要既有入口：

- `/line-identity`：LINE 身分確認與綁定
- `/line-registration`：服務登記
- `/line-staff-orders`：月嫂案件查詢
- `/line-staff-schedule`：月嫂排班查詢
- `/line-mobile-admin`：工會手機管理

## 四、身分重複或變更

1. 使用者發現重複、錯綁或需要變更身分時，向工會提出。
2. 工會先查核當下有效綁定及待審核資料。
3. 工會使用既有身分維護介面執行解除、替換或重新綁定。
4. 未完成審核前，不由 Rich Menu 或前端切換身分。
5. 操作結果以後端 readback 為準。

## 五、工會操作

工會手機端沿用 `/line-mobile-admin` 的既有功能：

- 客服中心
- 排班審核
- 月嫂驗證

管理端身分維護沿用既有 Preview／Apply 與 readback。操作權限仍由後端 Session、LIFF Token 與 capability 判定。

## 六、Rich Menu 編輯與發布

1. `config/line_menu.json` 僅作 bootstrap 草稿，目前只保留一個啟用中的預設選單。
2. 選單內容與圖片由既有 Rich Menu 管理介面維護。
3. 發布前執行 Preview，核對選單內容與影響範圍。
4. 由已登入且具權限的管理員執行 Apply，排入發布工作。
5. 以發布紀錄與 LINE provider readback 判定成功；檔案修改或 queue 成功不等於 LINE 已生效。
6. 不使用已退役的 `line/setup_rich_menus.py`。

## 七、驗收

- bootstrap 設定只有一套共用預設 Rich Menu。
- 四個按鈕可正常開啟既有 LIFF 或送出對應訊息。
- 身分綁定與變更均依 Preview／Apply 流程處理。
- 身分衝突可由工會既有介面解除、替換或重新綁定。
- Rich Menu 經認證後台發布並完成 provider readback。
- 無使用者端角色或選單切換入口。
