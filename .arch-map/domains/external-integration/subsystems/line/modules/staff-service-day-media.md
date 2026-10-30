# Module: staff-service-day-media

## Parent
- domain: `external-integration`
- subsystem: `line`

## Responsibility
已驗證月嫂在 LIFF 選定 assignment/service-day 後，將 JPG/PNG 寶寶或餐食照片送入 Scheduling 受控檔案 staging，並把 opaque staging facts 與 typed attachment kind 交給日誌 Preview／Apply。

## Implementation
- entrypoints:
  - `api/routes/staff_service_day_media.py`
  - `api/dependencies/service_day_media.py`
  - `api/schemas/line_staff_self_service.py`
  - `line/static/staff_baby_log.html`
- NAS transport: `api/routes/line_media_proxy.py`、`api/routes/private_line_media.py`、`api/dependencies/line_media_proxy.py`、`infrastructure/http/line_media_client.py`。
- NAS 公開 transport 不建立本機 storage workflow；私人端只接受 `line-media-proxy` 機器身分及原始 LINE ID token，重用既有日誌／媒體 endpoint 的 identity、owner 與 transaction。公開 response／idempotency 保持一致；沒有檔案路徑、列目錄或刪除代理。
- 本人日誌附件下載只接受該日誌已保存的 opaque file_id，驗 Scheduling／case／purpose 後才經受控 storage 開檔；原始 LINE token 放 body，回應 private no-store／nosniff。
- NAS composition: `api/nas_apps.py` — 公開 LINE factory 只掛 proxy routes；私人 routes 只掛管理 factory，無 local-storage fallback。
- `POST /service-day-media/settings` 透過同一 verified LINE／私人機器認證取得有效檔案上限；公開入口與私人入口不同設定時取較小上限。共用 runtime 設定由 controlled-files API composition 擁有。
- `subsystems/line/liff_media_upload.py` 接收 transport 提供的容量，保留格式驗證，未新增餐食內容辨識。
- LIFF 同頁提供所選照片預覽、已提交附件預覽／下載與錯誤提示；未知 Apply 結果保留同 key 重試，不另建命令。
- owning mutation: Scheduling service-day-log workflow registers the controlled object and attachment.
- media storage adapter: `infrastructure/line/media_adapters.py` — unassociated media uses shared-root `_staging/line_media`; Rich Menu image uploads route to `04_LINE選單資源 (media)/rich_menus` for the publisher's reader. Write-time shared layout readiness, no constructor writes; canonical metadata/owner and existing explicit development roots remain unchanged.

## Verification
- test_root: `tests/domains/external-integration/subsystems/line/modules/staff-service-day-media/`
- integration_root: `tests/domains/external-integration/subsystems/line/integration/test_private_line_media.py`
- contract/integration: `tests/domains/external-integration/subsystems/line/integration/test_staff_service_day_media_api.py` — JPEG/PNG, digest/size/idempotency and typed baby/meal staging
- static: `tests/domains/external-integration/subsystems/line/modules/staff-service-day-media/contract/test_line_staff_calendar_contract.py`
- routing: `.arch-map/domains/external-integration/subsystems/line/index.md`

## Provenance
- verified LIFF identity and controlled-file handoff — `architecture_declared` — current self-service specification.
- implementation and test paths — `source_observed` — current repository.
