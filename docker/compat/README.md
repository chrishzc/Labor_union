# Cloud Run 現況相容性測試映像

這三個映像只供本機與隔離 staging 的相容性驗證，不得標記為 `latest`、推進正式環境或連接正式資料庫。

## 建置

一般操作請在repository root執行共用builder；它會建置三個images並完成non-root、built-image
imports、API／UI health、UI→API及runtime→Private API驗收，失敗時不允許後續push：

```powershell
.\scripts\launchers\build_and_validate_cloud_run_compat_images.ps1 -DryRun
.\scripts\launchers\build_and_validate_cloud_run_compat_images.ps1
```

三個輸出名稱固定為`union-api-compat:compat-<HEAD>`、`union-ui-compat:compat-<HEAD>`及
`union-runtime-ops-compat:compat-<HEAD>`。image是本機／Artifact Registry產物，不提交Git；Git只保存
Dockerfile、lockfile、builder與驗收契約。

Docker 會自動採用各 Dockerfile 同名的 `.dockerignore`。建置前仍應檢查 context，且不得用 `--secret` 以外的方式傳入敏感值。

三個測試映像分別安裝 `compat-api`、`compat-ui`、`compat-runtime-ops` dependency group，避免把其他 process 的完整依賴一併封裝。Redis client 已自此測試封裝移除；API 與 runtime-ops 映像預設 `REDIS_URL` 為空字串，Redis 不再是啟動或 readiness 前置條件。

## 本機啟動

API 必須取得隔離測試資料庫設定。以下只展示非敏感 wiring；密碼應由本機 env file 或 secret mount 注入，不得寫入 image 或此文件：

```powershell
docker run --rm --name union-api-compat -p 18080:8080 --env-file <test-api-env-file> -e PORT=8080 union-api-compat:<test-id>
docker run --rm --name union-ui-compat -p 18501:8080 -e PORT=8080 -e API_BASE_URL=http://host.docker.internal:18080 union-ui-compat:<test-id>
```

健康檢查：

```powershell
Invoke-WebRequest http://127.0.0.1:18080/health -UseBasicParsing
Invoke-WebRequest http://127.0.0.1:18501/_stcore/health -UseBasicParsing
```

runtime-ops 的每個 entry point 必須分開執行；共用 image 不代表共用 process：

```powershell
docker run --rm union-runtime-ops-compat:<test-id> python -m scripts.run_durable_job_worker --check
docker run --rm <runtime-env> union-runtime-ops-compat:<test-id> python -m scripts.run_durable_job_worker --once
docker run --rm <runtime-env> union-runtime-ops-compat:<test-id> python -m scripts.run_line_worker --once
docker run --rm <runtime-env> union-runtime-ops-compat:<test-id> python -m scripts.run_incident_worker --once
docker run --rm <monitor-env> union-runtime-ops-compat:<test-id> python -m scripts.run_service_monitor --once
```

UI、Worker 與 Monitor 不得注入 `DB_HOST`、`DB_PORT`、`DB_USER`、`DB_PASSWORD` 或 `DB_DATABASE`。本機 smoke 可使用 local shared-key auth；Cloud Run staging 必須改用各自 service account 的 Google OIDC。

## 驗證邊界

- API：`/health`、OpenAPI、代表性唯讀查詢；若執行 mutation，只能使用 disposable/staging 資料。
- UI：Streamlit health、登入頁與 API client wiring。
- Worker：先 `--check`，再用隔離 API 跑 `--once`；確認 container 內不存在 DB credential。
- Monitor：所有 URL 必須顯式設定，不得沿用 localhost default。
- 本機 JSON、模板、archive 與 media 都是 ephemeral；container/revision 重建後遺失屬預期限制。

停止或移除本機驗證 container 時，只能指定上述明確 container name；不得使用全域 prune 或清理使用者其他 image/container。
