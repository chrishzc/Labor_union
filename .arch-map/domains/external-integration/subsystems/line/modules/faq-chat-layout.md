# Module: FAQ 聊天室版面

## 責任邊界

- 需求：[需求書 #29 §4.1](../../../../../requirements/29_LINE服務說明、客服互動與選單角色正式規格.md#41-共用問答與聊天室版面)；管理入口：[需求書 #20 §5.1](../../../../../requirements/20_LINE客服與月嫂自助服務正式規格.md#51-管理端桌面分頁)。
- LINE 擁有分類卡片的版面與正式選單投影；[Knowledge Retrieval](../../../../knowledge-retrieval/subsystems/knowledge-retrieval/modules/reviewable-qa-catalog.md) 擁有題目、答案、別名與正式版本。共用分類以穩定 ID 銜接；在版面中只存卡片設定及題目引用，不複製題目、答案或網頁清單。分類是可由後台增加的資料，不為每個分類建表。
- 本頁是目標設計，不表示已接線或驗收。現況入口：`ui_react/src/pages/line_management/AiCustomerServiceStudioPage.tsx`、`CommonQaCatalogPanel.tsx`、`subsystems/line/service_help_application.py`，網頁 FAQ 經 `api/routes/line_service_help.py`。

## 前端設計

| 區域 | 內容與操作 |
|---|---|
| 左：分類卡片 | 顯示分類名稱、題數或草稿狀態；「＋ 新增分類」展開名稱表單。建立後切到新卡片並聚焦標題。 |
| 中：編輯 | 卡片標題、說明、最多四個選題槽、短文字、移動／移除與底部快捷入口；「儲存版面草稿」「發布聊天室版面」分開。 |
| 右：手機預覽 | 可點的分類選單、卡片、答案；草稿／已發布切換。無正式版的分類在已發布選單不可見，從編輯器切換查看時明示尚未發布。 |

空名／同名就地提示；儲存與發布失敗不顯示成功，保留表單可重試。發布前提示影響哪一個通路。正式預覽與聊天室共用版面投影規則；預覽不呼叫 LINE 寄送。沿用固定卡片，不做自由畫布。

## 前後端接線與版本

1. AI 客服工作室從受管理的 Query 讀取分類、版面草稿與已發布版本，以及權威題庫提供的已發布選題清單。分類新增不需另到第二個入口；須保證名稱唯一、ID 穩定。題庫管理可引用該分類 ID，但**題目發布與版面發布仍是兩個操作**。
2. 編輯命令只修改草稿。發布命令在伺服器檢查權限、預期版本、題目引用及卡片限制；版本衝突回傳目前版本，不能覆寫他人的新稿或冒充成功。正式公開讀取只使用最後成功發布的版面；中途失敗維持上一版。
3. 聊天室讀已發布分類版面，按鈕只帶穩定題目 ID（沿用舊指令相容路由），回覆時向 Knowledge 讀當下正式版本。找不到或已停用的引用不能用舊內容補位；來源失敗則走既有重試／留言指引，不誤報為空。
4. 保持既有客服導覽、AI LIFF 入口與上線中的 Rich Menu。舊兩個分類先保留 ID、入口與版面；現有題目引用對應正式目錄，不能把 JSONL 檔案重新升格為正式來源。本 PR 不新增表、API 或 migration。

## 實作落點與切換順序

1. **先解開題庫的草稿與正式讀取。** 現況 [修訂舊題](https://github.com/chrishzc/Labor_union/blob/6783f9d8b75daa3cc851ea3df0774c69edbb4a5c/infrastructure/mysql/knowledge_retrieval_repository.py#L697-L729) 把同一題的 root 設回 `draft` 並清除發布欄位，而 [公開讀取](https://github.com/chrishzc/Labor_union/blob/6783f9d8b75daa3cc851ea3df0774c69edbb4a5c/infrastructure/mysql/knowledge_retrieval_repository.py#L928-L940) 只讀目前版本且要求 `published`。直接讓兩通路使用該查詢會讓修訂中的題同時消失。先建立獨立的已發布版本指標，再讓所有公開查詢都走它；不把編輯列表或搜尋索引當公開來源。
2. **重用 LINE 設定儲存機制，不重啟退役功能。** 建議在 [LINE 設定 revision/current 表](https://github.com/chrishzc/Labor_union/blob/6783f9d8b75daa3cc851ea3df0774c69edbb4a5c/db/schema_parts/155_line_identity_review_configuration.sql#L241-L273) 擴增專屬 FAQ 版面 kind，沿用權限、預期 revision、防重和稽核。現有兩表的 kind 是 ENUM；此路徑需要一次相容升級，不是新增分類時改 DB schema。不能直接借 `customer_service`：[現行驗證器](https://github.com/chrishzc/Labor_union/blob/6783f9d8b75daa3cc851ea3df0774c69edbb4a5c/subsystems/line/configuration_application.py#L388-L402) 明確拒絕其非空設定，也不借需呼叫 LINE 平台的 Rich Menu 發布流程。FAQ 版面快照須同時可讀取 `draft_layout`／`published_layout`（發布連同新 revision 原子提交）；公開 Query 只投影已發布部分，不能讓既有泛用設定讀取暴露草稿。分類名稱與 ID 共用，後台題庫顯示同一分類清單；保留既有題庫分類文字的讀取相容性，先遷移對照，不以文字或順序當 ID。
3. **新舊 LINE 按鈕分流。** [現行分類導覽](https://github.com/chrishzc/Labor_union/blob/6783f9d8b75daa3cc851ea3df0774c69edbb4a5c/subsystems/line/service_help_application.py#L362-L395) 和舊卡片是 message action，舊訊息不會重新產生。新 Flex 及 Quick Reply 使用版本化的 FAQ postback，資料只傳分類或題目的穩定 ID；短標籤改名不改識別。接到現有一對一 LINE inbound/Reply 路徑，不放寬群組可用範圍。舊文字指令和舊題目文字透過已發布的舊別名相容表解析，改題名前建立必要對照；無唯一正式匹配時引導選擇／留言，不以同義詞猜題。官方支援 [postback／label 上限](https://developers.line.biz/en/reference/messaging-api/#postback-action) 與 [每則訊息最多 13 個 Quick Reply](https://developers.line.biz/en/docs/messaging-api/using-quick-reply/)；分類多時主選單須能翻頁或繼續瀏覽，不以 Quick Reply 靜默截斷。實作時用同一版面／按鈕投影組出預覽及 LINE payload。
4. **最後切兩個讀取入口。** [網頁 API](https://github.com/chrishzc/Labor_union/blob/6783f9d8b75daa3cc851ea3df0774c69edbb4a5c/api/routes/line_service_help.py#L88-L131) 目前會先取最多 100 筆 Knowledge、再判斷是否為 FAQ。排序與分頁應針對正式 FAQ 投影；用穩定游標讀到結尾，不讓非 FAQ 記錄占掉頁面，也不把一頁當全部。先在 GitHub CI 用合成資料比對舊分類、題目、別名與政策固定說明；確認所有舊入口可找回已發布題目或有明確替代後，再切至共用讀取、移除舊 runtime JSONL。不能先拔檔再補資料。

## 驗收分工（尚未執行）

- 前端：用既有測試入口，確認新增分類、重名、預覽切換、選題四槽與發布失敗不誤報；關鍵使用路徑可用瀏覽器從新增走到正式選單。
- 後端：以假題庫和版本儲存驗證草稿隔離、舊按鈕解析、停止讀取 JSONL、停用、來源故障及超過 100 題的網頁分頁。DB 只驗受影響的版本與分類／題目引用的讀寫與唯一性，不跑一整套業務矩陣。
