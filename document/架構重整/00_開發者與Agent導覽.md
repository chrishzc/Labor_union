# 重整後開發者與 Agent 導覽

## Current authority

使用者最新明確裁決優先。正式業務語意依 `01_規格基線/15_正式規格索引與裁決總表.md` 與較新的 formal amendment 指向的 current owner spec；既有業務規格、狀態機與欄位權威依正式規格保留來源追溯。

`AGENTS.md` 與 [Agent 任務分級與交付規範](./00_Agent任務分級與交付規範.md) 決定工作範圍、停止條件與最小交付，不取代正式業務語意。

`.arch-map/` 只提供導航 evidence，閱讀順序不是權威順序。Current source、schema、focused test 與實際 readback 只提供現況或驗證 evidence，不能反向創造需求或覆蓋正式規格。

歷史計畫、舊 Work Package、封存 evidence、已刪檔名與 Git history 只供追溯，不是 current implementation authority。

## Fast navigation

任務分級與最小交付先依 [Agent 任務分級與交付規範](./00_Agent任務分級與交付規範.md)；其餘導航依下列最短路徑。

只有功能或業務描述時：

1. 在 `.arch-map/` 做 filename-only bounded search。
2. 命中唯一最接近的 leaf 時直接讀取；候選不明時才讀 `.arch-map/index.md`，沿單一 Domain → Subsystem → Module 最短路徑定位。
3. leaf 已列出 owner、implementation、adapter 與 focused test 後停止。
4. 只有路徑失效或缺少會改變實作決策的事實時，才在 owning directory 做一次 bounded source search。

已知 exact path／symbol 時直接開檔，不先掃 repository。

## Current source layout

| 需求類型 | 先讀／先改的邊界 |
|---|---|
| 業務命令 | owning Domain → `subsystems/` Query／Preview／Apply → typed API schema／route → React API client／page |
| 唯讀查詢 | owning read model／query repository → API route → `ui_react/src/api/` → adapter／page |
| 管理端 UI | `ui_react/src/components/MasterLayout.tsx` navigation → `ui_react/src/App.tsx` render → page／component／typed client |
| 銀行流水、補助或付款 | 對應 Finance Import、Client Finance、Staff Payables 或 Government Subsidy owner；UI 不建立根事實 |
| LINE／Webhook | inbox／outbox／durable task → owning application workflow → provider adapter |
| Migration | release manifest → candidate／backup／validation → explicit Apply；不得由啟動器隱式套用 |
| API／CLI 退役 | 確認 current caller、owner、replacement 與 focused readback；不得只因 static search 為零就刪除 |

## React-only UI boundary

Current 管理端只有 `ui_react/`。舊 `ui/`、`.streamlit/`、Streamlit API clients／pages／components、rollback deep link、entry queue 與 retirement validator 已移除。

不得：

- 尋找或復活 `ui/app.py`；
- 新增 Streamlit dependency；
- 把舊 UI 測試當成 current acceptance；
- 以歷史 queue／receipt 阻擋 current React 修改；
- 讓 React 組合金額、日期、資格、狀態或 transaction result。

React entry 必須同時存在於：

- `ui_react/src/components/MasterLayout.tsx` navigation；
- `ui_react/src/App.tsx` render branch。

## Verification

優先使用最直接的 focused oracle：

```powershell
.\.venv\Scripts\python.exe -m pytest <direct-test>
cd ui_react
npm test -- <direct-test>
```

只有 failure signal、跨 boundary 修改或 release acceptance 明確要求時才擴大。

Schema、migration、production、provider、credential 與外部寫入是不同權限；文件或測試通過不構成執行授權。

## 零元客戶基準義務升級（2026-09-29）

本次人工授權範圍為 schema／migration 修復、完成本機 development DB 關卡並套用升級、commit／push；
原匯入檔案不在本機，匯入重試由操作人員在原主機完成。部署或 production DB 不在範圍內。
Orders 歷史服務天數帳務沿用正式規格 27 §6.5、§7：全補助且無樓層費的零元客戶基準義務
立即 settled，仍保留事件與 source identity，供結清 readback 與後續差額關聯使用。

新 release `labor-union-client-zero-obligation-establishment-2026-09-29-v1` 僅替換
`client_obligation_events.chk_client_obligation_event_amount`。新增例外限定 `established`、
before／after 金額都為零且到期日都空；負金額與其他未異動事件仍拒絕。
沒有 system seed、business-row backfill、資料刪除、owner／transaction 或 entry switch 變更。
新安裝與 preserve-data chain 共用 part 1046，舊 part 111 與其 immutable manifest 保留原樣。

本版本的可攜 qualification 由真實 MySQL fresh bootstrap 與代表性資料 dump → candidate → verify
產生，發布位置為 `validation/receipts/PROV-ZERO-OBLIGATION-local-additive-qualification-20260929.json`。
qualification 只證明本版本 artifact，不取代另一台主機自己的備份與 current metadata 檢查；
原始 dump、local backup、journal 與操作 receipt 留在 ignored scratch，不提交業務資料。

既有資料庫先使用 `.venv\Scripts\python.exe -m scripts.update_local_database` 取得零寫入計畫，
確認 latest release 與待套用 part 1046；未知或缺失約束需阻擋，不得手動略過。
套用前仍須依 Migration 正式規格 §9 完成 disposable fresh-bootstrap、preserve-data candidate、
source backup 與 qualification gates，並取得 DB 執行授權。完成 schema Apply 後再重試歷史訂單 workbook。
相同 release 已為 exact 時不重套；套用失敗可保留 journal 依既有 runner resume。
切換前可丟棄 candidate 並保留 source；一旦有零元 established event，不可回退舊約束。

靜態驗收使用 migration module 的 `contract/test_client_zero_obligation_establishment_schema.py`，
涵蓋 hash／fresh／chain、一致 descriptor、predecessor／successor／drift 與 earlier-artifact successor。
其中 MySQL CHECK 情境只做 SELECT、不寫資料；未設定完整 disposable MySQL 環境時明確 skip，
不能代替真正 fresh／preserve engine qualification。升級是否可交付以正式 §9 gate table 為準。
