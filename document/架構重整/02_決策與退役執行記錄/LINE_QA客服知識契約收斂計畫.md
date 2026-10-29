---
doc_type: implementation-gap-tracker
declared_status: blocked
updated: 2026-09-09
owner: Customer Service / Knowledge Retrieval / LINE Integration
domain: Customer Service / Knowledge Retrieval / LINE Integration
formal_authority: document/架構重整/01_規格基線/29_LINE服務說明、客服互動與選單角色正式規格.md
source_artifact: document/line/AI客服QA題庫.jsonl
source_artifact_role: review-input-and-migration-evidence
db_change: not-authorized-by-this-document
---

# LINE QA 客服知識契約 Implementation Gap Tracker

## 1. 文件定位

本文件不是產品或 runtime Authority，也不再定義另一套 QA 狀態機。

LINE 服務說明、客服回答 catalog、人工轉接、automation boundary 與 Rich Menu audience 的正式語意，以：

`document/架構重整/01_規格基線/29_LINE服務說明、客服互動與選單角色正式規格.md`

為準。

本文件只追蹤規格 29 尚未被 current implementation／資料／API／UI／readback 證明完成的缺口。任何與規格 29 衝突的舊設計均視為 superseded，不得反向覆蓋 formal baseline。

## 2. 已被後續正式規格取代的舊設計

下列舊設計不再成立：

1. `document/line/AI客服QA題庫.jsonl` 是正式 runtime catalog。
2. QA lifecycle 只用 boolean `enabled=true|false` 即可代表可發布／不可發布。
3. 不需要逐題 human review、owner／reviewer 或 versioned publication workflow。
4. `enabled=true` 可直接視為已核准自動回答。
5. UI／API 只需要「全部／啟用／未啟用」即可完整表達正式治理狀態。

Current formal baseline 已裁決：JSONL／XLSX 只作內容輸入或 migration evidence；可自動回答的 item 必須經人工核准、版本化發布，具備 stable identity／revision、category、audience／role、source/provenance、approved wording、owner、reviewer、`published|retired` lifecycle、automation boundary 與 manual-fallback reason。

## 3. Current evidence

目前 `document/line/AI客服QA題庫.jsonl` 仍是過渡輸入格式，主要欄位為：

- `id`
- `category`
- `tag`
- `question`
- `aliases`
- `answer`
- `enabled`
- `source_ref`
- `notes`（部分列）

這個格式可以繼續作人工 review input，但不得因 `enabled=true` 就升格為 `published` runtime Authority。

本文件不以「曾存在 loader／API／React panel」作完成證據；只有 current source、test、DB／versioned storage、API readback、UI readback 或可重現 acceptance 能證明規格 29 的 gate 已完成。

## 4. 尚未完成的 Material Gaps

### GAP-QA-01：逐題人工 review 與 ownership

每個候選 answer item 必須能確認：

- stable item identity 與 revision；
- owner；
- 最後 reviewer；
- category；
- audience／role；
- source／provenance；
- approved wording；
- automation boundary；
- manual-fallback reason（需要時）。

空白、重複、來源不足、互相衝突、無 owner、過期或含個案承諾的項目不得發布。

狀態：`BLOCKED / NOT_PROVEN_COMPLETE`

### GAP-QA-02：versioned publication lifecycle

正式 lifecycle 必須以 versioned catalog 的 `published | retired` 表達，不得以 JSONL 的 boolean `enabled` 代替正式 publication state。

更新流程必須收斂為：

`來源輸入 → normalize / deduplicate → human review → versioned publish → read-only answer query`

Workbook、crawler、模型或前端不得自行核准或覆寫 current published revision。

狀態：`BLOCKED / NOT_PROVEN_COMPLETE`

### GAP-QA-03：conflict／invalid candidate queue

至少要能隔離並追蹤：

- duplicate／near-duplicate；
- conflicting answer；
- missing source；
- missing owner／reviewer；
- stale policy wording；
- 個案化承諾或需要 owning Domain Query 的內容；
- 無法安全 automation 的 item。

這些項目不得因舊 `enabled=true` 或模型語意命中而進入自動回答候選集合。

狀態：`BLOCKED / NOT_PROVEN_COMPLETE`

### GAP-QA-04：runtime candidate boundary

Current M2／Knowledge route 必須只能從已核准的 READY／published candidate set 取回 closed candidates；模型只能回候選 QA identity 或 `UNSUPPORTED`，server 再讀取核准 answer。

模型不得：

- 自由生成政策、費用、資格或個案結果；
- 以未發布／retired／conflict item 回答；
- 選擇 closed candidate set 之外的答案；
- 直接執行 Domain mutation。

無唯一結果、來源不足、非法 candidate id、index／model unavailable 或 ambiguity 時必須 fail closed 並進 durable manual fallback。

狀態：`BLOCKED / NOT_PROVEN_COMPLETE`

### GAP-QA-05：API／React readback

API 與 React 必須呈現正式 catalog lifecycle 與 review／publication evidence，不得只把 `enabled_count` 或「啟用／未啟用」當成完成條件。

至少要能 read back：

- current published revision；
- lifecycle；
- owner／reviewer；
- source／provenance；
- audience／role；
- automation boundary；
- conflict／manual-fallback reason；
- item 是否具備自動回答資格。

狀態：`BLOCKED / NOT_PROVEN_COMPLETE`

## 5. 完成 Gate

本 tracker 只有在以下條件全部具備 current evidence 後才能標記 `completed`：

1. 所有預計自動回答項目完成逐題 review；不得用 legacy `enabled` 直接推定 published。
2. versioned catalog 與 `published|retired` lifecycle 已由唯一 owner storage／service 實作並可 read back。
3. conflict／invalid／manual-only items 會被 deterministic 地排除或進人工 queue。
4. runtime retrieval 只使用 READY／published closed candidate set；非法或 ambiguous candidate fail closed。
5. API 與 React 顯示的 publication／review 狀態與 owner storage 一致。
6. Service Help deterministic route、explicit human／wrong-answer precedence 與 Customer Service escalation 維持規格 20／29 的 owner contract。
7. focused automated tests 與至少一輪可重現 readback acceptance 通過。
8. formal spec 29、current source、test、API／UI 與操作文件之間沒有競爭性語意。

## 6. 退役條件

當第 5 節全部完成，且尚未完成事項已由更具體的 current work package／task register 承接時，本文件應標記 `completed` 並從 working tree 移除；稽核需求由 Git history 保留。

在此之前，本文件只作 implementation gap tracker，不授權 production mutation、provider 外送、credential、資料庫 migration 或自行變更 formal Authority。
