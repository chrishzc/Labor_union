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

主代理優先處理營運作業；只有 write set 可隔離時才由 LINE lane 平行。某一步因 Chrome、schema、NAS
target 或 provider 授權阻塞時，只跳過該步並繼續下一個已核准且獨立的工作，不重跑已完成 lifecycle。

| 順序 | Lane | Current IDs | 執行裁決 |
|---:|---|---|---|
| L1 | 可隔離 LINE | `CUR-LINE-RICHMENU-ACTION-01`、`CUR-LINE-RICHMENU-LOCAL-PREVIEW-01` | 先消除用 label 猜 action 的 live-drift，再做 typed action／message 編輯與本機互動預覽測試；主代理仍是共享 Rich Menu 檔案唯一 writer。 |
| L2 | 可隔離 LINE | `CUR-LINE-04` | Delivery closure → Identity → Rich Menu publication → Mobile Admin continuation；每一段完成才往下。 |
| L3 | 可隔離 LINE | `CUR-LINE-SURFACE-QA-01`、`CUR-LINE-FLEX-01` | 只補未完成 caller／Flex design preview，不重驗已完成 Identity、LIFF entry 或卡片 responsive。 |
| L4 | 可隔離 LINE | `CUR-LINE-RICHMENU-01`、`CUR-LINE-AI-LOCAL-01` | action 穩定後再做背景／名稱；AI 先完成零寫入本機預覽，正式 feedback 另依 blocker。 |
| L5 | 需外部條件 | `CUR-LINE-RICHMENU-AUTH-01`、`CUR-LIFF-E2E`、`CUR-LINE-PROVIDER` | 依序等待真 Admin Session、schema upgrade、provider sandbox／額度授權；不得用 bypass、假 token 或 queue 冒充完成。 |
| H1 | 等待使用者設計 | `CUR-FILE-NAS-01`、`CUR-DATA-CENTER-01` | M2 依 2026-08-25 人工裁決暫停；等待使用者完成介面與功能細項設計後再重開，不繼續 adapter、API、UI 或測試。 |
| H2 | 受 M2 影響 | `CUR-CONTRACT-01`、`CUR-LIFF-PROFILE-01` | 契約檔案流程依賴 M2；資料修改流程仍等待 persistence/schema capability。條件未解除前不施工、不改 DB。 |
| Z1 | 後置 | `CUR-UX-01`、`CUR-UI-01`、`CUR-PERF-01` | P0/P1 功能收斂後再做全頁雜訊、視覺與量測效能；不覆蓋使用者 UI dirty changes。 |

## 3. Current 執行清單

| ID | 優先級 | 狀態 | Owner／正式規格 | 範圍與 write set | 完成條件 |
|---|---:|---|---|---|---|
| CUR-CONTRACT-01 | P0 | `blocked` | Contract Signing／LINE；`00` §2.2、`21` 的 2026-08-25 amendment | current renderer 只產生 XLSX；既有 `storage_key`／metadata 尚未驗證為受控 NAS logical object reference／digest／version adapter，事件也缺外部平台 completion report。先完成 PDF renderer、NAS discovery/read adapter 與 typed reports；若現有 schema 不足才另立 DB Work Package。本次禁止 DDL／migration，不得用 raw NAS path、舊 archive URL 或 signed-return 假裝完成。 | 解鎖後：Chrome 走完未簽 PDF 下載 → 外部狀態人工／verified LINE 回報 → 最終 PDF 指定投放區／受控上傳 Preview／Apply → metadata＋NAS object readback。現有人工補登仍為 completed；provider push 另行列管。 |
| CUR-FILE-NAS-01 | P0 | `blocked` | Global controlled files／各文件 owner；`00` §2.2、`17`、`18`、`20`、`21` | 依 2026-08-25 人工裁決暫停 M2，等待使用者完成介面與功能細項設計後再重新確認 scope。現有本機草稿原樣保留但不視為已採用或完成；不再擴寫 adapter、API、UI 或測試，也不 mount、不搬檔、不碰 production、DDL／migration。 | 使用者提供設計後，重新核對 storage port、discovery／reconciliation、opaque reference、metadata、清單／下載與各 Domain owner，再另行恢復執行及驗收。 |
| CUR-DATA-CENTER-01 | P1 | `proposed` | Global React entry／controlled files／Case Import／Data Browser；`12` §3.4、`19` §5 | 規劃將側邊欄「資料匯入」改名為「資料中心」，內含 `NAS 檔案`、`資料匯入`、`數據瀏覽` 三分頁；NAS 只先定義資料夾與其中檔案名稱的簡單 read-only 投影，不另列層級、用途、案件／人員、版本、大小、更新時間或異常狀態。舊 `data-browser` 保留為相容深連結；不得複製或刪減既有匯入／瀏覽功能。介面版型與互動等待使用者設計，本次不改 React route/page/API。 | 使用者確認介面設計後，另將本項推進為 `approved` 並固定 UI write set／acceptance；實作時需驗證三分頁、舊 deep link、登入後目標、back／forward，以及既有匯入 Preview／Apply與數據瀏覽 Query 無退步。 |
| CUR-LINE-SURFACE-QA-01 | P0 | `in-progress` | LINE Integration／Customer Service；`17`、`20`、`23` | `CUR-LINE-01` 的 exact successor，只盤點／補齊尚未完成的 React tab、Mobile Admin 與 LIFF typed caller；已完成 Identity UI、LIFF entry 與卡片 responsive 不重跑。只改對應 client／page／tests，不碰 provider、DB schema、entry switch。 | 未完成入口逐一有 typed Query 或明確業務 blocker；mutation 維持 Preview → 確認 → Apply → receipt/readback；Chrome 0 假空資料、靜默隱藏、「後端未提供／未開放／API 錯誤／無法載入」。 |
| CUR-LINE-AI-LOCAL-01 | P1 | `in-progress` | Customer Service／LINE UI；`15` §17、`20` §6 | 保留 AI 事件工作室規則編輯、滿意度調查、指標槽位與人工 fallback；正式 feedback／catalog contract 未完成前只做 zero-write browser-local deterministic preview，不硬編統計、不建立假工單、不保存正式回饋。 | 原設計控制均可到達；本機預覽明示未保存，未解決固定顯示轉人工語意。正式 feedback Query／record／receipt 由 `CUR-LINE-AI-FEEDBACK-01` 另行解鎖。 |
| CUR-LINE-FLEX-01 | P1 | `approved` | LINE Integration／UI；`20` §6 | 補齊 4 個既有 Flex 資產的去敏 typed design preview；保留原設計，不接 raw provider payload、demo token 或 client identity。 | 四個 Flex 均可由 strict DTO 顯示與錯誤分流；缺 owner fact 明示 blocker，focused tests／build／Chrome 通過。 |
| CUR-LINE-BABYLOG-01 | P1 | `approved` | Scheduling／LINE file transport；`00` §2.2、`20` §5.4 | 寶寶日誌文字、附件與餐食照片的 verified Staff LIFF staging cleanup、Preview／Apply／receipt/readback；檔案 bytes 依賴 `CUR-FILE-NAS-01`，Scheduling 保留 owner。不得用 direct POST、公開 URL 或 watcher discovery 冒充完成。 | 依 `requires_cooking` 與正式服務日驗證；合法提交建立唯一日誌／附件版本，失敗 cleanup 可重試且不留假完成；UI 只顯示檔案投影，Chrome verified-token E2E 仍依 `CUR-LIFF-E2E`。 |
| CUR-LIFF-PROFILE-01 | P0 | `blocked` | Client／Staff owner／LINE intake；`20` §6.1、`23` | 正式 Query／Preview／Apply／receipt／owner readback 契約已裁決；目前缺 owner allowlist／aggregate version 的 live implementation、request／decision persistence capability，且現有 schema 未證明足夠。本次禁止 DDL／migration，不得直接 SQL、借用身分審核流程或以 query-string `userId` 授權。 | 解鎖後：Chrome 由 LIFF 提交 → 管理端同內容顯示 → Preview／確認／owner Apply → DB readback → LIFF／管理端一致；另驗證拒絕、stale、replay、越權與 rollback。 |
| CUR-LINE-04 | P1 | `in-progress` | LINE UI adapters；`17` §3.2、`20` §6、`15` §17 | 依 Delivery closure → Identity → Rich Menu publication → Mobile Admin customer/review 完成 server-side pagination。Delivery UI／focused tests 已進行中，仍須全組 regression／build／Chrome；後續不得以固定上限或記憶體切片取代。 | 每段 Chrome 可前後翻頁且 filter reset 正確，末頁鎖定與 server total/range 一致；stale response 不覆蓋新頁，不顯示 raw cursor／fingerprint／idempotency 雜訊；focused tests 與 build 通過。 |
| CUR-LINE-RICHMENU-01 | P1 | `approved` | LINE Rich Menu／Media；`17` §3.5、`20` §6 | Rich Menu 工作台新增背景圖與按鈕顯示名稱的 draft 編輯；保留 action／熱區／audience，修改建立新 revision，不能覆寫 processing／published snapshot，也不能在草稿階段直接呼叫 provider。 | Chrome 編輯背景與名稱後，同 revision 預覽正確；Preview → 確認 → Apply 產生 committed definition／receipt，stale revision fail closed。provider publication／push 本次 `not_run`，不得假造成功。 |
| CUR-LINE-RICHMENU-ACTION-01 | P0 | `in-progress` | LINE Rich Menu／Media；`17` §3.5、`20` §6 | 保留既有手機模擬點擊畫面，新增 closed typed action 編輯。live audit 已確認 React adapter 丟棄 action、頁面改用 label／順序猜測；generic configuration Apply 也未綁 Preview fingerprint。須建立專用 typed draft Query／Preview／Apply／receipt/readback，重用既有 configuration owner／repository。編輯範圍包含 URI／canonical LIFF target、message text、postback data、rich menu alias；kind 切換清除不相容欄位。不碰 provider publication、DB schema 或 entry switch。 | Chrome 修改四種合法 action 後，手機點擊投影與 server readback 一致；message 顯示並保存操作者輸入的實際候選訊息，按鈕改名不改 action/message。非法 scheme／target／長度、stale、fingerprint mismatch、processing／published 均 fail closed；Preview → 確認 → Apply → receipt/readback，focused tests／build 通過，provider `not_run`。 |
| CUR-LINE-RICHMENU-LOCAL-PREVIEW-01 | P0 | `approved` | LINE Rich Menu UI；`17` §3.5、`20` §6 | 為使用者新增的手機本機互動預覽建立 focused／Chrome 測試。預覽以 current server draft＋browser-memory edits 即時重繪；點擊只模擬 typed target／message，不寫 DB、不建立 delivery/publication、不呼叫 provider，也不取代 server Preview。只改 Rich Menu UI/tests，與 action task 由同一 writer 序列整合。 | 測試背景／名稱／四種 action／message 編輯立即反映、取消還原、改名不改 action、kind 切換清欄位、未知 target 明示 blocker；監測 local edit/click 為零 mutation request。server Preview 後仍需確認 Apply，Apply readback 與手機畫面一致；Chrome 0 假成功／API error，provider `not_run`。 |
| CUR-LINE-RICHMENU-AUTH-01 | P0 | `in-progress` | Access／LINE Rich Menu publication；`17` §3.5、`25` | canonical capability mapping 與 React 提示已修正；本機免驗證模式現在明確說明不可發布，不冒充 root。仍須以真實已登入且 enabled 的管理員 Session 驗證 Preview／queue；不得以帳號名稱硬編放行。 | focused RBAC 驗證 canonical 管理員可進 publication flow、無權角色仍為 403；Chrome 真實 Session 不再誤判。本機 bypass 的零寫入 Preview 已通過；queue 僅能在 provider worker 隔離時驗證，真實 provider publication 仍依 `CUR-LINE-PROVIDER`。 |
| CUR-UX-01 | P1 | `in-progress` | Global UX／各 owner；`00`、`12`、`15` | 全頁盤點並移除一般操作者不需要的 fingerprint、version、cursor、idempotency 與 provider/debug 雜訊；保留必要業務原因、receipt 摘要與可復原入口。 | Chrome 逐頁無技術雜訊、靜默隱藏或只有 disabled 控制；合法鎖定具明確業務原因，進階稽核資料不進一般畫面。 |
| CUR-UI-01 | P2 | `proposed` | React presentation；`12` 與使用者保留設計 | 功能流程完成後才做全頁視覺對齊；不得恢復已放棄的營運分析／月報設計，也不得覆蓋使用者 UI dirty changes。 | 以 Chrome 與保留設計逐頁比較；功能、可達性、responsive 與 WCAG 不退步。 |
| CUR-PERF-01 | P2 | `proposed` | Global／React | 先定義可重現的載入、request 數、互動延遲與 bundle 基準，再做有量測證據的效能改善。 | baseline、變更前後數據、回歸測試與 build 均可重現；不得只以主觀感受宣稱改善。 |

## 4. Blocked／deferred，不得繞過

| ID | 狀態 | 原因 | 解鎖條件 |
|---|---|---|---|
| CUR-LIFF-E2E | `blocked` | 真實 LIFF 登入已到 server，但 development DB 的 `flow_purpose` 尚未包含正式 `staff_self_service`；目前禁止 schema／migration／DDL。 | 另行取得本機 schema upgrade 授權並通過 DB change gates，再以 verified token 重跑；query-string `userId` 只能導航，不能授權。 |
| CUR-LINE-PROVIDER | `blocked` | 使用者要求先不真實 push，以免消耗免費額度；production/provider side effect 亦未授權。 | 使用者另行指定 sandbox delivery 範圍與額度後，只測 provider lane；不得重跑已完成本機 UI。 |
| CUR-LINE-AI-FEEDBACK-01 | `blocked` | 滿意度正式 Query／record／receipt、統計 owner 與 durable manual-ticket linkage 尚無核准 public contract；`CUR-LINE-AI-LOCAL-01` 只能零寫入預覽。 | 先在 `20` 補齊 owner、root facts、typed Query／Preview／Apply、receipt/readback、privacy 與人工 fallback 並取得人工確認；不得用 local counter 或 notification rules 假造。 |
| CUR-LINE-QA | `blocked` | QA workbook loader runtime／owner review 尚未完成；來源 Excel 不是 SSOT。 | loader 可用且 owner、category、source、approved answer 經人工確認後，另立 exact Work Package。 |
| CUR-CLOUD-01 | `proposed` | Cloud Run、Worker supervision、Access production cutover、external alert sink 均延後。 | 指定隔離 project／NAS DB、operator、預算、故障注入與 rollback scope，並另行核准。 |
| CUR-RETIRE-01 | `blocked` | production、entry switch、legacy retirement 與 Phase 6C 不在目前授權。 | 完成逐入口 caller／replacement／regression，取得 exact retirement/cutover 授權。 |

## 5. 已完成／superseded，不得重複測試或重建資料

| ID | 狀態 | Current completion fact | 正式來源 |
|---|---|---|---|
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
| CUR-DATA-01 | `completed` | 客戶資料顯示 6 個已採納 typed facts，月嫂名冊顯示 7 類服務能力；Chrome 已驗證非空與合法空值，缺值明示「尚未登錄」，無 raw survey／來源 metadata。48 項 focused tests 與 build 通過。 | `17` Case Import、`24` §3.3 |
| DONE-STAFF-RUNTIME | `completed` | Staff 三分頁 identity binding、合法空資料與 Availability runtime 已驗收。 | `15` §15 |
| DONE-OPERATIONS-REPORTS | `completed` | Operations 六頁與週報三分頁 runtime accepted，既有季度／年度報表 regression 通過。 | `15` §§15、15.1 |
| DONE-ANOMALIES-QUERY | `completed` | Anomalies detail／recovery query 為 completed-read-only；Finance correction mutation 的 runtime 完成事實另列於下列 `CUR-FIN-01`。 | `15` §1、`06` |
| CUR-FIN-01 | `completed` | 真 FastAPI＋受控 `lu_test_*` 已由 Chrome 實點完成 Finance correction Preview → 確認 → Apply → worker terminal receipt；Finance Import outbox delivery 後，來源 root fact 自動投影為 inactive／resolved，未以通用 Resolve 硬改狀態。 | `06`、`22` §13.5 |
| CUR-SCHED-CASE-01 | `completed` | Chrome 實選跨月案件 `115000008`（2026-09-05～2026-10-13）；九月與十月分別顯示完整可見區段，typed 衝突月嫂兩月皆標示整段受影響，切換／清除後無 stale 投影或 API error。 | `02` Calendar Read |
| CUR-LINE-01 | `superseded` | 過大 umbrella 已拆為 `CUR-LINE-SURFACE-QA-01`、`CUR-LINE-04` 與 Rich Menu exact tasks；已完成 Identity／LIFF entry／卡片 UI 不重開。 | `15` §17、`20` §6 |
| CUR-LINE-02 | `superseded` | 已拆為可執行的 `CUR-LINE-AI-LOCAL-01` 與契約 blocker `CUR-LINE-AI-FEEDBACK-01`，避免本機預覽被誤判成正式回饋完成。 | `15` §17、`20` §6 |
| CUR-LINE-03 | `superseded` | 已拆為 `CUR-LIFF-PROFILE-01`、`CUR-LINE-FLEX-01`、`CUR-LINE-BABYLOG-01`；三條 lane 的 owner、依賴與完成條件不再共用一個狀態。 | `20` §§5.4、6、6.1；`23` |

## 6. 維護與停止條件

- 每完成一項，先更新其 owner 正式規格的驗收狀態，再把本表該列改為 `completed`；下一輪不得因舊
  handoff、舊 Work Package 或舊測試結果重開。
- 新需求先找 current 正式 owner；已有答案直接依規格執行。只有 public contract、owner、根事實、
  schema、外部副作用或不可逆操作缺少 Authority 時才停止要求裁決。
- current 任務完成後，對應 completed／superseded 文件依 archive gate 移出 active 目錄；本表只保留
  必要完成摘要，不保存日常 logs、完整 receipt 或 evidence。
- 前端驗收使用 Chrome 實點 UI；除 provider lane 外不得以 API mutation 取代 UI。所有結果只使用
  `passed | failed | blocked | not_run`，且不得用舊測試、單一 HTTP 或子代理摘要宣稱整體完成。
