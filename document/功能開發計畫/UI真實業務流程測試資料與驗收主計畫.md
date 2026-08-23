# UI 真實業務流程測試資料與驗收主計畫

---
status: approved
priority: P0-planning
owner: product-and-domain-owners
initiative: ui-real-business-flow-validation
updated: 2026-08-12
---

## 0. 人工確認紀錄

- 人工確認日期：2026-08-12
- 確認內容：本主計畫的真實業務生命週期、Part 0～16 邊界與順序、文件先行 gate、
  infrastructure readiness audit、現有 33 案 inventory 方法及主計畫 acceptance。
- 核准效力：可依第 12 節順序撰寫各 Part 的 proposed 規格文件與執行唯讀 inventory／readiness
  audit。
- 尚未授權：production code、schema、migration、seed、pytest、validation DB 重建或修正、
  production DB、外部 LINE、銀行／付款／補助操作、部署、cutover、Git stage／commit／push。
- 後續 gate：每個 Part 仍須獨立完成規格、readiness matrix、proposed write set 與 acceptance，並取得
  該 Part 的人工確認後，才能建立可執行 Work Package 或開始 mutation。

## 1. 目的

本計畫建立一套可依真實案件生命週期操作、重建及稽核的 UI 驗收資料。測試不得只按頁面、
資料表或既有八個 `UI-*` receipt 分組，而必須從來源資料進入系統開始，依業務事件順序走到
配對、簽約、資料變更、服務執行、銀行流水、帳務核銷、月嫂應付、政府補助與結案。

本文件是 initiative 主計畫，不取代 Global／Domain 正式規格。每個 Part 必須先完成自己的
business scenario、契約、資料矩陣及驗收文件，取得人工確認後，才能進行 production code、
schema、seed、pytest 或資料庫 mutation。

## 2. Business scenario

管理人員需要在隔離的 validation database 中，以與日常營運相同的 UI 和 typed API 完成：

```text
匯入客戶／案件／月嫂來源資料
→ 檢查匯入結果與修復無效資料
→ 建立正式案件、訂單條款及月嫂可服務能力
→ 搜尋候選月嫂並建立配對方案
→ 鎖定檔期並寄送月嫂契約
→ 月嫂簽回並建立簽約前服務承諾及訂金義務
→ 匯入銀行對帳單並核銷訂金
→ 寄送及回收客戶契約
→ 原子完成 Contract Completion
→ exact conversion 為正式指派及排班
→ 處理資料修改、改派、請假、順延及代班
→ 確認實際服務開始與完成
→ 匯入後續客戶收款、月嫂付款及政府撥款銀行流水
→ 執行客戶帳務、月嫂應付與政府補助核銷
→ 處理少匯、溢匯、退匯、reversal、recovery 及異常重開
→ 完成訂單與跨 Domain 對帳
```

每一站都必須同時驗證正常、阻擋、人工修復、same-command replay、stale、conflict、rollback
與跨站不變量；不得只保存最終成功畫面。

每一站驗收通過後發布 versioned DB stage baseline 與 restore verifier，下一站從前一 baseline 恢復後
繼續。開發者可 reset 到 Import 後、配對後、契約後、排班後或完成後等已發布階段，重測該站與
後續操作。多案件在同一 baseline 中分布於不同 UI 狀態，因此不要求為每個中間狀態永久凍結一個
不可操作案件；baseline artifact 本身不可改寫，實際操作在 restore 後的 working DB 進行。

## 3. Authority、範圍與 non-goals

### 3.1 Authority

- Global 契約：`document/架構重整/01_規格基線/00_Global_共同契約.md`
- 正式規格索引：`document/架構重整/01_規格基線/15_正式規格索引與裁決總表.md`
- Contract Signing：`21_Contract_Signing_Commitment與正常驗收資料鏈正式規格.md`
- 銀行流水及帳務異常：`22_銀行流水匯入與帳務異常處理正式規格.md`
- Import 現行語意：`15_正式規格索引與裁決總表.md`、`09_Finance_Import_Domain.md`、
  `17_External_Integration_LINE_Access正式規格.md`；入口退役相鄰計畫：
  `document/架構重整/02_決策與退役執行記錄/Import_Entry_and_Legacy_Writer_Retirement_工作包.md`
- React page-slice routing decision：
  `document/架構重整/02_決策與退役執行記錄/PROV-20260817-react-admin-page-slice-migration-execution-decision.md`
- WP56 只作歷史驗收與本輪 inventory 證據，不授權直接沿用其資料作為 current SSOT。

### 3.2 Scope

- 建立全生命週期 UI scenario catalog 與 dependency graph。
- 為每個 Part 定義必要 root facts、events、projections、commands、typed errors 及資料狀態。
- 盤點現有 `lu_test_dataset_contract_signing_v4` 33 個 canonical import cases 的可用性。
- 定義可重建的 seed、DB/API/UI verifier、receipt 與人工 browser acceptance 契約。
- 規劃 isolated validation database 的建立、驗證及明確人工 mutation gate。

### 3.3 Out of scope

- 本主計畫本身不授權修改 production code、schema、migration、seed 或 pytest。
- 不授權重建、清空或修正任何 validation／candidate／production database。
- 不授權正式 LINE 傳送、銀行操作、付款、補助送件、部署或 cutover。
- 不把現有 UI、資料表、receipt 或最終 projection 自動升格為業務 SSOT。
- 不在本文件複製各 Domain 的金額、資格、日期或狀態公式。

### 3.4 React page-slice applicability

本主計畫的 Scenario／DB 治理仍是 mutation、controlled-data、transaction、worker、external provider
與跨站 Domain invariant 的必要權威；它不再是既有 typed GET real-data query 接線的無條件前置。React
依 `PROV-20260817-react-admin-page-slice-migration-execution-decision.md` 逐頁判定：

- `query-only` page slice：沿用現有 typed GET 或補該頁最小 typed view，保留 UI slot，對缺欄顯示
  `unavailable`，執行 API／UI 的 success、empty、typed error／auth、timeout／abort、PII 與 reload
  evidence；可用既有allowlist開發測試DB做GET UI觀察。若同一exact Work Package另含受控mutation，則依
  2026-08-21裁決可在該DB建立或修改本次owned測試資料，不需另建non-root disposable DB。
- `mutation／controlled-data` slice：才套用本計畫的 scenario lineage、fixed clock、隔離 validation DB、
  Preview／Apply／receipt、replay／stale／rollback 與 transaction oracle。
- 一頁可同時含兩種 slice；query 已完成不解鎖 mutation，mutation blocker 也不阻塞同頁已閉合 query。

因此，本文件中的全生命週期 dependency graph 仍約束完整業務驗收與高副作用流程，但不得被解讀為
所有 React page query 的中央施工前置。每個 page-slice Work Package 必須明確標記 mode、write set、
必要 evidence 與 out-of-scope，避免把無關缺口擴張成共同阻塞。

## 4. 執行原則

1. 完整 business mutation／controlled-data 驗收依業務 dependency graph 排序；query-only page slice 依自身
   bounded contract 與 UI scope 排程，不依頁面選單或檔名排序，也不等待無關 mutation predecessor。
2. 上游資料未建立或仍在 review 時，下游 scenario 必須 fail closed。
3. 每個 Part 使用獨立且穩定的 scenario identity；不可讓同一案件經後續 mutation 後失去前態。
4. UI 只顯示 typed API result；不得用 SQL 預先偽造 Domain 成功狀態。
5. Query 唯讀、Preview 零寫入、Apply fresh-read；每個 mutation 只有一個 outer UoW owner。
6. accepted、rejected、stale、replay 與 rollback 都要有可獨立驗證的 oracle。
7. 拒絕情境本來就可能沒有最終 root row；mutation／controlled-data slice 必須以 receipt、零 partial-write
   與 read isolation 驗證。query-only slice 只驗證 typed error／empty／read isolation，不建立 mutation receipt。
8. Mutation／controlled-data 測試資料只能進名稱與環境均通過allowlist的development／validation database；
   2026-08-21人工已撤銷「既有DB只能GET」及「必須non-root disposable DB」。可使用目前credential（包括root）
   在既有`lu_test_*` DB執行已核准scope的受控mutation，但必須隔離scenario identity、限定owned rows、保存
   before/after與receipt，並做scoped cleanup或明確保留。disposable DB為選配；schema／migration、全庫seed、
   reset、replacement、`--switch`、`union_db`及production target仍不在此授權。
9. 每個 Part 在撰寫場景時同步執行基礎建設 readiness audit；不得等到 seed 或 UI 實作時才發現
   schema、typed port、worker、登入／actor audit 安全邊界或驗證工具不存在。
10. 基礎建設目前可運作只屬 live evidence；若不符合正式契約仍標示 `live-drift`，不得反向修改
    業務場景來配合現況。

## 5. Part 與生命週期順序

| 順序 | Part | 主要業務操作 | 前置依賴 | 文件狀態 | 實作 gate |
|---|---|---|---|---|---|
| 0 | 全域測試資料治理 | identity、clock、資料隔離、seed/replay/oracle 契約 | 無 | proposed；待人工確認 | 未開放 |
| 1 | 來源檔上傳與 Import | Current HCM／BeClass／Staff／銀行檔＋獨立 Historical Import lane＋版本化髒資料 corpus | Part 0 | 待撰寫 | 未開放 |
| 2 | Import Review 與正式案件升格 | 無效欄位、重複、人工修正、Case bootstrap | Part 1 | 待撰寫 | 未開放 |
| 3 | 訂單條款與生命週期起點 | Terms、洽談中、阻擋、預計服務條件 | Part 2 | 待撰寫 | 未開放 |
| 4 | 月嫂主檔、資格與可服務能力 | 資格、區域、時段、LINE、銀行帳戶、休假 | Part 1 | 待撰寫 | 未開放 |
| 5 | 月嫂配對中心 | 候選搜尋、排除原因、分段、coverage、檔期鎖 | Part 3、4 | 待撰寫 | 未開放 |
| 6 | 月嫂契約與 Commitment | 產生、寄送、簽回、日期守恆、訂金義務 | Part 5 | 待撰寫 | 未開放 |
| 7 | 訂金對帳與客戶契約 | 匯入對帳單、訂金核銷、客戶寄送／簽回 | Part 6 | 待撰寫 | 未開放 |
| 8 | Contract Completion 與正式排班 | 原子完成、exact conversion、Calendar/Payroll isolation | Part 7 | 待撰寫 | 未開放 |
| 9 | 資料修改、改派、請假與代班 | Terms change、supersede、occupancy、假日、buffer | Part 8 | 待撰寫 | 未開放 |
| 10 | 實際服務與訂單完成 | actual start、逐日服務、完成、取消拒絕、資料鎖 | Part 8、9 | 待撰寫 | 未開放 |
| 11 | 客戶後續收款、退款與核銷 | 期款、少收／多收、退款、return、reversal | Part 7、10 | 待撰寫 | 未開放 |
| 12 | 月嫂薪資與應付核銷 | obligation、清冊、付款、少匯、補發、退匯、recovery | Part 8、10 | 待撰寫 | 未開放 |
| 13 | 政府補助與撥款核銷 | Draft、送件、核准、短撥、溢撥、墊付、reversal | Part 8、10 | 待撰寫 | 未開放 |
| 14 | 異常警示與人工修復閉環 | claim、resolve、reopen、auto-resolve、typed action | Part 1～13 | 待撰寫 | 未開放 |
| 15 | LINE 與外部副作用 | binding、delivery、retry、timeout、exhausted | Part 1～14 | 待撰寫 | 未開放 |
| 16 | 跨 Domain 端到端驗收 | 完整人物劇本與全鏈對帳 | Part 0～15 | 待撰寫 | 未開放 |
| 17 | Data Browser 去敏資料查詢 | allowlisted source、masked pagination、typed detail與source lineage | Part 0及各來源唯讀projection | identity已核准；result `NOT_RUN` | 只由3D-DB-H／DB-R bounded WPs開放 |

Part 14、15 的契約在上游各 Part 撰寫時就必須引用；其集中 Part 用於跨 Domain 一致性驗收，
不表示異常與 LINE 要等到最後才思考。

Part 17是獨立的跨source唯讀驗收identity，不表示它在業務生命週期上晚於Part 16。它只擁有server-masked
Query／typed detail與immutable lineage顯示；raw row、任意table／SQL、source correction及entry cutover均不屬此Part。

## 6. 每個 Part 的文件完成定義

每個 Part 必須建立獨立計畫文件，至少包含：

1. status、priority、owner、Domain／Subsystem、updated date。
2. 操作者、真實 business scenario、前置資料與下游消費者。
3. scope、out-of-scope、dependencies、exact proposed write set。
4. SSOT、root facts、immutable events、derived projections 與禁止 seed 的欄位。
5. state machine、正常流程、阻擋流程、修復流程與 terminal states。
6. typed Commands／Queries／Views／Errors／Blockers。
7. transaction、lock、commit owner、partial failure 與外部副作用。
8. idempotency、replay、stale、timeout、retry、conflict 與 rollback。
9. UI 工作區、逐步操作、欄位、按鈕狀態、navigation 與 receipt 呈現。
10. scenario matrix：happy、boundary、invalid、repair、replay、conflict、concurrency。
11. 每個 scenario 的 fixture、expected、DB oracle、API oracle、UI oracle 與清理方式。
12. 現有 33 案的保留／補強／取代／隔離裁決及 `live-drift`。
13. Module、Subsystem、Domain、Global required tests。
14. acceptance、人工確認欄位、未決問題與 implementation activation gate。
15. Infrastructure readiness matrix、缺口 owner、補建順序及阻擋條件。

文件即使標成 `completed` 也只代表規格撰寫完成；只有人工將該 Part 明確確認為 `approved`，
並核准 exact write set，才可開始實作。

## 6.1 基礎建設 readiness audit

基礎建設稽核與業務場景設計同步進行，但兩者不可互相取代。每個 Part 至少逐項檢查：

| 層級 | 必查項目 | Ready 的最低證據 |
|---|---|---|
| Global contract | Actor、BusinessClock、version、fingerprint、idempotency、typed error、correlation | 共用型別及實際 caller 一致；無 UI 自算或 message parsing |
| Transaction | outer UoW、lock order、commit owner、rollback、outbox | 成功／失敗／replay 均能證明零 hidden commit 與零 partial write |
| Schema | root/event/receipt/outbox/version/index/constraint | schema／migration變更仍須以disposable fresh與preserve-data candidate重建並通過約束驗證；一般API／UI mutation可用既有allowlist開發測試DB |
| Domain／Subsystem | root ownership、state machine、Preview／Apply、typed ports | 正式規格、production chain 與 tests 可一對一追溯 |
| API | typed request／view／error、capability、stale/replay | route 不直接寫 DB，成功與失敗 envelope 均有契約測試 |
| UI | bounded typed client、loading/blocker/receipt、repair navigation | raw dict 不穿透 render，Apply 前有 Preview，成功只以 server receipt 顯示 |
| Import／Archive | upload allowlist、digest、ephemeral cleanup、immutable evidence | 來源可追溯，cleanup failure 不偽造 import failure，archive failure fail closed |
| Worker | durable job、inbox/outbox、retry、timeout、dead-letter／人工入口 | restart 後可續跑，同 command 不重複 Domain mutation |
| Access／Security | service auth、admin principal、capability、audit、secret boundary | UI 與 API 都 fail closed，測試不輸出 secret 或完整個資 |
| Observability | job／outbox lag、typed failure、correlation、operator query | 可從 UI 或受控 operator 入口定位 pending、failed、retrying 與 terminal receipt |
| Test isolation | DB allowlist、fixed clock、fixture separation、external fake | 不可能指向 production；LINE、銀行、補助及付款副作用皆為受控 adapter |
| Rebuild／Verifier | bootstrap、seed、projector rebuild、DB/API/UI oracle | 從乾淨 DB 可重建；verifier 驗證日期集合與 identity，不只計數或最終狀態 |
| Performance／UX | bounded query、pagination、N+1、timeout、large batch | 真實資料量下仍符合明確 budget，degradation 有 typed 行為 |
| Release／Recovery | dependency、migration compatibility、backup/restore responsibility | 不要求本計畫部署，但所有待補基建有 owner、順序與 recovery boundary |

每一項只能使用以下結論，不使用模糊的「大致完成」：

- `ready`：正式契約與 current evidence 一致，且有可重跑驗證。
- `partial`：主路徑存在，但缺少必要錯誤、修復、驗證或操作入口。
- `missing`：正式場景需要，但目前沒有 canonical 能力。
- `live-drift`：現況存在，卻違反或偏離正式契約。
- `blocked`：缺少人工裁決、上游契約或安全隔離，禁止開始實作。
- `not-applicable`：本 Part 確實不需要，文件必須說明理由。

Part 文件必須把 `partial`、`missing`、`live-drift`、`blocked` 轉成具 owner、dependency、
proposed write set 及 acceptance 的 infrastructure gap；不能只列問題，也不能在未核准前順便修復。

## 6.2 Part activation gate

每個 Part 依下列順序推進：

```text
Business scenarios 完成
→ Root facts／state machine／typed contracts 完成
→ Infrastructure readiness audit 完成
→ 現有資料與 entrypoint inventory 完成
→ 缺口及 proposed write set 完成
→ 人工確認業務契約與基建補建範圍
→ 才可建立 Work Package 並開始實作
```

若缺口會改變 owner、SSOT、public interface、entry point、external provider、transaction boundary、
schema、production data 或 deployment，必須停在人工確認，不得以測試資料需求自行擴張架構。

## 7. 月嫂配對 Part 的最低場景集合

月嫂配對是獨立的大型 Part，不得只放在 Assignment happy path。最低需包含：

- 單一月嫂正常候選與正常配對。
- 多候選排序及可解釋的入選／排除原因。
- 無候選、資格不符、區域不符及服務時段不符。
- 既有 assignment occupancy、waiting-deposit lock 與七日 buffer 衝突。
- 單月嫂完整服務、多月嫂分段、分段缺口、日期重疊及服務日數不守恆。
- 配對 Preview、Apply、same-command replay、不同 payload conflict 及 stale plan version。
- 檔期鎖建立、訂金逾期但不自動釋放、人工修復及方案 supersede。
- UI 顯示候選、排除原因、coverage、每日工時、衝突日期、blocker、Apply readiness 與 receipt。

## 7.1 Import Part 的 Historical／Dirty-data 最低場景集合

Part 01 必須把 current import 與 historical import 分成兩條 command lane。Historical Import 用來保存、
辨識、對帳及核准採用過去已發生的事實，不得假裝舊事件今天重新發生，也不得因採用歷史資料觸發
LINE、現行義務、現行政策重算或其他 current side effect。

髒資料必須來自既有問題紀錄的去敏 synthetic corpus，至少涵蓋：

- 第一列題號／第二列中文表頭、全形／空白、表頭位於第 3 或第 16 列、核准表頭別名。
- 說明頁在資料頁之前、任意 sheet 名、多個有效 sheet、歷史多 sheet 及歧義 sheet selection。
- 西元／民國年、不同分隔符、Excel datetime、`24:00`、閏日、非法日期及文字月份。
- 手機、銀行帳號、分行碼、虛擬帳號的 numeric cell、尾端 `.0`、前導零遺失及全形數字。
- 金額千分位、小數、空白、`--`、負數、正負零、科學記號、極大值及公式 cell。
- 空列、NaN、公式空字串、合計／footer、只有格式無值及重複表頭。
- 同 identity 同名／異名、同 query number 不同內容、缺唯一 identity 及姓名／電話不足以唯一配對。
- Historical Orders 來源狀態 `0／1／2`、blank、unknown、矛盾狀態及危險 default 防止。
- current／historical cutoff overlap、同一來源跨 lane 重送、改名重送及部分批次重跑。
- target schema 缺 table／column／constraint／trigger、writer contract stale 及 drift 靜默漏欄防止。
- 匯入已 commit 但 anomaly projection／暫存檔 cleanup 失敗；不得重做 Domain mutation或誤報失敗。

每個髒資料 row 都要有且只有一個 outcome：written、review、ignored、duplicate、retry-required 或
batch-failed；總數必須守恆。無法唯一還原的識別碼或歷史政策只能保留 evidence/review，禁止猜值。

Historical Import 的現行業務語意以 `15` 與 Orders／Case Import 正式規格及已封存的 WP80、WP92、
WP95 evidence 為準；不得沿用 ADR-001 的歷史 checklist。若 Part 01 驗收仍缺 fixture identity、
corpus 或 scenario evidence，必須在 Part 01 自己的 proposed 文件具名列出 owner、scope、驗收與
人工裁決入口，不得因本主計畫已 approved 就宣稱 Historical Import ready。

## 8. 跨站不可破壞的不變量

- Import review 完成前不得建立正式案件根事實。
- 配對只建立 plan／commitment 前置資料，不建立 execution assignment。
- 月嫂未完成簽回且服務日不守恆時，不得建立有效 commitment 或訂金義務。
- 訂金核銷可使訂單成立，但客戶未簽回前不得建立 execution schedule。
- 客戶簽回與 Contract Completion 必須原子完成。
- commitment 與 execution 的 case、plan/version、staff、日期集合必須 exact equal。
- 修改條款、改派、請假或代班不得原地覆寫歷史，必須保存 cancel/create 或 supersede lineage。
- 清冊、Alert、LINE delivery、UI session 或銀行匯入列本身都不能冒充正式帳務或 Domain 成功。
- 月嫂應付與政府補助不因客戶帳務顯示結果而被推算。
- 人工 resolve Alert 不代表根因已消失；monitor 可依相同 predicate reopen。

## 9. 現有資料 inventory 基線

2026-08-12 唯讀稽核觀察到目前設定的 `lu_test_dataset_contract_signing_v4` 有 33 個 distinct
canonical import cases，但不可直接判定為 33 個完整 UI scenarios。主要已知問題：

- 正常鏈 `115000051` 的 verifier 預期 5 個 official service days，現況讀到 10 筆兩代 schedule，
  判定為 `live-drift`，阻擋 Calendar／Scheduling happy-path 驗收。
- 現行 `scripts/seed_ui_validation_dataset.py` 引用已不存在的 anomaly seed module，乾淨 DB 在任何
  foundation 寫入前即失敗，無法重建歷史 v4 資料集。
- Staff Payables 缺少少匯、補發、退匯及 recovery 資料。
- Government Subsidy 只有 Draft，缺 Submitted、Approved 與 funding reconciliation。
- 多數 replay、stale、conflict、rollback 只有歷史 receipt，不能只由 DB final state 判讀。

Part 0 必須先建立 canonical inventory manifest，逐案記錄來源、scenario ownership、可重建性、
污染／漂移、保留理由與 successor；在完成分類前不得清理或重產既有資料。

## 10. 建議文件與實作波次

每一個 Wave 都先完成該 Wave 的 infrastructure readiness report；共同基建缺口由 Part 0 擁有
治理與排序，各 Domain 專屬缺口仍由對應 Part 擁有，避免建立跨 Domain 巨型測試服務。

### Wave A：建立可信任的上游資料

- Part 0：全域測試資料治理。
- Part 1：來源檔上傳與 Import。
- Part 2：Import Review 與案件升格。
- Part 3：訂單條款。
- Part 4：月嫂主檔與能力。

### Wave B：配對、契約與訂金

- Part 5：月嫂配對中心。
- Part 6：月嫂契約與 Commitment。
- Part 7：訂金對帳與客戶契約。
- Part 8：Contract Completion 與正式排班。

### Wave C：服務中的真實變化

- Part 9：資料修改、改派、請假與代班。
- Part 10：實際服務與完成。

### Wave D：後續金流

- Part 11：客戶收款與退款。
- Part 12：月嫂應付。
- Part 13：政府補助。

### Wave E：跨域閉環

- Part 14：異常中心。
- Part 15：LINE 與外部副作用。
- Part 16：全生命週期 E2E。

同一 Wave 內只有在 SSOT、write set 與依賴不重疊時才能平行實作；文件研究可以平行，正式
mutation 必須依 dependency graph 及人工 activation gate 執行。

## 11. 主計畫 acceptance

本主計畫只有在以下條件全部完成後，才能標成 `approved`：

1. 人工確認 Part 0～16 的邊界、順序、owner 與 dependency graph。
2. 每個 Part 都有唯一文件落點、狀態、驗收與人工 activation gate。
3. 現有 33 案完成逐案 inventory，而非只做表級 count。
4. 每個 scenario 能追溯到正式規格、fixture、expected、DB/API/UI oracle 與 receipt identity。
5. `115000051` schedule drift 與 seed 無法重建問題已被指派至明確 Part；在修復前維持 blocker。
6. 沒有任何文件以現有 DB、UI 或歷史 receipt 覆蓋正式業務語意。
7. production DB、外部 LINE、銀行操作、部署與 cutover 仍明確排除。
8. Part 0～16 均完成 infrastructure readiness matrix，且每個非 `ready` 項目都有唯一 owner、
   dependency、人工 gate 與可驗收的 closure evidence。
9. 共用基建缺口與 Domain 業務缺口已分開，沒有為了測試方便把業務規則搬進 seed、UI、script
   或 generic infrastructure。

## 12. 下一個文件工作

依序撰寫並送人工確認：

1. `Part_00_全域測試資料治理與Scenario契約.md`
2. `Part_01_來源檔上傳與Import_UI驗收計畫.md`
3. `Part_02_Import_Review與正式案件升格_UI驗收計畫.md`
4. `Part_03_訂單條款與生命週期起點_UI驗收計畫.md`
5. `Part_04_月嫂主檔資格與可服務能力_UI驗收計畫.md`
6. `Part_05_月嫂配對中心_UI驗收計畫.md`

Part 00～05 均完成並確認後，才進入契約、訂金及正式排班文件；任何 seed／code／schema／DB
實作都不得先行。
