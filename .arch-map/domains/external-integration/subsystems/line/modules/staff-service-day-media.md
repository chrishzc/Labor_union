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
  - `line/static/staff_schedule.html`
- owning mutation: Scheduling service-day-log workflow registers the controlled object and attachment.

## Verification
- test_root: `tests/domains/external-integration/subsystems/line/modules/staff-service-day-media/`
- contract/integration: `tests/domains/external-integration/subsystems/line/integration/test_staff_service_day_media_api.py` — JPEG/PNG, digest/size/idempotency and typed baby/meal staging
- static: `tests/domains/external-integration/subsystems/line/modules/staff-service-day-media/contract/test_line_staff_calendar_contract.py`
- routing: `.arch-map/domains/external-integration/subsystems/line/index.md`

## Provenance
- verified LIFF identity and controlled-file handoff — `architecture_declared` — current self-service specification.
- implementation and test paths — `source_observed` — current repository.
