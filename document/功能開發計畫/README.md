# 功能開發計畫索引

本目錄只保留尚在規劃、blocked／deferred，且尚未由正式規格完整承接的 initiative。功能計畫不建立 production mutation、provider、deployment或資料庫操作 Authority；正式 owner與產品語意以 [`15_正式規格索引與裁決總表.md`](../架構重整/01_規格基線/15_正式規格索引與裁決總表.md) 及其 Domain／Global規格為準。

Task 96目前是 [bounded closeout](../架構重整/02_決策與退役執行記錄/96_Current_剩餘代辦任務總表.md)，不再是active施工register。任何 deferred／not-run功能若要恢復，應由對應owner建立新的current successor與明確acceptance，不得把舊計畫中的priority、baseline或write set直接復活。

## Active／deferred計畫

| 文件 | Current用途 | 下一個material gate |
|---|---|---|
| [Current-state異常機制瘦身執行計劃](PROV-20260829-current-state-anomaly-slimming-execution-plan.md) | 歷史execution lineage與尚未完成的文件收斂來源；current產品contract已由`06_Anomalies_Domain.md`固定為runtime exact set `{LINE-006}`。本鏈仍被正式索引與generated inventory引用，暫不移除。 | 先清理formal index／generated inventory的歷史連結，再判定整鏈移除；不得因此重開多碼Anomalies產品。 |
| [NAS檔案庫與資料中心管理介面正式規範](NAS_檔案庫與資料中心管理介面正式規範.md) | `approved`的UI／資料中心規劃來源；不取代Controlled Files owner contract。 | 取得受控NAS target、authenticated Browser acceptance與明確storage boundary。 |
| [Cloud Run＋單一Cloud VPN雲端部署測試計畫](Cloud_Run_單一Cloud_VPN_部署測試計畫.md) | `proposed`，僅作隔離環境與go/no-go測試設計。 | 指定隔離cloud project／NAS DB、operator、budget、rollback與故障注入範圍。 |
| [Cloud Run Durable Job Worker Supervision](Durable_Job_Worker_Supervision_延後開發計畫.md) | `proposed / deferred`。 | 指定隔離cloud test project、OIDC、operator、故障注入與雲端驗收gate。 |
| [LINE QA客服知識契約收斂](LINE_QA客服知識契約收斂計畫.md) | `blocked`；workbook只作review input。 | loader可用，且每題owner／category／source／approved answer完成人工review。 |

## Current產品參考

下列文件仍保存未完全搬入正式規格的產品／驗收輸入，因此保留：

- [LINE Rich Menu多角色圖文選單與互動中心正式規範](LINE_Rich_Menu_多角色圖文選單與互動中心正式規範.md)
- [LINE Rich Menu本機視覺比對與互動模擬工作室正式規範](LINE_Rich_Menu_本機視覺比對與互動模擬工作室正式規範.md)

Anomalies／LINE repository-local整合結果由 [`PROV-20260830-line-anomalies-slimming-integration-receipt.md`](../架構重整/03_追蹤清單與證據/evidence/PROV-20260830-line-anomalies-slimming-integration-receipt.md) 保存；該receipt不代表provider、DB engine、Browser、production或deployment acceptance。

## 2026-09-01文件收斂

下列LINE backend slimming文件綁定舊baseline、舊counts與已過期的`awaiting-user-resume`狀態；其仍有效的owner／boundary已由`17`、`20`、`23`、`26`、production code與Task 96 closeout承接，因此自current工作樹移除，由Git歷史保存：

- `LINE_BACKEND_SLIMMING_PLAN.md`
- `LINE_BACKEND_SLIMMING_POST_PREP_AMENDMENT.md`
- `LINE_BACKEND_SLIMMING_PARALLEL_EXECUTION_REFRESH.md`
- `LINE_BACKEND_STATE_AUDIT.md`
- `LINE_BACKEND_RESOLVED_WRITE_SET.md`

需要稽核時，從清理前基準 commit `1f7c9cd7d90895f7846333c48cdb37c95da4caad` 精準取回。舊文件中的LINE legacy retirement、provider cutover或其他未完成工作，不因文件移除而視為完成；是否恢復必須由新的current successor依live source重新盤點。
