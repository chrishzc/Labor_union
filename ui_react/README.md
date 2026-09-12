# 工會行政系統 React 管理端

`ui_react/` 是目前唯一的管理端 UI，使用 React、TypeScript 與 Vite。業務操作經 typed API client 呼叫 FastAPI，再由 owning Subsystem／Domain 處理；前端不建立業務根事實。

## 啟動與 API

完整本機環境的依賴安裝見 [根 README](../README.md)，FastAPI、React、monitor 與 workers 的啟動方式見 [啟動與本機維運腳本](../scripts/launchers/README.md)。`npm run dev` 只啟動前端，不會啟動後端或資料庫。

標準開發頁面為 `http://127.0.0.1:5173/admin/`。前端 API transport 使用相對 `/api`；[vite.config.ts](vite.config.ts) 的開發代理讀取 `VITE_DEV_API_TARGET`，未設定時指向 `http://127.0.0.1:8000`。

## 前端指令

下列命令在 `ui_react/` 執行；首次使用或鎖檔變更後先執行 `npm ci`。

| 命令 | 用途 |
|---|---|
| `npm run dev` | 啟動 Vite 開發伺服器。 |
| `npm test -- <直接相關測試路徑>` | 以實際測試路徑取代括號內容，執行 focused Vitest 測試。 |
| `npm run build` | 執行 TypeScript build check 並產生 Vite 前端產物；不部署。 |
| `npm run lint` | 執行目前的 Oxlint 設定。 |

指令定義以 [package.json](package.json) 為準。測試優先選擇 `src/tests/` 中直接受影響的檔案；只有 failure signal 或 release acceptance 明確要求時才執行完整 `npm test`，不將表內所有命令當作每次修改的固定 gate。

## 程式定位

管理端入口由 `src/components/MasterLayout.tsx` 的 navigation 與 `src/App.tsx` 的 render branch 共同承接，API clients 位於 `src/api/`。工作範圍、規格權威與停止條件依 [AGENTS.md](../AGENTS.md)，不以此 README 或舊 Streamlit UI 取代正式業務規格。
