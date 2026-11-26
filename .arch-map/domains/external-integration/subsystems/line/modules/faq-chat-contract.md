# LINE FAQ 前後端與資料交接契約

來源：[需求書 #29 §4.1](../../../../../requirements/29_LINE服務說明、客服互動與選單角色正式規格.md#41-共用問答與聊天室版面) · [前端設計與角色入口](faq-chat-layout.md) · [Knowledge 發布版本](../../../../knowledge-retrieval/subsystems/knowledge-retrieval/modules/reviewable-qa-catalog.md)。下列新操作是 #436 規劃契約，還不是上線 API。既有 Q&A 治理 API 路徑與權限不改。

## 查、寫、讀回

新管理入口前綴 `/api/v1/line/faq-layout`。所有 GET 和 Preview 唯讀。以 `BaseResponse.data` 回傳資料，沿專案 typed error 形狀；所有路徑透過既有前綴處理機制（前端用 `applicationFetch`）。管理 Query／Preview／寫入沿 LINE `CONFIG_MANAGE`，不把 draft 暴露於公開查詢；題庫沿既有 Knowledge manager／publisher，不新增可跳過審核的權限。

| 方法與路徑 | 輸入 → 成功輸出 | 作用 |
|---|---|---|
| GET `/` | 無 → `draft_revision, published_revision, draft_layout, published_layout` | 整份版面單一 revision，無正式版兩個 published 欄位均為 null。 |
| POST `/preview` | `{mode:"draft",layout,category_id}` 或 `{mode:"published",category_id}` → `{view, issues}` | 草稿使用傳入的編輯內容；正式版由伺服器重讀。兩者只讀正式答案，零寫入零傳送。正式版未發布或無該分類回 404 `faq_category_not_published`。 |
| POST `/categories` | `{name, expected_revision}` → `{operation_id, draft_revision, category_id}` | 建立帶穩定 ID 的共享分類及空白草稿卡片；先存不對外出現。 |
| PUT `/draft` | `{expected_revision, layout}` → `{operation_id, draft_revision}` | 保存現有分類的版面編輯，不隱含建立、刪除或重命名分類。 |
| POST `/publish` | `{expected_revision}` → `{operation_id, draft_revision, published_revision}` | 發布整份已儲存草稿；不接收未保存的 layout，不改 Q&A、不呼叫 LINE 發布 Rich Menu。 |
| GET `/operations/{operation_id}` | 原 `Idempotency-Key` → 相同操作回執 | 查不到是沒有可讀回的回執，不等同於確認未寫入；先刷新 Query，必要時同鍵重送。 |

表中路徑接在前綴後，GET 根路徑不附尾斜線。所有寫入必帶 `Idempotency-Key`、`X-Correlation-ID`。expected_revision 為最近一次成功讀回之整份 draft revision；初始化未建立用 0，正常版本為正整數。每次成功寫入均前移 draft_revision；只有 publish 同一次設定交易更新 published_revision。前端若仍有未存編輯，先儲存再發布；兩次寫入使用不同操作鍵。回執識別等於本次操作鍵。相同鍵及相同命令重送回原回執，不新增版本；同鍵不同內容回 409。Query 讀回的現況可以比回執更新，兩者不可互相覆寫。

**資料型別。** `Layout = {categories: CategoryCard[]}`（陣列即顯示順序）。`CategoryCard = {category_id: string, name: string, title: string, description: string, footer_label: string, questions: QuestionLink[]}`；`QuestionLink = {qa_id: string, label: string}`，ID 和短文是版面資料，不含答案。名稱 trim 後 1–24 字、同一清單正規化 NFKC 加大小寫折疊後唯一；名稱是識別顯示，卡片標題另可編輯。標題發布時必填，最長 36；說明 ≤150、底部文字 ≤28、題目短文 ≤24，空說明／底部省略；底部若有值仍只到現有 AI LIFF，不能輸入任意 URL。題目短文空白使用正式題目產生受限短標籤，Quick Reply 另驗其上限，不能直接複用 24 字 Flex 標籤。最多四筆、同卡 qa_id 不重複；同題可用在不同卡片。可儲存空卡；發布若卡片無有效題目或指定引用已停用則回欄位錯誤，不影響舊版。既有分類、題目各沿原固定 ID；新分類 ID 後端生成，不受名稱影響。分類按建立順序顯示，既有分類延續目前順序；分類排序、改名、刪除與自訂 CTA 目的地本輪不做。分類建立後可供題庫選擇；分類可在 FAQ 網頁出現的依據是已發布的題，不是 LINE 版面是否發布。

**視圖型別。** Preview 回 `view={category_id,title,description,footer_label,buttons:[{qa_id,label,question,answer}]}`；有失效引用時不塞假答案，回 `issues:[{code, field, qa_id?}]`，field 為具體欄位／陣列路徑。正式 FAQ 仍用既有 `GET /api/v1/line/service-help/faq`，保留 `items,categories`，增加 `next_cursor:string|null`；接受 `cursor` 與 `limit`（預設 50，1–100）。網頁逐頁取得完整題庫，不另寫固定上限。以 stable qa_id 排序／游標，服務端先套 published 與 FAQ 投影再分頁；游標無效回 422，資料故障回 503，不當空清單。分類名稱從共用映射讀取，不依賴卡片是否上線；公開回應不帶草稿／稽核／管理員資料。版面選題讀取相同的正式投影。題庫編輯以 Knowledge 管理權限呼叫 `GET /api/v1/knowledge/faq-categories`，`data.categories` 回 `{category_id,name}[]`，來源為版面共用分類。題目公開清單每筆帶 `version` 與可空的 `category_id`。管理端可用 `qa_id` 精確讀回單題，與 `cursor` 互斥，沿用清單回應。編輯既有題目需帶當前 `expected_version`（本輪在現有 ingest body 增加既有 QA 修訂的版本欄位，保持首次建立與非 QA 呼叫相容）；發布／停用沿原 `expected_version`，回既有 item/version/index_job，另以公開回讀確認正式結果。若有正在修改的草稿且題目仍有正式版，從最新編輯版本提交停用時須即時撤下正式版；不能因編輯狀態是 draft 而拒絕撤下。只有從未發布的 draft 不可用「停用正式版」命令。

| 結果 | 前端下一步 |
|---|---|
| 401／403 未登入或無權 | 顯示現有重登／權限提示，不重送。 |
| 404 `faq_category_not_published` | 正式預覽顯示尚未發布，不回退到草稿。 |
| 422 `faq_layout_invalid`／無效游標 | 保留輸入，定位欄位；不提示成功。 |
| 409 `faq_layout_revision_conflict`／`faq_layout_idempotency_conflict` | 讀回新版讓使用者對照，不覆寫或自動改鍵再送。 |
| 503 `knowledge_catalog_unavailable`／`faq_layout_unavailable` | 顯示來源暫不可用；若是寫入結果不明，先查原鍵及正式資料。 |

## LINE 接線與相容

- 新分類卡片用 `faq:v1:category:<category_id>`；題目用 `faq:v1:question:<qa_id>`。ID 不帶名稱、答案或個資；沿既有已驗證一對一事件的 Reply-only 路徑。解析器驗動作和 ID 格式，不接受任意操作；未知／停用導回常見問題或專員，來源故障明示暫不可用。新題目取正式答案時不等索引，其他搜尋不得以舊索引越過停用／未發布檢查。
- 舊 message action 不會改寫：保留兩個舊分類指令和舊題目文字的精確對照；多筆同名不任選。既有服務進度、修改資料及 AI 導航保留。分類主選單使用 6 個問答分類為一頁，既有固定行動另保留，如有後頁才呈現下一頁、非首段可返回；用 `faq:v1:menu:<page>` 帶非負頁碼（首段為 0），無效或超界回首段，不以 Quick Reply 決定清單涵蓋範圍。Flex 與 Quick Reply 的各自限制見版面模組。
- 對照匯入以既有 JSONL／舊卡片為來源清單，比對正式項目，不在 runtime 讀取。保留別名、順序、既有特殊政策說明；無唯一匹配列差異，不把舊答案偷偷發布或用文字硬接其他題。

## DB 交接與切換

- 建議在兩張 `line_configuration_*` 既有 ENUM 增加 `faq_chat_layout`；一個 typed JSON 快照（`schema_version=1`）存分類 ID／名稱、draft_layout、published_layout 和 published_revision。沿用唯一的 kind+revision、idempotency、current→revision FK；compare-and-set、快照、current 與稽核同一交易。公開只取 current 指向的快照內已發布部分。非 FAQ 種類、舊 Rich Menu 版本和記錄不改。新分類建立於同一事務，以快照為名稱／ID 對照來源，不另建分類表或重複名稱清單。題目版本存 category_id；無 category_id 的已發布老資料以明確映射解析，不以字串模糊猜。
- Knowledge root 正式指標是 nullable BIGINT UNSIGNED（與 item_version 一致）；讀時以同一 item_id+version join；歷史快照不可改寫。新的不可變版本要保存可供發布回讀的來源與標題；候選實作讓後端組成完整版本快照，不混讀草稿 root。版本、指標、憑證及發布索引工作遵守同一 owner 交易，以新連線查出沒留下半套。重放用原鍵及 fingerprint 回讀，不能因目前狀態已變而新增事件。
- 保留資料升級先在與原服務分離的候選庫套用 1087。正式資料維護者核對唯讀盤點，提交有 `reviewed_by`、`categories` 和 `legacy_questions` 的對照。保留升級的 release manifest 呼叫共用回填邏輯，留存對照檔雜湊及盤點、回填、讀回的回執。以唯讀盤點的 fingerprint 核對鎖定後的回填計畫，只補有證據的缺值，保留不可變歷史、草稿與已停用狀態。
- 回填提交後，受控升級另開連線，核對正式指標、實際相容文字解析及必要的正式版面。保留資料驗證通過才在候選庫寫入 `migration:shared-line-faq:reader-ready:v1`。切換前再以新連線核對就緒憑證與候選資料指紋，才可切換 `DB_DATABASE`。API 與 LINE worker 讀取同一憑證。沒有憑證時維持相容讀取，資料來源或憑證讀取失敗時回暫不可用。已啟用共用 reader 時，JSONL 僅供播種與遷移。
- 歧義、來源證明不足、回填或讀回失敗會記在候選操作回執，原服務的資料庫保持原指向。已嘗試回填的候選以相同審核檔案及原操作回執續接。對照需要修正且已嘗試回填時，保留該候選供稽核，再從原庫快照建立新候選。重跑在同一候選補缺值與讀回，不產生第二份初始正式版面。切換後若應用有故障，保留候選與已發布的 Knowledge 版本及版面，停用新入口或修復程式後向前恢復。已有新寫入時，不直接把環境指回升級前原庫。
- `python -m scripts.backfill_shared_line_faq` 可作唯讀盤點，獨立 CLI 的 `--apply` 限明確指名的本機 `lu_test_*`。正式保留資料回填只由受控候選升級執行。真實舊資料的歧義由資料維護者確認，這項工作是正式切換門檻。

## 最少的驗收與歸因

| 案例 ID（需求書 §4.1） | 應斷言的結果 | 主責與證據 |
|---|---|---|
| FAQ-01 新分類 | 空名／重名不寫；有效草稿可預覽但不能見於已發布選單；有正式題後發布、重新開啟可見 | 前端走一條 Playwright 旅程；後端 fake port 驗狀態與錯誤契約。 |
| FAQ-02 正式 A／草稿 B | 草稿 B 兩通路都仍回 A；發布 B 後舊按鈕及網頁都回 B；停用後舊按鈕走指引；不能由索引補回 A/B | 後端用例與 consumer/provider 契約；隔離 LINE payload fixture，不稱官方宿主實測。 |
| FAQ-03 完整 FAQ | 101 筆已發布＋非 FAQ 及草稿混合；逐頁恰好 101 筆，未選入卡片也找得到；503 不顯示零筆真相 | 後端測既有公開路由；前端驗跨頁與錯誤。 |
| FAQ-04 原子與重送 | 同鍵同命令一次寫入；變更內容同鍵 409；交易內正式指標與回執已寫後、提交前注入失敗，新連線仍讀舊正式版且無本次回執 | DB 在隔離 MySQL 只驗受影響持久化、升級及回讀；不重跑業務矩陣。 |
| FAQ-05 舊入口 | 舊詞可唯一映射則取得當前正式版；歧義不猜、已停用或不存在不給舊答案；LINE 無 Push、無 Rich Menu 發布 | 後端／LINE 合約測試與 SDK payload 驗證；正式 LINE 真宿主需獨立驗收。 |

在既有 Knowledge／LINE 測試入口擴充案例並讓 GitHub CI 有明確選跑，不在地端跑測試檔。記 PR head、base、實際 checkout、run／attempt、實跑 test ID；工作流程綠但案例沒選到仍是 not_run。不把執行證據寫回設計文件。文件接手測試先用 FAQ-02：若需求未定草稿可見性就是 PM 缺口；需求已定但 API 只讀目前版本就是後端設計缺口；契約正確而草稿造成正式讀取消失就是實作問題；若 CI 沒選到，先補驗收證據，不判定產品通過。
