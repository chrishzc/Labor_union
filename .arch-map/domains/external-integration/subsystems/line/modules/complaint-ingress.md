# Module: complaint-ingress

## Parent

- domain: `external-integration`
- subsystem: `line`

## Responsibility

將符合 `complaint.v1` 固定詞／前綴的 LINE 明確客訴導入 Customer Service
escalation 的 caller-owned UoW；例如「我要客訴：服務態度很差，請協助處理。」。
一般「退費／主管處理」語句不因此自動取得 complaint 語意。

另承接明確呼叫專員與 active conversation hold：呼叫文字或 typed postback 直接建立去敏 ticket、hold、masked alert intent 與簡短受理回覆；一般留言不啟動聊天室 AI 或自動轉人工。「問題／其他問題／5／6」只開自助導覽，active hold 內仍附加原案件。專員正式結案時解除 hold 並通知完成。舊回答錯誤／繼續／恢復 AI 入口只提示停用，不開單、不得結案或解除 hold。LINE 不擁有客服、Payroll 或 assignment root。

## Implementation

- `subsystems/line/runtime_human_escalation_source.py`
- `subsystems/line/service_help_application.py`
- `subsystems/customer_service/escalation_application.py`
- `subsystems/customer_service/escalation_contracts.py`
- `infrastructure/mysql/customer_service_repository.py`
- `infrastructure/mysql/customer_service_escalation_repository.py`
- `subsystems/line/human_escalation_delivery.py`
- 客訴／runtime critical 新告警組裝時讀取既有訊息設定的說明文字；去敏摘要、目標快照與管理入口仍沿原流程。一般轉真人通知不套用客訴文案，既有 delivery task 不重寫。
- `subsystems/line/delivery_worker.py`
- `infrastructure/mysql/line_delivery_task_repository.py`
- `api/routes/customer_service.py`
- `ui_react/src/pages/LineManagementPage.tsx`

## Current flow and readback

- 工單收到新訊息後可以 `resolved → handling`；新的 escalation 仍走
  `open → claimed → handling → resolved`。`start_handling_for_escalation()`
  在 ticket version CAS 下接受 `waiting | handling`，不能因工單已重新開啟而拒絕接手；
  沒有新訊息的 `resolved` 工單仍不能由此操作直接接手。
- 2026-10-22 人工裁決取消群組告警。客服告警只擷取唯一啟用管理員個人對象；沒有或多個管理員不任選一人。新 intent 不選群組，歷史 group intent 拒絕投遞；provider 前亦拒絕既有群組告警工作。
- 告警投遞來源為 `customer_service_escalation` 與 `escalation:<id>`，terminal
  outcome 回寫 escalation 的告警狀態。管理員結案後發給客戶的完成通知則使用既有
  `customer_service_ticket` 與 ticket id，僅記錄其 delivery task outcome，不覆蓋告警狀態。
- 告警附上 catalog「開啟客服系統」對應的 `/line-mobile-admin?target=customer_service`
  導航。基底依序取非空 `LINE_PUBLIC_BASE_URL`、`BASE_URL`；缺少或格式無效時回報
  `human_escalation_management_url_unavailable`，catalog 入口缺失則為
  `human_escalation_management_entry_unavailable`，由既有 outbox failure 路徑記錄。
  手機測試須配置可到達的本站 HTTPS URL；程式的 URL 格式檢查本身不證明可連線。
- 此 URL 不含授權 token；mobile-admin 仍驗證 LINE 身分與管理員 binding。
  群組專用 Safe Review Link 已退役，普通導航仍須驗證 LINE 管理員身分。

## Verification

- test_root: `tests/domains/external-integration/subsystems/line/modules/complaint-ingress/`
- source baseline: PR #299 `4eb58e07e94660308ba8afd05d39931f0301fdf1`。
- recorded evidence: run `34733277249` / job `103659935152` 的 29 項 M4 回歸，與保留的 24 項 LINE 回歸合計 53 項通過；部分實際 adapter SQL 在 SQLite 執行，其餘使用 owner/UoW/provider 替身。此證據不涵蓋完整 pytest、MySQL 鎖／整合、手機、真實 provider 或部署；不改寫既有手機驗收紀錄。

## Safety boundary

Raw complaint text is not carried into the escalation command, ticket note, or
alert. The Customer Service owner retains its required routing identity; the
source fingerprint is evidence only. Provider delivery remains the existing
committed intent/outbox boundary.

客服正式結案沿 Customer Service owner 的 version／lock；LINE 的舊 AI 按鈕與指令不得呼叫 requester resume writer，也不改寫既有結案 receipt。
