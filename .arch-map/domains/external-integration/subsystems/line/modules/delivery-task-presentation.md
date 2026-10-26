# Module: delivery-task-presentation

## Parent
- domain: `external-integration`
- subsystem: `line`

## Responsibility
呈現LINE-owned delivery task的既有server pagination、allowlisted filter、masked item與detail navigation。一般畫面不得顯示query error code或raw backend／provider detail；不得改寫delivery intent／receipt、worker、retry或provider transport責任。

## Implementation
- primary: `ui_react/src/components/LineDeliveryTaskWorkbench.tsx`
- transport: `api/routes/line_tasks.py` — 現行訂金、各期逾期、日誌、資訊問答與服務日期／代班來源映射到既有公開分類；list／detail 不回傳 raw recipient、payload 或 provider error。未知來源仍 fail closed。

- client: `ui_react/src/api/line_delivery/line_delivery_query_client.ts` — category 審核／款項／客服篩選在伺服器分頁前套用，總數同一集合。
- 現行來源含 service-start-day／response／completion 與 second-payment reminder／settled，沿原 order／finance 公開分類。

## Contracts
- `document/架構重整/01_規格基線/20_LINE客服與月嫂自助服務正式規格.md` — LINE delivery與provider邊界。
- `document/架構重整/01_規格基線/12_Global_效能與UX體感架構.md` — 一般畫面資訊層級與closed error boundary。

## Verification
- layout_status: `custom_current`
- test_root: `ui_react/src/tests/line_delivery_task_workbench.test.tsx`
- routing: `.arch-map/tests/domains/external-integration/subsystems/line/modules/delivery-task-presentation.md`
- integration_root: `tests/test_line_delivery_public_query_route.py`

## Change triggers
Reconcile when delivery-task presentation、pagination/filter/stale suppression、closed error或focused test location changes。
