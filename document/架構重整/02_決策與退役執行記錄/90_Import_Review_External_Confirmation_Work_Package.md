---
doc_type: work-package
declared_status: approved
date: 2026-08-14
owner: Case Import / Orders / Finance Import / Anomalies / LINE Integration
priority: P0
---

# 90 匯入異常外部確認與重新提交 Work Package

## Execution sequencing／successor

WP90 定義 warning tracking Query 與人工狀態 Preview／Apply 的完整目標契約。WP92 是目前執行
slice：只授權 import scripts、lane Preview／Apply 與正式寫入；warning center UI、typed Query、
人工轉態與 WarningReferral 明確 deferred，需由後續 Work Package 取得 write set 與驗收授權。
這是交付順序，不是撤回或改寫 WP90 已核准的業務決策。

## 人工裁決與 business scenario

資料有誤或缺漏時，公會人員通常無法立即判定正確值，必須聯絡填寫者、客戶、月嫂或其他資料來源
當事人確認。系統不得讓人員在警示中心猜測欄位、直接覆寫匯入原始列，或將 LINE 回覆直接載入正式
資料。警示中心的責任是記錄此筆資料的處理狀態；正確資料原則上必須由新的受驗證來源重新提交，或由
既有 owning Domain typed command 依已確認的外部根事實建立新 immutable result。HCM已建案的缺漏／
無效欄位是例外：可由其 owning typed field-completion command 補齊指定欄位，不經警示中心直接改值。

## 共同不變量

1. HCM、Client BeClass、Staff historical、歷史訂單與銀行來源的 immutable source fact 永不 update／delete。
2. 警示中心只保存 actor、狀態、去敏聯絡摘要、reason、evidence reference、版本與時間；不保存原始
   workbook、完整個資、LINE 對話內容或未驗證的修正欄位。
3. 狀態固定為 `open`、`awaiting_external_confirmation`、`response_recorded`、`reimport_requested`、
   `closed`、`auto_resolved`。前四者維持 active；公會人員可用一般處理說明將外部確認工作推進為
   `closed`，並保存 immutable status event 與 committed outbox，但不得因此宣稱原始資料已修正。
   `auto_resolved` 只能由後續已確認 root fact 的 predicate rescan 產生。
4. 不存在唯一 LINE recipient binding 時，系統不得自動傳送 LINE；公會人員以既有合法管道聯絡。
   具 recipient binding、核准模板與 committed outbox 的未來通知能力另依 LINE Integration contract 實作。
5. 新來源重新提交必須走各 lane 的 typed Preview／Apply、fresh validation、fingerprint 與 idempotency；
   成功後由 root-fact predicate 重掃自動解除關聯警示，不以人工按鈕冒充資料已修正。
6. Finance 不可改寫 bank row。已確認銀行事實只能走既有、有限的 Finance Import／owning Domain
   typed recovery action，append-only 建立 ledger、allocation、recovery 或 return。
7. Finance workbook 必須逐列隔離：可正規化列照常匯入；金額、日期、帳號或格式無法正規化的列不建立
   canonical bank row，但必須建立可追蹤的 Finance source warning。跨檔 fingerprint 完全相同的交易
   不新增 occurrence，只在本次 receipt／計數明示已存在。
8. 每個警示類型必須另有可審核登錄，至少載明 owning Domain、code、觸發條件、正式資料效果、
   顯示的去敏摘要、可採取的後續處理、解除 predicate、可操作 actor與LINE通知狀態。未完成該類型
   登錄及人工審核前，不得自行推定 UI 文案、按鈕、通知或自動解除方式。

## 第一階段操作裁決

第一階段固定由公會人員以既有 LINE、電話或其他合法管道自行聯絡來源當事人；系統只提供
`待聯絡`、`已聯絡／等待回覆`、`要求重新提交`與終態的去敏追蹤。不得在此階段建立自動 LINE
delivery、recipient 推測、訊息模板或對話內容保存。來源當事人重新提交完整資料後，才回到各 lane
原有的 typed Preview／Apply。

## Scope 與 write set

- 為每個 owning import/review root 建立 immutable tracking/disposition event、current projection、typed Query
  與「更新處理狀態」Preview／Apply；不得新增通用 corrected-payload endpoint。
- HCM `IMPORT-004`、Client／Staff BeClass review、Orders `HISTORICAL-ORDER-001` 及 Finance manual-review
  必須各自保留 owner 與 predicate，僅共用 Global command envelope／outbox contract。
- 異常中心只顯示業務狀態與合法下一步，例如「待聯絡填寫者」與「等待重新提交」。
- 必要時新增 additive schema、release metadata、descriptor、focused/disposable/preserve-data evidence 與
  entrypoint review；不得操作 production data 或隱式 backfill。

## Out of scope

- 從來源列自動猜 LINE recipient、傳送未核准訊息或保存 LINE 對話。
- 直接修改 workbook row、bank row、Client、Order、Staff 或以人工輸入建立正式資料。
- 以單一 generic correction form 合併不同 Domain 的資料語意。

## Acceptance

1. 任一匯入異常可建立、查詢及 versioned Preview／Apply 更新追蹤狀態；same-key replay、different-payload
   conflict、stale version 與 partial failure 均 fail closed。
2. 警示中心無直接編輯來源欄位的 UI/API；來源重新提交後才可能建立正式 root fact。
3. 一般 `closed` 狀態與重新提交成功各有 immutable event、receipt、outbox 與 root-fact-aware anomaly
   projection evidence；`closed` 只代表外部確認工作結束，不能成為原始資料已修正或正式 root 已建立的證據。
4. Finance fixed recovery actions 保持 append-only，且任何未知銀行列只可追蹤、不能強制入帳。
5. focused、disposable MySQL、UI 與 preserve-data gates 分別通過後才可標記完成。
