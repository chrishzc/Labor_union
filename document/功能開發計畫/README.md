# 功能開發計畫索引

狀態：`current-plans-operational-manual-and-source-review`  
更新日期：2026-09-02

本目錄同時保存三類仍有用途的文件：可執行操作／測試手冊、尚未完成的 blocked／deferred計畫，以及尚待逐條搬移的 `source-review`。它們都不取代 `document/架構重整/01_規格基線/` 的正式 owner與產品語意，也不自行授權production mutation、provider外送、部署、付款、credential或資料庫操作。

## Current 可執行手冊

- [LINE 四大模組詳細測試手冊與 Agent 前置條件規範](LINE_四大模組_詳細測試手冊與前置條件.md)：保留 M0～M4 的 Agent前置、手機E2E操作、readback、驗收層級與cleanup。它是current操作手冊，不是SSOT；route、schema、owner或正式驗收契約變更時必須同步更新，且不得覆蓋 `17`、`20`、`23`、`26`、`29`。

## Active／blocked／deferred計畫

| 文件 | Current用途 | 下一個material gate |
|---|---|---|
| [Cloud Run＋單一Cloud VPN部署測試計畫](Cloud_Run_單一Cloud_VPN_部署測試計畫.md) | `proposed`，保存隔離環境、故障注入、go/no-go與rollback測試設計。 | 指定隔離cloud project／NAS DB、operator、budget、rollback與故障注入範圍；再依當時官方能力更新。 |
| [Cloud Run Durable Job Worker Supervision](Durable_Job_Worker_Supervision_延後開發計畫.md) | `proposed / deferred`，保存worker pool、child supervision、lease recovery與outage acceptance。 | 指定隔離cloud test project、OIDC、operator、故障注入與雲端驗收gate。 |
| [LINE QA客服知識契約收斂](LINE_QA客服知識契約收斂計畫.md) | `blocked / approved-for-read-only-inspection`；workbook只作review input。 | loader可用，且每題owner／category／source／approved answer／automation boundary完成人工review。 |

Deferred或blocked不等於retired。這三份文件在其material gate完成、工作被正式successor承接或人工明確取消前，不得只因已有高階正式規格而刪除。

## Source-review 文件

下列歷史文件保存尚未完全搬入正式規格的產品、UI與machine-contract輸入，已恢復但明確為非Authority：

- [LINE Rich Menu多角色圖文選單與互動中心正式規範](LINE_Rich_Menu_多角色圖文選單與互動中心正式規範.md)
- [LINE Rich Menu本機視覺比對與互動模擬工作室正式規範](LINE_Rich_Menu_本機視覺比對與互動模擬工作室正式規範.md)
- [NAS檔案庫與資料中心管理介面正式規範](NAS_檔案庫與資料中心管理介面正式規範.md)

檔名、舊front matter或內文中的「正式」「approved」只代表歷史狀態，不建立current Authority。逐節處置與再刪除條件見 [功能開發計畫來源審閱與退役閘門](SOURCE_REVIEW_DISPOSITION.md)。

## 欄位盤點工作區

`document/文件整併工作區/06_欄位權威性與計算邏輯盤點.md` 及其逐表子目錄已從清理前基準完整恢復。它們依 `15_正式規格索引與裁決總表.md` 只作 field-lineage source：可保存schema現況、writer、derived value、freeze與live-drift證據，但不能覆蓋正式Domain owner。

## 再次退役的必要閘門

任何本批恢復文件再次刪除前，必須同時成立：

1. 每個條目已標記為「已由正式規格承接」「仍有效待搬移」或「已被後續裁決否定」。
2. 所有「仍有效待搬移」已搬入唯一owning formal spec並有current source／test或readback驗證。
3. 所有「已被後續裁決否定」已從code、test、validation JSON、launcher、索引與操作文件consumer移除或改綁。
4. executable consumers、`15` current index及相關正式規格已同步，且刪除後focused verification通過。

目前source-review仍有多項「仍有效待搬移」，所以再次刪除狀態為 `BLOCKED`。

## 既有歷史收斂

2026-09-01已移除的LINE backend slimming文件與已完成／superseded的Anomalies execution plans仍維持Git歷史保存；本次恢復不復活其舊baseline、舊priority、舊write set、provider cutover或production Authority。需要稽核時依原清理commit精確取回，不把歷史文件自動升格為current requirement。