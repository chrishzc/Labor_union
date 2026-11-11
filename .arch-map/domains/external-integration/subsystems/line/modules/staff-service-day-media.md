# Module: staff-service-day-media

> **Status: Retired (2026-11-10)**
> 依據高齡友善決策，月嫂服務日寶寶日誌與餐食照片回歸於各案件之「LINE 群組相簿」拍照上傳，免除網頁操作；原 LIFF 上傳頁面（`line/static/staff_baby_log.html`）已移除，相關 API 端點退役回傳 HTTP 410 GONE（符合 `19_Global_Entry_Point_Governance.md`）。資料庫既有檔案與關聯完整保留。

## Parent
- domain: `external-integration`
- subsystem: `line`

## Responsibility
[RETIRED] 原由已驗證月嫂在 LIFF 選定 assignment/service-day 後，將 JPG/PNG 寶寶或餐食照片送入 Scheduling 受控檔案 staging。退役後由 LINE 群組成員自行在相簿分享，系統不強制由機器人或網頁表單介接。

## Implementation
- entrypoints:
  - `api/routes/staff_service_day_media.py` (HTTP 410 GONE: `service_day_media_retired`)
  - `api/routes/staff_service_day_logs.py` (HTTP 410 GONE: `service_day_log_retired`)
  - `api/routes/line_media_proxy.py` (HTTP 410 GONE)
  - `line/static/staff_baby_log.html` (DELETED)
- NAS transport: 原 `api/routes/line_media_proxy.py`、`api/routes/private_line_media.py`，現已停止月嫂上傳代理。
- owning mutation: 歷史日誌檔案保留於受控儲存，不再接受新前端日誌上傳。

## Verification
- test_root: `tests/domains/external-integration/subsystems/line/modules/staff-service-day-media/`
- integration: `tests/domains/external-integration/subsystems/line/integration/test_staff_service_day_media_api.py` (驗證 410 GONE)
- static: `tests/domains/external-integration/subsystems/line/modules/staff-service-day-media/contract/test_line_staff_calendar_contract.py`
- routing: `.arch-map/domains/external-integration/subsystems/line/index.md`

## Provenance
- retirement decision (2026-11-10) — `architecture_declared` — `document/架構重整/01_規格基線/15_正式規格索引與裁決總表.md` §19, `20_LINE客服與月嫂自助服務正式規格.md` §5.4。
