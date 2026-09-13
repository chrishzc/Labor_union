# Module: complaint-ingress

## Parent

- domain: `external-integration`
- subsystem: `line`

## Responsibility

將符合 `complaint.v1` 固定詞／前綴的 LINE 明確客訴導入 Customer Service
escalation 的 caller-owned UoW；例如「我要客訴：服務態度很差，請協助處理。」。
一般「退費／主管處理」語句不因此自動取得 complaint 語意。

另承接真人轉接確認／active conversation hold／原 requester 恢復 AI：自然的
找真人／拒絕 AI／回答錯誤語句在確認前零 ticket／hold，明確 postback 才建立去敏
ticket、automation hold、masked alert intent 與 durable notice；此確認規則不能
混寫為所有 explicit complaint 都必須先點 postback。requester resume 由 Customer
Service owner 原子結案並 release hold。LINE 不擁有客服、Payroll 或 assignment root。

## Implementation

- `subsystems/line/runtime_human_escalation_source.py`
- `subsystems/line/service_help_application.py`
- `subsystems/customer_service/escalation_application.py`
- `subsystems/customer_service/escalation_contracts.py`
- `infrastructure/mysql/customer_service_repository.py`
- `infrastructure/mysql/customer_service_escalation_repository.py`
- `subsystems/line/human_escalation_delivery.py`
- `subsystems/line/delivery_worker.py`
- `infrastructure/mysql/line_delivery_task_repository.py`
- `api/routes/customer_service.py`
- `ui_react/src/pages/LineManagementPage.tsx`

## Current flow and readback

- 工單收到新訊息後可以 `resolved → handling`；新的 escalation 仍走
  `open → claimed → handling → resolved`。`start_handling_for_escalation()`
  在 ticket version CAS 下接受 `waiting | handling`，不能因工單已重新開啟而拒絕接手；
  沒有新訊息的 `resolved` 工單仍不能由此操作直接接手。
- 客服告警優先擷取唯一啟用群組的 recipient/configuration snapshot。額外啟用的
  管理員通知對象不使群組失效；多個啟用群組仍拒絕。沒有群組且恰有一個啟用管理員
  時保留既有行為，多個管理員不任選一人，也不新增多對象發送。
- 告警投遞來源為 `customer_service_escalation` 與 `escalation:<id>`，terminal
  outcome 回寫 escalation 的告警狀態。管理員結案後發給客戶的恢復通知則使用既有
  `customer_service_ticket` 與 ticket id，僅記錄其 delivery task outcome，不覆蓋群組告警。
- 告警附上 catalog「開啟客服系統」對應的 `/line-mobile-admin?target=customer_service`
  導航。基底依序取非空 `LINE_PUBLIC_BASE_URL`、`BASE_URL`；缺少或格式無效時回報
  `human_escalation_management_url_unavailable`，catalog 入口缺失則為
  `human_escalation_management_entry_unavailable`，由既有 outbox failure 路徑記錄。
  手機測試須配置可到達的本站 HTTPS URL；程式的 URL 格式檢查本身不證明可連線。
- 此 URL 不含授權 token；mobile-admin 仍驗證 LINE 身分與管理員 binding。
  普通導航與短效一次性 Safe Review Link 是不同路徑，不能用前者宣稱規格 26 的
  `R4-SAFE-LINK` 告警直達閉環已通過。

## Verification

- test_root: `tests/domains/external-integration/subsystems/line/modules/complaint-ingress/`
- shared regression: `tests/domains/external-integration/subsystems/line/subsystems/test_line_m4_continuation_regressions.py` — reopened ticket SQL/CAS、group/admin selection、告警導航、客戶結案通知與群組告警 outcome 分離。
- source baseline: PR #299 `4eb58e07e94660308ba8afd05d39931f0301fdf1`。
- recorded evidence: run `34733277249` / job `103659935152` 的 29 項 M4 回歸，與保留的 24 項 LINE 回歸合計 53 項通過；部分實際 adapter SQL 在 SQLite 執行，其餘使用 owner/UoW/provider 替身。此證據不涵蓋完整 pytest、MySQL 鎖／整合、手機、真實 provider 或部署；不改寫既有手機驗收紀錄。

## Safety boundary

Raw complaint text is not carried into the escalation command, ticket note, or
alert. The Customer Service owner retains its required routing identity; the
source fingerprint is evidence only. Provider delivery remains the existing
committed intent/outbox boundary.

Requester resume 必須綁定同一 LINE identity 與 conversation hold；只允許
`open | claimed | handling` 對話型 escalation，並沿 owner version／lock 防止與後台 resolve 競爭。
