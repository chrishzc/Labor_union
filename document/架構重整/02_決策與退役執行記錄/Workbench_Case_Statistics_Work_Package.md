# 待辦看板案件統計串接

狀態：complete。用途：管理這次新增 public GET、React 串接與週報統計修正的跨層驗證；完成後不另建 receipt。

Authority：2026-10-13 使用者確認單排 UI 並要求接上後端。
正式規格：[§15.2](../01_規格基線/15_正式規格索引與裁決總表.md#152-待辦看板案件統計與週報狀態合併2026-10-13-人工裁決)。比較基準：`f67aff0aa32af4d566755e9209cebd2d120c3d37`；保留任務開始前所有 dirty／untracked 成果。

| Requirement | 工作與 owner | 驗證 |
| --- | --- | --- |
| CASESTAT-01／02 | Reporting Query＋既有 MySQL read adapter：曆年、季度、月份與資格計數 | Python 年初、閏月、空集合、資格、年度不縮小 |
| CASESTAT-03 | Reporting aggregation＋XLSX：合併歷史狀態；年度從 1/1 起算 | 既有週報 contract＋歷史 normal 配對、JSON／XLSX |
| CASESTAT-04 | 既有 operations-reports route／schema＋strict client | authenticated GET、invalid quarter/month、缺值保留、no PII、aggregate mismatch |
| CASESTAT-05 | WorkbenchCaseStatistics＋既有看板：沿用核准單排 | 固定十欄、abort／late response、error／retry、refresh、待辦 query 不變、Browser |
| CASESTAT-06 | Reporting 共用資格彙總：已知零值與未知分開，看板／週報同期間一致 | 全年／季度／月份 direct parity、零值與 null、5173 實際代理路由 |

Write set：`subsystems/reporting/weekly_operations_report_query.py`、`weekly_operations_report_export.py`；`infrastructure/mysql/weekly_operations_report_query_adapter.py`；`api/routes/operations_reports.py`、`api/schemas/operations_reports.py`；現有 Reporting client／schema、ReportsPage、看板統計 component／page／CSS；直接受影響測試與 current fixtures；兩個 owning Arch Map leaf、正式規格本節與本文件。

依序完成 server candidate／strict GET、React 串接、focused tests、development localhost 唯讀 Browser、diff／architecture closure。
不得 mutation DB、修改 schema、連 production、呼叫 provider 或部署。開發階段未授權 Git 寫入；使用者後續明確要求 `commit push`，授權將本次統計 write set 提交並推送到既有 `origin/main`，不包含其他任務的 dirty／untracked 成果。
來源不可用時只顯示失敗，不以示意值或零代替；必要驗證缺環境時如實回報 BLOCKED，不把本機測試當作 live DB 通過。
回復限本次 write set；不得清除或覆蓋既有使用者成果。

驗證：PASS — Python 21、React／client 50、完整 TypeScript＋Vite build、lint、git diff --check、architecture closure。Browser 已使用真統計 GET＋development localhost `union_db`，僅掛載唯讀 endpoint 並以 fixture principal 隔離使用者 Session；正式 authentication 的拒絕路徑另由 contract test 驗證。桌機／手機、年度／季度／月份、空月份、failure／retry、refresh 均通過；看板示例卡片不作真實案件驗證來源。全部 DB 操作為 SELECT，未 migration／修改資料／部署。

2026-10-13 runtime 追補：使用者實際入口為 `http://127.0.0.1:5173/admin/#order-workbench-v2`。其代理的 8000 後端未重載，統計 GET 回 404；已重新載入正式 `api.main`，維持登入驗證，並限定 reload 監看 source directories，避免 scratch 檔案引發連續重啟。5173 統計路由現已存在，匿名請求回 401。修正週報將已知零筆不符合案件回 null 的缺陷；看板／週報共用資格彙總，真正未分類仍保留 null。
PASS：新增 parity regression 後 Python 22、React／client 37、production source TypeScript 檢查；真 DB 全年 21 件、第四季 19 件、十月份 19 件，總數及十欄比較均無差異；diff／architecture closure 通過。完整 build 本次 FAILED，原因是工作區客戶名冊測試的既有 `ByRoleOptions.exact` 型別錯誤，未修改其他任務檔案。使用者已在原 Chrome／5173 看板按重試並確認「已顯示數字」，runtime 問題關閉。

建置追補：使用者要求排除客戶名冊測試型別錯誤後，工作區中的相關修正已生效；客戶名冊 35 項測試及完整 TypeScript＋Vite build 均 PASS。該名冊檔案混有另一任務的未提交功能，本統計提交不納入它的完整 diff。
