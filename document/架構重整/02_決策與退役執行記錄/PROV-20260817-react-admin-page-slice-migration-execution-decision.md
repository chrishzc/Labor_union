---
doc_type: architecture-decision
declared_status: approved
decision_status: completed
date: 2026-08-17
owner: integration-owner
domain: Global / Admin Web Presentation
subsystem: react-admin-page-slice-migration
initiative: react-admin-migration
decision_scope: React page-by-page real-data migration routing and evidence gates
approval_required: 已由使用者明確採用「逐頁精簡遷移模式」；個別 production、mutation、entry cutover 與 retirement 仍須各自 exact Work Package 核准
updated: 2026-08-17
---

# React 管理端逐頁精簡遷移執行裁決

## 1. 人工裁決與問題修正

2026-08-17 使用者明確裁決：「採用逐頁精簡遷移模式」。本裁決修正先前把 React query 接線、後端契約治理、Scenario／DB 驗收、entry cutover 與 Streamlit 退役串成單一全域前置 DAG 的執行方法。

原有治理文件仍是各自範圍的權威來源；本文件只負責 migration routing。它不改寫 Domain 語意、Part 00 的資料安全規則、既有 Work Package 的歷史證據，也不授權未核准的 production mutation。

## 2. 核心執行規則

每一個 React page／entry 以一個最小 page-slice Work Package 推進。Work Package 必須只選取該頁實際需要的 component、bounded client、adapter、測試與文件，並保留現有 UI 結構。

1. **Existing typed GET 直接接線**：已有穩定、已驗證的 typed GET，直接建立 page client／adapter 並接入既有畫面；不等待其他頁、全域 Scenario runtime、DB engine 或 mutation predecessor。
2. **Raw 但穩定的 response 只做最小 typed view**：若頁面所需 GET 已存在但 public response 尚未封閉，只建立該頁最小 typed view／redaction contract；不得把 raw `dict` 穿透到 renderer，也不得藉機重構整個 Domain。
3. **次要缺欄原位 unavailable**：缺少非核心欄位、detail、timeline、recovery 或未核准 projection 時，保留既有 slot 並明確顯示 `unavailable`／後端尚未提供；不得用 mock、前端推導或假成功補洞。這不阻塞同頁其他已可驗證區塊。
4. **Mutation 獨立**：Preview／Apply／receipt、action handler、狀態機與外部副作用不因 query 已接線而自動解鎖；每個 mutation family 另有 bounded Work Package 與自己的 contract、scenario、DB／transaction、browser 與 receipt gate。
5. **只有真正的 owner／transaction／provider／DB 變更才另包**：需要重新裁決 SSOT、owner、outer UoW、schema／seed／migration、production data 或外部 provider 的項目，建立明確 gap／Work Package；不要為一個缺欄位建立跨全域的前置工程。
6. **現有 Global／Scenario 工作收尾但不作所有 query 前置**：Global FastAPI error boundary、correlation precedence 與 Scenario canonical verifier 仍依其已核准包完成並保留證據；它們只在該頁實際依賴其 public contract、controlled-data scenario 或 mutation gate 時成為前置。
7. **既有 DB 只作 GET UI 驗收**：可使用既有資料庫觀察唯讀 UI query 結果；不得以既有 DB 執行 mutation、seed、migration、repair 或建立測試資料。需要 mutation／controlled-data evidence 時，仍依對應 Work Package 的隔離環境與 gate。
8. **不使用 DDH**：本裁決、Work Package、gate 或 evidence 不以 DDH 作為必要工具或授權來源。

## 3. Page-slice 生命週期

```text
page inventory
→ existing typed GET / minimal typed view 判定
→ page adapter 接既有 component
→ unavailable slots 明確化
→ page-level query verification（API + UI + error/empty/reload）
→ 只對該頁未閉合的 mutation／owner／transaction／provider 建立 successor
→ 該頁 query candidate 完成後才進 entry-specific cutover readiness
```

一個 page-slice 的 query 完成，不代表整個 domain、entry、mutation 或 Streamlit retirement 完成；同樣地，另一頁的 blocker 不得回溯阻塞本頁已閉合的 typed GET。

## 4. Page-slice Work Package 最小內容

每包只需記錄以下內容，並由 Integration Owner 在最新 base 上凍結：

- page／route／對應 Streamlit entry 與 UI surface。
- 現有 typed endpoint、最小 response view、auth／error envelope 與 adapter mapping。
- 每個 UI slot 的 `wired`、`unavailable`、`blocked-by-mutation` 或 `out-of-scope` disposition。
- exact write set：page、client、adapter、focused tests、evidence 與必要文件；不得競寫 shared transport、lockfile、catalog 或其他 page。
- query-only acceptance：success、empty、typed error／auth、timeout／abort、reload／deep-link，以及既有 DB UI evidence（若可用）。
- mutation follow-up：只有在頁面確實需要 mutation 時，列出獨立 successor、owner、transaction、provider、scenario／DB gate 與人工確認入口。
- rollback：query failure 可回到既有 Streamlit entry；不回滾 Domain data，也不以保留舊 URL冒充 operational rollback。

## 5. Gate routing

| Slice 類型 | 必要前置 | 不應被要求的全域前置 | 完成上限 |
|---|---|---|---|
| Existing typed GET | endpoint／schema／auth 可驗證；page adapter 與 query tests | mutation scenario、disposable DB engine、其他頁 query、provider | `query-real-data-validated` |
| Raw stable GET 的最小 typed view | 該頁最小 public view、redaction、typed error與focused contract test | 全域 Domain 重構、無關 Part、mutation DB receipt | `query-contract-validated` 或 `blocked-public-contract` |
| Mutation／controlled data | exact command contract、Preview／Apply、outer UoW、scenario lineage、隔離 DB／browser／receipt | 不相關頁面與不相關 provider | `mutation-local-validated`／`blocked` |
| Entry cutover | 該 entry 的 page slices、entry registry、forward／rollback、dual-run與觀測 evidence | 未被該 entry 消費的其他 domain | `readiness-candidate`／`switched-observation` |
| Streamlit retirement | 單一 entry 的 replacement、rollback retention、caller／data lineage與 retirement receipt | 尚未完成的其他 entry | `retired`（逐 entry） |

Part 00 的 Scenario／DB receipts 只有在 slice 宣稱 mutation、controlled data、transaction、worker、external side effect 或跨站 Domain invariant 時才是該 slice 的必要 gate。對既有 typed GET 的 real-data query 接線，Part 00 仍提供語意與安全原則，但不再作無條件的 implementation blocker。

## 6. 對既有文件與 Work Package 的處置

- 不刪除、不覆蓋、不重算任何舊 Work Package、receipt、Scenario 或 DB evidence。
- 原本的 central DAG、B0～B9 predecessor waves 與 Global／Scenario predecessor 條目，標記為 **mutation／controlled-data／cross-cutting contract lane** 的 routing；不得再解讀為所有 page query 的總前置。
- 已核准且正在收尾的 Global FastAPI correlation precedence 與 Phase 3 Scenario canonical verifier，相依頁面仍依其自身 contract 使用；其完成狀態不會被本裁決虛構或提前升級。
- 既有 page-specific gap／Work Package 保留原狀；若只是 query 欄位缺口，新增 successor 應保持 page scope，不將無關 action 一併解鎖。
- Main migration plan、UI scenario plan、02/README 與 Phase 3～6 dependency matrix 必須各自留下本裁決的 inbound reference，避免出現第二份 page-slice SSOT。

## 7. 明確禁止

- 不以「整頁有一個 disabled button」阻塞其他 GET／read-only slot。
- 不以既有 UI 能顯示、HTTP 200、mock、歷史 receipt 或現有 DB final state 宣稱 mutation／Domain acceptance。
- 不把 query-only 完成宣稱為 entry cutover、replacement 或 Streamlit retirement。
- 不為了縮短 page slice 而放寬 typed decoding、auth、PII masking、correlation、error envelope 或既有 Domain invariant。

## 8. 驗收與文件同步

本裁決的落地證據為：

1. 本文件本身是唯一 canonical routing decision。
2. React migration main plan 的 execution mode、Phase 3～6 routing 與逐頁矩陣引用本文件。
3. UI scenario master plan 明確區分 query-only page evidence 與 mutation／controlled-data evidence。
4. Phase 3～6 dependency matrix 將 page-query lane 與 mutation／controlled-data DAG 分開。
5. 02/README 僅保留本文件與相關已完成修訂的索引列；不建立第二份決策摘要。

本次同步只改文件；未修改 production、tests、DB、schema、seed、migration、launcher、entry router、部署或 Git history。
