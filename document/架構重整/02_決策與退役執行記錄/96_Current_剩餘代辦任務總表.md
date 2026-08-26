---
doc_type: gap-register
declared_status: in-progress
date: 2026-08-25
owner: architecture-governance / product-and-domain-owners
---

# Current 剩餘代辦任務總表

## 1. 用途與唯一性

本表是目前唯一的跨功能 active 代辦入口。正式業務語意、owner、根事實與狀態機仍由
`01_規格基線` 擁有；本表只路由未完成工作，不複製完整規格。舊 session handoff、已完成
Work Package、功能開發 umbrella 計畫、archive、history 或 evidence 不得重新形成 current 待辦。

狀態只使用 `proposed | approved | in-progress | blocked | completed | superseded`。只有
`approved`／`in-progress` 且落在目前人工授權內的項目可施工；`blocked` 不得以假資料、直接 DB
寫入、query-string 身分或 provider 假成功繞過。

## 2. Current 執行順序

主代理優先處理營運作業；只有 write set 可隔離時才由 LINE lane 平行。2026-08-26 人工已授權全部
current lane 進入規格補齊、本機實作與受控驗收；依賴未就緒時只跳過該步，不重跑已完成 lifecycle。
這項授權包含 `lu_test_*` 必要 schema gate 與 LINE sandbox qualification，但不省略 DB change gates、精確
target／recipient／quota readback、rollback 或 provider receipt；未指定的 production／`union_db`／entry switch
與不可逆 retirement 仍不得直接執行。

| 順序 | Lane | Current IDs | 執行裁決 |
|---:|---|---|---|
| O1 | 營運儲存基礎 | `CUR-FILE-NAS-01` | 先固定 controlled-file port／discovery／reconciliation／opaque reference，再做 typed NAS Query／下載／staging；不以既有 UI mock 反推 contract。 |
| O2 | 營運契約 | `CUR-CONTRACT-01` | 儲存基礎可驗證後，完成 PDF renderer、外部平台 completion reports、最終檔案 Preview／Apply／readback。 |
| L1 | LINE 媒體與日誌 | `CUR-LINE-BABYLOG-MEDIA-01` | 重用 O1 storage capability，完成 verified LIFF staging、digest、版本與 cleanup；不得另建直接落檔路徑。 |
| L2 | LIFF 資料異動 | `CUR-LIFF-PROFILE-01`、`CUR-LIFF-E2E` | 先做 schema inventory／release gates，再補 owner persistence 與 verified-token Chrome E2E。 |
| L3 | Rich Menu／provider | `CUR-LINE-RICHMENU-01`、`CUR-LINE-RICHMENU-AUTH-01`、`CUR-LINE-PROVIDER` | 現有登入 Session 可先完成 fresh Chrome；sandbox qualification 只在精確 target／recipient／quota 回讀後執行。 |
| L4 | 客服知識 | `CUR-LINE-AI-FEEDBACK-01`、`CUR-LINE-QA` | 先補 owner／privacy／receipt 契約並唯讀盤點 QA workbook；未逐題 review 前不 publish。 |
| Z1 | 收斂後置 | `CUR-UX-01`、`CUR-UI-01`、`CUR-PERF-01` | 功能完成後做剩餘 UX Chrome、視覺與可量測效能；不覆蓋使用者 UI dirty changes。 |
| Z2 | 發布／退役 | `CUR-CLOUD-01`、`CUR-RETIRE-01` | 可開始 qualification、caller／replacement 與 rollback 準備；實際 external deploy／entry switch／retirement 需精確 target gate。 |

## 3. Current 未完成執行清單

| ID | 優先級 | 狀態 | Owner／正式規格 | 範圍與 write set | 完成條件 |
|---|---:|---|---|---|---|
| CUR-CONTRACT-01 | P0 | `approved` | Contract Signing／LINE；`00` §2.2、`21` 的 2026-08-25 amendment | 人工已授權本機實作、必要 `lu_test_*` schema gate 與 sandbox 驗收。依序完成 PDF renderer、NAS discovery/read adapter、雙方 completion reports 與最終檔案 typed Preview／Apply；不得用 raw NAS path、舊 archive URL 或 signed-return 假裝完成。 | Chrome 走完未簽 PDF 下載 → 外部狀態人工／verified LINE 回報 → 最終 PDF 指定投放區／受控上傳 Preview／Apply → metadata＋NAS object readback。provider 實送依 L3 精確 target gate。 |
| CUR-FILE-NAS-01 | P0 | `approved` | Global controlled files／各文件 owner；`00` §2.2、`17`、`18`、`20`、`21` | 人工已授權建立後端 controlled-file capability。先盤點現有 storage port／metadata／schema，再固定 discovery／reconciliation、opaque reference、清單、authenticated download、staging 與 cleanup；必要 schema 只限 `lu_test_*` 並通過完整 DB gates。 | typed Query／Preview／Apply／receipt/readback 與失敗 reconciliation 通過；NAS path 不進 UI／API／log。production mount、`union_db`、實體搬檔與 entry switch 仍須精確 target gate。 |
| CUR-LIFF-PROFILE-01 | P0 | `approved` | Client／Staff owner／LINE intake；`20` §6.1、`23` | 人工已授權 owner persistence、必要 `lu_test_*` schema release 與 Chrome E2E。須先完成 schema inventory／DB gates，再實作 owner allowlist、aggregate version、request／decision persistence；不得直接 SQL、借用身分審核流程或以 query-string `userId` 授權。 | Chrome 由 LIFF 提交 → 管理端同內容顯示 → Preview／確認／owner Apply → DB readback → LIFF／管理端一致；另驗證拒絕、stale、replay、越權與 rollback。 |
| CUR-LINE-RICHMENU-01 | P1 | `in-progress` | LINE Rich Menu／Media；`17` §3.5、`20` §6 | source／focused tests 已完成；2026-08-26 Chrome 已重新登入，原 Session blocker 解除。只補 editable menu 真 Query、合法空清單／選取 → Preview → 確認 → Apply → readback；上傳另走 O1 staging，不接舊直接上傳端點。 | Chrome 完成 fresh 正向與 drift／唯讀原因驗收；provider publication 依 L3 sandbox target gate，不得假發布。 |
| CUR-LINE-RICHMENU-AUTH-01 | P0 | `approved` | Access／LINE Rich Menu publication；`17` §4.1、`25` | authenticated enabled 使用者契約與 source tests 已完成；人工已授權 sandbox queue／provider qualification。queue 前必須回讀 exact environment、target、recipient、quota 與 worker isolation；未登入、disabled、local bypass 與 production target 仍 fail closed。 | 以 enabled `chris` Session 完成 queue → worker → provider sandbox receipt／readback；不得用 UI toast、queued 狀態或帳號名稱冒充 delivery。 |
| CUR-UX-01 | P1 | `in-progress` | Global UX／各 owner；`00`、`12`、`15` | source／focused regression 已完成；2026-08-26 Chrome 已重新登入，原 Session blocker 解除。只補 Finance fresh 錯誤路徑與 Account 唯一 enabled root 清冊正向驗收，不重改已完成頁面。 | Chrome 驗收 passed 後移入 completed；不得由顯示名稱或過期 Session 倒推 root fact。 |
| CUR-UI-01 | P2 | `approved` | React presentation；`12` 與使用者保留設計 | 人工已授權功能收斂後逐頁視覺、responsive 與 WCAG 對齊；不得恢復已放棄的營運分析／月報設計，也不得覆蓋使用者 UI dirty changes。 | 以 Chrome 與保留設計逐頁比較；功能、可達性、responsive 與 WCAG 不退步。 |
| CUR-PERF-01 | P2 | `approved` | Global／React | 人工已授權建立可重現的載入、request 數、互動延遲與 bundle baseline，再做有量測證據的改善。 | baseline、變更前後數據、回歸測試與 build 均可重現；不得只以主觀感受宣稱改善。 |

CUR-UX auth evidence correction（2026-08-26）：CUR-UX 列所稱「`chris` 非 server root fact」無有效
證據，固定撤回。該 403 發生於舊 `local_bypass` API，是預期安全行為；改以
`local_developer_session` 重啟後，既有瀏覽器 token 已失效並回 401。Account root 清冊正向驗收只能在
重新登入真實 Session 並回讀唯一 enabled root 後判定，不得由舊 403、前端顯示名稱或過期 Session 倒推。

CUR-UX Anomalies addendum（2026-08-26）：複合 disabled 缺口的 source 與 regression 已完成。正式 action
固定分類、未填理由、尚未 Preview、內容變更、提交中與結果確認中均顯示 closed 業務原因並以
`aria-describedby` 關聯；Drawer／背景篩選鎖定亦明示原因，進入追蹤編輯後不再保留 disabled「開啟」
按鈕。Anomalies focused `12 files / 133 tests`、TypeScript、focused oxlint passed；fresh Chrome 正向因
瀏覽器 Session 已失效為 `blocked`，不得以 focused test 冒充 browser passed。CUR-UX 列末「仍須續查
Anomalies 複合 disabled」由本 addendum supersede。

CUR-UX auth-session addendum（2026-08-26）：React 已以 rejected-token exact guard 處理 human request 401；
只有被拒 token 仍等於目前 Session 時才清除並卸載 protected shell。登入挑戰、403、network／5xx、不同
service token 與晚到舊 token 不受影響。focused auth／transport `5 files / 97 tests`、TypeScript passed，
focused oxlint 只有 `App.tsx` 既存 Fast Refresh export warning。Chrome 在 `local_developer_session` API 重啟後
以舊 token 觸發 401，已實際返回登入頁且不再顯示 `chris` 舊 shell，結果 `passed`。重新登入後的 Finance
正向與 Account root 清冊正向仍分別為 `blocked`／`blocked`，不由本修正冒充完成。

## 4. 已授權但仍有執行門／依賴

| ID | 狀態 | 原因 | 解鎖條件 |
|---|---|---|---|
| CUR-LIFF-E2E | `approved` | 人工已授權 `lu_test_*` 必要 schema upgrade 與 verified-token E2E；`flow_purpose` 仍須透過正式 release chain 補齊。 | 完整通過 DB change gates後再測；query-string `userId` 只能導航，不能授權。 |
| CUR-LINE-PROVIDER | `approved` | 人工已授權 LINE sandbox／免費額度內的 provider qualification；先前「不真實 push」裁決由本項 supersede。 | 執行前回讀 exact environment、target、recipient、quota 與 worker isolation；只送最小受控案例並保存 provider receipt。production recipient 不在 blanket approval 內。 |
| CUR-LINE-BABYLOG-MEDIA-01 | `approved` | 人工已授權 media lane；依賴 O1 受控 NAS staging、digest、版本、cleanup／reconciliation 與下載投影。 | O1 owner contract 通過後施工；不得用既有 direct upload、公開 URL 或 watcher discovery 冒充。 |
| CUR-LINE-AI-FEEDBACK-01 | `approved` | 人工已授權先補正式 feedback contract，再施工 Query／record／receipt、統計 owner、privacy 與 durable manual-ticket linkage。 | 正式規格完成 closure gate 後才實作；不得用 local counter 或 notification rules 假造。 |
| CUR-LINE-QA | `approved` | 人工已授權唯讀 inspect QA workbook 與建立 review queue；Excel 仍不是 SSOT，逐題答案不因 blanket approval 自動成為 approved answer。 | loader 可用後盤點；owner、category、source、exact answer 與 automation boundary 逐題 review 後才可 publish。 |
| CUR-CLOUD-01 | `approved` | 人工已授權 Cloud／worker／alert sink qualification 與部署準備。 | 實際 external deployment 前須解析隔離 project、NAS DB、operator、預算、故障注入與 rollback；不得落到 production／`union_db` 猜測 target。 |
| CUR-RETIRE-01 | `approved` | 人工已授權 caller／replacement／regression、retirement plan 與 cutover rehearsal。 | 實際 production entry switch 或不可逆 retirement 前仍須 exact target、rollback、maintenance window 與 readback gate。 |

## 5. 已完成／superseded，不得重複測試或重建資料

| ID | 狀態 | Current completion fact | 正式來源 |
|---|---|---|---|
| CUR-DATA-CENTER-01 | `completed` | canonical 側欄已收斂為「資料中心」，既有 NAS 高保真前端、工作簿匯入與原 Data Browser 組成三分頁；`data-browser`／`databrowser` 相容入口、back／forward 與 canonical active 投影均由 Chrome 實驗通過。訂單與客戶來源各載入 25 筆真 Query，無指定錯誤標記。focused 5 files／30 tests、修正後 route regression 3 files／22 tests、TypeScript／build passed；NAS 操作明示為本機預覽，真 storage capability 仍由 `CUR-FILE-NAS-01` 阻塞。 | `19` §5、NAS 正式規範 §6／§8 |
| CUR-LINE-AI-LOCAL-01 | `completed` | AI 事件工作室保留規則編輯、滿意度調查、nullable 指標槽位與人工 fallback；focused Vitest 3 passed，Chrome 實點「未解決」後明示正式流程應轉人工、客服待辦尚未接通且不假造工單。正式 feedback 仍由 `CUR-LINE-AI-FEEDBACK-01` 維持 blocked。 | `15` §17、`20` §6 |
| CUR-LINE-RICHMENU-LOCAL-PREVIEW-01 | `completed` | 手機預覽以 current server draft＋browser-memory edits 即時重繪；Chrome 已實點 URI、message、postback、rich menu switch 與 unknown target，皆只顯示 typed candidate，不開網址、不送訊息。取消後回復 persisted v5，FastAPI 僅見初始 GET、沒有 Preview／Apply／provider request。 | `17` §3.5、`20` §6 |
| DONE-LIFECYCLE-11 | `completed` | fresh 案件 `115000152` 已由 Chrome 完成 HCM 匯入至 11 步、三個結清投影全部 completed；不包含真實 LINE provider delivery。 | `15` §15 |
| DONE-STAFF-CALENDAR | `completed` | Staff `#531` 已完成不可服務期間 Preview／Apply、Matching 排除、Calendar 顯示、取消與恢復。 | `15` §15、`24` §7 |
| DONE-FINANCE-NORMAL | `completed` | 正常 ready-dispatch 已完成 Upload → Preview → Apply → terminal receipt，核銷成功且 pending 為零。 | `15` §15、`22` §13.4 |
| DONE-CONTRACT-MANUAL | `completed` | lifecycle 案已以不可變 evidence 完成雙方人工簽回；人工入口不是 LINE delivery success。 | `15` §15、`21` §§4、8 |
| DONE-LINE-IDENTITY-UI | `completed` | 身分查詢、解除 Preview／Apply、replacement／retry／manual completion 與 Chrome readback 已完成；不等於 LIFF/provider 全流程。 | `15` §17、`23` |
| CUR-SCHED-UI-01 | `completed` | 排班月曆已移除無占用日期的灰色假方塊，姓名下顯示 typed 可排班狀態；真實 assignment／lock／buffer／不可服務期間仍正常顯示，focused tests、build 與 Chrome 通過。 | `02` Calendar Read |
| CUR-ORDERS-BOARD-01 | `completed` | 代辦看板以 server-owned unfinished scope 自動讀完所有 continuation；Chrome 首次載入 94 筆、完成訂單 0 筆，無人工下一頁，分類與末頁案件搜尋正常。 | `01` §3.1.2 |
| CUR-ORDERS-LIST-01 | `completed` | 訂單管理與代辦看板共用同一 94 筆未完成集合；完成訂單 0 筆、無人工下一頁，continuation 去重與 partial failure focused tests 通過。 | `01` §3.1.3 |
| CUR-LINE-LIFF-ENTRY-DRIFT-01 | `completed` | LIFF 工作室 8 個入口已依 canonical route 對齊並由 Chrome 實點；gateway／bind／identity 共用正式身分 shell，profile_update 明確保留待建狀態且不導向假頁面。 | `20` §6；profile 正式功能仍由 `CUR-LIFF-PROFILE-01` 列管 |
| CUR-LINE-LIFF-CARDS-UI-01 | `completed` | LIFF 中央手機模擬器在桌面與窄容器均維持 360px 正常寬度；窄容器改為工作區內局部捲動，不再壓扁手機。黃色盤點說明不存在，8 個 LIFF、4 個 Flex 均保留；68 項 focused tests、build 與 Chrome 通過。 | `20` §6 |
| CUR-LINE-FLEX-01 | `completed` | 四張原始 Flex 卡已依 Eraser M1～M4 對應 current owner 並收斂 closed typed presentation contract；focused Vitest 2 passed、TypeScript passed。Chrome fresh reload 後逐卡實點，均顯示去敏文案、owner-fact blocker 與零假發送邊界，無 application error／warn。真實 projection／postback／delivery／provider 與原圖缺失需求依 26 留到 96 後，不屬本項完成範圍。 | `20` §6.2、`26` |
| CUR-LINE-SURFACE-QA-01 | `completed` | FastAPI current route 載入後，Chrome 實點三方群組顯示合法零筆狀態；發送明細關閉後晚到結果未重開 Drawer；Rich Menu 顯示 typed geometry 與 active snapshot blocker，且取消 action 不清除外觀 candidate。React 3 files／20 tests、Python 4 tests、TypeScript passed。測試 DB 零群組，群組／事件正向翻頁 `not_run`，由 focused numbered tests 覆蓋且未偽造 owner root fact。 | `20` §6 |
| CUR-DATA-01 | `completed` | 客戶資料顯示 6 個已採納 typed facts，月嫂名冊顯示 7 類服務能力；Chrome 已驗證非空與合法空值，缺值明示「尚未登錄」，無 raw survey／來源 metadata。48 項 focused tests 與 build 通過。 | `17` Case Import、`24` §3.3 |
| DONE-STAFF-RUNTIME | `completed` | Staff 三分頁 identity binding、合法空資料與 Availability runtime 已驗收。 | `15` §15 |
| DONE-OPERATIONS-REPORTS | `completed` | Operations 六頁與週報三分頁 runtime accepted，既有季度／年度報表 regression 通過。 | `15` §§15、15.1 |
| DONE-ANOMALIES-QUERY | `completed` | Anomalies detail／recovery query 為 completed-read-only；Finance correction mutation 的 runtime 完成事實另列於下列 `CUR-FIN-01`。 | `15` §1、`06` |
| CUR-FIN-01 | `completed` | 真 FastAPI＋受控 `lu_test_*` 已由 Chrome 實點完成 Finance correction Preview → 確認 → Apply → worker terminal receipt；Finance Import outbox delivery 後，來源 root fact 自動投影為 inactive／resolved，未以通用 Resolve 硬改狀態。 | `06`、`22` §13.5 |
| CUR-SCHED-CASE-01 | `completed` | Chrome 實選跨月案件 `115000008`（2026-09-05～2026-10-13）；九月與十月分別顯示完整可見區段，typed 衝突月嫂兩月皆標示整段受影響，切換／清除後無 stale 投影或 API error。 | `02` Calendar Read |
| CUR-LINE-01 | `superseded` | 過大 umbrella 已拆為 `CUR-LINE-SURFACE-QA-01`、`CUR-LINE-04` 與 Rich Menu exact tasks；已完成 Identity／LIFF entry／卡片 UI 不重開。 | `15` §17、`20` §6 |
| CUR-LINE-02 | `superseded` | 已拆為可執行的 `CUR-LINE-AI-LOCAL-01` 與契約 blocker `CUR-LINE-AI-FEEDBACK-01`，避免本機預覽被誤判成正式回饋完成。 | `15` §17、`20` §6 |
| CUR-LINE-03 | `superseded` | 已拆為 `CUR-LIFF-PROFILE-01`、`CUR-LINE-FLEX-01`、`CUR-LINE-BABYLOG-01`；三條 lane 的 owner、依賴與完成條件不再共用一個狀態。 | `20` §§5.4、6、6.1；`23` |
| CUR-LINE-BABYLOG-01 | `superseded` | 已拆為可施工的 `CUR-LINE-BABYLOG-TEXT-01` 與受 NAS 阻塞的 `CUR-LINE-BABYLOG-MEDIA-01`；純文字完成不得冒充媒體完成。 | `20` §5.4 |
| CUR-LINE-04 | `completed` | Delivery、Mobile Admin customer/review、Identity review 與 Rich Menu publication history 已使用 server numbered pagination、range/total、末頁鎖定與 stale guard。Fresh Rich Menu React `2 files / 19 tests`、Python route `12 passed`；26 筆 fixture 覆蓋第 1→2 頁。Chrome 合法空歷程 passed；零發布／零 pending review 的正向翻頁 `not_run`，未假造資料。Mobile verified Chrome 續由 `CUR-LIFF-E2E` 列管。 | `17` §§3.2、3.5；`20` §6；`15` §17 |
| CUR-LINE-RICHMENU-ACTION-01 | `completed` | 專用 typed draft Query／Preview／Apply／receipt/readback 與四種 closed action 已完成；server 以 exact revision 投影 `editable／processing／published`，唯讀版本不掛載 mutation controls，缺失或漂移固定 fail closed。Python focused 52、React 33、TypeScript 與 focused oxlint passed；fresh 唯讀 Chrome 因無合法 fixture 且需重新登入為 `not_run`，未假發布。 | `17` §3.5、`20` §6 |
| CUR-LINE-BABYLOG-TEXT-01 | `completed` | `requires_cooking=false` 的純文字寶寶日誌已完成 verified staff Query → zero-write Preview → 確認 → fresh-lock Apply → receipt／owner readback；true／unknown 顯示明確 blocker，無 media input，legacy direct POST 回 410。terminal replay 先回既有 receipt，outcome-unknown UI 禁止盲目重送。focused 53 passed、LIFF JavaScript syntax passed；verified-token Chrome 由 `CUR-LIFF-E2E` 列管為 `not_run`，照片／附件仍由 `CUR-LINE-BABYLOG-MEDIA-01` 阻塞。 | `20` §5.4 |

## 6. 維護與停止條件

- 每完成一項，先更新其 owner 正式規格的驗收狀態，再把本表該列改為 `completed`；下一輪不得因舊
  handoff、舊 Work Package 或舊測試結果重開。
- 新需求先找 current 正式 owner；已有答案直接依規格執行。只有 public contract、owner、根事實、
  schema、外部副作用或不可逆操作缺少 Authority 時才停止要求裁決。
- current 任務完成後，對應 completed／superseded 文件依 archive gate 移出 active 目錄；本表只保留
  必要完成摘要，不保存日常 logs、完整 receipt 或 evidence。
- 前端驗收使用 Chrome 實點 UI；除 provider lane 外不得以 API mutation 取代 UI。所有結果只使用
  `passed | failed | blocked | not_run`，且不得用舊測試、單一 HTTP 或子代理摘要宣稱整體完成。
- Eraser M1～M4 與四模組總覽已由
  `26_LINE四大模組Eraser流程圖轉錄與驗收基線.md` 保存為後續逐節點驗收基線。原圖尚未承接的
  需求固定為 `deferred-after-96`；不新增本表 current 工作、不中斷 96 收斂，也不得重開本表已完成項目。
