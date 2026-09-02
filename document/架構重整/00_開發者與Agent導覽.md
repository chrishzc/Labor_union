# 重整後開發者與 Agent 導覽

## Current authority

1. 使用者最新明確裁決。
2. `AGENTS.md` 的工作範圍與停止條件。
3. `.arch-map/index.md` 與最接近的 Module／Subsystem leaf。
4. `01_規格基線/15_正式規格索引與裁決總表.md` 指向的 current 正式規格。
5. Current source、schema、focused test 與實際 readback。

歷史計畫、舊 Work Package、封存 evidence、已刪檔名與 Git history 只供追溯，不是 current implementation authority。

## Fast navigation

只有功能或業務描述時：

1. 在 `.arch-map/` 做 filename-only bounded search。
2. 讀最接近的 leaf。
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
