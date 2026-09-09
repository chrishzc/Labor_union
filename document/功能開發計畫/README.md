# 功能開發計畫索引

狀態：`current-plans-and-operational-manual`  
更新日期：2026-09-09

本目錄只保存兩類 current 文件：可執行操作／測試手冊，以及尚未完成的 blocked／deferred／proposed 計畫。它們都不取代 `document/架構重整/01_規格基線/` 的正式 owner 與產品語意，也不自行授權 production mutation、provider 外送、部署、付款、credential 或資料庫操作。

## Current 可執行手冊

- [LINE 四大模組詳細測試手冊與 Agent 前置條件規範](LINE_四大模組_詳細測試手冊與前置條件.md)：保留 M0～M4 的 Agent 前置、手機 E2E 操作、readback、驗收層級與 cleanup。它是 current 操作手冊，不是 SSOT；route、schema、owner 或正式驗收契約變更時必須同步更新，且不得覆蓋 `17`、`20`、`23`、`26`、`29`。

## Active／blocked／deferred 計畫

| 文件 | Current 用途 | 下一個 material gate |
|---|---|---|
| [Cloud Run＋單一 Cloud VPN 部署測試計畫](Cloud_Run_單一Cloud_VPN_部署測試計畫.md) | `proposed`，保存隔離環境、worker supervision、故障注入、go/no-go 與 rollback 測試設計。 | 指定隔離 cloud project／NAS DB、operator、budget、rollback 與故障注入範圍；再依當時官方能力更新。 |
| [LINE QA 客服知識契約收斂](LINE_QA客服知識契約收斂計畫.md) | `blocked implementation-gap-tracker`；JSONL／XLSX 只作 review input 與 migration evidence，legacy `enabled` 不代表正式 publication。 | 完成逐題 owner／reviewer／source／audience／approved wording／automation boundary review，落地 versioned `published\|retired` catalog、conflict queue、closed-candidate runtime 與 API／React readback 驗收。 |

Deferred 或 blocked 不等於 retired。這兩份文件在其 material gate 完成、工作被正式 successor 承接或人工明確取消前，不得只因已有高階正式規格而刪除。

## 欄位盤點工作區

`document/文件整併工作區/06_欄位權威性與計算邏輯盤點.md` 及其逐表子目錄依 `15_正式規格索引與裁決總表.md` 只作 field-lineage source：可保存 schema 現況、writer、derived value、freeze 與 live-drift 證據，但不能覆蓋正式 Domain owner。

## Source-review closeout（2026-09-09）

功能開發計畫中的三份 source-review 規格已完成語意處置，不再屬 current working set：

- `LINE_Rich_Menu_多角色圖文選單與互動中心正式規範.md`：有效的 audience、current role、typed action、draft／publish 邊界已由正式規格 `17`／`23`／`29` 承接；與 current 契約衝突的三選單、角色推測、禁止 `richmenuswitch`、硬編 endpoint／page／component 等舊設計不搬移。
- `LINE_Rich_Menu_本機視覺比對與互動模擬工作室正式規範.md`：canvas／area／action validation、before／after、role preview context、零 provider 外送、零 publication task、Preview≠publish 與 terminal readback 已由 `17`／`29` 承接；舊 UI layout／示例 wording／特定 screenshot 細節不建立 Authority。
- `NAS_檔案庫與資料中心管理介面正式規範.md`：仍有效的 Controlled File Storage machine contract 已升格至 `document/架構重整/01_規格基線/30_Controlled_File_Storage_NAS正式規格.md`；Global `00` 只保留跨 Domain 不變量並改指向 `30`。

上述歷史來源與完成後的 disposition 記錄退出 working tree，由 Git history 保存。後續修改直接更新唯一 owning formal spec、current implementation、test 或本目錄操作手冊，不恢復舊 source-review Authority。

## 既有歷史收斂

2026-09-01 已移除的 LINE backend slimming 文件與已完成／superseded 的 Anomalies execution plans仍維持 Git 歷史保存；本次 source-review closeout 同樣不復活舊 baseline、舊 priority、舊 write set、provider cutover 或 production Authority。需要稽核時依 Git history 精確取回，不把歷史文件自動升格為 current requirement。