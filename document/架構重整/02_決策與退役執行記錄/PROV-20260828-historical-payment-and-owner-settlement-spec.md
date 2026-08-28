# 歷史付款證據與 owner 帳務結清規格

- `spec_id`: `PROV-20260828-historical-payment-and-owner-settlement`
- `declared_status`: `approved`
- `current_item`: `CUR-P0-HISTORICAL-PAYMENT-SETTLEMENT-01`
- `owners`: Finance Import、Client Finance、Staff Payables、Anomalies；Orders／HPROJ 只組合 typed readback
- `authority`: 2026-08-28 使用者明確裁決
- `formal_sources`: `00_Global_共同契約.md`、`04_Client_Finance_Domain.md`、`05_Staff_Payables_Export_Domain.md`、`06_Anomalies_Domain.md`、`16_Staff_Payables與Client_Refund正式規格.md`、`PROV-20260827-historical-order-operational-baseline-spec.md`

## 1. Objective 與名詞邊界

使用系統前已存在的歷史案件，可能仍在服務中且尚未付款，也可能早已付款或結清。系統不得因
「歷史案件」或歷史訂單狀態 `1` 自動推定任何付款、退款、月嫂 payout 或 Step 11 完成；歷史六欄
訂單檔只提供案件、狀態、日期與月嫂來源，不是帳務證據。

下列語意固定分開：

- `payment fact`：誰付給誰、付款方向及其對應義務的具體事件；只改變該 owning Domain 的義務。
- `owner settlement`：Client Finance 或 Staff Payables 依其全部 current obligations、付款、退款、退匯、
  reversal 與合法 disposition 重建的結果，不是單一付款事件。
- `historical order Step 11`：Orders completion、正式服務、Client Finance terminal readback 與 Staff Payables
  terminal readback 全部成立後的跨 Domain 組合結果；任一邊未完成即不得顯示完成。

客戶付款給工會只影響 Client Finance；工會尚未付款給月嫂時 Staff Payables 保持 payable，Step 11 保持
未完成。客戶補助退款是 Client Finance 的 `payable_to_client/subsidy_return`，收款人是客戶；政府補助
撥款與政府溢撥退還才由 Government Subsidy 擁有，三者不得混稱或互相結清。

### 1.1 Requirement identities

| ID | Requirement |
|---|---|
| `HPS-01` | payment fact、owner settlement與Step 11保持三層分離，禁止跨owner推定 |
| `HPS-02` | Finance Import對帳單優先；historical manual只限pre-system adopted case |
| `HPS-03` | Client receivable、client refund、client subsidy return三方向由Client Finance分開處理 |
| `HPS-04` | Staff payout只由Staff Payables exact staff／case／obligations處理 |
| `HPS-05` | owner historical Query／Preview／Apply具fresh lock、receipt、replay與同UoW outbox |
| `HPS-06` | historical source不得偽造bank row／allocation／date；later owner event可更新或重開 |
| `HPS-07` | Anomalies頁顯示原因、消除方式及同頁owner typed修復，禁止generic close/editor |
| `HPS-08` | HPROJ只組合owner terminal readback；Client與Staff皆terminal才可完成Step 11 |
| `HPS-09` | 正式操作使用既有enabled internal frontend account能力；local no-auth只可作development驗收 |

## 2. 證據優先序與 eligibility

1. 首要來源是帳務系統的 Finance Import 對帳單匯入。歷史與新匯入的銀行對帳單都先形成 canonical
   bank facts，再依付款方向委派 Client Finance 或 Staff Payables 的既有 reconciliation Q/P/A。
2. 對帳單可唯一處理時固定走正常核銷；不得顯示第二次「標記已付」，也不得建立重複 payment。
3. 只有已正式採納、來源時間位於系統啟用前的 historical case，且舊銀行／帳務證據缺失、歸屬不明或
   無法可靠還原時，才允許具權限的 enabled internal user 使用歷史人工確認。正在服務但尚未付款的歷史
   案件不因 eligibility 自動完成；沒有實際確認時保持 open／payable。
4. 歷史人工確認是受控的替代證據來源，不是「無法還原 allocation」的付款定義。一般／新案件、未採納
   歷史來源、跨案、payer／payee／direction 不明或 obligation set 不可唯一綁定時固定拒絕。
5. 付款日期無法確定時保存 `unknown`／null 與原因，不得使用匯入日、操作日或目前日期冒充付款日。
6. 正式人工確認不得要求資料庫root帳號，也不得綁死特定個人帳號；既有enabled internal前端使用者依
   current business capability執行。local no-auth bypass只限development／validation，不得成為production權限路徑。

## 3. Owner-specific historical commands

### 3.1 Client Finance

Client Finance 的 historical action 必須先明確選擇方向與 obligation set：

- 客戶付款給工會：只清償選定 `receivable_from_client`；
- 工會退款給客戶：只清償選定一般 `payable_to_client/refund|adjustment`；
- 工會退還客戶補助款：只清償選定 `payable_to_client/subsidy_return`。

`已付款` 表示上述特定方向與選定義務已發生付款；`已結清` 表示所選 Client Finance obligations 已由
授權歷史處分終止，但不替另一方向、其他未選義務、Staff Payables 或 Government Subsidy 建立付款事實。
同案多筆義務可在 UI 全選，但 Apply payload 與 event 仍保存 exact obligation identities。

### 3.2 Staff Payables

Staff Payables 的 `已付款` 只表示工會已對選定月嫂義務完成 payout；`已結清` 只終止 exact selected staff
obligations。不得由客戶已付款、Orders completed、清冊下載或政府撥款推定月嫂已收款。不同 staff、案件、
方向或不唯一義務不得合併。

### 3.3 共通 command envelope

兩個 owner 各自提供 `Query → Preview → Confirm → Apply → receipt/readback`，不得建立跨 Domain
`CompleteHistoricalOrderSettlement`。Preview 零寫入；Apply fresh-lock current owner aggregate、歷史採納
identity、來源證據候選與 exact obligations，並保存：

- case、owner、payer、payee、direction、obligation identities／amount snapshot；
- confirmation kind `paid | settled` 與付款日期或明確 unknown；
- historical adoption identity/version、actor、reason、evidence reference／source availability；
- expected owner version、preview fingerprint、idempotency、correlation、event、receipt 與 outbox。

同 key＋同 payload回原 receipt；同 key＋不同 payload為 conflict。owner event、current projection、receipt、
audit 與 HPROJ source envelope 必須由同一 owner outer Unit of Work 一次提交；任一失敗全部 rollback。

## 4. Reducer、後續更正與報表

- 一般 bank-backed payment 仍依既有 ledger／allocation reducer；歷史人工 payment／settlement 使用獨立 typed
  source kind，不偽造 Finance Import row、銀行 allocation、交易日期或 provider success。
- owner 的 paid／settled projection可以接受已核准歷史事件，但 public readback 必須標示 evidence source，
  使人工歷史確認與 bank-verified payment 可稽核區分；它們不因來源不同而改變付款方向或跨 owner。
- 後來匯入相容銀行事實時，只能由 owner 的 reconciliation／evidence-link 流程補強 lineage，不得建立第二次
  收付款。後來發生退款、退匯、reversal、金額／服務更正或新 obligation 時，以 strictly-newer owner event
  更新 current projection；未被舊事件 exact 綁定的新義務保持 open，必要時重新開啟異常。
- true ledger integrity conflict 可保留獨立 integrity anomaly；不得因付款或 owner settlement 成立就刪除
  不同根因的 alert。

## 5. Anomalies React repair hub

異常頁是主要人工入口，但不是 root editor。每筆 alert detail 必須顯示 owner、付款方向、payer／payee、
exact obligations、金額／到期日、已找到的 bank candidates、正常核銷 blocker、歷史 eligibility、解除條件及
Apply 後 fresh readback。頁內 drawer 依 typed action 提供：

1. `使用對帳單核銷`：呼叫現有 owner reconciliation；
2. `歷史人工確認已付款／已結清`：只在本規格 eligibility 成立時出現，呼叫對應 owner historical Q/P/A。

未知 action/schema/version、跨 owner、stale、identity ambiguous、outcome unknown 或 readback unavailable 時
fail closed。UI 不得直接 UPDATE obligation／status、generic close alert，亦不得把 Client、Staff、Government
三種帳務合併成一個「訂單已結清」按鈕。

## 6. HPROJ 與 Step 11

HPROJ 不解析 Excel、bank row 或 UI 輸入，只消費 owner committed event／receipt／source envelope 後 fresh-read
Client Finance 與 Staff Payables 的 typed terminal predicates。Step 7 只讀 Client Finance deposit settlement；
Step 11 分別保存 Client Finance settlement 與每個 Staff Payables payout observation。只有全部 required
observations terminal 且其他 completion roots 成立，active historical membership 才可歸零。

## 7. Acceptance

- `HPS-A1`：歷史進行中、尚未付款案件保持 open/payable，不因 status 1 或 historical eligibility 自動結清。
- `HPS-A2`：可唯一對應的銀行入／出款走正常 owner reconciliation，零重複 manual event。
- `HPS-A3`：客戶付款給工會只清 Client Finance receivable；Staff Payables仍 payable、Step 11未完成。
- `HPS-A4`：工會付款給月嫂只清 exact staff obligations，不改 Client Finance。
- `HPS-A5`：客戶補助退款由 Client Finance 清償 `subsidy_return`；不投影成 Government Subsidy 或 staff payout。
- `HPS-A6`：eligible historical case 在無可靠銀行證據時可由人工 Q/P/A記錄 exact owner/direction/obligations；
  unknown date不被偽填，Apply後只有該 owner predicate更新。
- `HPS-A7`：同案只處理部分 obligations時其他 obligations與alert保持；全選仍保存逐筆 identities。
- `HPS-A8`：一般案件、跨案／跨owner、payer/payee/direction不明、stale、同key異payload、timeout/readback
  unavailable均零假成功。
- `HPS-A9`：後續退款、退匯、reversal或新義務以較新owner event重開／更新對應alert，舊history immutable。
- `HPS-A10`：Client terminal、Staff未terminal時Step 11保持未完成；兩邊與其他completion roots全terminal才完成。
- `HPS-A11`：Anomalies頁完整顯示原因、消除方式及同頁typed修復；不得generic close或直接欄位／SQL寫入。
- `HPS-A12`：additive schema完整通過DB 3.1 gates及另一台configured developer acceptance；未通過時固定
  `DB_CHANGE_NOT_READY`。
- `HPS-A13`：一般enabled internal前端帳號可走相同typed修復；development no-auth可驗收相同行為但不改變
  production authentication／authorization契約。

## 8. Scope、change inventory 與 exclusions

- `schema-only`: owner-specific immutable historical evidence/event/link/receipt/projection與shared source envelope所需
  additive successor；exact object由task package late-bind。
- `system-seed`: none。
- `business-row-backfill`: none；既有歷史列不自動轉換。
- `destructive`: none。
- `excluded`: 歷史六欄訂單新增付款欄、generic order settlement、production／`union_db`、provider payment、
  reset／replacement／`--switch`、existing-row rewrite、Graphify。

```yaml
spec_route:
  status: SPEC_READY
  requirements: [HPS-01, HPS-02, HPS-03, HPS-04, HPS-05, HPS-06, HPS-07, HPS-08, HPS-09]
  acceptance: [HPS-A1, HPS-A2, HPS-A3, HPS-A4, HPS-A5, HPS-A6, HPS-A7, HPS-A8, HPS-A9, HPS-A10, HPS-A11, HPS-A12, HPS-A13]
convergence:
  status: READY
  blockers: []
```
