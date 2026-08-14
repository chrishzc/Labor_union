---
doc_type: work-package
declared_status: in-progress
date: 2026-08-14
owner: Global Deployment / Runtime Supervision
priority: P0
---

# 87 Cloud-ready Runtime Supervision Work Package

## 人工核准與 Task Charter

2026-08-14 使用者批准 Worker／Monitor 第二階段，交付條件為程式具備上雲端所需的 runtime
security、readiness 與 failure semantics；本輪先不建立或修改 Dockerfile，待使用者完成地端測試後
再另案封裝。Knowledge Retrieval 的啟用、Chroma readiness 與 Agent 串接不在本輪範圍。

- business scenario：獨立 Worker／Monitor 在本機或 Cloud Run 身分下，只透過 Private Operations
  API 執行一次性 operation；API 是唯一 DB connection owner。
- owner：Global Runtime Supervision／Deployment Security Boundary。
- 根事實：既有 MySQL queue、heartbeat、health observation 與各 Domain transaction 不變。
- 風險：偽造 service identity、永久錯誤被無限重試、API process identity 冒充 Worker、Monitor
  使用與 API 不同的 Redis／media path、DB 失聯仍被 `/health` 誤認為 ready。
- 最小設計：caller identity 綁定 authenticated principal；local/test 使用 shared key，production 使用
  Google-signed OIDC；API-side dependency readiness 使用 API 真實設定；typed `retryable` 控制 bounded
  retry；一次性 worker 失敗回傳非零。

## Global → Domain → Subsystem → Module

- Global：service identity、Google OIDC audience／caller allowlist、typed error、bounded retry、liveness／
  dependency readiness 與去敏 observability。
- Domain：不變更業務規則、根事實、狀態機、outer Unit of Work 或 external side effect owner。
- Runtime Supervision Subsystem：驗證 caller identity，記錄真正的 Worker runtime identity，使用 API
  process 的 Redis／media／MySQL 設定產生 readiness observations。
- Module／Adapter：Private Operations FastAPI dependency、Google auth adapter、typed HTTP client、Worker／
  Monitor CLI 與 focused tests。

## Scope、write set 與 non-goals

- production Private Operations API 接受經驗證的 Google OIDC ID token；audience 與 caller service
  account 必須精確符合設定，local shared key 不得成為 production fallback。
- 每個 endpoint 固定允許的 caller service；header／payload service name 不得自行擴權。
- Worker request 攜帶 instance id、process id、hostname、started time 與 release version；API 使用這份
  caller evidence 記錄 heartbeat，不再使用 API process PID／hostname 代替 Worker。
- Private HTTP client 解析 typed `retryable`，只對 transient transport／server failure 進行有上限、
  exponential backoff＋jitter 的重試；authentication／configuration failure 立即停止。
- 所有 Worker／Monitor `--once` 在 retryable 或 non-retryable failure 都回傳非零。
- Monitor 只做 API／UI／public edge／LIFF 外部探測；Redis、media storage、MySQL 與 queue readiness
  由 API 使用自身實際設定探測。
- 不啟用 Knowledge Retrieval runtime、不驗證 Chroma、不修改 Knowledge lifecycle。
- 不修改 schema、migration、seed、backfill 或 production data。
- 不建立 Cloud Run、IAM、network、Pub/Sub、Dockerfile／image 或任何外部資源，也不部署。
- Incident durable cursor／multi-instance lease 與 DB outage Pub/Sub backup 仍是後續獨立 Work Package。

## Write set

- `document/架構重整/01_規格基線/18_Global_Deployment與治理正式規格.md`
- `document/架構重整/02_決策與退役執行記錄/README.md`
- `document/架構重整/03_追蹤清單與證據/evidence/entrypoint_review_queue_v1.jsonl`
- `api/dependencies/internal_service_auth.py`
- `api/dependencies/private_operations.py`
- `api/dependencies/runtime_heartbeat.py`
- `api/routes/private_operations.py`
- `api/schemas/private_operations.py`
- `infrastructure/http/private_operations_client.py`
- `scripts/run_durable_job_worker.py`
- `scripts/run_line_worker.py`
- `scripts/run_knowledge_worker.py`（只套用共用失敗退出契約，不啟用 Knowledge）
- `scripts/run_incident_worker.py`
- `scripts/run_service_monitor.py`
- `.env.example`、`README.md`、`pyproject.toml`、`uv.lock`
- `tests/` 中直接相關 focused tests
- `history/work_log.md`（只追加去敏驗證證據）

## 驗收

1. production 缺 token、錯 issuer／audience、未列入 allowlist 或 service name mismatch 全部 fail closed。
2. local/test shared key 保持可測；production 永不接受 shared-key fallback。
3. Worker heartbeat 的 PID／hostname／instance id 來自 authenticated caller payload。
4. Monitor source 不再讀取 `REDIS_URL` 或 `MEDIA_STORAGE_ROOT`；API-side readiness 才使用兩者。
5. typed `retryable=false` 即使 HTTP 503 也不重試；transient failure 在 budget 內 backoff，耗盡後失敗。
6. 每個 Worker／Monitor `--once` 的 failed cycle 都回傳非零。
7. Worker／Monitor 仍無 MySQL import 或 DB credential；沒有新增或修改 Dockerfile。
8. focused Module／Subsystem／Global tests、compile、launcher smoke 與 `git diff --check` 通過。

## DB change gate

| Gate | 狀態 | 證據 |
|---|---|---|
| Scope | PASS | 本 Work Package 明確排除 schema／migration／data mutation |
| Change inventory | PASS | schema-only、system-seed、business-row-backfill、destructive 均為無 |
| Static release | NOT_RUN | 無 DB change，不適用 |
| Descriptor | NOT_RUN | 無 DB change，不適用 |
| Read-only plan | NOT_RUN | 無 DB change，不操作既有 DB |
| Engine verification | NOT_RUN | 無 DB change |
| Developer acceptance | NOT_RUN | 待使用者地端服務驗收 |
