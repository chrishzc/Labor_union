# Part 00：全域測試資料治理與 Scenario 契約

---
status: proposed
priority: P0
owner: global-validation-governance
domain: Global
subsystem: validation-data-governance
initiative: ui-real-business-flow-validation
updated: 2026-08-12
---

## 1. Authority 與目的

本文件執行已確認的
`document/功能開發計畫/UI真實業務流程測試資料與驗收主計畫.md` Part 00，定義 Part 01～16
共同遵守的 scenario identity、固定時鐘、資料隔離、seed/rebuild、oracle、receipt、inventory 及
外部副作用替身契約。

權威來源依序為人工最新確認、`00_Global_共同契約.md`、`15_正式規格索引與裁決總表.md`、
各 Domain 正式規格及主計畫。本文件只擁有跨 Part 驗證治理，不擁有任何 Domain 的狀態、日期、
資格或金額公式。

## 2. Business scenario

測試負責人必須能從版本控制中的 root／external input 建立一個全新的隔離資料庫，依正式 typed
commands 重播指定業務場景，再以 DB、API 及 UI oracle 證明結果。相同 artifact 重建必須得到相同
業務 identities 與預期結果；失敗、stale、conflict 及 rollback 也必須是正式可驗收結果。

```text
選定已核准 scenario release
→ preflight artifacts／schema／target／external adapters
→ 建立全新 disposable database
→ 匯入 root／external input fixtures
→ 依 dependency graph 執行 typed commands
→ rebuild projections
→ 執行 DB oracle
→ 執行 typed API oracle
→ 執行 UI／browser oracle
→ replay／stale／conflict／failure injection
→ 產生 receipt 與 inventory linkage
→ 保留驗收證據；依核准流程處置 disposable database
```

## 3. Scope、non-goals 與 proposed write set

### 3.1 Scope

- 定義 Part 01～16 共用的 scenario package 與 identity contract。
- 定義 validation database allowlist、確認、防誤連與外部副作用隔離。
- 定義 root fixture、command lineage、expected、oracle、receipt 與 inventory manifest。
- 定義 fixed clock、deterministic identity、seed/rebuild/replay 及 drift detection。
- 唯讀盤點現有 validation infrastructure 與 33 個 canonical import cases。
- 將共用基建缺口與 Domain 專屬缺口分流。

### 3.2 Non-goals

- 不定義各 Domain 的業務公式或場景內容。
- 不以 generic seed 直接建立 derived projection、receipt、outbox 或完成狀態。
- 不建立跨 Domain 巨型測試 service。
- 不授權重建／清空／修正任何現有 DB。
- 不授權 production code、schema、migration、seed、pytest 或外部服務 mutation。

### 3.3 未來若獲核准的 proposed write set

本節只供人工審核，尚未授權實作：

- `validation/catalog/`：scenario catalog、dependency、identity 與 inventory contracts。
- `validation/scenarios/`、`validation/fixtures/`、`validation/expected/`：新增或升版的 canonical contracts。
- `validation/receipts/`：符合統一 receipt contract 的新驗收證據。
- `scripts/` 中專用 validation bootstrap／runner／inventory／verifier；不得擴張 production writer。
- `tests/` 中直接對應的 validation governance tests。
- `document/功能開發計畫/` 中本文件與後續 Part 文件。
- 如發現 schema/release 缺口，必須另立明確 Work Package；Part 00 不自動取得 schema write 權。

### 3.4 文件與模組查核順序（Graphify 輔助）

- 後續撰寫各 Part 或盤點功能時，先查詢既有 `graphify-out/graph.json`／manifest，以 scenario 關鍵詞、
  entry point、UI、API、Subsystem、Domain 及 caller/callee 關係定位候選模組，再回到原始碼與正式規格
  逐一核對；不得只靠全文搜尋猜測模組範圍。
- `graphify-out` 只作導航輔助，不是 SSOT。使用前檢查目標檔是否已被 manifest 索引及 graph 是否可能
  落後目前 worktree；未索引、mtime／digest 不符或找不到關係時，以 live source 補查並標記 graph
  coverage gap，不用 graph 結果覆蓋原始碼或規格。
- 最終裁決仍依人工最新決定、正式規格、live source／schema／API／UI 的權威順序。Graph node、edge、
  rationale 或舊快取不能證明功能存在、已驗收或允許修改。
- 若執行環境提供正式 Graphify Skill，須先完整讀取其 `SKILL.md` 再使用。目前工作區只有
  `graphify-out` artifacts，沒有可用的 Graphify Skill instruction file，因此本輪直接唯讀查詢 artifact。

## 4. Canonical scenario package

每個 scenario 使用獨立目錄身份或 manifest linkage。下列 artifact 先由 evidence applicability matrix
裁決為 `required`、`optional`、`not-applicable` 或 `blocked`；只有 `required` 是該 scenario 必備：

| Artifact | Canonical responsibility |
|---|---|
| scenario manifest | scenario ID、revision、Part、owner、dependencies、clock、execution mode、commands |
| root fixture | 去敏、最小、可版本化的 root／external inputs |
| expected manifest | DB/API/UI 期待值、拒絕結果、零寫入與跨 Domain invariants |
| command lineage | command type、actor、reason、correlation、idempotency、expected versions、fingerprint lineage |
| DB oracle | 精確 identity、日期集合、事件 lineage、row delta、constraint 與 forbidden rows |
| API oracle | typed view／error envelope、版本、blockers、receipt identity |
| UI oracle | workspace、步驟、按鈕狀態、顯示值、repair navigation、re-observe |
| receipt | artifact digests、runner revision、environment、assertions、result、observed identities |
| inventory record | current DB presence、rebuildability、drift、retention、successor、evidence links |

scenario package 不得只保存 row count、敘述或最終 projection。任一 artifact 改變都必須產生
新 digest；若改變業務語意或 identity，必須升 scenario revision，不得覆寫舊 receipt 的意義。

### 4.1 Evidence applicability matrix

- 每個 Part 及 scenario 在寫 fixture／runner 前，須逐項裁決 UI、typed API、DB root facts、業務守恆、
  replay／recovery 證據為 `required`、`optional`、`not-applicable` 或 `blocked`。
- `required` 必須通過；`optional` 只有在本次 scope 實際具備對應能力時才納入；`not-applicable` 必須
  記錄業務理由，不得空白；`blocked` 必須記錄缺少的基礎建設、owner 及解除條件，且不得視為通過。
- 不產生 mutation 的查詢／預覽 scenario，不要求虛構 DB 寫入證據；需要時改驗證零寫入。沒有 replay
  語意的流程不得為湊齊層數製造無業務意義的 replay 測試。
- Receipt 只收錄適用證據、必要的跨階段 invariant，以及不適用／阻擋裁決。Part 不需同時具備五類
  證據，但所有 `required` 證據及 stage-level 必要守恆都通過後，才可進入該 scenario 所屬 stage 的
  promotion 判定。
- Evidence 分成兩種執行邊界：Browser receipt 只證明 UI 可見互動與輸出；API／DB、Domain invariant、
  worker、outbox、callback、idempotency 及 failure-path 證據由適用的 pytest／專用 verifier 負責。
  不得要求單一 Browser scenario 同時承擔所有後端證據，也不得因 pytest 通過就視為 UI 已通過。

### 4.2 Existing scenario adoption，禁止重複造輪

- WP56 已證明的 business flow、fixture intent、expected state、repair/replay 步驟及 oracle 應優先
  採用；只有正式規格已變更、artifact 無法重播或缺少必要驗收時才補建。
- 採用前建立 `source scenario/receipt → successor scenario` mapping，逐欄標示 unchanged、renamed、
  regenerated、superseded 或 unresolved。
- 僅案件編號等 identity 不合法時，不重寫整個場景；保留原業務語意，換成符合正式格式且不碰撞的
  identity，再由 canonical Import／workflow 重新產生下游關聯。
- 舊 receipt、舊 fixture digest 及舊 DB observation 都不得原地修改；它們持續證明當時版本。
- successor 必須證明除了核准的 identity／去敏欄位轉換外，關鍵 root intent、command sequence、
  blockers、expected result 與跨 Domain invariants 均與來源場景相同。

## 4.2 測試資料實作的兩條路線

後續實作不是只有「全部重建」一種方式。每個 Part／scenario 必須在 Work Package 中明確選擇
Route A、Route B 或說明為何需要兩者都做；不得在執行中臨時混用。

### Route A：從頭逐筆建立（clean replay）

以全新或已安全 reset 的開發／validation DB 為目標，像 WP56 normal-chain 一樣，從合法來源資料
開始，依正式業務順序一筆一筆執行 Import、Review、配對、契約、銀行匯入、核銷及後續 commands。

適用情況：

- 驗證完整生命週期、transaction、replay、stale、rollback 或跨 Domain invariants。
- 現有 DB 資料來源不明、已污染、無法唯一映射或存在阻擋性 `live-drift`。
- 需要證明 developer DB reset 後可重現相同測試情境。

必要證據：

- clean/reset baseline identity 與 schema/scenario release。
- 每個步驟的 command lineage、row delta、receipt/outbox 及 fixed clock。
- DB/API/UI oracle；相同 release 再次 reset/replay 結果一致。
- 禁止直接建立 derived projection 或跳過上游狀態。

### Route B：修改原有 DB、缺口再新增（adopt and augment）

以明確指定的現有開發／validation DB 為基線，先唯讀盤點既有 roots、events、receipts、projections
及 drift；可證明來源和業務語意的資料予以沿用，只對缺少的狀態／案例透過 owning Domain 的正式
Import／Preview／Apply／repair command 新增或修正。

適用情況：

- 既有 33 案或 50 案 frozen fixture 已覆蓋大部分需求，僅缺少少數狀態或邊界案例。
- WP56 既有場景可直接 adoption，只需合法九碼案號、current contract 或缺口補強。
- 需要保留現有開發者常用資料及 UI 操作脈絡。

必要證據：

- mutation 前 inventory snapshot、基線 digest、DB identity、備份／reset recovery 路徑。
- 每筆採用資料的 source→current／successor mapping 與可用性判定。
- 只新增缺口；不得直接 UPDATE 正式 status、日期、金額、assignment、ledger、alert、receipt 或 projection。
- Apply 前後精確 row delta、未受影響案例 digest、current DB/API/UI oracle。
- same command replay 零新增；失敗時有再次 reset 或由正式 correction command 恢復的入口。

### Route 選擇規則

| 判斷條件 | Route A | Route B |
|---|---|---|
| 需要證明完整流程可重建 | 必須 | 可作補充，不可取代 A |
| 只缺少少量獨立 UI 狀態 | 可選 | 優先 |
| 來源／lineage 不明 | 優先重建 | 禁止直接採用 |
| 現有資料有可隔離且可修復 drift | 可作乾淨對照 | 取得核准後可用正式 repair |
| 現有資料已污染且無法唯一修復 | 必須 | 禁止 |
| 需要驗收 DB reset | 必須 | reset 前後可另驗基線保留策略 |

兩條路線都不授權修改 production DB。Route B 的「修改原有 DB」只指人工明確指定、可 reset／recover
的開發或 validation DB；每次 mutation 仍須對應已核准 Part／Work Package、exact target 與 write set。

### 4.3 分庫開發與收尾收斂

- 開發及驗收期間 Route A 與 Route B 使用不同 target profile，避免日常 augmentation 污染 clean replay
  基準。Route A 不得讀取或依賴 Route B DB。
- `core` profile：Route A 的最小可信任完整流程，保持可從零重建，作為 regression 基準。
- `developer` profile：Route B 的日常 UI 資料，採用既有可證明資料並補足已核准缺口。
- `part-NN` profile：特定 Part 的隔離情境，只服務 focused development／debugging。
- 全計畫落地收尾時合併的是 scenario catalog、fixtures、command lineage、expected、oracle 與 reset
  release，不直接將兩個實體 DB 以 `INSERT ... SELECT`、dump merge 或通用 UPDATE 拼接。
- final developer baseline 必須從乾淨 DB 依合併後的 scenario release 重新建立，先完成九碼案號、
  虛擬帳號、external event、document digest、idempotency identity 及 master data collision preflight。
- 收尾重建後執行完整 DB/API/UI oracle、replay/stale/conflict/rollback 與跨 Domain reconciliation；
  通過後才能發布新的 `developer` reset release。
- 合併後仍永久保留獨立 `core` reset profile；`developer` 可包含 core 場景，但不能取代 core 的
  獨立可信任證據。

### 4.4 依流程階段保存可恢復 DB baseline

測試資料以多案件共同覆蓋不同狀態，不假設所有案件會同時只剩「完成」。主要恢復機制是依業務
順序建立 versioned stage baseline，而不是為每個 UI 狀態永久凍結一個不可操作案件。

```text
stage-00-clean
→ 執行並驗收 Import／Historical Import
→ stage-01-imported
→ 執行並驗收 Review／正式案件升格
→ stage-02-reviewed
→ 執行並驗收月嫂主檔／配對
→ stage-03-matched
→ 執行並驗收月嫂契約／Commitment
→ stage-04-staff-contracted
→ 執行並驗收訂金對帳／客戶契約
→ stage-05-client-contracted
→ 執行並驗收 conversion／排班／服務變更
→ stage-06-scheduled
→ 執行並驗收服務完成／後續金流／補助
→ stage-07-completed
```

- 每個 stage 只能在前一 stage、該階段 commands 及 DB/API verifier 全部通過後發布。
- stage baseline 保存 exact schema release、scenario release、source stage、DB artifact identity/digest、
  command receipts、row/invariant summary 及 restore verifier；不得只保存一個未驗證 dump。
- 開發者可把 DB reset 成資料夾內任一已發布 stage，再重新操作該階段或後續流程；reset 不覆寫
  已發布 baseline artifact。
- 同一 stage 中可有多個案件停在不同狀態，供 UI 同時測試正常、等待、阻擋、review、異常與修復；
  catalog 必須記錄各案件在該 stage 的 expected state。
- stage 是 developer recovery artifact，不是業務 SSOT，也不是本專案已退役的 ADAD checkpoint／task gate。
- Route A 逐站建立可信任 stage；Route B 可從核准 stage 恢復後 adoption/augment，但發布下一 stage 前
  必須重新執行完整 verifier 與未受影響案例 digest。
- 若 DB artifact 不具跨 schema portability，reset runner 必須改用前 stage＋versioned commands 重播；
  不得因 restore 快速而跳過 schema compatibility 或 source lineage。

### 4.5 Replay release 為權威，DB snapshot 為快取

- 每個 stage 的 canonical replay release 是唯一重建權威，至少包含 schema/scenario release、allocation、
  master references、external fixtures、commands、fixed clock、expected、projection rebuild、verifier 及 digests。
- DB snapshot 只是同一 stage 的快速恢復快取，不是 root facts、規格或唯一重建來源。
- snapshot 必須綁定 source stage、schema release、scenario release、database engine/tool version、created-at、
  content digest、row/invariant summary 及 restore verifier identity。
- reset 使用資料夾內該 stage 的 snapshot；若該 release 沒有可用 snapshot，才依同一資料夾 manifest
  指定的 canonical replay 建立。Snapshot 不相容或 digest mismatch 時停止，不勉強套用。
- Historical／dirty source 必須保留為 versioned、去敏 fixture，不能只封存在 DB snapshot 裡。
- snapshot 不可人工修改後重新發布；必須由核准 runner 從通過驗收的 working DB 產生。

### 4.6 Canonical stage artifact directory

所有 Route A／B、core／developer／part-NN 及 final baseline artifacts 固定集中於同一 canonical root：

```text
validation/stage_baselines/
  README.md
  catalog/
    stage_catalog.json
    case_number_allocations.json
    master_allocations.json
  releases/
    <release-id>/
      manifest.json
      stages/
        <stage-id>/
          stage_manifest.json
          fixtures/
          commands/
          expected/
          snapshots/
          receipts/
```

- `catalog/` 保存跨 release identity reservation 與 stage 索引；`releases/` 保存 immutable release。
- `fixtures/` 只放 canonical root／external input；`commands/` 保存順序及 identity；`expected/` 保存 oracle。
- `snapshots/` 只放快取與其 digest metadata；`receipts/` 保存產生、restore、replay 及 verifier 證據。
- 大型 DB snapshot 若不適合進 Git，`snapshots/` 只提交 manifest、digest、size、tool identity、受控 locator
  與 restore policy；實體 artifact 放正式核准的 artifact storage，不得散落 root、logs 或 scratch。
- source fixture 與 generated output 不得混放；任何 artifact 都必須能由 release/stage manifest 唯一定位。
- 不在其他 document、fixture 或個人目錄建立競爭 catalog；舊 artifacts 以 linkage/adoption mapping 引用。

### 4.7 Stage promotion lifecycle

每個 stage release 使用固定 lifecycle：

```text
candidate → verified → published → superseded
```

- `candidate`：本階段已執行但驗收未完成；不可作下游正式來源、不可更新 developer 預設 reset，
  catalog 必須明示不可依賴。
- `verified`：適用的自動 DB/API oracle、receipt/digest、replay/stale/conflict/rollback、上游 invariant、
  restore rehearsal 及 Browser UI 驗收已通過。
- `published`：自動驗證、必要 Browser UI 驗收及 restore 後 re-verification 全部通過；artifact digest 固定，
  可作下一 stage 來源並顯示於 DB reset 選單。
- `superseded`：published 後發現錯誤或有 successor；原 artifact 保留唯讀，不修改 manifest、snapshot、
  receipt 或 digest。所有下游引用必須重新驗證或由 successor 重建。

禁止從 `candidate` 直接跳到 `published`，也禁止以人工勾選取代自動 oracle。Stage promotion receipt
必須記錄 actor、reason、source stage、artifact digests、automated verification、browser UI acceptance、
restore verification、known blockers/skips/live-drift 及 successor linkage。

### 4.8 Promotion gate

每個 stage 必須通過上游與 artifact identity gate，並依該 stage 已核准的 evidence applicability matrix
通過所有 `required` 項目。下列條目僅在相關能力適用時成為 promotion gate；不適用者須附業務理由：

1. 上游 published baseline、schema release、scenario release 及 artifact digests 完全相符。
2. 本階段所有 import／command／dirty-data rows 各有唯一且守恆的 outcome。
3. 無 orphan root、duplicate event、identity collision、hidden commit 或 partial formal write。
4. 未受影響案件、共享 master 及上游 invariants 的 digest／oracle 未改變。
5. 九碼案號、虛擬帳號、client/staff、LINE、銀行 ownership 及 occupancy 符合 catalog。
6. Current／Historical Import cutoff 無未裁決 overlap，review rows 未誤升格正式資料。
7. 適用 DB、typed API 與 UI 的流程，其 observation 一致；mutation UI 成功須由 server receipt 證明。
8. 流程具有相應語意時，Replay、stale、different-payload conflict、rollback 及指定 failure injection 通過。
9. 涉及外部副作用時，invocation count、outbox/job state 及 suppression policy 符合 expected。
10. 從發布候選 artifact restore 到新 working DB 後，stage verifier 再次通過。
11. Blocker、skip、unsupported action、`live-drift` 與人工 follow-up 均完整揭露。

Candidate 驗證失敗可修正輸入或實作後重建新 candidate；Browser UI 驗收失敗則退回 candidate。
Published 發現問題只能建立新 revision 並 supersede，不能原地修補。只有 `published` stage 可供下游及
一般開發者 reset；診斷工具如允許載入 candidate，必須有醒目警示且不得產生 promotion evidence。

## 5. Identity 契約

### 5.1 測試 metadata 與正式資料 identity 分離

- `scenario_id` 只存在 validation catalog、fixture metadata、receipt 或人工可讀備註，不是案件、
  客戶、月嫂、銀行、契約、command 或任何正式業務資料的 identity。
- 正式資料 identity 必須完全遵守 owning Domain／來源系統的 canonical 格式及生成流程，不得加入
  `UIRB`、`WP56`、scenario revision 或測試前綴。
- `case_no` 使用既有九碼數字業務格式，並由正式 Import／Case bootstrap 流程形成；測試 runner
  不得自行發明字串案號或直接繞過來源流程寫入。
- 現行財務關聯證據為：`115000001` 對應虛擬帳號 `99781699115001`；虛擬帳號固定以
  `99781699` 加民國年度三碼及案件流水三碼形成。案號 allocation 必須避免碰撞並保留可反解性。
- 月嫂、銀行列、contract document/event、batch、correlation、idempotency 及 external event identity
  同樣由各自正式契約產生；scenario metadata 只能在獨立 catalog／備註建立 linkage。
- DB auto-increment ID 只能記為 observed identity，不得成為跨 reset/rebuild fixture 的唯一 locator。
- replay 重用原正式 command identity；新的業務嘗試依正式 command 契約取得新 identity，不能由
  測試 runner 任意換 key 規避 conflict。

#### UI 搜尋與人類辨識

- 案件編號維持正式九碼格式及正常 Import／bootstrap 生成流程；不得為方便測試改造 case identity。
- Scenario 可在案件既有備註使用簡短且人類可讀的標記，例如 `[UI測試] 月嫂配對－跨區無可用人員`，
  但 production UI 不需解析該文字，也不以它驅動業務規則。
- Checklist 同時記錄案件編號與辨識備註，Agent 可使用 UI 實際支援的任一方式尋找案件；若 UI 不支援
  備註搜尋，仍以案件編號為 canonical 查找方式。
- 同一案件跨多個 Part 時，備註只描述主要用途；其餘條件、scenario linkage 與覆蓋語意保存在 catalog
  及 checklist，不持續堆疊於業務備註。
- 不以客戶姓名、月嫂姓名、正式狀態或其他業務欄位承載 scenario ID；也不為此新增測試專用 UI
  欄位、filter 或 production schema。
- 案件被 supersede 時更新 catalog successor 與 checklist 引用，不改寫舊案件備註冒充同一案例。

### 5.2 案號 allocation、collision 與隔離

- Part 00 建立唯一的中央 case-number allocation catalog，分配符合正式九碼規則的 validation
  case number；catalog 只是測試資料配置及追溯 metadata，不改變案件編號業務語意。
- 各 Part、fixture、seed、runner、browser script 或人工操作不得自行選擇、遞增或改寫案號；只能
  使用 catalog 對該 scenario release 核准的配置。
- 分配前必須盤點現有 `115000001`～`115000050` frozen fixture、WP56／33 案、`115900001` 起
  歷史異常規劃及 current DB identities；已保留的合法案號不得被新 scenario 重用。
- catalog 必須同時保存 scenario metadata、scenario revision、profile、case_no、ROC year、sequence、
  衍生虛擬帳號、來源／successor、allocation status 及 collision-check digest。
- collision preflight 至少檢查完整九碼 `case_no`、由 `99781699＋年度三碼＋流水三碼` 形成的虛擬
  帳號、HCM／BeClass query identity、external event、contract document/event、Route A／B、core／
  developer／part-NN 及 final release 的所有 reserved/active identities。
- 同一 scenario release 在 reset/rebuild 後必須取得相同案號；案號 allocation 是 versioned artifact，
  不得依 DB auto-increment、執行順序或 runtime random 決定。
- 案號釋放不得因 DB reset 或資料刪除自動發生；只有 scenario 永久退役、successor 已驗收且人工
  裁決後才能標為 retired。為避免歷史銀行資料誤配，retired 案號與虛擬帳號預設仍不可重用。
- 不同 scenario／revision 的正式 case、external event、document digest、idempotency identity 不得碰撞。
- runner 在 mutation 前掃描 identity collision；任一碰撞都 fail closed。
- 共享 master fixture 必須以 versioned reference 使用，不允許某 scenario 靜默修改供其他場景共用的 root。
- 為保存前態，`waiting_customer_signature`、`converted`、`payment_recovery` 等狀態使用不同 case，
  不讓單一 mutable case 同時代表多個 UI 驗收狀態。

### 5.3 Client／Staff canonical master pool

- 中央 catalog 管理正式來源 identity、client/staff identity、LINE binding、銀行帳戶 ownership、
  profile/revision 及 observed DB ID。
- Client 與 case 固定一對一：每個測試客戶只能有一筆案件，不跨案件重複使用，也不建立回購、再次
  懷孕或同家庭多案測試。每個 case 配置自己的去敏 client root。
- Staff 可跨多案件重複使用，以驗證真實檔期、行事曆及每月應付；正常案例的有效服務日期不得衝突。
  只有明確的 occupancy／衝突 scenario 可安排候選期間重疊，且不得把衝突月嫂形成重複正式指派。
- Staff canonical master pool 提供去敏、穩定且可 reset 的正常能力組合，至少涵蓋不同服務區域、
  服務時段、技能／胎數、假日政策、LINE 綁定、銀行資料完整性及在職狀態。
- 共用 Staff 主檔只能作 scenario 的受控前置 root；任何 scenario 不得靜默修改其資格、occupancy、
  LINE、銀行 ownership 或狀態。Client 不屬於跨案件共用 master。
- 會形成 occupancy、請假／代班、buffer、多案件競爭、共享帳戶、身分歧義、LINE conflict、少匯、
  退匯或 recovery 的場景，使用專屬隔離主檔，不得被其他場景引用。
- 正式 client/staff identity 必須依現有來源及 Import 契約形成；scenario metadata 只作備註 linkage，
  不使用自訂 business identity。
- DB auto-increment `client_id`／`staff_id` 只作 observed identity；跨 reset 以 canonical source identity
  查回，不能把數字 ID 寫死為 fixture SSOT。
- Route A／B 收尾前執行 master collision preflight；共享與專屬 identities、LINE subject、主要／共享
  銀行帳戶以及 active occupancy 都必須唯一或符合場景明確要求。

#### 月嫂行事曆與配對候選排除

- 行事曆／月曆是 Staff Matching 與 Scheduling 的必要 UI 測試範圍，不只是下游顯示頁面。
- 配對中心提供五個可勾選的篩選條件，預設全部勾選：`檔期`、`服務地區`、`希望服務天數（幾天內）`、
  `是否需要月嫂下廚`、`每日服務時數`。Browser 必須驗證預設狀態，以及取消／重新勾選代表性條件後
  候選結果依實際規則更新；不得自行增加其他 filter。
- 日期相關候選分兩類：與正式服務或等待訂金鎖定的實際占用衝突者，在勾選「檔期」時不得列為可選
  候選；只碰到行事曆 7 日緩衝者仍可顯示，但須在候選列清楚備註緩衝衝突，不得呈現為完全無衝突。
- 配對 Browser scenario 必須分別建立「實際占用衝突」、「只碰到 7 日緩衝」與「無衝突」資料，驗證
  排除、顯示加註及正常顯示三種結果。關閉「檔期」篩選時的呈現仍須清楚保留行事曆衝突資訊，不得
  讓使用者誤認可以直接形成合法正式指派。
- 同一月嫂在不重疊案件可被再次選擇，並在行事曆正確顯示各案件服務日期；清單與月曆不得遺漏、
  重複或把相鄰檔期誤判為衝突。
- Browser 驗證候選名單與行事曆互動結果；occupancy 日期集合、effective assignment generation、請假／
  代班、buffer、邊界日期及並行競爭由 pytest 驗證。不得為測試新增不存在的 availability 欄位。
- 月嫂請長假／無法提供服務應屬「檔期」並顯示於行事曆，不另設「在職／可服務狀態」配對 filter。
  目前該紀錄功能尚未實作，先列為 product／infrastructure gap；待正式功能與 UI 入口完成後，再補
  Browser checklist 與測試資料，不得先臆造欄位或直接 seed 結果。

#### 單月嫂候選、多候選聯繫與多月嫂分段

- 系統先搜尋可完整承接案件的單一月嫂；存在完整承接人選時優先顯示單月嫂候選。沒有單人完整
  承接時，才進入 2／3／4 段多月嫂配置，預設 2 段。
- 洽談中可同時加入多位各自能完整承接的候選人，逐位發送訂單資訊、記錄時間／狀態、意願及拒絕
  理由；這是 Candidate Contact Pool，不是多人共同服務 segments，不產生 lock／assignment。
- 管理員從 willing 的完整承接候選中選定一位後，才建立單月嫂 matching plan。候選聯繫與傳送履歷
  是不同 UI 操作，不得因已聯繫就顯示為已配對或正式占用。
- 多月嫂共同服務時，每段分別選擇月嫂及日期；聯集須完整涵蓋案件需要的服務日期且無重疊／遺漏。
  同一份洽談 matching plan 不重複選同一月嫂作不同服務段。
- 編輯中的多月嫂草稿可暫時空缺、重疊或超出範圍；正式聯繫／送出前才依完整方案阻擋。找不到完整
  組合時仍顯示部分可行人力、未覆蓋日期及原因。
- 多月嫂方案只有全部已選月嫂都為 willing 才能向客戶傳送履歷；客戶確認後才形成等待訂金 lock，
  訂金核銷並通過正式規則後才轉成 assignment 與行事曆正式占用。
- Browser checklist 至少涵蓋：單人完整承接、多完整候選聯繫與選定、無單人後的完整多段、部分覆蓋、
  草稿錯誤送出阻擋、全員 willing 後送履歷、客戶確認後 lock、訂金後轉正式指派與行事曆。

#### 配對資訊發送、意願與履歷紀錄

- Browser 對每位候選月嫂分別操作「訂單資訊-1」與「訂單資訊-2」，驗證各自的發送狀態與時間；
  補送其中一份資訊時，不得把另一份顯示成同次重新發送。
- 意願使用目前正式 UI／API 定義的狀態。更新後重新整理仍須保留；拒絕時保存拒絕理由，被拒絕者
  不得被選為最後配對人選。不得為 checklist 自行新增意願 enum。
- 單月嫂 Candidate Contact Pool 只有 willing 候選可被選定建立 matching plan。多月嫂共同服務時，
  任一已選月嫂尚未 willing，按下傳送履歷只顯示未通過原因與人員，不得實際發送。
- 全員 willing 後才顯示／允許填寫共用履歷備註並發送；多月嫂履歷內容須明確說明由多位月嫂共同
  完成。單月嫂依正式規格允許對已選月嫂個別補寄履歷。
- 每次實際發送前重新查詢最新檔期及完整方案；若出現衝突，不發送，並在 UI 顯示月嫂與衝突日期。
- 重新聯繫、修改意願、取消組合或重新配對不得刪除既有資訊發送、意願、拒絕理由及履歷歷程。
- LINE 自動回歸使用測試 Adapter 驗證後台狀態，另以專用真人測試帳號及實際 LINE App 完成人工驗收，
  核對實際收到的文字、按鈕、Flex／LIFF／Rich Menu 介面、點擊與回覆後的後台同步。Email 若無另行
  裁決仍使用測試 Adapter；provider retry／idempotency／failure 由 pytest 驗證。

#### 月嫂契約、客戶契約與 Contract Completion

- Matching plan 完成後，每個月嫂 segment 分別產生／寄送月嫂契約。Browser 驗證範本、文件版本、
  寄送狀態、簽回狀態，以及實際選擇簽回檔後執行「記錄月嫂簽回」。
- 任一月嫂 segment 尚未簽回時，UI 應指出缺少項目，不建立完整 Commitment，也不允許寄送客戶契約。
  最後一段月嫂簽回後，UI 顯示全段完成，並呈現簽約前服務承諾及訂金義務已形成的適用結果。
- 全部月嫂契約完成後，才可產生／寄送客戶契約。Browser 實際選擇客戶簽回檔並操作「記錄客戶簽回
  並完成合約」，驗證客戶已簽回、Contract Completion 及剩餘期款的使用者可見結果。
- 訂金核銷、客戶簽回、Contract Completion 與 execution conversion 是分離事實。客戶簽回前即使
  Orders 已成立，也不得顯示正式 Assignment 或正式行事曆服務班表。
- 文件版本變更後提交舊簽回資料時，UI 應要求重新確認，不得套用錯誤版本。未選檔、缺少可簽版本或
  前置條件不足時，顯示可理解的 blocker 與修復方式。
- Browser 聚焦檔案選擇、按鈕、文件版本、狀態與跨工作區阻擋；digest、stale version、原子交易、
  Commitment 精確日期守恆、冪等及零 partial write 由 pytest／專用 verifier 驗證。

## 6. 時間契約

- 所有業務時間固定使用 `Asia/Taipei`。
- scenario manifest 必須提供 timezone-aware `business_now`；runner 必須注入 `FixedBusinessClock`。
- 禁止 fixture、seed、runner 或 oracle 直接使用系統現在時間決定到期、季度、假日或狀態。
- 外部檔案內的 occurred time 與執行 clock 分開保存。
- 日期集合以排序後 ISO date 明列；不得只驗證 `COUNT(*)`。
- 跨月、跨年、閏日、DST 不適用的台北時區語意及國定假日另由相應 Part 定義，但仍使用本 clock 契約。

### 6.1 Central Business Calendar catalog

- 採用中央 Business Calendar catalog，管理 scenario 的 BusinessClock、source periods、service dates、
  due dates、payment months、claim quarters、holiday version、cutoff／overlap window 及 expected period keys。
- Catalog 是「條件與既有覆蓋索引」，不是要求每個 Part 重新製造所有日期組合。每項能力先記錄真實
  業務前置條件、日期規則、最小必要邊界及目前哪些案件／stage 已涵蓋。
- 測試設計先查詢上游 stage、Route A／B、WP56 adoption、33／50 案及已配置 scenarios；已有資料且
  lineage／oracle 足夠就直接採用。只有條件未被涵蓋時，才在對應 Part 補規格、allocation 與資料。
- 不因技術上能跨月、跨季或跨年就自動增加案例；只有正式業務規則、實際操作、歷史事故或已知風險
  需要時才列入 acceptance。
- 各 Part、fixture、seed、runner、browser test 不得自行使用系統現在時間或未登錄日期。相同
  scenario/stage release reset 後必須得到相同月份、季別、逾期與 holiday 結果。
- 案件編號的建立年度、來源事件年度、服務年度、付款月份及補助季別是不同概念；不得因服務跨年
  改寫案號，也不得以案號年度直接推測所有帳務／補助歸屬。

### 6.2 Requirement-driven coverage record

每項測試需求至少記錄：

- `business_condition_id`、操作者與真實業務原因。
- 必要 root facts、日期／期間條件及正式規格來源。
- 上游 stage／既有 case／fixture／receipt 的候選覆蓋。
- `covered`、`partially-covered`、`missing`、`not-required` 或 `live-drift` 判定。
- 若已涵蓋：adoption mapping、oracle 與不可破壞條件。
- 若未涵蓋：應補規格的 owning Part、資料需求、route、案號／master allocation 及 acceptance。

下表是已知現實條件與檢查方向，不代表每格都要新增獨立案件：

| 項目 | 真實條件與 coverage 檢查 |
|---|---|
| Current Import | 同檔 replay、retry、來源未來日期等實際 import 規則是否已有資料 |
| Historical Import | 實際歷史年份、各來源 cutoff／overlap、unknown source time 與過去髒資料是否已涵蓋 |
| Historical Orders | 來源真的存在的取消／完成／洽談中、缺日期與矛盾日期，不補造不存在的歷史狀態 |
| 預約／配對 | 懷孕期間先預約，預計服務開始與建檔／配對可能相隔 10 個月以上；驗證未來檔期與資料變更 |
| 正式服務／排班 | 單案預計／正式服務區間最多 60 天；只依實際需要涵蓋跨月、假日、buffer、請假／代班 |
| 契約／收款 | 簽署、訂金及期款的真實到期關係；有跨月／跨年業務才補相應案例 |
| 月嫂應付 | 依實際服務與應付月份核對；只需覆蓋資料集中實際出現的月份及已知跨月／補發情境 |
| 政府補助 | 依名冊與申報實務檢查前年、今年、明年及相關季別；先採用既有案件，缺季別／狀態才補 |
| 異常監控 | 依真正有期限或掃描 predicate 的項目測到期前後與 reopen，不為無時效項目製造 overdue |
| 文件／archive | 依 document version、supersede 與實際 retention 規格；storage 未裁決前不臆造年限 |

### 6.3 Historical time corpus

- Historical dirty fixtures 必須明列 `source_effective_at`、`source_recorded_at`、`ingested_at`；未知值
  使用 typed unknown，不以 reset time／ingest time補值。
- 最低包含民國／西元混用、年份只有二／三碼、Excel serial date、文字月份、`24:00`、閏日、非法
  日期、end-before-start、跨年區間及缺 timezone 的 datetime。
- Historical cutoff 由資料類型分別配置，不能讓 HCM、BeClass、Staff、Orders、Finance 共用一個
  未經業務確認的日期。
- Historical Adoption 只保存可證明的時間事實；缺少當時 policy/version 時保留 evidence/review，
  不套用 current policy 反算歷史結果。

### 6.4 Government Subsidy multi-year matrix

政府補助 Part 必須至少建立相對於 `validation_reference_year` 的：

- 前年：歷史已送件／已核准／已撥款、遲延撥款、reversal 或 unresolved evidence。
- 今年：Q1～Q4 Draft／Submitted／Approved／partial/full funding 及當期修訂。
- 明年：符合服務事實但尚未到可送件時點、future planning／eligibility blocker，不得提前形成已送件或已付款。
- 跨年服務：服務日期跨 12／1 月，依正式規格進正確季度／年度，不遺漏、不重複。
- 跨年度撥款：claim year 與實際 receipt year 不同，仍保留 claim identity、allocation 及會計期間事實。

每個年度／季別都要逐案 expected manifest、item count、total amount、included/excluded reasons 及名冊
digest；但先審核既有資料是否已涵蓋。只有缺少必要年度、季別或狀態時才補規格與資料，不要求
為每個年度／季別排列製造無業務意義的組合。只驗證單一 2026 Q3 或總額仍不足以完成驗收。

### 6.5 最小充分資料集與停止新增條件

- 不設定固定案件總數，也不要求每個 assertion 都新增一案。每筆新增案件必須對應尚未覆蓋的真實
  `business_condition_id`，並在 catalog 說明為何不能 adoption 或補強既有案件。
- 判斷順序：先查既有案件是否具備全部必要條件；部分具備時先判斷能否以正式後續流程補足；只有
  lineage／狀態／隔離需求不允許採用時才建立最小新案件及必要專屬 master。
- Lineage 不明／污染、互斥狀態需同時比較、共享 occupancy 會被改變、身份／資格／地區／時間條件
  不同、歷史 cutoff 不同、identity/LINE/bank conflict 或會破壞既有 oracle 時，才構成新增理由。
- 顯示文字／排序、既有 root conditions 相同、same-command replay/stale/conflict、同檔 duplicate、
  同 Alert timeline、reset 後可重複操作或只為增加筆數，都不構成新增案件理由。
- Part 在所有必要 conditions 已 `covered` 或有明確 blocker，代表性 happy/blocked/repair/failure paths
  可由 DB/API/UI oracle 驗證，且新增資料不再增加業務語意時停止新增。
- 剩餘問題若是 infrastructure、功能缺失或正式規格未決，必須記為 gap/blocker，不能以增加假資料
  掩蓋。

### 6.6 個資、金融敏感資料與外部收件人安全

- 姓名、電話、地址、身分證字號、銀行帳號及其他可識別資料一律使用虛構或已去識別內容；只有
  parser／business rule 確實需要時，才建立格式及檢核碼合法的 synthetic value。非法輸入案例必須
  明確標示預期錯誤，不得混入正常 master pool。
- 案件編號、銀行帳號及虛擬帳號由中央 catalog 配置並驗證衍生值碰撞；不得使用來源不明或可能
  對應真實收付款人的帳號。
- LINE、Email、簡訊、電子簽署與付款收件人只能使用 test adapter 或保留的測試 namespace；任何
  runner 在 preflight 無法證明隔離時必須 fail closed，不得實際聯絡或付款給第三人。
- 歷史髒資料 fixture 應保留前導零遺失、Excel cell type、空白欄、混合日期格式、重複列等問題的
  資料形狀，但內容必須重新合成；不得直接提交歷史正式附件或原始個資。
- Fixture、log、receipt 及下載驗收摘要只保留最小必要去敏內容，不得包含完整帳號、secret
  或可回推自然人的欄位組合。
- 每份測試資料資產必須在 manifest 標示 `synthetic`、`deidentified` 或 `invalid-by-design`，並記錄
  產生方式、允許用途及 redaction policy；既有 WP56、validation assets 與現有 DB 需先完成敏感
  資料唯讀盤點，來源或安全性不明者不得直接升格為 current canonical fixture。

### 6.7 內部使用者同權限與測試邊界

- 依 2026-08-12 最新人工裁決，所有已登入且 enabled 的內部使用者具有相同業務功能權限；保留
  authentication、actor identity、session 與 audit，不建立 role／capability 差異資料。
- 各 Part 不建立有權／無權角色、職責分離、dynamic grant／revoke 或依職稱顯示不同功能的 UI
  scenario。跨流程仍保存實際操作者與前後狀態，但操作者不同不改變可用業務功能。
- 測試至少確認未登入／session 無效者不能操作、enabled 使用者可使用相同功能，以及 mutation 的
  actor、reason、time、版本與結果可稽核。這是 authentication／traceability 驗收，不是 RBAC 驗收。
- 外部服務認證、SystemPrincipal 命令 allowlist、資料庫 target、production safety、secret 與
  Preview／Confirm／Apply 仍是獨立安全門禁，不因內部使用者同權限而取消。

### 6.8 Browser 自動化與 LINE 真人介面驗收

- 所有可由網頁完成且 UI 證據為 `required` 的業務操作，都由 Browser 自動化實際點擊、輸入、送出、
  重新整理並觀察畫面；不得以直接呼叫 API 代替 UI 操作。
- Browser 驗收聚焦使用者可見的欄位、按鈕、提示、狀態轉換、錯誤引導、列表／月曆內容及實際上下載。
  API／DB oracle 只有在 applicability matrix 判定必要時由 pytest／專用 verifier 另外執行，不綁進每個
  Browser script。
- 一般後台 UI 仍以 Browser 自動化為正式可重跑路線。人工操作瀏覽器只用於腳本除錯、觀察或補充
  確認，不另形成 manual-only 流程或競爭 receipt。
- LINE client 是明確例外：須由真人以專用測試 LINE 帳號操作實際 App，逐項確認訊息內容、版面、
  按鈕、LIFF／Rich Menu 導向與回覆。人工驗收只在 checklist 記錄日期、測試帳號代號、訊息／模板
  版本及 pass／fail，不要求保存 LINE 截圖或影片，也不得使用一般客戶／月嫂正式帳號。
- 各 Part 的 UI execution mode 只能是 `browser-required`、`browser-file-dialog-assisted`、
  `browser-blocked` 或 `not-applicable`。
- 上傳一律使用 canonical fixture；Browser 可直接指定檔案時不開啟 OS 選檔視窗。只有原生檔案／
  資料夾選擇器無法由 Browser 控制時，才允許人工選擇 manifest 指定的 fixture／隔離目錄，並標記
  `browser-file-dialog-assisted`；其餘 UI 步驟與結果仍須自動化。
- 下載必須實際取得檔案，優先使用固定隔離的測試下載目錄；若 OS 強制人工選擇資料夾，只協助該
  邊界。後續檔名、格式、內容、筆數、金額、digest 與 forbidden mutation 仍自動驗證。
- Browser script 使用穩定 business locator 或 test locator，不依賴畫面座標或脆弱 CSS。缺少穩定
  locator、可控下載目錄或檔案攔截能力時標記 UI infrastructure blocker。
- 截圖、錄影、Browser trace、console log 與 network log 不作正式驗收產物，也不要求長期保存。
  執行期間如為除錯暫時產生，僅放 `scratch/`／`logs/`，不得提交 Git；完成診斷後不納入 canonical release。
- Worker、outbox、callback、retry、timeout、冪等及 provider failure 組合由 pytest 驗證；Browser 只需
  驗證正式 UI 已提供的正常互動與使用者可見結果，不為後端機制製造複雜等待或 failure matrix。

#### 可交接重跑的 UI 測試清單

UI 驗收的長期正式產物是文字化、可由其他 Agent 重跑的 checklist，不是視覺錄製。每一項至少記錄：

- Part、scenario ID、業務目的與適用工作區。
- 使用的 published baseline、fixture／案件編號及必要前置狀態。
- 按實際操作順序排列的 Browser 步驟、輸入值及檔案選擇位置。
- 每個必要 checkpoint 應看到的狀態、欄位、提示、列表／月曆結果與後續頁面結果。
- 實際下載時應驗證的檔名、格式、內容條件、筆數／金額摘要；不保存下載檔複本作 UI 證據，canonical
  expected／fixture 另依其資料契約管理。
- 可接受的檔案對話框人工協助、已知 blocker、失敗分類及應從哪個 baseline 重跑。
- 最終 `passed`／`failed`／`blocked` 摘要、執行版本與時間；不附截圖、影片或 trace。

清單必須避免依賴只有原執行者知道的畫面座標、臨時資料或 session，讓另一個 Agent 能從指定 reset
baseline 依序再操作一次並得到相同結果。

#### UI checklist canonical directory

最終 UI 重跑清單固定集中於 `validation/ui_business_workflows/`，不得散落至文件目錄、root、receipt
目錄或 Agent 私有筆記。建議結構：

```text
validation/ui_business_workflows/
├─ README.md
├─ checklist_manifest.yaml
├─ part_01_import/
├─ part_02_import_review/
├─ part_03_case_management/
├─ part_04_staff_matching/
├─ part_05_staff_contract/
├─ part_06_client_contract/
├─ part_07_finance_import/
├─ part_08_client_reconciliation/
├─ part_09_scheduling/
├─ part_10_service_completion/
├─ part_11_staff_payables/
├─ part_12_staff_payout/
├─ part_13_government_subsidy/
├─ part_14_anomalies/
├─ part_15_documents/
└─ part_16_end_to_end/
```

每個 Part 目錄包含 `README.md`、`checklist.md`、`expected.yaml`、`result_summary.md`，以及只有該 Part
專用時才建立的 `fixtures/`。共用 fixture 只引用 canonical source，不複製。Root manifest 記錄執行順序、
Part／scenario ID、前置 stage、checklist 路徑、使用案件、Browser execution mode、狀態及下游依賴。

Part README 只說明業務範圍、前置 baseline、覆蓋條件及 out-of-scope；checklist 只提供可操作步驟；
expected 只保存可機器比對的預期。正式規格仍是業務語意 SSOT，checklist 不得另行發明規則或形成
競爭規格。其他 Agent 應能從此目錄的 README 與 manifest 開始，無須搜尋散落文件即可依序重跑。

#### Checklist maintenance

- UI 功能、正式業務流程、使用者可見結果或必要前置條件改變時，同一開發工作必須更新對應 Part
  checklist、expected 與 manifest linkage。
- 純內部重構且 UI 操作／結果不變時不修改 checklist；locator 改變但業務流程不變時，只更新 Browser
  script／locator mapping，不改寫 checklist 的業務描述。
- 測試案件或 baseline 被 supersede 時，更新 manifest identity／lineage 與必要引用，不重寫無變更的
  操作內容，也不得修改舊 historical result 的意義。
- 執行時遇到規格不明，標記 `specification-gap` 並停止猜測 expected；由正式規格裁決後再更新清單。
- 每個 Part 完成時整理一次 checklist 與 result summary，不因每次重跑建立文件版本；最終收尾才依
  manifest 執行完整清單並更新各 Part `result_summary.md`。
- WP56 receipt 持續為 immutable historical evidence，不因 current checklist 建立、更新或通過而修改、
  刪除或改算 current pass rate。

### 6.9 Part 依賴分級與 blocker 傳播

- 流程仍按真實業務順序執行，但任一 scenario 失敗不自動凍結全部 Part。Scenario manifest 必須把
  前置條件分類為 `hard-dependency`、`soft-dependency`、`independent-lane` 或 `global-dependency`。
- `hard-dependency` 缺少必要上游根事實時，只停止受影響案件及其下游。例如 Import 未建立正式案件
  不能配對，客戶合約未完成不能建立正式 Assignment；不得直接 seed 下游狀態繞過。
- `soft-dependency` 失敗時，可改用 catalog 中另一筆已由正式流程形成合法前置狀態的案件繼續，receipt
  必須記錄替代 identity 與 lineage，不能把替代案冒充原案修復完成。
- `independent-lane` 與失敗根事實無直接依賴，可繼續驗收。歷史 dirty Import review 不必阻擋另一筆
  已正式匯入案件的配對或不相依的文件基礎建設測試。
- `global-dependency` 如 DB reset、schema bootstrap、登入、Browser runtime 或安全隔離失敗，暫停所有
  依賴該基礎建設的 scenario，並記錄 global blocker。
- 個別 scenario 可在同 stage 內繼續產生診斷證據，但任何 `required` scenario 未通過或為 blocked 時，
  該 stage 不得 published。這是 stage publication blocker，不等於禁止所有獨立測試工作。
- 每個 Part 必須記錄必要前置 stage／案件狀態、可用替代案件、失敗影響的下游 scenario、是否阻擋
  stage 發布，以及修復後應從哪個 published baseline 重跑。

### 6.10 Browser UI 驗收粒度

- Browser scenario 以一段完整、真實且可由操作者理解的業務操作為單位，不為每個欄位、按鈕、
  component 或 CSS 狀態建立獨立 E2E。
- 每段適用流程至少驗證：能找到目標案件／業務項目、主要狀態／日期／金額／人員正確、可完成操作、
  成功或失敗提示可理解、重新整理後結果仍存在，以及後續工作區顯示應出現的結果。
- 純外觀的顏色、間距、排序動畫與像素差異不逐項驗證；只有會造成誤判、無法操作、資訊遺漏或正式
  UI 契約明確要求時才納入 Browser assertion。
- 同一功能的大量格式、邊界輸入與後端 failure combinations 由 pytest 負責；Browser 只選具有真實
  業務意義且能增加 UI 覆蓋的代表性正常、阻擋及修復流程。
- 同一跨頁業務流程優先形成一條具有清楚 checkpoint 的 Browser scenario；只有需獨立 reset、會互相
  污染、失敗診斷困難或可獨立重跑時才拆分，不以頁面或按鈕數量決定腳本數。

### 6.11 統一失敗分類與重跑入口

Scenario 失敗不能只記 `failed`，也不能預設為測試資料不足。每筆失敗指定一個 primary category，
必要時另列 secondary impacts：

- `product-defect`：UI 或正式業務功能不符合規格。
- `test-data-gap`：缺少必要案件條件、前置狀態或 fixture。
- `infrastructure-gap`：Browser runtime、DB reset、環境、檔案上下載等共同能力不足。
- `automation-defect`：locator、等待條件或 Browser script 本身錯誤／過期。
- `specification-gap`：現有文件不足以裁決 expected result。
- `live-drift`：live code／schema／DB／UI 與已確認規格不一致。
- `external-blocked`：缺少適用的測試 Adapter，或需要已允許的檔案選擇協助但尚未完成。
- `upstream-blocked`：必要的上游流程、published baseline 或根事實尚未具備。

失敗紀錄至少包含 Part、scenario、案件／業務 identity、最後成功 checkpoint、expected、observed、
primary category、secondary impacts、是否阻擋 stage 發布、修復責任範圍，以及修復後應從哪個 published
baseline 重跑。分類本身不改變 blocker propagation，仍依 6.9 判斷影響範圍。

### 6.12 金額條件與 UI 驗收

- 本系統測試金額一律為整數，不建立小數、四捨五入、浮點誤差或幣別換算 scenario，也不建立歷史
  費率版本問題。Expected 與 UI 顯示均以正式整數金額表示。
- 合約金額、訂金、尾款、月嫂薪資及補助金額須由案件的正式服務條件與業務流程形成；不得為方便
  測試直接修改應收、應付、核銷、補助或其他 projection 使總額對上。
- Checklist 記錄必要輸入條件、操作前後及下游工作區應顯示的整數金額，不在 Browser script 重算
  公式。精確公式及大量邊界由 pytest 驗證，Browser 聚焦顯示與互動結果。
- Requirement coverage 依實際業務至少盤點正常全額、分次付款、少匯／補匯、溢匯／無法自動歸類、
  調整／沖正、跨月月嫂應付及跨季／跨年度補助；先採用既有案件，缺少必要條件才新增。
- 同一筆業務金額在合約、應收、銀行核銷、月嫂應付及補助之間依各 owning Domain 正式規則銜接，
  expected manifest 記錄必要逐筆金額、合計及 included／excluded reason，以驗證無遺漏、重複或誤期。

### 6.13 正式欄位用詞與 UI 文案一致性

- UI checklist 不自行翻譯或發明欄位。訂單基本日期／天數依現有正式文件使用：`due_date`「預產期」、
  `start_date`「預計開始日期」、`service_days`「希望服務天數」、`actual_start_date`「服務開始日期」。
- 「預計服務期間」、「規劃服務日」、「正式服務日期」及「總服務天數」不得被當成這組訂單基本
  欄位，也不得因測試清單用詞而要求新增 schema。排班逐日事實須在 Scheduling Part 依其正式契約
  另外辨識，不與訂單基本資料混用。
- 實作各 Part 時同步盤點對應 UI、文件模板與下載文件的顯示文案；同一正式欄位若出現「預計開始日／
  預計開始日期」或「服務天數／希望服務天數」等漂移，統一為上述正式中文名稱。
- 文案統一只修改 presentation／template label 與相應 Browser checklist，不改欄位 identity、schema、
  Domain 語意或既有資料。若現有文件對同一欄位具有不同且明確的業務語意，標記 `specification-gap`
  取得裁決，不自行合併。

### 6.14 跨 Domain 狀態分離與狀態文案

- 案件同時具有 Orders、Matching、月嫂合約、客戶合約、Client Finance、Scheduling／服務、Staff
  Payables／Payout、Government Subsidy 及 Anomalies 等各自狀態；不得用單一案件「完成」標籤代替。
- 各 Part 實作前先依正式規格、schema enum／root event、typed API view 與 mounted UI 建立
  `Domain state value → 正式中文文案 → 出現工作區` 對照。Live 現況不得反向覆蓋正式狀態語意。
- Browser checklist 必須驗證該操作實際影響的各 Domain 狀態及後續工作區結果；同名 technical value
  位於不同 Domain 時仍保持不同 identity，不合併成共用案件狀態。
- 同一 Domain state 在不同頁面應使用相同中文文案。實作時可統一純 presentation label，但不得因此
  新增 schema enum、狀態、轉換或旁路修改 root fact。
- UI 若把不同 Domain 狀態混為單一標籤，依證據分類為 `product-defect` 或 `live-drift`；找不到正式
  中文名稱時標記 `specification-gap`，不得由 checklist 作者臆造。
- 代表性驗收須保留正交狀態，例如訂金核銷後 Orders 可為「訂單成立」，客戶合約仍為「等待客戶
  簽回」，Scheduling 尚未形成正式指派；不得因其中一項成功就宣告整條流程完成。

### 6.15 UI 錯誤、阻擋訊息與警示中心

- Browser 不逐字鎖定完整中文句子，而驗證訊息出現在正確工作區與時機、受影響 identity 可辨識、
  使用者能理解問題與被阻擋操作，並提供實際可用的修復入口或下一步。
- Checklist 驗證穩定的 typed blocker／Alert category、必要關鍵資訊及修復導向；完整 error code、API
  payload、邊界組合與 reducer 行為由 pytest 驗證。純技術錯誤不得顯示 traceback、SQL、secret 或
  raw exception。
- 警示中心必須納入各適用 Part 的 Browser 流程：先確認錯誤資訊、案件／來源、狀態與修復入口正常
  顯示；再由正式 UI 流程排除根因、重新整理或重新查詢，確認對應 active Alert 正常消失或轉為已解決。
- Alert 消失必須源於根因已排除及正式狀態更新；不得以關閉提示、隱藏列、前端暫態或直接改 DB 冒充
  解決。根因仍存在時，Alert 應保持 active，或依正式 monitor 規則重新出現。
- 相同 root issue 不應產生無法區分的重複 active Alert。歷程、reopen、auto-resolve 與去重的完整狀態機
  由 pytest 驗證；Browser 只測具有代表性的顯示→修復→消失，以及規格要求時的未修復仍顯示流程。
- 修復後除警示中心外，也要回到原工作區確認 blocker 已解除、原操作可繼續或資料狀態已正確更新。

### 6.16 UI 列表、查詢、篩選與導向

- 不建立所有 filter／sort／pagination 的排列矩陣；各工作區只驗證實際業務會使用的代表查找方式。
- 適用 Part 至少依需求驗證：案件編號查案、客戶／月嫂相關資料、待處理狀態、月嫂應付月份、補助
  季度／年度、未核銷／待審核項目及 active Alert。不存在於目前 UI 的搜尋維度不得因測試而新增。
- 套用篩選後應只顯示符合項目，清除後恢復原清單；存在分頁或大量資料時，目標項目仍須可由正式
  查詢方式找到，不要求 Browser 逐頁掃描。
- 警示中心、訂單總覽及其他工作區提供的 deep link／navigation 必須帶到正確案件、月份、清冊或
 修復面板；Browser 驗證抵達後 identity 與必要 context，不只驗證連結可點。
- 排序只在影響實際工作順序時驗證，例如警示建立時間、應付月份或正式規格定義的待處理順序；純
  顯示偏好不納入驗收。
- 搜尋字串邊界、特殊字元、完整 pagination 組合與 query performance 由 pytest／專用 verifier 負責；
  Browser 使用 checklist 指定的真實代表資料。

### 6.17 UI 資料修改與修正流程

- 完整業務流程必須涵蓋真實需要的資料修正，不只驗證新增與完成狀態。Browser 先找到正確 identity、
  確認原值，再由既有正式 UI 編輯或 Preview／Confirm／Apply 入口操作。
- 只修改正式規格與目前功能允許變更的欄位；不得假設所有欄位可在任何狀態修改，不新增 generic
  editor，也不得直接 UPDATE DB 作為 UI 驗收步驟。
- 成功後重新整理確認新值持續存在，並到相關工作區確認顯示同步。若既有合約、核銷、排班、帳務或
  補助受影響，依正式規則驗證重送、重算、阻擋、修復或禁止修改的使用者可見結果。
- 代表性 Browser checklist 至少依適用性涵蓋正常修改、狀態阻擋修改及修復後重試；同值未變更不應
  讓 UI 顯示已產生無意義的新業務結果。
- 修改操作的 actor、reason、time 與結果應可由既有 audit 入口追溯。欄位 allowlist、state guard、
  stale version、same-payload replay、rollback 與事件精確性由 pytest 驗證。

### 6.18 取消、作廢、沖正與修訂

- UI 業務流程納入正式規格已存在的案件取消、配對取消／更換月嫂、合約作廢重建、收款沖正、月嫂
  付款調整／補匯、補助名冊修訂／排除／撥款沖正，以及其他 owning Domain 明確定義的反向處理。
- 沒有正式 Command、state transition 或 mounted UI 入口的反向操作，不因測試自行新增，也不得以
  direct DB update、刪除或覆寫原紀錄模擬完成。
- Browser 驗證能找到原始資料、理解影響、完成必要確認，並在原工作區及適用下游看到取消、失效、
  餘額重開、替代 identity、修訂或重新處理狀態。原始紀錄與歷程必須仍可追溯。
- 正式規則允許反向處理後重新開始時，至少選一個有真實業務意義的代表 repair path；不要求每種反向
  操作排列所有後續組合。
- 金額／服務日守恆、append-only event、版本、冪等、stale、rollback 及禁止刪除由 pytest 驗證；
  Browser 聚焦使用者可見的影響與可繼續操作性。
- 各 Part 先盤點 WP56、現有 DB 與前段 published baseline 是否已有可採用的反向狀態；只有必要條件
  未涵蓋時才新增最小 scenario。

### 6.19 各 Part 獨立案件為主、單一代表案件完整 E2E

- 測試資料設計以各 Part 使用不同且最適合該業務條件的案件為主；不要求單一 mutable case 承擔
  Import、阻擋、取消、付款差異、補助跨年及所有其他互斥狀態。
- Part 案件依中央 catalog、最小充分資料集與 dependency 規則採用既有資料或補足缺口，並保護其他
  Part 的前置狀態；可共享 canonical master，但不得交叉污染 scenario root facts。
- 另保留一個合法九碼的代表性 E2E 案件，從 Import 依正式 UI 業務順序走到所有對該案適用的最終
  流程，用來證明跨 Part 串接。它只需是現實且完整的正常案例，不負責涵蓋所有例外與邊界。
- E2E 案件若依法／依業務不適用補助或其他支線，應驗證正確排除結果，不為追求「走過所有頁面」
  人工改造資格。只有真實適用的流程才納入該案。
- Part 16 必須從 clean reset／published baseline 實際重播該 E2E 案件，不能把不同 Part 的結果摘要
  拼接後宣稱單案完整通過。各 Part 開發期間仍可使用 Route B 既有 DB 補強。

## 7. 資料庫、reset 與外部副作用安全

### 7.1 Database target

- DB 名稱不作業務契約；`union_db` 或其他名稱是否可 reset，由明確註冊的 environment/target profile
  決定，不以單一名稱前綴假定安全。
- profile 至少綁定 environment、host、port、database、用途、可否 reset、允許的 fixture/scenario
  release、schema release 及 operator confirmation policy。
- database 與 explicit confirmation 必須完全相同；runner 必須驗證 environment、local/isolated host
  allowlist、connection identity 及 profile registration。
- 禁止 fallback 到預設 host、user、password 或 database；secret 不可進 command evidence。
- 清空、刪除或重建現有 validation DB 每次都需人工明確確認；normal runner 只能新建，不能 overwrite。

### 7.2 Developer DB reset contract

Reset 工具只負責：

```text
Reset DB
→ Restore／Replay 資料夾內選定的 baseline
→ 完成
```

- 操作方式沿用根目錄 `reset_DB.bat`：使用者直接開啟，不需輸入參數、選擇 target DB、選擇 baseline
  或說明用途。
- Target DB 與預設 baseline 由版本控制中的單一 developer-reset manifest 固定；bat 只呼叫正式 reset
  runner，不在 bat 內重複定義資料規則。
- 有 snapshot 就 restore；沒有 snapshot 才依同一 baseline manifest replay。
- 不建立 working session、操作目的、evidence workflow 或 promotion workflow。
- 不自動把 reset 後的 DB 回寫成 snapshot、catalog、receipt 或新 baseline。
- Reset 完成只表示資料已恢復；baseline 的 verifier 與 promotion 在 artifact 建置／發布時完成，
  不混入一般 reset 操作。
- reset 失敗就回報失敗；使用者可再次執行 reset，不增加額外 recovery 狀態機。
- 目前 `reset_DB.bat` 零參數開啟時會自動將本機 `union_db` reset 成固定 v3 fixture，操作模式保留；
  後續只把固定來源改為 developer-reset manifest 指向的 canonical folder baseline。

### 7.3 External adapters

- LINE 自動化使用 validation adapter，且另以專用真人測試帳號連接實際 LINE provider 做介面與訊息
  驗收；不得傳送給一般客戶／月嫂或使用正式業務群組。email/SMS、電子簽章 provider、實際銀行
  付款及政府正式送件仍使用明確 validation adapter，不得觸及真人、正式帳戶或正式政府系統。
- validation adapter 保存去敏 recipient identity、payload digest、intent、attempt、acknowledgement、
  success/failure/timeout、retry 及 outbox/job linkage，不得把測試成功冒充 production 成功。
- Excel／銀行對帳單匯入、合約文件產生、測試 archive、下載／預覽及 XLSX 清冊實際執行。
- provider timeout、duplicate acknowledgement 及 worker retry 仍透過 committed outbox/durable job 驗證。

### 7.3.1 LINE 管理中心與訂單狀態自動推送

- LINE Part 的主要目標是確認 LINE 管理中心的訊息模板、預覽、啟用／停用、測試發送、delivery
  task／attempt、失敗重試、Rich Menu、LIFF、身分綁定、客服回覆與操作紀錄功能實際有效。
- 每個管理中心功能先以 Browser 操作，再由專用真人測試帳號確認 LINE App 實際結果；只驗後台顯示
  「已發送」不足以通過。LINE App 的文字、變數代入、按鈕、版面、連結及回覆結果都須逐項確認。
- 未來新增「依訂單狀態自動推送」前，須先核准 machine-readable mapping：明確的 owning Domain
  事件／狀態轉換、recipient role、固定 template identity＋revision、變數契約、觸發時機、去重 identity、
  不發送條件及 supersession。不得依 UI 中文狀態、輪詢畫面或自由文字猜測推送。
- 驗收矩陣必須逐一覆蓋所有核准的狀態／事件 mapping：建立正確且唯一的 delivery task、綁定正確
  收件人與固定訊息版本，真人收到的內容正確；不適用狀態不發送，重播不重複，狀態快速連續變更
  依正式 supersession 規則處理。
- 訊息模板修改須形成新版本；既有 delivery／歷史訊息仍指向當時版本。停用或缺少 mapping 時 fail
  closed 並產生可操作警示，不得退回任意預設文字。

### 7.4 銀行對帳單與帳務核銷驗收

- 使用版本化、去敏的測試銀行對帳單，實際經正式 upload／Import／normalization／classification／
  Preview／Apply／owning Domain reconciliation，不能只 mock parser 或直接 seed ledger。
- 每筆銀行列驗證 canonical bank fact、direction、amount、source identity、classification、allocation、
  receipt、remaining amount、alert/review outcome 及 same-file replay。
- 正常入款必須實際證明客戶訂金／期款能正確核銷；月嫂付款與政府撥款測試列則由對應 Domain
  正式核銷，不由 Finance Import 自行改狀態。
- 少匯、溢匯、重複、格式錯誤、identity 歧義、退匯及 reversal 使用髒資料／邊界 fixture 驗證，
  並證明一元不消失、不重複及 alert 只在根因消失後解除。
- 銀行不會提供更正版對帳單；後續只會匯入下一期對帳單。已匯入流水的原始金額、日期、方向、
  摘要及來源 identity 不得覆寫，新一期流水也不得取代舊流水。
- 無法自動判斷時由人員在 UI 選擇案件、帳款類別及應收項目，經 Preview／確認後手動銷帳；能辨識為
  非業務流水時，選擇正式存在的非業務分類，不強迫配到案件。
- 暫時無法判斷的流水保持待處理並出現在警示中心。人工銷帳完成後，應收餘額更新且警示正常消失；
  已銷錯帳時必須先走正式沖正，再重新核銷至正確項目，不能直接改寫原 allocation／ledger。
- Browser 至少驗證待人工處理→手動銷帳→警示消失、錯帳沖正→重新核銷、無法判斷持續待處理，以及
  下一期匯入後舊流水與處理歷程仍完整存在。精確 ledger 守恆與事件不可變由 pytest 驗證。

### 7.5 月嫂每月應付驗收

- 不執行真實付款，但必須由正式 assignment、服務日、Payroll obligation 及調整事件產生應付資料。
- 逐月驗證每位月嫂及全體的應付明細、金額加總、到期／付款月份與清冊顯示月份。
- 月份歸屬由 Staff Payables／Payroll 正式規格決定；測試 expected 不得在 UI 或 fixture 另造公式。
- 跨月服務、多 assignment、多月嫂、取消、雙薪、少匯 remaining、補發、退匯及 recovery 都要證明
  只出現在正確月份，且 original／remaining 不重複列入。
- 清冊下載不改變付款狀態；後續只有測試銀行結果的正式核銷可改變支付 projection。
- Browser 不只檢查待核銷與餘額歸零，也要從月份摘要進入已核銷歷程，核對月嫂、付款日期、銀行
  流水、核銷金額、應付款、案件／assignment、備註及核銷後剩餘金額。
- 一筆付款分配多筆應付款時，各 allocation 顯示加總等於付款金額；多筆付款清償一筆應付款時，各次
  allocation 加總等於已付金額。畫面須能核對 `原應付＝有效已核銷＋未付餘額`，正式 adjustment／
  reversal 另列，不得藏入一般付款總額。
- 少匯與後續補匯各自保留核銷歷程；退匯／沖正後原紀錄仍顯示失效或已沖正，不得從歷史消失。
  月份摘要分列應付總額、已核銷總額、未付餘額及調整／沖正金額，且依正式歸屬月份顯示，不因操作
  核銷日期任意移月。
- 客戶收款及政府補助撥款使用相同原則：不能只驗證「核銷成功」，也要核對已核銷明細、allocation、
  有效／失效歷程、剩餘餘額與期間摘要。精確跨事件守恆由 pytest／專用 verifier 驗證。

### 7.5.1 服務開始、服務日期異動與訂單完成驗收

- 正式指派成立後，才能在「服務開始確認」輸入「實際服務開始日」並走 Preview／Apply；尚未正式
  指派時必須顯示可理解的阻擋原因，不能由 UI 直接建立服務事實。
- 套用服務開始後，服務日期、正式指派與月曆必須同步顯示最新結果；重新整理後結果仍一致。
- 「確認服務日期」所確認的日期筆數必須等於「希望服務天數」。日期異動後，既有日期表必須重新
  發送並由客戶與月嫂重新確認，不能沿用異動前的確認狀態。
- 使用代表案件操作請假、代班與順延，核對服務日期、當日服務月嫂、月曆及後續月嫂應付款月份同步
  更新；服務總天數不得因異動遺失或重複。
- 全部正式服務日完成且沒有 blocker 前，訂單維持「服務中」；符合完成條件後才由正式自動完成流程
  進入「訂單完成」。完成案件仍保留於行事曆供唯讀查閱，且不得再取消。
- 若服務日期異動改變 `orders.actual_end_date`，後續月嫂應付款月份及政府補助歸屬季度必須分別依
  owning Domain 正式規則重新呈現；UI 不自行計算月份或季度。
- Browser 驗證可見狀態、Preview／Apply、重新確認、月曆連動與阻擋訊息；精確日期集合、總天數、
  completion instant、assignment／Payroll 重建及跨 Domain 不變量由 pytest 驗證。

### 7.6 政府補助季別名冊驗收

- 不對政府正式送件，但使用正式 planning/query workflow 產生季度／年度候選與 XLSX 名冊。
- 案件核銷季別以服務開始後最終確認的實際服務結束日期 `orders.actual_end_date` 判定：1～3 月為 Q1、
  4～6 月為 Q2、7～9 月為 Q3、10～12 月為 Q4。不得使用建檔日、預計開始日期、申請／送件日、
  核准日或政府撥款日改變案件所屬季別。
- Browser 必須使用接近季末／季初的代表案件，核對 UI 清單與下載 XLSX 都只出現在
  `actual_end_date` 對應季度；跨季服務依實際結束日歸入單一季度，不得在兩季重複列入。
- 政府撥款跨年度或晚於申請季度時，仍保留原案件的服務結束季別與 claim identity；入款日期只作
  receipt／會計期間事實，不回寫名冊歸屬。
- 逐季驗證 eligible cases、排除案件、assignment／official service facts、補助金額、item count、
  total amount、revision 及每案來源 identity，確保無遺漏、無重複、無跨季誤列。
- 案件跨季、資格不符、取消、服務未完成、補助 short/over payment、reversal 及工會墊付使用獨立
  expected；名冊產生或測試 submission 不得自行標示政府已核准／已付款。
- 每個季別 baseline 保存名冊 digest 與逐案 expected manifest，不能只驗證總額。

### 7.7 文件產生、封存與下載驗收

- 「使用者下載」與「系統封存」是不同責任。後台可由不同裝置登入；Browser 驗收只要求檔案能透過
  瀏覽器成功下載到當次操作裝置，並核對檔名、格式與必要內容，不規定或保存使用者端下載路徑。
- Browser 自動化使用測試執行器的暫存下載資料夾，驗證完成即可清理；不得把使用者端下載資料夾
  當成系統 archive，也不要求保留截圖、影片或下載測試產物供人工觀看。
- 只有具有持久業務證據語意的文件才要求系統封存，例如月嫂／客戶回傳契約及正式規格明定的不可
  變輸出快照。純查詢匯出若正式規格未要求封存，不得因測試方便自行升格為永久文件。
- 對必須封存的文件，驗證產生、archive 及下載 bytes 的 SHA-256、MIME、size、document version、
  actor 與 security audit 一致；archive failure 不得顯示成功或提供不存在的下載。
- 測試封存必須指向隔離的 validation storage，不得寫 production archive。測試 artifact 的保存與
  DB baseline／reset 契約分開；reset 不得誤刪正式或歷史封存文件。
- 系統 archive 必須透過可設定的 storage port 使用穩定 storage key，不能讓 Domain／UI 依賴某台
  裝置的絕對路徑。本機部署可使用指定資料夾；雲端部署可改接 persistent volume／object storage，
  並維持相同 digest、不可覆寫、讀回驗證及 audit 契約。
- 正式部署的 storage provider／root、容量、retention、備份、還原、加密及 orphan cleanup 尚未裁決，
  標記 `human-decision-required`；Part 06／Part 13 實作前提出選項供人工確認，Part 00 不猜正式路徑。

## 8. Seed、runner、projection 與 oracle 邊界

### 8.1 允許 seed

- 經核准的 master/root facts。
- 原始或正規化前的外部輸入 fixture。
- validation-only provider configuration 與 actor/capability roots。
- failure injection plan；不得寫入 production table 冒充已發生 failure。
- 依既有真實問題最小化、去敏後建立的 dirty-data external input corpus；保留 cell type、sheet/layout、
  representation error 與 source lineage，但不得包含真實個資、完整帳號或未授權原始附件。

### 8.2 禁止直接 seed

- Orders lifecycle status、contract completion、assignment schedule、payroll／payable projection。
- Client／Staff／Government ledger、allocation、settlement、recovery 結果。
- current alert、resolved/reopened projection、receipt、outbox、durable job terminal state。
- cache、view、summary、current occupancy、下載結果或 UI session state。

所有 derived state 必須由正式 workflow／projector 建立。若某歷史資料無法由 root 唯一重建，進
inventory `unresolved`，不得由 seed 猜值。

### 8.4 Historical／dirty-data fixture contract

- historical import、preserved DB migration、current import、reconciliation 與 current correction 是五種
  不同 execution intent，不得共用一個 generic apply command。
- 每個 dirty fixture 必須連結 `source_problem_id`、format profile/version、去敏方式、sheet/header、
  cell representation、expected row outcomes、typed issues、side-effect policy 及 fixture digest。
- 真實附件只作受控 format evidence；repository fixture 使用最小 synthetic workbook，不複製真實個資。
- Historical Orders v1 只接受已確認的 `0→取消、1→完成、2→洽談中`；blank、unknown 或矛盾值進
  review，不使用預設值，不補造現行狀態機事件。
- historical row 保存 `source_effective_at`、`source_recorded_at`、`ingested_at`；時間未知要明示，
  不得用 ingest time 冒充事件發生時間。
- historical lane 預設 suppress current notifications、obligations、matching、schedule、payment 或 subsidy
  side effects；只有逐 Domain 核准的 HistoricalAdoption 才能建立 canonical history。
- 同 source identity 落入 current/historical cutoff overlap 時整批 fail closed，進人工 resolution。
- 每個 fixture 驗證 row-outcome 守恆及零 partial business graph；schema/format failure 與 row validation
  分開，不得因 failure audit table 也缺失而覆蓋原始 typed cause。

### 8.3 Oracle 規則

- DB oracle 同時檢查 expected roots/events/projections 與 forbidden/zero-partial-write rows。
- 對 assignment、schedule、allocation 等集合，以 canonical identities 和完整集合比對，不只比數量。
- API oracle 驗證 typed model；不得依 message 字串判斷。
- UI oracle 使用與操作者相同的 mounted entry point，先 re-query，再操作 Preview／Apply。
- replay 比對 receipt identity 與 row delta；stale/conflict/rollback 必須明列預期 error 和零寫入集合。

## 9. Receipt 契約

每個可宣稱通過的 scenario receipt 至少記錄：

- contract、scenario ID/revision、Part、result、executed time、BusinessClock。
- Git revision；dirty worktree 時另記所有直接輸入 artifact digest，不能只記 HEAD。
- runner identity/revision、execution mode、database identity（不得含 secret）。
- fixture、scenario、expected、schema release、runner 的 path 與 SHA-256。
- command lineage、observed root identities、assertion count 與逐項結果。
- DB/API/UI oracle 結果、replay/stale/conflict/rollback 結果。
- external adapter mode、outbox/job observation、skip／blocker／live-drift。

只允許 `passed`、`failed`、`blocked`；`blocked` 不等於 pass。歷史 UI narrative receipt 若不符合本
contract，只作 evidence link，不得放入 current passing receipt 集合。

## 10. 現有 33 案 inventory 契約

Part 00 後續只讀 inventory 必須逐一輸出：

| Field | Meaning |
|---|---|
| case identity | canonical case/import identity，不只 auto-increment ID |
| observed database | DB identity 與唯讀觀察日期 |
| source lineage | seed/runner/receipt/unknown |
| candidate Part/scenario | 最可能歸屬；不唯一時標 unresolved |
| root completeness | 是否有足夠 roots 可重建 |
| current states | Orders、contract、scheduling、finance、payable、subsidy、alerts 摘要 |
| drift | duplicate generation、orphan、projection mismatch、receipt mismatch |
| rebuildability | reproducible／partial／not-reproducible／unknown |
| disposition | retain-as-evidence／adopt-after-proof／replace／quarantine／manual-review |
| successor | 新 scenario identity；尚無則空白並記 blocker |
| evidence | query digest、artifact links、人工裁決 |

inventory 是 evidence，不是 migration 或 deletion 授權。既有 33 案在 successor 驗收前不可清除、
改寫或重產。

## 11. Infrastructure readiness matrix（2026-08-12）

| Capability | Status | Current evidence | Gap／Owner |
|---|---|---|---|
| Injectable BusinessClock | `ready` | `shared_kernel/clock.py` 有 timezone-aware `FixedBusinessClock` | 各 Part 必須證明實際 workflow 注入，不可只存在型別 |
| Scenario contract validator | `partial` | 57 scenarios、127 business requirements；唯讀 validator 通過 | 舊命名／suite 模型尚未連結 Part 0～16 lifecycle catalog；Part 00 |
| Fixture validator | `partial` | 32 fixtures；唯讀 validator 通過 | 缺完整 UI lifecycle fixtures 及逐案 identity；各 Part |
| Receipt validator | `live-drift` | 唯讀驗證失敗；多份 digest stale，WP56 UI receipts contract 不相容 | 統一 current receipt contract、歷史 evidence 分區；Part 00 |
| Disposable DB name/confirmation | `partial` | bootstrap 拒絕既存 DB 並要求 confirmation | allowlist 過寬為 `lu_test_*`，仍有預設帳密 fallback；Part 00／Import ADR |
| Developer DB reset | `partial` | `reset_DB.bat` 零參數開啟會自動重設本機 `union_db` 為固定 v3 snapshot | 尚未由 developer-reset manifest 指向 canonical folder baseline；Part 00 |
| Route A/B final convergence | `missing` | 已有人工策略裁決，尚無 release/runner | 分庫執行、artifact-level merge、clean final rebuild、core 保留；Part 00／Part 16 |
| Stage baseline restore chain | `missing` | 目前 reset 只載固定 v3 snapshot，沒有逐流程 stage release | Import 後逐站 publish/restore/verifier，開發者可選 stage；Part 00＋Part 16 |
| Canonical stage artifact directory | `missing` | validation artifacts 目前分散於 datasets、fixtures、receipts、generated documents 及 snapshot v2/v3 | 固定 `validation/stage_baselines/`、manifest routing、external snapshot locator；Part 00 |
| Stage promotion lifecycle | `missing` | 現有 snapshot／receipt 沒有一致 candidate/verified/published/superseded gate | promotion receipt、UI acceptance、restore re-verification、immutable supersede；Part 00 |
| Validation schema manifest | `live-drift` | manifest 固定 96 parts；目前 base digest、part count、ordered digest 都不符 | 升版 release manifest，不覆寫舊 release；另立 schema release WP |
| Clean rebuild | `blocked` | bootstrap 有安全流程，但 schema gate 目前失敗 | schema release、seed chain 及 receipt gate 收斂前禁止宣稱可重建 |
| Integrated seed | `live-drift` | `seed_ui_validation_dataset.py` 引用已刪除 module，乾淨 DB 零寫入即失敗 | 建立 dependency-aware runner；未核准前不修；Part 00＋各 Part |
| Integrated DB verifier | `live-drift` | `115000051` 預期 5 日、觀察 10 rows；只檢查單案九項投影 | 改為集合、lineage、forbidden rows 與多 scenario verifier；Part 00／Part 08 |
| Existing 33-case inventory | `missing` | 目前只有表級／prefix 統計 | 建立逐案唯讀 inventory manifest；Part 00 |
| Central case-number allocation | `missing` | 現有 frozen/legacy/WP56 案號分散在 scripts、fixtures 與 DB | versioned catalog、virtual-account collision preflight、禁止各 Part 自選；Part 00 |
| Client/Staff master catalog | `missing` | 現有 staff/client roots 分散且部分 runner 寫死 observed staff ID | 共同 master pool、專屬隔離 pool、LINE/bank/occupancy collision；Part 00＋Part 04 |
| Business Calendar／coverage catalog | `missing` | 現有 fixtures 多集中 2026 Q3，clock/date 與覆蓋理由分散 | 先記條件與既有覆蓋，缺口才補；預約可逾 10 個月、正式服務最多 60 天；Part 00＋各 Part |
| Minimum sufficient dataset governance | `missing` | 現有 33／50 案與 WP56 scenarios 尚未按 business condition 去重 | 新增理由、adoption-first、停止條件與 gap/blocker 分流；Part 00＋各 Part |
| WP56 scenario adoption | `partial` | 歷史 flow、fixture intent、UI/DB receipts 可供追溯 | 缺 source→successor mapping、合法九碼案號與 current oracle；Part 00＋對應 Part |
| Route A clean replay | `partial` | WP56 normal-chain runner 提供歷史模式 | current seed/schema/receipt drift 阻擋完整重建；Part 00＋各 Part |
| Route B adopt/augment | `missing` | 目前只有人工 DB 盤點，沒有 canonical adoption/augmentation contract | inventory、target confirmation、delta、unaffected digest、recovery；Part 00＋各 Part |
| Historical dirty-data corpus | `missing` | Finance 有部分歷史 format tests；HCM／Client BeClass／Staff／Orders 未形成完整 versioned corpus | ADR `IMP-P6-01～19`、`48/43/5` identity、row outcomes、side-effect suppression；Part 01 |
| External side-effect isolation | `partial` | 個別測試有 archive/fake/outbox harness | 缺全 scenario registry 與 fail-closed adapter preflight；Part 00／Part 15 |
| Bank statement to reconciliation E2E | `partial` | Finance import／reconciliation 有局部 E2E 與 WP56 歷史 receipt | 缺全流程測試檔、各帳務 owner 核銷及邊界金額矩陣；Part 01／07／11～13 |
| Monthly staff payable oracle | `partial` | 有 payable query／export 與少數 obligations | 缺逐月逐 staff 加總、跨月、remaining／recovery 不重複 oracle；Part 12 |
| Quarterly subsidy roster oracle | `partial` | 有 Draft planning 與 XLSX 能力證據 | 缺逐季完整性、跨季、排除、提交／核准／撥款生命週期；Part 13 |
| Validation archive/download | `partial` | Contract archive/download tests 存在 | 長期固定 storage、retention、capacity、backup/cleanup 尚未裁決；Part 06／13／15 |
| Durable worker/restart | `partial` | 有 durable job scenarios/receipts | current receipt freshness 不足，且需逐 Part 證明同 command 零重複；Part 15 |
| DB/API/UI three-layer oracle | `partial` | WP56 有歷史 UI receipts，部分 typed verifiers 存在 | 缺統一 contract、mounted entry coverage、browser artifact digest；Part 00＋各 Part |
| Secrets/PII evidence boundary | `partial` | repo 規則禁止 secret/PII | runner CLI 仍允許 default password，缺 machine-verifiable redaction gate；Part 00 |
| Performance baseline | `partial` | PERF scenarios 存在 | 未連結真實 lifecycle dataset size 與每 Part budget；各 Part／Part 16 |

### 11.1 Readiness verdict

Part 00 目前為 `blocked-for-implementation`：可繼續唯讀 inventory 與文件設計，但不能開始共用
runner、seed、schema release 或 DB rebuild。解除條件是本文件人工確認後，建立 exact-scope Work
Package，並將 schema release、receipt contract、inventory 與 runner 的 write set 分開核准。

## 12. Infrastructure gaps 與建議拆包

| Gap ID | Gap | Proposed owner | Dependency | Closure evidence |
|---|---|---|---|---|
| P00-G01 | 33 案逐案 inventory 缺失 | Part 00 | 本文件確認 | versioned inventory＋唯讀 query digest＋人工 disposition queue |
| P00-G02 | Scenario lifecycle catalog 缺失 | Part 00 | Part 01～16 IDs | catalog validator 證明 dependency／identity 無碰撞 |
| P00-G03 | Receipt contract 分裂且 stale | Part 00 | G02 | current receipts 全通過；歷史 receipts 明確分區且不算 pass |
| P00-G04 | Validation schema release 漂移 | Global schema release | 人工核准 schema WP | 新 immutable manifest、digest、fresh bootstrap postcheck |
| P00-G05 | Seed chain 不可重建 | Part 00＋各 Part | G02、G04 | fresh DB 全鏈 seed/replay；零 direct derived seed |
| P00-G06 | Integrated verifier 過窄 | Part 00＋各 Part | G02、G05 | DB/API/UI 集合 oracle、forbidden rows、replay/stale/rollback |
| P00-G07 | Target/secret/external adapter preflight 不完整 | Part 00／Part 15 | security review | fail-closed tests，無 default credentials，外部 invocation count 零 |
| P00-G08 | `115000051` 兩代 schedule 漂移 | Part 08 | P00-G01 | lineage 裁決、有效 generation oracle、未修前維持 blocker |
| P00-G09 | Developer DB reset 尚未使用 canonical default baseline | Part 00 | G02、G04、G05 | 零參數開啟 `reset_DB.bat`→依固定 manifest Restore／Replay→完成 |
| P00-G10 | WP56 可重用場景尚未完成 adoption mapping | Part 00＋對應 Part | G01、G02 | 不重做 flow；合法案號重播後通過 current DB/API/UI oracle |
| P00-G11 | Route A／B runner 與證據契約尚未落地 | Part 00＋各 Part | G01～G10 | A 可 clean replay；B 只補缺口並證明未影響既有案例；兩者皆可 reset/recover |
| P00-G12 | Route A/B 收尾收斂與 final developer reset release 缺失 | Part 00＋Part 16 | G01～G11、Part 01～16 | artifact-level merge、clean rebuild、完整 oracle；保留獨立 core profile |
| P00-G13 | 中央案號 allocation catalog 缺失 | Part 00 | G01、G02 | 九碼案號與所有衍生 identity 無碰撞；reset deterministic；retired 預設不重用 |
| P00-G14 | Client/Staff canonical master pool 與隔離主檔 catalog 缺失 | Part 00＋Part 04 | G01、G02、G13 | reset deterministic；共享主檔唯讀；專屬場景零交叉污染；LINE/bank/occupancy 無意外碰撞 |
| P00-G15 | Historical dirty-data Import corpus 與 adoption evidence 缺失 | Part 01 | G01～G14、Import ADR P6 | 去敏 corpus、逐列 outcome 守恆、cutoff/identity review、side-effect suppression、E2E receipt |
| P00-G16 | 依流程階段的 DB baseline publish／restore chain 缺失 | Part 00＋Part 16 | G01～G15 | stage 00～07 lineage、artifact digest、restore verifier、working DB reset、跨 stage replay |
| P00-G17 | Stage artifacts 尚未集中至 canonical directory | Part 00 | G01～G16 | 固定目錄、唯一 manifest routing、source/generated 分離、舊 artifacts adoption linkage |
| P00-G18 | Stage promotion lifecycle 與 reset visibility gate 缺失 | Part 00＋Part 16 | G01～G17 | candidate→verified→published receipt；只有 published 可供下游/reset；supersede immutable |
| P00-G19 | 文件長期固定 storage／retention／capacity 尚未裁決 | Part 06＋Part 13＋Part 15 | 文件與清冊規格 | 實際 archive/download digest；人工確認 location、權限、retention、backup、cleanup |
| P00-G20 | Central Business Calendar 與 requirement coverage catalog 缺失 | Part 00＋各 Part | G01～G19 | 條件→既有資料→gap 判讀；fixed clocks；預約／服務跨度分離；必要 multi-year oracle |
| P00-G21 | 最小充分資料集與停止新增治理尚未落地 | Part 00＋各 Part | G01～G20 | 每案對應 uncovered condition；無重複語意；coverage 完成後停止新增 |
| P00-G22 | 既有 WP56／validation assets／DB 的個資與金融敏感資料來源、安全分類尚未盤點 | Part 00＋Part 15 | G01、G02、G07 | 資產分類完整；去敏規則與外部收件人隔離驗證通過；來源不明資料不進 canonical release |
| P00-G23 | 各 Part／scenario 的 evidence applicability matrix 尚未建立 | Part 00＋各 Part | G02、各 Part 正式契約 | UI／API／DB／守恆／replay-recovery 逐項裁決；所有 required 通過；N/A 有業務理由；blocked 有 owner 與解除條件 |
| P00-G24 | live code／schema／tests 可能仍依賴舊 role、capability 與 dynamic grant 模型 | Access＋UI／API callers | 最新同權限裁決與獨立核准 Work Package | 唯讀 inventory 完成；移除差異化業務授權後，登入、actor、session、audit 與外部安全門禁仍通過 |
| P00-G25 | Browser E2E locator 與檔案上下載基礎建設尚未逐 Part 盤點 | Part 00＋各 UI Part | G02、G23 與 mounted UI | required UI 全由 Browser 重播；檔案邊界例外可追溯；API 不取代 UI；後端可靠性由 pytest／verifier 分開證明 |
| P00-G26 | Part／scenario dependency class 與 blocker propagation 尚未建模 | Part 00＋各 Part | G02、G16、G23 | hard／soft／independent／global 依賴可驗證；只阻擋受影響下游；required 未通過不發布 stage |
| P00-G27 | Browser scenario 粒度與代表性流程尚未逐 Part 裁決 | Part 00＋各 UI Part | G23、G25、G26 | 以完整業務操作驗收；跨工作區結果可見；無無意義元件級 E2E；邊界組合由 pytest 承接 |
| P00-G28 | Scenario failure taxonomy、責任範圍與重跑入口尚未統一 | Part 00＋各 Part | G23、G26、G27 | 每筆失敗唯一 primary category；資料／產品／infra／automation／spec/drift 可分辨；baseline 重跑入口明確 |
| P00-G29 | 可由其他 Agent 重跑的 UI checklist 與結果摘要契約尚未建立 | Part 00＋各 UI Part | G25～G28 | 無截圖／影片依賴；baseline、案件、步驟、checkpoint、expected、重跑入口完整；另一 Agent 可重現 |
| P00-G30 | UI checklist canonical directory、manifest 與逐 Part 檔案尚未建立 | Part 00＋各 UI Part | G17、G29 | 固定目錄與唯一 manifest routing；共用 fixture 不複製；checklist 可重跑且不成為競爭 SSOT |
| P00-G31 | UI checklist 變更觸發、supersede linkage 與最終整理責任尚未制度化 | Part 00＋各 UI Part | G29、G30 | UI／流程變更同步更新；純重構不擾動；spec gap 不猜測；Part 完成及收尾時整理結果 |
| P00-G32 | 合法九碼案件與 UI 人類辨識備註尚未建立 catalog／checklist mapping | Part 00＋各 UI Part | G13、G29、G30 | 案號 canonical；備註僅供辨識；不新增測試欄位；successor linkage 可追溯 |
| P00-G33 | 整數金額條件、跨 Domain 銜接與 UI expected 尚未逐 Part 盤點 | Finance／Payroll／Subsidy UI Parts | G20、G21、G23、G29 | 無小數／費率版本測試；必要金額情境由既有資料優先覆蓋；逐筆與合計守恆 |
| P00-G34 | 訂單基本欄位的 UI／文件文案存在同義漂移，尚未逐入口統一 | Orders＋相關 UI／templates | 各 Part 實作核准與正式欄位契約 | `due_date`／`start_date`／`service_days`／`actual_start_date` 顯示名稱一致；不改 schema 或 Domain 語意 |
| P00-G35 | 跨 Domain 狀態值、正式中文文案與 UI 工作區對照尚未完成 | 各 Domain＋UI Parts | 各 Domain 正式 state machine 與 G23 | 狀態分離；同 Domain 文案一致；跨 Domain 不合併；Browser 驗證適用的正交狀態 |
| P00-G36 | 警示中心的錯誤顯示、修復導向與根因排除後消失尚未逐類驗收 | Anomalies＋各來源 Domain UI | G23、G27、G35 | 代表性 Alert 可見且可辨識；正式 UI 修復根因後消失；未修復不假解除；原工作區 blocker 同步解除 |
| P00-G37 | 各工作區實際查找、篩選、必要排序與 deep link 尚未形成代表性 UI checklist | 各 UI Part | G27、G29、G32、G36 | 目標資料可找到；清除篩選可恢復；跨工作區 identity 正確；不建立無意義排列矩陣 |
| P00-G38 | 各階段允許修改的欄位、UI 修正入口與下游影響尚未盤點 | Orders＋各 owning Domain UI Part | G23、G27、G35、G37 | 代表性正常／阻擋／修復重試可操作；重新整理持久；下游顯示一致；不直接改 DB |
| P00-G39 | 正式取消／作廢／沖正／修訂入口及可採用測試資料尚未逐 Domain 盤點 | 各 owning Domain UI Part | G01、G21、G23、G38 | 只測正式反向命令；原紀錄保留；下游狀態一致；代表性 repair path 可重跑 |
| P00-G40 | 各 Part 獨立案件配置與單一代表 E2E 案件尚未完成 catalog／lineage | Part 00＋Part 01～16 | G13、G21、G26、G32 | Part 案件互不污染；一案 clean replay 走完所有適用流程；不要求單案涵蓋全部例外 |
| P00-G41 | Client 一案一人、Staff 跨案配置、配對篩選與行事曆候選判斷尚未完成 | Part 00＋Staff Matching／Scheduling | G14、G20、G23、G40 | 每客戶一案；五項 filter 預設全勾；實際占用衝突排除；7 日緩衝仍顯示並備註；行事曆正確 |
| P00-G42 | 月嫂請長假／無法提供服務的行事曆紀錄功能尚未實作 | Staff／Scheduling＋Calendar UI | 正式功能規格與獨立核准 Work Package | 長期不可服務作為檔期顯示；配對候選正確排除／註記；不新增獨立在職 filter；Browser＋pytest 通過 |
| P00-G43 | 單人完整候選、Candidate Contact Pool、多月嫂分段與 lock→assignment UI 鏈尚未形成可重跑清單 | Staff Matching／Scheduling UI | G25、G29、G41 與配對正式規格 | 候選聯繫不形成占用；單人優先；多段完整性；全員 willing gate；等待訂金與正式行事曆分離 |
| P00-G44 | 配對資訊-1／2、意願／拒絕理由、履歷 gate 與歷史保留尚未形成 Browser checklist | Staff Matching＋LINE test adapter | G25、G29、G43 | 分項發送狀態正確；willing gate；發送前重查檔期；歷史不刪；無真實外部傳送 |
| P00-G45 | 月嫂分段契約、客戶契約、文件版本與 Contract Completion UI 鏈尚未形成可重跑清單 | Contract Signing＋Orders／Finance／Scheduling UI | G25、G29、G43、G44 | 全段月嫂簽回 gate；客戶契約後置；實際上傳；訂金／簽回／completion／conversion 分離 |
| P00-G46 | 銀行流水人工分類／手動銷帳、錯帳沖正重核及跨期歷程尚未形成 Browser checklist | Finance Import＋Client Finance＋Anomalies UI | G25、G29、G36、G45 | 不假設銀行更正版；原流水不覆寫；人工銷帳；錯帳先沖正；警示與餘額同步；跨期歷程保留 |
| P00-G47 | 月嫂付款、客戶收款與補助撥款的已核銷明細／allocation／期間摘要尚未納入 UI 驗收 | Client Finance＋Staff Payables＋Subsidy UI | G23、G29、G33、G46 | 已核銷金額與來源正確；原額＝有效核銷＋餘額；沖正歷程保留；月份／季別摘要一致 |
| P00-G48 | 政府補助案件依實際服務結束日期歸屬季度的 UI／XLSX 邊界資料尚未驗收 | Government Subsidy UI | G20、G29、G47 | `actual_end_date` 唯一決定 Q1～Q4；季末／季初與跨季案件不重複、不遺漏；撥款日不改歸屬 |
| P00-G49 | 服務開始、服務日期異動、請假／代班／順延與自動完成的跨域 UI 鏈尚未形成可重跑清單 | Orders＋Scheduling＋Payroll UI | G29、G35、G38、G41、G47、G48 | 正式指派 gate；日期數等於希望服務天數；異動後重發重確認；月曆／應付月份／補助季別連動；完成後唯讀且不得取消 |
| P00-G50 | 月嫂每月應付清冊到實際銀行付款的 Browser 主流程與補救入口尚未完整 | Staff Payables＋Accounts Payable Export＋Finance Import UI | G25、G29、G33、G46、G47、G49 | 正確月份與同月嫂跨案彙總；XLSX 明細及合計；下載不改付款狀態；銀行出款核銷；少匯 remaining／補匯、超額追償、退匯／沖正歷程；警示隨根因解除 |
| P00-G51 | 使用者端下載與系統持久封存尚未形成一致的跨部署 storage 契約 | Contract Signing＋Reporting／Export＋Infrastructure | G10、G25、G29、G45、G50 | 任一登入裝置可下載；不規定 client 路徑；只封存正式業務證據；local／cloud provider 可替換；stable key、digest、不可覆寫、audit、backup／restore 與 orphan cleanup 明確 |
| P00-G52 | Browser 第一登入 gate、帳號安全設定、TOTP 與獨立操作紀錄 UI 尚未完整 | Access＋Admin UI | G11、G25、G29、G31、G51 | 帳密成功／失敗為首測；TOTP 第二步；修改帳號／密碼；綁定／解除／重綁；credential 變更撤銷其他 session；操作紀錄可查且敏感資料遮罩；不建立角色差異 |
| P00-G53 | 多位內部使用者同時操作的 stale conflict、重複提交與檔期競爭尚未形成 Browser 驗收 | Global＋Orders／Scheduling／Finance／Contract UI | G25、G27、G29、G38、G41、G52 | 舊畫面零覆寫；提示重新載入與重新 Preview；同 key replay 不重複；月嫂重疊檔期僅一方成功；成功／衝突／重試 actor 可追溯 |
| P00-G54 | 長時間背景作業的 pending／terminal／結果未知、worker 恢復與 DB reset 隔離尚未形成一致 UI 契約 | Global Durable Jobs＋Import／Scheduling／Payroll／Subsidy／LINE UI | G12、G25、G26、G29、G36、G53 | 未收 receipt 不顯示成功；job 可重查；逾時不盲目重送；同 identity 不重複；worker 恢復可續跑；terminal failure 有人工入口；reset 後無舊 job 污染 |
| P00-G55 | 可完成全流程的共用主檔 baseline、缺漏修復與主檔版本對下游影響尚未逐項驗收 | Access＋Staff／Scheduling／Staff Payables／Subsidy／Contract Settings UI | G20、G29、G36、G41、G47、G52、G54 | reset 含正常共用主檔；少量缺漏案例；正式 UI 修復；警示解除；新版本不改歷史；敏感欄位遮罩；無 UI 維護入口者列 infrastructure gap |
| P00-G56 | LINE 管理中心缺真人 App 驗收，訂單狀態／事件到固定訊息版本的自動推送契約尚未建立 | LINE Integration＋Orders／各來源 Domain | G25、G29、G35、G44、G45、G52、G54、G55 | 後台 Browser＋專用真人 LINE 帳號雙驗；管理功能逐項有效；核准 mapping 全覆蓋；正確 recipient／template revision；不適用不送；replay 不重複；歷史版本可追溯 |
| P00-G57 | 跨年／月／季時間邊界的整套 UI 尚未能由 baseline 固定 BusinessClock 重播 | Global Clock＋Orders／Payroll／Subsidy／Anomalies／LINE／Export | G12、G20、G29、G48、G49、G50、G54、G56 | Asia/Taipei 固定時間隨 reset 還原；不改裝置時間；到期前／當下／後、月底、季底、年底正確；正式 UI 無任意改時入口；直接 system clock caller 收斂 |
| P00-G58 | 真實歷史資料量下的分頁、篩選、跨頁摘要與完整匯出尚未形成 UI 驗收 | Orders＋Staff／Calendar／Finance／Anomalies／LINE／Audit／Documents UI | G18、G20、G29、G37、G47、G55、G57 | 優先用去敏歷史 baseline；bounded query；跨頁不漏不重；搜尋可定位；摘要不只算當頁；匯出含完整範圍；載入／失敗可辨識；必要時才補 volume fixture |

不得把以上全部合併成單一大型 mutation。G01～G03 可先作 metadata／唯讀治理；G04 是獨立 schema
release；G05～G07 依後續 Part 的正式契約逐步啟用；G08 由 Scheduling owner 裁決。

## 13. Required tests（未授權實作）

### Module

- scenario ID/revision、namespace、digest、dependency graph、collision validator。
- timezone-aware clock、canonical date set、receipt schema、redaction rules。
- database/host/environment/external-adapter allowlist pure validation。

### Subsystem

- preflight 零寫入；任一 gate 失敗不建立 DB、不觸發 provider。
- fresh DB bootstrap、root-only seed、command dependency、projection rebuild。
- same release rebuild determinism、same-command replay、different payload conflict。

### Domain／Global

- 各 Part 依真實業務能力裁決 happy、blocked、repair、replay、stale、rollback 的適用性；不得要求每個
  Part 為所有類型建立 scenario。所有被裁決為 `required` 的類型必須具備驗收資料與證據。
- 跨 Domain 失敗留下零 partial formal rows，但 post-commit side effect 可獨立 retry。
- DB/API/UI 同時適用時，oracle 對同一 root facts 給出一致 typed 結果。
- runner 不可能連到 production/candidate，也不可能真的送 LINE／付款／補助。

## 14. Acceptance 與人工確認項目

Part 00 文件只有在人工確認以下內容後才能成為 `approved`：

1. scenario package、identity、clock、database safety、oracle、receipt 與 inventory 契約。
2. scenario metadata／備註的命名及 revision 規則；不得寫入或取代任何正式 business identity。
3. 既有 33 案只能唯讀 inventory，未授權清理／採用／修正。
4. readiness matrix 的非-ready 判定及 P00-G01～G21 owner 分流。
5. Part 00 仍不授權 production code、schema、seed、pytest 或 DB mutation。
6. 文件核准後第一個可執行範圍只應是 P00-G01 唯讀 inventory 與 P00-G02 metadata catalog；
   任何其他 gap 必須另有 exact-scope Work Package 與人工確認。

## 15. 人工裁決紀錄與尚待確認

2026-08-12 人工已裁決：

- scenario 只可存在 metadata／備註；正式資料 identity 不使用自訂測試 identity。案件編號必須遵守
  現有固定格式，因其連動虛擬帳號生成、Finance resolver、配對與其他下游關聯。
- DB 名稱不限制；最終必須提供安全 DB reset，讓開發者復原指定測試情境。
- 採用先執行唯讀 33 案 inventory 與 metadata catalog，不同時修 seed 或 schema。
- WP56 receipts 不刪除且不否定當時驗收，定位為 historical evidence。後續優先採用 WP56 已有
  測試資料與流程，不重複造輪；若案件編號不符合正式格式，successor 使用可直接運作的九碼案號，
  並重新生成虛擬帳號、配對及其他正式下游關聯。
- 歷史 receipt 與既有 DB row 不原地改名；案件編號轉換發生在 successor fixture／正式重播流程，
  source→successor mapping 保留完整追溯。
- 測試資料實作分為兩條路線：Route A 從乾淨／reset DB 依正式流程逐筆建立；Route B 盤點並修改
  指定的原有開發／validation DB，只對缺口用正式 commands 新增或修復。各 Part 必須先選路線、
  target、write set、recovery 與 acceptance，不能在執行中混用。
- Route A 與 Route B 兩者都採用。Route A 是可信任、可重建的核心驗收基準；Route B 是保留既有
  有價值資料、補足 UI 狀態的日常開發資料。Route B 不得成為 Route A 的前置依賴，也不得以
  「現有畫面可操作」取代 Route A 的完整流程證據。
- Route A／B 開發期間分庫；全計畫收尾時只合併 versioned scenario artifacts 與 reset release，
  從乾淨 DB 重建 final `developer` baseline，不直接拼接實體 DB。獨立 `core` profile 永久保留，
  `part-NN` profile 用於 focused development／debugging。
- 採用中央 case-number allocation catalog。各 Part／fixture／seed 不得自行選號；catalog 固定分配
  正式九碼案號，並驗證虛擬帳號、HCM／BeClass、external events、Route A／B 與所有 reset profile
  的跨 release collision。同一 release reset 後案號必須一致，retired identity 預設不重用。
- 採用共同 canonical Client／Staff master pool 加場景專屬隔離主檔。共享主檔唯讀並支援正常能力
  組合；會改變 occupancy、LINE、銀行 ownership 或形成異常／recovery 的場景使用專屬主檔。
  DB auto-increment ID 只記 observed mapping，不作跨 reset identity。
- Historical Data Import 納入 Part 01 的獨立測試 lane，並使用源自既有問題紀錄的去敏髒資料 corpus。
  必須收斂 Import ADR 尚未完成的 `IMP-P6-01～19` 及 `48/43/5` fixture gap；歷史匯入預設不影響
  current state 或觸發現行 side effects，無法唯一還原者保留 evidence/review，不猜值。
- 採用依真實流程逐站保存可恢復 DB baseline：先驗收 Import 並發布 imported stage，再依序完成
  review、配對、契約、對帳、排班、服務與帳務 stage。多案件可在同一 stage 分布於不同 UI 狀態；
  開發者透過 DB reset 恢復任一已驗證 stage 後重新操作，不必為每個狀態永久凍結不可操作案件。
- 採用 canonical replay release 為權威、DB snapshot 為快速恢復快取。所有 stage artifacts 集中於
  `validation/stage_baselines/`，依 catalog／release／stage 分層管理；source fixture、commands、expected、
  snapshots 與 receipts 分開。大型 snapshot 可外置，但 locator、digest 與 restore policy 必須留在 manifest。
- 採用 `candidate → verified → published → superseded` stage lifecycle。只有完成自動 oracle、必要人工
  UI 驗收及 restore re-verification 的 `published` stage 可作下游來源或出現在一般 DB reset 選單；
  published artifact 發現問題只能由新 revision supersede，禁止原地修改。
- 銀行對帳單使用測試檔真實走完整 Import 與 owning Domain 核銷；月嫂應付逐月驗證明細、歸屬與
  加總；政府補助逐季驗證名冊完整性、排除與金額；文件實際產生、封存及下載並比對 digest。
  文件長期固定 storage 尚未設定，維持 `human-decision-required`，不先猜測資料夾。
- 採用 Central Business Calendar／requirement coverage catalog。每項先記真實業務條件並檢查前面
  stages／既有資料是否涵蓋，缺少才由 owning Part 補規格與資料，不為排列組合而測試。懷孕預約至
  預計服務可超過 10 個月，但單案正式服務／排班區間最多 60 天，兩者不得混為全年排班。Historical
  與 Government Subsidy 的 multi-year coverage 同樣先 adoption，只有必要缺口才新增。
- 不設定固定案件總數，採最小充分資料集。每個新案件必須對應尚未涵蓋的真實 business condition，
  並說明無法採用／補強既有案件的理由；當新增資料不再增加業務語意覆蓋時停止新增。

尚待確認：

- Part 00 文件整體是否核准；核准效果仍只開放唯讀 inventory／metadata catalog，不授權 seed、schema
  或 DB mutation。
