# Phase 6 Streamlit retirement impact inventory（2026-08-17）

## Current result

`PHASE6_NOT_READY`。搜尋current source／tests／active docs得到211個含Streamlit／8501的候選paths；
這是舊盤點的候選引用數，不是刪除清單；因原紀錄未保存command、scope、exclude rules、base ref及
`files | matches`計數種類，**211不得作為可重現release input**。Phase6A machine-readable inventory必須
重新產生並保存上述metadata。歷史evidence／receipts必須保留。

Fresh registry baseline也不是綠燈：queue 526、current discovery 530，已漏4個API entries；另有1個
Streamlit與11個React identities未被current generator收錄。Phase6 validator必須分開驗證21個UI
cutover identities與完整API／CLI／UI queue，不能只補頁面或沿用自我生成expected。

Fresh 2026-08-17 readiness command（entry queue + launcher inventory + local smoke + online script）結果為
`1 failed, 14 passed`；失敗固定在 queue/discovery drift。這是 `PHASE6_NOT_READY` 的正向 fail-closed
證據，不授權移除任何 Streamlit source、dependency、launcher 或 test。

同日執行 `scripts.launcher_preflight --profile local-windows` 與
`scripts/launchers/start_local_development.bat --dry-run` 均回傳 `status: ready`、`side_effects: none`。
這只證明目前 **API + Streamlit** 的 legacy local profile依賴齊全；因 preflight／dry-run 尚未盤點React
artifact、5173／production hosting或rollback identity，不能把此PASS解讀成React runtime或retirement ready。

## Current responsibilities that still depend on Streamlit

- Runtime registry：`ui/app.py`動態載入10個pages。
- Launcher：Windows、Unix、no-auth與ngrok supervisor。
- Health：8501 `/_stcore/health`、service monitor、smoke與preflight。
- Migration rehearsal：restart/runtime targets與`--rehearsal-streamlit-port`。
- Dependencies：`streamlit`、`streamlit-cropper`及lockfile。
- Current docs：root README、launcher README、Developer Guide、Deployment SSOT。
- Tests：AppTest、panel/session-state、launcher/monitor、auth、migration rehearsal與LINE runtime contract。

## Three required waves

1. **6A Release gate**：exact核准後可先建立fail-closed validator／inventory；current結果必須not-ready，
   且不移除任何source。
2. **6B Runtime successor**：核准production React hosting、artifact/health/CSP/rollback，更新launcher/monitor/rehearsal。
3. **6C Per-entry source retirement**：依精確manifest逐entry刪除Streamlit pages/helpers/tests及最後dependencies；不得整個`ui/`批次移除。

Phase6B目前另有`BLOCKED_DEPLOYMENT_SSOT_CONFLICT`：18號正式規格已退役target-host／vendor deployment
profile，而proposed `/admin/`方案只能作application artifact runtime的bounded amendment。未經exact approval
不得修改18號規格、掛載`/admin/`或建立production selector；核准也不得復活特定host／vendor／RTO/RPO決策。

## Files that must remain until all gates pass

- `ui/app.py`、10個runtime pages及Streamlit rollback artifact。
- `scripts/run_service_monitor.py`、entry queue、migration rehearsal abstraction。
- 所有尚未被React browser／rollback evidence取代的Streamlit tests。
- FastAPI、Domain、Subsystem、workers、DB data及歷史evidence。

## DB gate

Scope PASS（唯讀inventory）；其餘DB gates NOT_RUN；結論`DB_CHANGE_NOT_READY`。
