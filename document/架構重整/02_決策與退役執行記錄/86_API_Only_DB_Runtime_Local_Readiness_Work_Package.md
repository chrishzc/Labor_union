---
doc_type: work-package
declared_status: in-progress
date: 2026-08-14
owner: Global Deployment / Runtime Supervision
priority: P0
---

# 86 API-only DB Runtime Local Readiness Work Package

## 人工核准與 business scenario

2026-08-14 使用者明確核准下列四項施工：Private Operations API、Monitor 改走 API、Worker
改走 API，以及移除 FastAPI lifespan 內嵌 worker。交付門檻是所有服務可在地端獨立啟動並供
使用者驗收；Cloud Run、雲端網路、NAS production DB、deployment 與 cutover 留待地端驗收後
另行授權。

本次安全不變量是：MySQL 只有 FastAPI process 可以建立連線。Worker 與 Monitor 不得持有
DB hostname、port、username 或 password，也不得 import concrete MySQL adapter；它們只使用
經 service authentication 保護的 Private Operations API。

## Global → Domain → Subsystem → Module

- Global：固定 API-only DB access、service authentication、獨立 process health 與 fail-closed
  production guard；不改變既有 outer Unit of Work、outbox、idempotency 或 commit owner。
- Domain：不變更任何業務根事實、狀態機、公式或 typed business rule。
- Runtime／Jobs／LINE／Knowledge Subsystem：既有一次性 command/cycle 仍為唯一 application
  operation；HTTP 只觸發完整 cycle，不把 claim、side effect 與 completion 拆成跨 request 交易。
- Module／Adapter：FastAPI composition 建立 MySQL adapter；Worker／Monitor CLI 只負責 identity、
  polling、timeout、retry 與 typed HTTP client。Streamlit 與 public business API contract 不變。

## Scope、write set 與 non-goals

- 新增隱藏於 OpenAPI schema 的 `/internal/v1/runtime/*` private endpoints 與 typed request/response。
- local/test 只接受獨立的 `INTERNAL_SERVICE_SHARED_KEY`；使用 constant-time comparison，key 不得出現
  在 URL、log 或 response。production 不得啟用 shared-key fallback，未配置正式身分驗證時 fail closed。
- Durable、LINE、Knowledge worker process 移除 MySQL import 與 DB credential，改呼叫一次性 API operation。
- Monitor 在外部探測 API／UI／public edge／local storage 後，把 typed observations 交給 API；DB、
  queue、heartbeat 查詢與 alert projection 只在 API transaction 中執行。
- FastAPI lifespan 不再啟動 architecture outbox 或 security-audit retention background thread。
- 原 lifespan 的 anomaly outbox 與 security-audit retention 改由獨立 Incident Worker 透過同一
  Private Operations API 觸發，避免移除 thread 後功能靜默消失。
- 更新本機 launcher/config 說明與 focused tests；保留既有 CLI module 名稱。
- 不修改 schema、migration、seed、backfill 或 production data；不操作 `.env` 指向的既有 `union_db`。
- 不部署 Cloud Run、不建立 Google Cloud resource、不開放 NAS 3306、不修改防火牆或外部 provider。
- Google-signed OIDC/IAM 驗證與 Cloud Run service-to-service audience 綁定屬後續 deployment Work Package；
  本輪 production mode 在該 verifier 未落地前固定拒絕 private operation。

## Transaction、retry 與 partial failure

- 每個 private operation 是單一 request／單一完整 cycle；API 端沿用既有 DB transaction 與 commit owner。
- Worker 只在 API 回覆成功後視為 cycle 完成；timeout／5xx 為 retryable，4xx authentication/config
  failure 為 fail closed，不得偽造成功。
- Monitor 無法連到 API 時只能輸出非敏感錯誤並於下次 cycle 重試；不得旁路直接寫 DB。
- 相同 durable command 的 idempotency、lease 與 retry 狀態仍由既有 durable queue SSOT 決定。

## Write set

- `document/架構重整/01_規格基線/18_Global_Deployment與治理正式規格.md`
- `document/架構重整/02_決策與退役執行記錄/README.md`
- `api/main.py`、`api/routes/`、`api/dependencies/`、`api/schemas/` 內本功能檔案
- `scripts/run_service_monitor.py`
- `scripts/run_durable_job_worker.py`
- `scripts/run_line_worker.py`
- `scripts/run_knowledge_worker.py`
- `scripts/run_incident_worker.py`
- `subsystems/anomalies/outbox_worker.py`
- `subsystems/access/security_audit_retention_worker.py`
- `scripts/launchers/` 與 `config/` 中直接相關說明或啟動設定
- `tests/` 中本功能 focused tests
- `history/work_log.md`（只追加本次成果與證據）

## 驗收

1. 靜態檢查證明全部 Worker／Monitor CLI 不 import `infrastructure.mysql` 或 `get_connection`。
2. Private endpoint 無憑證、錯誤憑證與 production shared-key 均 fail closed；local 正確 key 才可執行。
3. Durable cycle 保留 claim／handler／complete 或 fail 的原交易語意；HTTP 邊界不拆 transaction。
4. Monitor 可完成一次性外部 probe 與 API persistence request；API 不可用時不接觸 DB。
5. FastAPI lifespan 不啟動任何 embedded worker；各 worker process 可獨立啟停。
6. focused Module／Subsystem／Global tests、launcher smoke、compile 與 `git diff --check` 通過。
7. 本機服務以不操作 production/NAS DB 的 safe check 或 mocked composition 驗證可啟動；真正地端
   DB 的整合驗收由使用者後續執行。

## DB change gate

| Gate | 狀態 | 證據 |
|---|---|---|
| Scope | PASS | 本 Work Package 明確排除 schema／migration／data mutation |
| Change inventory | PASS | schema-only、system-seed、business-row-backfill、destructive 均為無 |
| Static release | NOT_RUN | 無 DB change，不適用 |
| Descriptor | NOT_RUN | 無 DB change，不適用 |
| Read-only plan | NOT_RUN | 無 DB change，不操作既有 DB |
| Engine verification | NOT_RUN | 無 DB change |
| Developer acceptance | NOT_RUN | 留待使用者地端整合驗收 |

## 2026-08-14 Windows launcher regression repair

首次交付後，使用者實際執行一般 launcher 發現服務未啟動。受控重現證明 DB 與各 service
operation 正常，根因是 batch `for /f` 內嵌 quoted Python command 被 `cmd.exe` 錯誤拆解，導致
`INTERNAL_SERVICE_SHARED_KEY` 未產生。修復改用 Windows PowerShell CSPRNG 子程序，並在一般
launcher 與 smoke 共用；一般 launcher 另固定等待 FastAPI 與 Streamlit health 200 後才啟動
Worker／Monitor。修復後 controlled full-service smoke 必須沒有 `not recognized`、ConnectionError、
401／503 或 Traceback 才算通過。
