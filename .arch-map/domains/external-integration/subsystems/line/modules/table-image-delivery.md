# Module: table-image-delivery

## Parent
- domain: `external-integration`
- subsystem: `line`

## Responsibility
初步候選與正式推薦的資訊一、資訊二及每週服務各產生一張系統資料圖片。初步候選的共用回覆卡獨立；正式推薦的客戶按鈕位於每週服務圖片同頁。圖片顯示資料保存於原 delivery snapshot，初步候選的去識別投影由 Orders owner 保留。
資訊一依受眾分流：月嫂版是 Payroll 單價、預估總薪資及預計付款日；客戶版是 Client Finance 費用與繳款約定，不互相複用財務內容。

## Implementation
- `subsystems/line/table_image_contracts.py` — immutable display documents from owner projections.
- `subsystems/line/table_image_messages.py` — a single initial candidate Flex task contains three image bubbles and one shared action bubble; private document metadata never reaches provider.
- `domains/line/canonical_payload.py` — validates the canonical payload and bounds the private PNG data carried by a confirmation snapshot.
- `subsystems/line/table_image_links.py` — purpose-bound opaque bearer reference, same seven-day lifetime and existing confirmation secret configuration.
- `subsystems/line/table_image_query.py` — verify reference before readonly committed snapshot lookup.
- `infrastructure/line/table_image_renderer.py` — in-memory PNG for tables and each PDF resume page. Resume pages use the same committed picture read and lead the customer confirmation Flex carousel in a single Push.
- `infrastructure/line/table_image_logging.py` — redact capability URLs in uvicorn access and HTTPX transport logs without changing their typed formatter arguments.
- `api/routes/line_table_images.py` — bounded PNG read; public NAS forwards through existing media machine identity to private API.
- shared: `infrastructure/mysql/line_delivery_task_repository.py`, `subsystems/line/ports.py`, `infrastructure/line/messaging_api_adapter.py`, `infrastructure/http/line_media_client.py`, `api/main.py`, `api/nas_apps.py`.
- callers: `subsystems/scheduling/candidate_contact_pool_workflow.py`, `subsystems/scheduling/matching_notification_application.py`.
- preview: `notification-rules-presentation` injects same renderer, only embeds sample/authorized preview PNG data; no delivery URL or token is exposed.

## Contracts
- `document/架構重整/01_規格基線/17_External_Integration_LINE_Access正式規格.md` — LINE table image and display-only preview boundaries.
- `document/架構重整/01_規格基線/02_Assignments_Scheduling_Domain.md` — current confirmation package and recipient rules.

## Verification
- test_root: `tests/domains/external-integration/subsystems/line/modules/table-image-delivery/`
- routing: `.arch-map/tests/domains/external-integration/subsystems/line/modules/table-image-delivery.md`

## Change triggers
Reconcile snapshot representation, signed picture read, provider metadata stripping, renderer or proxy machine boundary changes.
