---
doc_type: work-package
status: implemented-and-rehearsed
date: 2026-08-09
approved_by: user
approval_date: 2026-08-09
---

# Preserve-data 與 Historical Reprocess 收斂 Work Package

## 範圍與前提

本 package 關閉 2026-08-09 矩陣中兩個真正的本機缺口：

1. Global preserve-data runner 的安全公開工作流；
2. Historical Reprocess 對「銀行根事實沒有 case reference」退款列的人工 owner
   selection。

它不授權接觸 `union_db`、正式 `.env` 或真實銀行資料。2026-08-09 已經使用僅綁定
localhost 的可丟棄 MySQL 容器完成專用 source→backup→candidate→migration→switch→restart/read-smoke rehearsal；可合法重播的銀行格式
品質仍是獨立 external gate；target-host deployment
acceptance 已由決策 53 退役。

## A. Global → Preserve-data Runner

| 層級 | SSOT／責任 | 不變量 |
|---|---|---|
| Global | `10_Global_保留資料Migration與Cutover_Subsystem.md` 的 source identity、release manifest、journal、config digest 與 cutover receipt。 | source 永遠唯讀；不得以普通 `.env` 隱式提供 source 或 candidate credentials。 |
| Subsystem | `preflight → backup → restore → apply → verify → switch → restart/read-smoke → recover/rollback`。 | 每一 phase 均有 strict UTF-8、無 secret 的 append-only receipt；source/candidate principal 分離。 |
| Module | source-principal guard、maintenance-token validator、CLI parser、switch-state reconciler、restart/read-smoke adapter。 | token 必須未過期且綁定 source identity／plan fingerprint；before/after hash 之外的 switch state 一律 fail closed。 |

公開 CLI 必須新增或完成：`--complete-restart`、`--recover-interrupted-switch`、分離的
source-read／candidate-write descriptor、source-principal evidence、maintenance token、receipt
directory。`--check`、`--dry-run`、`--backup`、`--switch` 都先執行適用的 preflight；不接受
`mysql_db`、`union_db` 或任一 operational database 作為 rehearsal target。

狀態機：`planned → backed_up → restored → migrated → verified → switched → completed`；
`switched` 在 restart/read-smoke 失敗時只能進入 `recover` 或 `rollback`，不得標 completed。

## B. Finance Import → Historical Owner Selection

採用建議方案：**人工、append-only 的 owner selection，絕不改寫銀行根事實。**

採用建議批次政策：**strict batch**。只要任一 eligible row 仍無唯一 owner，整個
Historical Reprocess Apply 維持 fail closed、零寫入；操作員先完成缺列的 selection 再重新
Preview。這避免同一 batch 一部分已重分類、另一部分留在舊候選而讓稽核誤以為批次完整。

| 層級 | SSOT／責任 | 不變量 |
|---|---|---|
| Finance Import Domain | immutable bank row、batch/row version、classification decision、reprocess receipt。 | bank reference 不補寫 case number；無唯一 owner 必須 fail closed。 |
| Client Finance Domain | case-owned open refund payable obligation。 | 只接受選定 case 的唯一 open obligation；不得以帳號或姓名猜測 case。 |
| Historical Reprocess subsystem | Preview 載入候選與人工 evidence；Apply 在原有 outer UoW 寫入 selection event、classification、owner dispatch、run/receipt/outbox。 | 同一 row + evidence + case + obligation + versions + actor 的 replay 回原 receipt；任何差異為 conflict。 |
| Module | typed request/schema、selection repository、candidate builder、MySQL migration、API/client/panel。 | expected batch/row/obligation version、preview fingerprint、idempotency key、actor/reason/evidence refs 全部必填。 |

新增 append-only `historical_owner_selection_events`：`bank_row_identity`、`case_no`、
`obligation_identity`、`actor`、`reason`、`evidence_references`、`source/batch/row/obligation
versions`、`preview_fingerprint`、`idempotency_key`、`reprocess_receipt_reference`。它是人工
case-evidence，不是銀行資料的修正，也不覆寫既有 `bank_references`。

Preview 收到 selection input 後，只回傳 canonical candidate/fingerprint；Apply 重新鎖定所有
版本，確認 obligation 唯一且仍 open，然後同一 outer UoW append selection event、完成 typed
owner dispatch、寫 receipt/outbox。鎖定、stale、無 obligation、跨 case、重複但不同 selection、
或 evidence 不足一律 typed conflict／validation error 並零寫入。

Historical Reprocess Apply 改為既有 durable-job envelope：API 接受固定 idempotency key 後只
建立 job；worker 仍是上述 outer UoW 的唯一執行者。Streamlit 保存 pending command snapshot，
顯示 loading，安全重送同一 key，並只輪詢該 job。這不改變 typed workflow 的業務規則。

## 驗收與外部界線

本機驗收：parser/preflight、principal/token、journal crash state、recovery、selection replay/
stale/rollback、API/UI loading/data flow、release metadata 與 disposable MySQL source/candidate
contract tests。

已完成的隔離驗收：專用 source→backup→candidate→migration→switch→restart/read-smoke，收據
位於 `03_追蹤清單與證據/evidence/preserve_data_rehearsal_20260809/`。來源 preflight 使用
唯讀 principal；MySQL trigger 定義匯出需要較高的 metadata 權限，因此僅在此 disposable
container 由既有 root snapshot 匯出，沒有對來源做資料或 schema 寫入。真實但可合法重播的
銀行樣本仍為外部驗收。TLS／HTTP2／latency／target-host worker recovery acceptance
已由決策 53 退役。

## 請確認

核准本 package 後，才可修改 runner CLI、migration schema、Historical Reprocess API/UI 與對應
測試。未核准前，既有 fail-closed reprocess 和 preserve-data CLI 行為維持不變。
