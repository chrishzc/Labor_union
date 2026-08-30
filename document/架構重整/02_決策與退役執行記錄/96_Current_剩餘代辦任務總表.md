---
doc_type: gap-register
declared_status: in-progress
date: 2026-08-25
owner: architecture-governance / product-and-domain-owners
priority_authority_date: 2026-08-30
---

# Current 剩餘代辦任務總表

> 2026-08-29 使用者曾暫停 Task 96，先完成 Task 97 repository-local architecture closeout；該前置已於
> 2026-08-30完成。2026-08-30最新人工優先序已恢復Task 96的current planning／execution priority，並固定
> 四階段主鏈：`Local DB 1003→current → LINE backend prerequisites → 其他owner backend → Anomalies closure`。
> 這項順序裁決不自動授權configured DB Apply、production／`union_db`、provider、deployment、entry switch
> 或其他外部／不可逆效果；每一階段仍須服從既有exact Authority與DB／provider gates。

## 1. 用途與唯一性

本表仍是 Task 96 未完成業務工作的唯一 register，也是current execution order的唯一owner。正式業務語意、owner、根事實與狀態機仍由
`01_規格基線` 擁有；本表只路由未完成工作，不複製完整規格。舊 session handoff、已完成
Work Package、功能開發 umbrella 計畫、archive、history 或 evidence 不得重新形成 current 待辦。

狀態只使用 `proposed | approved | in-progress | blocked | completed | superseded`。只有
`approved`／`in-progress` 且落在目前人工授權內的項目可施工；`blocked` 不得以假資料、直接 DB
寫入、query-string 身分或 provider 假成功繞過。

## 2. Current 執行順序

四個stage是序列dependency；不得把Stage 2～4派成彼此獨立的平行lane。同一stage內只有owner、write set、
acceptance與shared hot spots可隔離時才可平行。2026-08-26人工授權的規格補齊、本機實作與受控驗收仍有效；
依賴未就緒時只跳過該步，不重跑已完成lifecycle。
這項授權包含 `lu_test_*` 必要 schema gate 與 LINE sandbox qualification，但不省略 DB change gates、精確
target／recipient／quota readback、rollback 或 provider receipt；未指定的 production／`union_db`／entry switch
與不可逆 retirement 仍不得直接執行。

2026-08-26 人工補充 Authority：本機所有 DB 驗收皆為測試版本，`lu_test_*` 的建立、DDL candidate、
代表性測試資料寫入、Query／Preview／Apply、receipt readback 與 scoped cleanup 可直接執行，不需逐次請示。
本裁決不涵蓋 `union_db`、production、全庫 cleanup、replacement、`--switch` 或其他不可逆外部效果。

2026-08-28 人工以 [Agent 任務分級與交付規範](../00_Agent任務分級與交付規範.md) 取代逐 slice
`SPEC_READY／PACKAGE_READY` blanket gate。T1 與依既有契約施工的 T2 直接重用 current spec；只有
`SPEC_GAP` 才回 `spec-workshop`，只有 material execution 確需跨步驟 coverage／handoff 時才更新一份
living package。T3 邊界變更仍須 current spec、package 與人工 Authority。既有完成 evidence 不重做。

2026-08-30最新人工裁決取代上述2026-08-28歷史異常先行順序。Task 96的current主鏈固定如下；後一階段
不得以fixture、legacy writer、Anomalies-owned generic mutation或部分UI evidence繞過前一階段的owner contract：

1. **Local DB 1003→current**：先完成開發DB upgrade／resume／preserve-data與normal local startup基礎。
   fresh reset、terminal-only migration或launcher `--dry-run`都不能替代完整ordered release chain與代表資料readback。
2. **LINE backend prerequisite closure**：在穩定DB baseline上依序收斂M1 identity／dual-role persistence、
   M2 deterministic service backend的真正剩餘缺口、M3 candidate recipient／snapshot／token／delivery contract、
   M4 alert／escalation／terminal delivery source；其中`LINE-006`必須完成LINE owner-side typed Query／readback，
   不能只保留Anomalies detector或timeline projection。
3. **其他owner backend**：完成Scheduling、Government Subsidy、Staff Payables、Import／BeClass所擁有的13個
   deferred contracts。每個owner先提供自己的Query／Preview／Apply／receipt／fresh readback與lock／version語意，
   Anomalies不得代寫root mutation。
4. **Anomalies closure**：最後才消費前三階段完成的owner contracts，補detector／projection／action descriptor；
   owner mutation與durable recheck intent必須同一outer UoW提交，worker再讀fresh owner facts。完整15-code matrix
   只有在每碼都能「可發現、可修正、可重新驗證、predicate消失後issue可刪除」時才terminal。

Rich Menu provider qualification、NAS／Contract、其他LIFF、一般UX與後置工作不得插隊此四階段主鏈；既有完成
source／tests／receipts保留且不重做。前階段因exact external Authority明確blocked時，只可處理不依賴該效果、
且不會改變本主鏈語意的工作，不能把後階段標為完成。

2026-08-28 Task 96 暫時 terminal approval routing：需要 Host／sandbox 明確核准的終端機指令只提出一次
精確 request。沉默不構成 Authority，且 Host 不保證5秒內把控制權返還；若 request 回傳未批准、逾時或拒絕，
該 gate 固定記為 `BLOCKED_APPROVAL`，不重複追問，立即切到下一個不依賴該權限的 current package。使用者之後
補批准時才續跑原 gate；未執行的 command／DB／Browser evidence不得標成PASS。

2026-08-28 Task 96 completion bookkeeping gate：達到 current acceptance 時只更新實際擁有該 durable
fact 的 canonical artifact。本表只更新 owner、status、blocker 與下一個 material gate；一般 slice 不新增
tracked receipt 或重抄 commands。只有 release／migration／rollback／incident／external effect／audit 或
明確 consumer 需要時才保存 aggregate final receipt。局部 PASS 不得冒充 umbrella 完成。

| 順序 | Lane | Current IDs | 執行裁決 |
|---:|---|---|---|
| 1 | Local DB 1003→current | `CUR-LOCAL-DB-1003-CURRENT-01`、`CUR-LOCAL-DB-PORTABILITY` | upgrade／journal／resume／preserve-data／normal startup全部穩定後才交接Stage 2；任何schema新增都必須基於這個可重播baseline。 |
| 2 | LINE backend prerequisites | `CUR-LINE-MODULES-1-4-CLOSURE-01` | M1→M4 owner-side backend closure；M2只補direct evidence證明的缺口。`LINE-006` Query／readback是Stage 3前的必要gate。 |
| 3 | 其他owner backend | `CUR-ANOMALY-OWNER-BACKEND-PREREQUISITES-01` | Scheduling、Government Subsidy、Staff Payables、Import／BeClass完成13碼owner operations與fresh readback；不在Anomalies內建立replacement writer。 |
| 4 | Anomalies closure | `CUR-P0-ANOMALY-RECOVERY-01` | 只組合已完成owner contracts；補detector／projection／descriptor、mutation後fresh recheck與完整15-code terminal matrix。 |
| 5 | 其他既有Task 96 lanes | 本表其餘active IDs | 仍受各自Authority／dependency約束；不得插隊四階段主鏈。所有功能terminal後才做`CUR-UI-STITCH-UNIFICATION-01`。 |

2026-08-27 Authority closure（不新增 execution task）：服務中代班正常不要求代班月嫂獨立契約／簽回，
也不要求客戶追加確認／變更簽署；`substitution_supplement` 只是一條人工選配 evidence 路徑，缺少
它不得阻擋代班、排班 lineage 或薪資。Client Finance cancellation public result 逐筆必須帶
`direction` 與 `direction_amount_ntd`；`replace_open` 減額、`cancel_open` 固定
`no_finance_change`／0，只有已有正式收款後的 `create_refund` 才是 `refund_due`，完整 mapping
見 `04_Client_Finance_Domain.md` §3。這兩項已從 `AUTHORITY_GAP` 移除；後續只追蹤既有 owner
work packages 的 implementation／runtime／Browser evidence，不得以本段當作已完成驗收。

## 3. Current 未完成執行清單

| ID | 優先級 | 狀態 | Owner／正式規格 | 範圍與 write set | 完成條件 |
|---|---:|---|---|---|---|
| CUR-P0-HISTORICAL-IMPORT-01 | P0 | `completed` | Orders／`01`、`17` | 合法 review workbook 已在 Chrome Import UI 完成 Preview／Apply；MySQL readback 證明 `HISTORICAL-ORDER-001` review 已發布，但訂單 status／lifecycle version／assignment 均未變，符合 zero-mutation。未新增 public response、DB schema 或 migration。crash 後 durable resume 是 schema／migration 範圍，仍另立 Work Package。 | 已完成。final receipt：`03_追蹤清單與證據/evidence/2026-08-26_task96_p0_import_anomaly_staff_receipt.md`。 |
| CUR-P0-HISTORICAL-STATUS-012-01 | P0 | `completed` | Orders／`01`、`17` | 六欄 historical order source status 必須精確判定 `0→取消`、`1→完成`、`2→洽談中`；numeric `0` 不得與空白共用 fingerprint，Preview／receipt／React 必須顯示守恆 counts。不得擴張成 generic status editor 或 schema 變更。 | 25 Python、15 React、build、真 MySQL、no-auth Browser Preview／Apply與fresh Luna/high獨立複驗PASS；final receipt：`03_追蹤清單與證據/evidence/2026-08-28_historical_order_six_column_status_receipt.md`。 |
| CUR-P0-ANOMALY-RECOVERY-01 | S4 | `blocked` | Anomalies消費端＋各owner；`06`及15-code source map | PR #63已完成current identity／API／UI foundation與`LINE-004` typed consumer；Stage 4只消費Stage 2／3交付的owner Query／Preview／Apply／receipt／readback，補15-code detector／projection／action descriptor。不得在Anomalies內新增generic owner writer、claim／resolve替代路徑或直接SQL。既有H／R／C／A、HPROJ及historical remediation完成證據保留，不重跑也不作為owner prerequisite完成證明。 | Stage 1～3 terminal後，逐碼證明owner mutation與`anomaly.recheck` intent同一outer UoW、worker讀fresh owner facts、predicate成立時issue可發現，合法Apply後可重新驗證並刪除。15-code matrix全部terminal才完成；`LINE-004`目前只代表typed current consumer已完成，不外推為其餘14碼或完整remediation閉環。 |
| CUR-P0-HISTORICAL-PAYMENT-SETTLEMENT-01 | P0 | `in-progress`／`PACKAGE_READY` | Finance Import／Client Finance／Staff Payables／Anomalies／HPROJ；`04`、`05`、`06`、`16`；`PROV-20260828-historical-payment-and-owner-settlement-spec.md` | 對帳單為首要證據；只有pre-system且已採納的historical case可走owner-specific人工`paid | settled`。Client receivable、client refund、client subsidy return與staff payout分開；補助退款給客戶屬Client Finance；payment、owner settlement、Step 11不得混用。 | 2026-08-28使用者已明確授權依`PKG-HISTORICAL-PAYMENT-OWNER-SETTLEMENT`實作。完成additive DB gates、Client／Staff Q/P/A、異常頁同頁修復、later reopen、真MySQL/API/React/no-auth Browser後，再交接HPROJ驗Client terminal／Staff open時Step11 false及最終3→2→1→0；不得外推為33種異常全部完成。 |
| CUR-ANOMALY-CATEGORY-COUNT-01 | P0 | `completed` | Anomalies React；`PROV-20260828-anomaly-category-count-import-section-ux-spec.md` | 每個分類 tab 依目前 status filter 顯示數量；匯入待辦只在「全部」或「匯入資料」顯示，其他分類不得混入。 | React focused `31 passed`、production build、`git diff --check` 與 5183 no-auth 真 Browser 均 PASS；八個分類 count 會隨 status filter 同步，無關分類 DOM 不存在 import-warning section，console error 為 0。 |
| CUR-LOCAL-DB-1003-CURRENT-01 | S1 | `blocked` / `BLOCKED_DB_TEST_ENV` | Global Migration／`10`、`18`；`PROV-20260828-local-db-1003-to-current-upgrade-spec.md` | exact 1003=`matching_coordination_successor`；current repository靜態chain已延伸至1018，8/28規格的1012只是historical snapshot。既有Static release、Descriptor、read-only plan與舊Engine evidence保留，但1013～1018不得無新鮮engine evidence就外推為qualified。 | 2026-08-30 Stage 0主代理與獨立Luna High複驗均確認：current host缺少project `.venv`、DB target設定、MySQL client／Docker capability與可驗證`lu_test_*` identity，因此ordered upgrade、resume、preserve-data readback與normal startup均`NOT_RUN`，總結`DB_CHANGE_NOT_READY`。此blocker不阻擋repository-local owner contract inventory，但阻擋M1 schema／runtime completion；不得改用SQLite、mock、`union_db`或production假裝通過。 |
| CUR-P0-STAFF-QUERY-01 | P0 | `completed` | Staff／Global UX；`12`、`24` | Browser 實測初始 200 筆後載入下一頁，再搜尋唯一 marker 命中第 201 筆；cursor continuation、debounce、AbortController 與 generation stale suppression 維持既有合約。 | 已完成。final receipt：`03_追蹤清單與證據/evidence/2026-08-26_task96_p0_import_anomaly_staff_receipt.md`。 |
| CUR-LOCAL-DB-PORTABILITY | S1 | `blocked` / `BLOCKED_DB_TEST_ENV` | Global Migration／`10` §4.5 | 已移除 `lu_test_*` 名稱綁定與 shared qualification 的 reference DB／host／port／資料指紋耦合；每台機器 Apply 前仍必須建立release-scoped local dump／receipt，DDL前後驗row evidence，journal存在但原備份遺失時fail closed。 | 下一個material gate是提供具project dependencies、`APP_ENV=development`、localhost MySQL與明確`lu_test_*`目標的環境，再依序完成launcher dry-run、Python唯讀plan、ordered Apply／resume與保留資料readback；remote／production／`union_db`／MySQL system schema維持封鎖。與`CUR-LOCAL-DB-1003-CURRENT-01`共同構成Stage 1 runtime terminal gate。 |
| CUR-CONTRACT-01 | P0 | `in-progress` | Contract Signing／LINE；`00` §2.2、`21` 的 2026-08-25 amendment；`PROV-20260826-contract-external-platform-pdf-handoff-work-package.md` | final 1005 已補齊 immutable unsigned PDF purpose／checks；Scope、inventory、static、descriptor、read-only plan、fresh、preserve-data、resume 與 developer acceptance 均為 `PASS`，總結 `DB_CHANGE_READY`。canonical qualification：`validation/receipts/phase4/PROV-20260826-local-additive-qualification-contract-external-signing-successor.json`。 | DB gate 已完成；仍須以 enabled persisted human 的 fresh Chrome 完成未簽 PDF 下載 → staff/client completion reports → final PDF staging／Preview／Apply → receipt、metadata 與 NAS object readback。 |
| CUR-FILE-NAS-01 | P0 | `in-progress` | Global controlled files／各文件 owner；`00` §2.2、`17`、`18`、`20`、`21` | typed storage port、owner/version metadata、staging、Preview／Apply／replay、authenticated list／download、cleanup、五種 reconciliation outcome 與 Data Center adapter 已完成。release 1004 的 static、descriptor、fresh、含代表性舊資料 preserve-data candidate、qualification receipt 與唯讀 developer plan 全部 passed；Python 115、React 15 passed。未操作 `union_db`、production、replacement 或 `--switch`。 | local-bypass 403 負向已通過；仍須 enabled human Session 的 fresh Chrome 正向 list／download。正式 NAS mount、實體搬檔、retention、backup／restore、deployment 與 entry switch 不在本包 completion 內。 |
| CUR-LIFF-PROFILE-01 | P0 | `approved`／implementation `AUTHORITY_REQUIRED` | Client／Staff／Scheduling owner／LINE intake；`20` §6.1、`23`、`24` | 人工已裁決第一階段只做Client；Client／Staff本人一般資料、Staff媒合偏好與不可排班日期都可申請，人工確認後才寫owner root。Client建議首批9欄、條件式2欄；Staff一般資9欄與Scheduling偏好／不可排班候選已寫入`PROV-20260827-liff-profile-change-spec.md`，待逐欄裁決。不可排班強制核准的live schema／Domain缺口已立`PROV-20260827-staff-unavailability-committed-schedule-exception-spec-gap.md`。profile root/version仍待技術package；Scope／Inventory維持`BLOCKED`，其餘DB gates`NOT_RUN`，總結`DB_CHANGE_NOT_READY`。 | 先取得Client exact allowlist／enum與root/version裁決再編譯Client task pack；Staff後續獨立package。最終驗收仍包含LIFF申請→管理端diff→人工owner Apply→DB／雙端readback及拒絕、stale、replay、越權、排程衝突與rollback。 |
| CUR-LINE-RICHMENU-01 | P-after-S4 | `blocked` | LINE Rich Menu／Media；`17` §3.5、`20` §6 | editable no-auth runtime slice已通過；processing／published readonly source/schema/fixture/page gate已有partial evidence。最新優先序不把Rich Menu provider qualification視為M1～M4 backend prerequisite。 | 四階段主鏈完成後才以合法lineage續做Browser／provider qualification；不得direct seed、假發布或由publication history反推current lock。 |
| CUR-LINE-MODULES-1-4-CLOSURE-01 | S2 | `blocked` | LINE／Access／相關owner；`17`、`20`、`26_LINE四大模組Eraser流程圖轉錄與驗收基線.md`；`PROV-20260828-line-modules-1-4-closure-spec-gap.md` | Stage 1 baseline完成後依序補M1 identity／dual-role backend persistence、M2 deterministic service backend真正缺口、M3 candidate recipient／snapshot／token／delivery contract、M4 alert／escalation／terminal delivery source。只補owner-side正式契約，不復活direct DB更新或LINE平行業務狀態機。 | M1 schema如有變更須完整DB gates；M2不得重做已成立能力；M3需closed recipient snapshot與token／delivery semantics；M4須完成terminal source及`LINE-006` typed Query／readback。四模組backend regression通過後才交接Stage 3；真provider effect仍需獨立exact Authority。 |
| CUR-ANOMALY-OWNER-BACKEND-PREREQUISITES-01 | S3 | `blocked` | Scheduling／Government Subsidy／Staff Payables／Case Import／Finance Import／Orders；`01`、`02`、`05`、`14`、`16`、`17`、`24` | `SCHEDULE-006`、`SCHEDULE-002`、`SCHEDULE-003`；`GOVSUB-001`～`005`、`GOVSUB-007`；`PAYOUT-002`；`IMPORT-003`、`IMPORT-006`、`BECLASS-001`。各Domain擁有predicate、subject universe、lock/version、Query／Preview／Apply／receipt／fresh readback；Anomalies只可成為後續consumer。 | 13碼逐碼有owner-side terminal contract與負向／stale／replay／partial-failure oracle；mutation可在同一outer UoW提交durable recheck intent。禁止以navigation-only、Query-only、legacy producer或Anomalies generic mutation標完成。Stage 2 `LINE-006` gate通過後才開始，全部terminal後交接Stage 4。 |
| CUR-CONTRACT-FULL-PREVIEW-01 | P1 | `proposed`／Spec Pipeline `in-progress` | Contract Signing／Orders／Staff／Controlled Files；`21`與`db/templates`current inventory | 客戶契約與服務人員契約都必須依currently selected order替換正確訂單資料；允許current API欄位與舊版不同，但必須建立逐欄owner mapping。完整預覽不得被目前不完整契約草稿代替；兩種契約都要可下載PDF。 | 先完成SPEC_READY／PACKAGE_READY，並固定template identity/version、欄位authority、缺欄fail-closed、full-page render、PDF digest/download與visual QA。後續Module/API/React/Browser與rendered PNG全部通過才完成；未另行指定前排在LINE模組1～4後。 |
| CUR-LINE-RICHMENU-AUTH-01 | P-after-S4 | `blocked` | Access／LINE Rich Menu publication；`17` §4.1、`25` | authenticated enabled 使用者契約與 source tests 已完成；既有sandbox qualification Authority保留，但最新Task 96順序不允許它插隊四階段主鏈。 | Stage 4後才以enabled Session完成queue → worker → provider sandbox receipt／readback；執行前仍須回讀exact environment、target、recipient、quota與worker isolation，不得用UI toast或queued狀態冒充delivery。 |
| CUR-UX-01 | P1 | `in-progress` | Global UX／各 owner；`00`、`12`、`15` | source／focused regression 已完成；2026-08-26 Chrome 已重新登入，原 Session blocker 解除。後段另納入訂單資料重複顯示整理：同案例的開始／結束日期、服務人員、狀態等只保留一個主要營運摘要；`assignment_id`、`staff_id`、`sequence`、raw field name與逐欄重複的source/version改為按需展開的技術細節。不刪除owner provenance，也不將不同語意的Orders日期與Scheduling assignment日期錯誤合併。 | 完成資訊階層／重複盤點與owner語意對照；主畫面不重複顯示同一根事實，來源／版本在單一details/provenance入口仍可追溯，而語意不同的日期有明確標籤。React、responsive、WCAG與真Browser驗收PASS後才完成；不得由顯示名稱或過期Session倒推root fact。 |
| CUR-UI-01 | P2 | `approved` | React presentation；`12` 與使用者保留設計 | 人工已授權功能收斂後逐頁視覺、responsive 與 WCAG 對齊；不得恢復已放棄的營運分析／月報設計，也不得覆蓋使用者 UI dirty changes。 | 以 Chrome 與保留設計逐頁比較；功能、可達性、responsive 與 WCAG 不退步。 |
| CUR-PERF-01 | P2 | `approved` | Global／React | 人工已授權建立可重現的載入、request 數、互動延遲與 bundle baseline，再做有量測證據的改善。 | baseline、變更前後數據、回歸測試與 build 均可重現；不得只以主觀感受宣稱改善。 |
| CUR-INTERNAL-UI-UNMASKED-01 | P3 | `approved`／implementation `proposed` | Global UX／Access／各 owner；`12`、`15`、`25`；`PROV-20260827-internal-admin-ui-unmasked-display-spec-gap.md` | 已認證、enabled 且具業務權限的工會內部管理 UI 顯示 owner Query 的完整一般業務值；逐頁盤點並分批取代 Data Browser、Reports、Anomalies、LINE 管理頁及其他內部 surface 的 masking。不得用 raw payload、browser-side unmask 或跨權限 dump；外部 LINE／LIFF／自助頁、log／receipt／evidence、secret／credential／storage locator 不在本項完整值範圍。 | P0/P1 功能完成後，先完成 surface／field／permission／export/cache inventory與 task pack，再逐包通過 backend typed contract、authorization負例、bounded query／rate limit、React tests、build及 enabled-human Chrome 完整值／越權不可見驗收。 |
| CUR-UI-STITCH-UNIFICATION-01 | P-last | `proposed`／Spec Pipeline `SPEC_GAP` | Global UX／React／LINE surface owners；`PROV-20260828-stitch-ui-style-unification-spec-gap.md` | 所有前順位功能 terminal 後，盤點新增功能未套用共同 UI 風格的 surface；先用 Stitch 產生代表性設計證據，再將採用方向收斂為共用 tokens／components。LINE 預期為主要修正面，但仍須檢查全體 current React routes。不得改 owner/API 語意、用圖稿冒充 runtime，或覆蓋使用者 dirty UI changes。 | 執行時重新完成SPEC_READY／PACKAGE_READY；surface/state inventory、Stitch採用裁決、token/component mapping、desktop/mobile/WCAG與真Browser功能回歸全部PASS，且final receipt與文件狀態同一completion turn同步後才完成。固定為Task 96最後順位。 |

CUR-ANOMALY ANM-NM-B／C current correction（2026-08-27）：本段 supersede 上表對 C established
claim `live-drift` 的舊描述。`SCHEDULE-005` 已從 runtime reminder scan 移除，cutover regression
`23 passed`；六個 owner work-item target 的 exact identity／canonical version／fresh-lock 契約仍待收旂。
Staff established-first consumer 已修正，實際 producer 的 `updated` intent／`established` payload、
canonical `finance-import-row:<id>`、fresh-root、stale replay 與 fail-closed 由主代理重驗 `45 passed`；
C 改為 `in-progress`，真 MySQL old inactive／successor active／history retained 與 React history 仍 `NOT_RUN`。

CUR-ANOMALY finance MySQL addendum（2026-08-27）：三個 finance recovery code 已在真 MySQL 證明
Government 只有 owner disposition 完成後解除，Client／Staff partial recovery 都保持 active，只有 terminal
root 且 remaining=0 才從 active list 消失；receipt、outbox delivered 與 tracking status 均不構成解除條件。
1007／1008 preserve-data candidate 亦保留四張 event／matching 的舊資料且不補造 evidence。receipt：
`03_追蹤清單與證據/evidence/2026-08-27_finance_recovery_anomaly_mysql_receipt.md`。本 phase 原定的
Government／Client／Staff Luna High E4 唯讀 lanes 因 Host terminal-thread quota 未能建立，DDH 記錄 material
capability delta 後動態切回主代理單寫者序列驗證；所有實際建立的子代理仍均為 Luna High，未把未啟動 lane
算成成果。

CUR-ANOMALY 42-code necessity addendum（2026-08-27）：本輪因使用者新增「不保留系統完成後明確不應
出現的異常」驗收條件，DDH 停止舊的純漂移投影，動態重編為 Import／LINE 9、Orders／Scheduling 11、
Finance 22 三條互斥 E4 唯讀 lane；三個子代理皆明確使用 `gpt-5.6-luna`／`high`，無 nested delegation、
無 workspace writes。聯集精確 42、無重複／遺漏，native reconciliation `passed`。主代理依最新人工 Authority
校正為33個 active anomaly、7個 owner work items、1個退役 false-positive、1個 audit-only successor
occurrence；完整逐碼 durable evidence 位於
`03_追蹤清單與證據/evidence/2026-08-27_anomaly_rulebook_oracle_matrix.md`。這次確實發生一次 material
plan／operating-mode change；其 transient scratch 輸出未納入 Git，也不是後續施工依賴。
後續 migration-design phase 再以三條 Luna High E4 唯讀 lane 對照既有 owner work queue、bounded rescan、
successor/history 與候選 write set，DDH reconciliation 同樣 `passed`。結果確認 33 是已裁決的產品目標，
necessity migration Work Package 已建立；pure Domain catalog slice 已加入 lifecycle 與
`active_codes()`，精確驗證 `42 = 33 active + 7 work_item + 1 retired + 1 audit_only`，focused regression
`30 passed`。producer／既有 active alert 尚未移轉；dedicated maintenance API source 已存在並由
server-owned `SCHEDULE-005` policy 支援，但 durable execution receipt 尚未同步，因此 runtime evidence
仍為 pending receipt，不能把 catalog／API／三項 MySQL passed 當成 migration 或 developer acceptance 完成。
另發現
`line_identity_bindings` 現行單一 `line_user_id` 主鍵無法同時保存 customer＋staff 兩個 role-scoped roots，
需要 additive schema／preserve-data gates；不得以只修 SQL 顯示假裝 dual-role 已完成。

CUR-ANOMALY historical-import scope correction（2026-08-27）：完整歷史 workbook 不等於會觸發全部
33 個 active anomaly。v1 只有 status `0/1/2=取消／完成／洽談中`，沒有獨立「服務中」欄位；直接合法
產生的 canonical anomaly 只有 `HISTORICAL-ORDER-001`。只有 Scheduling owner 正式採納 assignment／
actual-service roots 後，真衝突才可能形成 `SCHEDULE-001/002/003/006`；Finance、Staff Payables、LINE、
Subsidy 等不能由 workbook 憑空產生。人工修正固定改 owner root，再 fresh recheck 自動解除；不得直接關閉
alert 或任意編輯 Orders status。完整欄位→owner→anomaly→修復入口與 acceptance mapping 位於
`03_追蹤清單與證據/evidence/2026-08-27_historical_import_anomaly_remediation_map.md`。現行 adoption
repository 直接寫 Scheduling assignment 是 `live-drift`，且 replacement／substitution／cancellation／
Scheduling conflict scenarios 尚未全部 runtime／Browser 通過，因此本項維持 `in-progress`。

本 catalog slice 原投影為 Luna High E3 exact-patch producer。第一份 proposal 將錯誤代碼分類，第二份雖修正
代碼清單但破壞 authority digest 並產生重複函式 hunk；兩份均在主代理語意／envelope gate 被拒絕且未套用。
DDH 因 repeated producer-quality delta 動態改為 E2 主代理有界 writer；最終 native `apply_patch` 耗時
`0.251s`，未觸發30秒停止門檻。這是本 phase 第二次 material operating-mode change，未把失敗 proposal
算成程式成果。

CUR-ANOMALY finance Browser／rulebook addendum（2026-08-27）：三條現有 Luna High／high 唯讀 lane 已分別
完成 finance/staff/government、LINE/access/service、scheduling/orders 規則書稽核，確認只有具 approved owner
predicate／QPA 的異常可發布自動解除；其餘維持 fail closed。進入共享 FastAPI／Vite／MySQL 後，DDH 由 E4
隔離稽核動態調整為 E2 單一 runtime writer。Browser 修正 current alert `source_domain` 與 recovery action binding
兩項 live-drift 後，三碼 Query/detail 與 exact action routing PASS；local-bypass Preview 403 負向 PASS，未繞過
persisted-human 權限。另以全新 `lu_test_task96_fin_rules_r4_20260827` 重跑規則書 lifecycle `3 passed in
8.05s`：Client／Staff partial 仍 active，Government disposition 或 recovery terminal root fresh readback 後才解除。
enabled persisted human Browser Apply 仍 `NOT_RUN`，本項維持 `in-progress`。

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

## 5. Historical order operational package status（2026-08-27）

`PROV-20260827-historical-order-operational-work-packages.md` 已完成六包編譯；2026-08-27人工已
採用B1／S1／S2，故WP-HOB-A storage與WP-HOB-C optional note的contract已回到`PACKAGE_READY`；
`SPEC_READY`不代表各bounded package已完成。下列結果只記錄本輪source／focused evidence，
不把 source green 或單層測試升格為 runtime／Browser 完成：

| Work Package | 本輪 evidence | Current status／remaining gate |
|---|---|---|
| `WP-HOB-A` Historical baseline／minimum-required-facts | domain／composition／1011 schema與engine、catalog-v2、六owner adapters及同connection composition已完成。真MySQL揭露Staff typed event/version drift後已修正；final static174，mixed owner-data與canonical-current negative readback均fresh P0/P1/P2=0。 | `in-progress`；下一步為projector repository/worker，再做API／React／adopted-positive H scenarios／真runtime。Contract legacy append-only recovery待人工核准；negative/mixed readback不能冒充人工修復閉環。 |
| `WP-HOB-B` pre-service replacement successor | `PKG-RPRE-OWNER-SUCCESSOR`已completed：domain／QPA／1012、concrete repository、真MySQL Apply/replay、Matching successor與exact readback均PASS。pure projector、typed API、production loader與React source亦已`completed`；fresh R-01、R-02、R-03、R-04及actual-service referral no-auth API／真Browser已PASS。R-01證明candidate history不變且無plan／commitment／assignment；R-03同UoW取消waiting lock、保留commitment/signback history、complete owner readback與staff mutex lock order均有正式證據。 | `in-progress`；只剩R-07。Matching `no_candidate`確認command＋既有RPRE綁定已獲人工核准並由Spec Pipeline編為`PACKAGE_READY`，進入實作／驗證。 |
| `WP-HOB-C` service-in substitution／optional supplement | 核心「無新契約／簽回亦不阻擋代班」gate `28 passed`；S1／S2已裁決 | `in-progress`／`DB_CHANGE_NOT_READY`；note schema／release／API／runtime尚未施工；note僅為備註，不影響substitution／Scheduling／Payroll。 |
| `WP-HOB-D` cancellation direction／reconciliation | cancellation explicit `direction` source candidate：Python `36`；authenticated receipt GET新增`3 passed`；React receipt-first reconciliation主代理重驗`56 passed`且build PASS | `in-progress`；既有receipt table現可用同Idempotency-Key唯讀查詢，200回讀成功不重送、404才使用原payload／key重送，其他錯誤維持unresolved且不POST。case-scoped Anomalies仍缺canonical多對多case binding，已另立`PROV-20260827-anomaly-case-binding-read-model-spec-gap.md`；真MySQL／enabled-human Browser均`NOT_RUN`，尚不能宣稱三分支或跨頁reconciliation完成。 |
| `WP-HOB-E` completion owner-terminal closure | canonical DB `lu_test_task96_scenarios_20260827` 的`HOB-F04-ROUTE-A-001`已由root fixture與正式Q/P/A command lineage建立；MySQL/API回讀Step 11 completed、historical alerts completed、active alerts 0。final Python `141 passed`、React `20 passed`、build PASS；r4 fresh Luna High verifier與DDH reconciliation PASS；no-auth Browser正向與console 0。 | `completed`；OrderTracker預設保持unfinished，明確勾選「包含已完成案件」後才同步載入all-scope摘要／stage projection並進入terminal HOB-E。未直接植入derived roots，未操作`union_db`、DDL／migration、provider或Graphify。 |
| `WP-HOB-F` versioned scenario／cross-page UI | F-04 manifest／root fixture／expected oracle／formal runner與Browser closure已完成 | `in-progress`；H-03＋A-02、R／C及其他安全情境仍須分開執行，F-04不代替剩餘scenario acceptance。 |

> 2026-08-27 最新裁決覆寫上表WP-HOB-C舊述：B1／S1／S2已採用；
> `substitution_note`及method僅是不影響流程的備註。未填、取消、寫入或附件archive
> 失敗都不得阻擋substitution、Scheduling lineage或Payroll。contract已`PACKAGE_READY`；
> schema／release／API／runtime仍`NOT_RUN`，總結維持`DB_CHANGE_NOT_READY`。
>
> WP-HOB-E最新執行證據：Orders/Scheduling adapter主代理重驗`35 passed`，Client Finance adapter
> 主代理重驗`37 passed`，並在真MySQL兩案回讀完整lineage／無blocker。Orders/Scheduling已改為
> 單statement snapshot／真event與generation version lineage，而且legacy replaced/cancelled不污染current official service。
> 現有`lu_test_*`無completed正向案例，且不得直接植入派生根；正式command鏈又缺少已證明可重播的
> matching accepted decision→commitment→waiting lock轉換與deposit facts，因此Orders/Scheduling真MySQL
> positive維持`NOT_RUN/BLOCKED`。Staff Payables正式規格只要求case-scoped current readback，未要求持久化
> case root或scalar version；必要性稽核排除`MAX(version)`與無證據的`SP1-M`過度施工，改以`SP2-Q`
> typed source vector為最低必要方案，2026-08-27已獲人工確認；`SP1-M`不施工。SP2-Q internal
> oracle／Query／Staff adapter先形成source candidate，r15 fresh Luna High verifier已通過SP2-Q；其後
> API／fresh projector／React完成。r16跨層verifier再找到Scheduling known gap被壓成泛化unavailable，及
> JavaScript number無法lossless承載signed BIGINT version兩項缺陷；主代理修正為精確Scheduling
> owner／referral與decimal-string transport contract。最終focused Python `137 passed`、React `23 passed`、
> build PASS，r17 fresh Luna High verifier PASS。no-auth development Browser負向驗收PASS；正式command
> F-04正向runtime／Browser因缺少可重播同案根事實維持`blocked`，整包仍`in-progress`。

> 2026-08-27 final supersession：上段保留當時r17 blocker歷史，不再代表current。canonical
> `lu_test_task96_scenarios_20260827`已由`HOB-F04-ROUTE-A-001` root fixture與正式Q/P/A command
> lineage建立同案terminal roots；final Python 141、React 20、build、MySQL/API、no-auth Browser與r4
> fresh Luna High／DDH reconciliation均PASS。WP-HOB-E current為`completed`；WP-HOB-F僅F-04 slice完成。

相鄰既有 owner slice `CLIENTREFUND-001` 維持 static source closure、runtime `NOT_RUN`。`PAYOUT-001` 已由
canonical `PAYOUT-001-EXACT-001` 完成 no-auth 真 MySQL／8016 API／5183 Browser、typed DurableJobWorker、
fresh owner readback與scanner recheck；原 fingerprint predicate false/resolved，active count 6→5。真runtime
另修正React StrictMode永久loading與60-bit bank version跨JavaScript精度漂移，final receipt見
`03_追蹤清單與證據/evidence/2026-08-27_payout_overdue_anomaly_remediation_receipt.md`。這仍不等於
Task 96 或33-code target全部完成，不以單一scenario外推。

> 2026-08-27 Spec Pipeline parallel calibration：Rich Menu processing/published readonly slice 已收斂為
> `SPEC_READY/PACKAGE_READY`，僅能使用合法既有publication lineage做唯讀Browser驗收；不得直接seed derived
> publication state。historical H/R/C/A 可分成H baseline、historical remediation drift、service-before
> replacement、service-in substitution、C core（排除C-05）、A safety與versioned scenario packages；C-05仍
> 等待ACB1。`PAYOUT-002`因late-event disposition、signed delta branches與completion predicate未裁決，
> `PAYOUT-003`因bank-master mutation owner、branch policy與closure oracle未裁決，兩者皆維持
> `AUTHORITY_REQUIRED`，不得進入implementation。

> Historical review remediation 狀態校正：enabled persisted-human Browser 正向仍是尚未完成的
> acceptance；developer local replacement／`--switch` 不在該工作包 effect ceiling，不是其
> completion gate。本裁決覆寫上表 `CUR-P0-ANOMALY-RECOVERY-01` 舊述中把兩者並列的部分。

本輪 DDH 曾依 authority、write-set 隔離、能力與驗證結果動態調整執行模式；所有實際建立的子代理均為
`gpt-5.6-luna`／`high`。該操作模式變更只保存為 execution evidence，不改寫 package scope、completion
gate 或人工裁決。

本輪後續序列再新增兩條互斥 Luna High lane：一條完成 WP-HOB-E read-only cross-owner Query，一條處理
cancellation outcome-unknown／late-response UI guard；另派 IMPORT-006 唯讀 verifier 核對 canonical
`batch_version`。嘗試新增 P0 register freshness verifier 時遭 Host thread quota 拒絕，DDH 立即重投影為
主代理唯讀校正，未把未啟動 lane 算成成果，也未增加共享文件 writer。

2026-08-27再次依material facts動態重投影：HOB-E原分成Orders/Scheduling、Client Finance、
Staff Payables三個互斥writer lane。Orders/Scheduling保持implementation candidate；Client Finance在真MySQL
發現current ledger enum／reducer integrity差距後，交回原owner writer於同一兩檔內補強；Staff Payables因
多staff case-level version／lineage無Authority而從writer降為spec verifier，零檔案修改。ACB1也由generic
schema candidate拆成definition-specific短期resolver盤點與通用binding長期裁決。所有子代理仍為
`gpt-5.6-luna`／`high`，沒有共享write set或競寫。

2026-08-27 Staff Payables spec verifier依`00_Global_共同契約.md`、`03_Payroll_Domain.md`、
`16_Staff_Payables與Client_Refund正式規格.md`與HOB controlling spec完成必要性反證：case-scoped current
readback為`MUST`；新持久化case settlement root、新case scalar version及其全域backfill均
`NOT_JUSTIFIED`。DDH因此把剩餘lane由`SP1-M` schema writer重投影為`SP2-Q` typed-contract writer；
2026-08-27人工已確認此方案。open／partially recovered overpayment保留獨立異常，但原obligation
已歸零且Staff owner terminal lineage完整時，不得單因recovery未結清而阻擋Step 11。一般案件仍由exact
payout/allocation形成該lineage；只有符合`PROV-20260828-historical-payment-and-owner-settlement-spec.md`
資格的pre-system historical case，才可由approved owner-specific historical event形成，且不得推定Client端也已結清。

2026-08-27 SP2-Q execution在DDH下依material verifier結果兩次由E3 verification退回E2單一整合writer：
第一輪補齊typed source kind、bank evidence、projection own version、target-bounded return／reversal、
recovery sources/events與material fingerprint；第二輪再補Orders root fingerprint、`UNAVAILABLE`分類、
嚴格amount/version/hash/reversal shape及deterministic recovery lineage。所有實際子代理均為
`gpt-5.6-luna`／`high`且零寫入。修正版主代理證據為`78 passed`＋真MySQL唯讀SQL解析PASS；
為避免把修正前review升格成final acceptance，fresh post-fix independent verifier明列為下一session首要gate。

2026-08-27 config 回讀確認 `max_concurrent_threads_per_session=5`，但本次Host實際提供的
active concurrency仍為4 slots（含主代理）；DDH以runtime capability為真，不把max config當已啟用5個
concurrent workers。Orders／Scheduling與case anomaly readback候選經主代理／E3複驗分別發現
legacy replaced assignment false-blocker，以及BusinessClock source-version／跨SELECT snapshot的P0 false-clean
風險；兩條lane均交回原Luna High writer於原exclusive write set修正，主代理不競寫。

## 6. 已完成／superseded，不得重複測試或重建資料

| ID | 狀態 | Current completion fact | 正式來源 |
|---|---|---|---|
| CUR-LOCAL-START-REACT-01 | `completed` | Windows／Unix 標準本機 launcher、唯讀 preflight 與 GET-only smoke 已收斂為 FastAPI `8000`＋React/Vite `5173`，不再啟動 Streamlit 或等待 8501。GitHub source archive 的 Windows launcher 固定保存 CRLF，避免舊版 `cmd.exe` 無法解析 `CALL` label。focused launcher tests `26 passed`、blocking flake8 `0`；archive-equivalent Windows dry-run ready，實際 smoke 僅建立 `api`／`react`，`/admin/` ready、relative `/api` 200，結束後 8000／5173 owned process 均清理。Legacy Streamlit source 未在本包刪除。 | `19` §6；`scripts/launchers/README.md` |
| CUR-LOCAL-DB-1003 | `completed` | `scripts/launchers/update_local_database.bat` 已對精確回讀的 `lu_test_dataset_contract_signing_v4` 套用 qualified schema-only Release 1003；25/25 statements 完成，post-schema 為 exact。升級前 dump 保留，升級後 `orders` 仍為 151 筆且 stable fingerprint 相同；未使用 `union_db`、replacement、`--switch` 或 production target。 | `10` §§4.1、4.5、7；qualification receipt `PROV-20260826-local-additive-qualification-matching-coordination-successor` |
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

## 7. 維護與停止條件

- 每次 completion 只更新真正改變的 canonical owner；本表保留 owner、status、blocker 與下一個 material
  gate。只有全部 acceptance 都有 current evidence 才把整列改為 `completed`；局部 PASS 只更新 living
  package 或本列摘要，不另建逐 slice spec／package／receipt。
- 新需求先找 current 正式 owner；已有答案直接依規格執行。只有 public contract、owner、根事實、
  schema、外部副作用或不可逆操作缺少 Authority 時才停止要求裁決。
- current 任務完成後，對應 completed／superseded 文件確認無 current consumer 後移出工作樹；本表只保留
  必要完成摘要，不保存日常 logs、完整 receipt 或 evidence。
- 前端驗收使用 Chrome 實點 UI；除 provider lane 外不得以 API mutation 取代 UI。所有結果只使用
  `passed | failed | blocked | not_run`，且不得用舊測試、單一 HTTP 或子代理摘要宣稱整體完成。
- Eraser M1～M4 與四模組總覽已由
  `26_LINE四大模組Eraser流程圖轉錄與驗收基線.md` 保存為後續逐節點驗收基線。原圖尚未承接的
  需求固定為 `deferred-after-96`；不新增本表 current 工作、不中斷 96 收斂，也不得重開本表已完成項目。
