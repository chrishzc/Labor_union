---
status: proposed
priority: P0-planning
owner: Global / Cloud Operations
domain: Global Deployment
subsystem: Cloud Run, Direct VPC, Cloud VPN and runtime supervision
initiative: cloud-run-single-vpn-deployment-test
updated: 2026-08-16
---

# Cloud Run＋單一 Cloud VPN 雲端部署測試計畫

## 0. 狀態、目的與授權邊界

本計畫定義雲端部署前的測試順序、隔離條件、故障案例與 go/no-go evidence。它不是 Cloud resource
建立、image deploy、IAM 授權、VPN 設定、production schema apply 或 production cutover 的授權。

測試基線採用「Cloud Run 應用服務＋地端 NAS MySQL、Direct VPC、HA VPN gateway 的**單一 tunnel**」：
此基線必須驗證 tunnel 中斷時 fail closed、告警與可控復原；不把自動 failover 或 99.99% SLA 視為
v1 的測試目標。雙 tunnel 是獨立可用性升級方案，未經新裁決不得混入本計畫。

## 1. 來源與現行裁決

- [單一 Cloud VPN 雲端部署簡報](../簡報/單一Cloud_VPN_雲端部署.pptx)：10 張投影片確認混合部署、
  API-only DB access、單一 tunnel 的故障語意、成本上限與上線前隔離／復原／追溯主軸。
- [單一 Cloud VPN 計畫書](../雲端部署/計劃書/單一Cloud VPN計畫書.md)：本計畫的 runtime、網路、
  identity 與 acceptance 基線。
- [Cloud Run Dockerfile 封裝計畫 v2](../雲端部署/計劃書/Cloud_Run_Dockerfile封裝計畫_v2.md)：
  image 分離、immutable digest、non-secret runtime config 與 build evidence。
- [Global Deployment 與治理正式規格](../架構重整/01_規格基線/18_Global_Deployment與治理正式規格.md)：
  release、recovery、private DB、OIDC 與 no-secret invariants。
- [雙 tunnel 比較計畫](../雲端部署/計劃書/Cloud_Run_Direct_VPC_HA_VPN雙Tunnel部署計畫.md)：
  僅用於未來可用性升級的差異比對，不是本測試的 PASS 條件。
- 官方產品核對（2026-08-16）：[Cloud Run worker pools](https://cloud.google.com/run/docs/deploy-worker-pools)、
  [Direct VPC egress](https://cloud.google.com/run/docs/configuring/vpc-direct-vpc)、
  [HA VPN topologies](https://cloud.google.com/network-connectivity/docs/vpn/concepts/topologies)。

外部平台特性以 Google Cloud 官方文件於執行時再次核對；本計畫不以 2026-08-16 的價格估算、
Console 畫面或產品名稱作為永久契約。

## 2. 目標架構與不可破壞的不變量

```text
External Application Load Balancer / Cloud Armor / IAP
  → Cloud Run: union-admin-ui / union-business-api / union-ingestion-producer
  → Cloud Run Worker Pool: durable + LINE + incident
  → Cloud Run Job: runtime monitor --once
  → Direct VPC egress → HA VPN gateway (one tunnel) → NAS DB VLAN → MySQL mTLS
```

測試必須證明：

1. NAS MySQL `3306` 不公開；只有 `union-business-api` 可透過 VPN 與 mTLS 到達指定的非正式 DB target。
2. UI、worker、monitor、ingestion producer 沒有 DB credential、MySQL client certificate／key 或 DB VLAN
   路徑；它們只能以 Google OIDC 呼叫 authenticated Private Operations／Business API。
3. public edge 僅公開 URL allowlist；IAP 之外的管理 UI、Private Operations、debug、Data Browser 與
   admin mutation 不可經 public path 存取。
4. `INTERNAL_SERVICE_SHARED_KEY` 不可在 production-like profile fallback；錯 issuer、audience、service
   account、service name 與過期 OIDC 均 fail closed。
5. DB／VPN 不可達時，所有 DB query、preview、apply 與 worker claim 明確失敗；不得用 cache、UI state、
   Pub/Sub 或成功畫面偽造 transaction success。
6. 所有 deployment artifact 使用 immutable image digest、non-secret revision label、secret version、
   correlation 與可回溯 receipt；不得把 secret 寫入 Git、CLI argument、log、UI 或測試報告。

## 3. 測試環境與啟動前條件

真正執行本計畫前，必須由人工提供並確認：

| 項目 | 最低條件 |
|---|---|
| 雲端 scope | 獨立、非正式 Google Cloud project／billing account；不得借用 production project。 |
| 地端 target | 與 production 隔離的 NAS DB VLAN 與 disposable／去敏資料庫；不得用 production MySQL 或 production backup。 |
| 網段 | Cloud subnet、NAS test VLAN 與既有 VPN／LAN CIDR 無重疊，並有明確 route allowlist。 |
| 身分 | test 專用 deploy/runtime service accounts，最小 IAM，禁止 user-managed long-lived key。 |
| Secret | Secret Manager 的 test versions；DB／mTLS material 只可由 API runtime 讀取。 |
| 容器 | 已通過 supply-chain／build／test evidence 的 immutable image digests；不使用 `latest`。 |
| 操作責任 | operator、時窗、預算上限、故障注入方法、停止條件、cleanup owner 與 receipt location。 |

缺少任一項為 `BLOCKED_SCOPE`。不得以本機 Docker、`.env`、`lu_test_*`、Cloud Console 預設值或任何
現有 production account 推定測試 target。

## 4. 測試波次與驗收

### Wave 0：唯讀設計與 artifact preflight

- 核對 image digest、SBOM／dependency scan、release manifest、Cloud Run region、resource names、
  runtime service-account matrix、secret *name*、network tag、OIDC audience／allowlist 與 URL allowlist。
- 對照單 tunnel baseline：明確記錄其無 failover SLA；任何要求「不中斷」的需求必須轉為雙 tunnel
  successor，不得在單 tunnel 結果中推論。
- 產出去敏 preflight receipt；不建立 Cloud resource。

### Wave 1：隔離與身分負向測試

- 驗證只有 API revision 能取得 DB secret 並通過 mTLS；其餘四類 runtime 的 secret mount、DB route、
  TCP 3306 與 direct DB client 皆被拒絕。
- 驗證 IAP group 外、未驗證 public caller、錯 OIDC issuer／audience／caller、過期 token 與 local
  shared key 均被拒絕，且 response／log 不洩漏 credential。
- 驗證 `run.app` 直連、非 allowlist URL、Private Operations、debug 與管理 mutation 被 edge／ingress
  擋下；LINE webhook、LIFF callback 與最小 health path 依明確 allowlist 行為。

### Wave 2：資料路徑、runtime 與觀測

- API 以 test DB 執行 authenticated readiness、read-only query 與一個可回滾／去敏的 typed command；
  驗證單一 outer UoW、receipt、audit 與 no hidden commit。
- Worker Pool 固定一個 instance，驗證 durable／LINE／incident child 各自 heartbeat、restart counter、
  queue lag 與 child permanent failure 告警；worker 不因 API instance 數量而重複執行。
- Monitor Job 以 `--once` 透過 API／edge 觀測；它不直接讀 DB。驗證 Scheduler 失敗、worker heartbeat stale、
  API readiness critical、queue lag／DLQ age 與預算門檻均產生去敏 alert。
- Ingestion producer 僅建立 durable command；不直接正式寫入。Storage／Eventarc fixture 必須去敏且可清理。

### Wave 3：單一 tunnel／DB 故障注入與復原

- 以核准、可復原的 test firewall／route／peer-side test action 模擬 VPN／DB unavailable；不得破壞
  production tunnel 或 production NAS。
- 確認 API liveness 與 authenticated readiness 被區分；依賴 DB 的操作回 typed retryable unavailable，
  worker 停止 claim，沒有 partial write 或假成功。
- 若 Pub/Sub fallback 已另有核准實作，測試只保存 versioned、去敏 alert envelope、DLQ 與 idempotent
  API write-back；若尚未實作，結果固定 `NOT_RUN`，不得以 topic 存在宣稱通過。
- 恢復路由與 mTLS 後，先跑 read-only smoke、source freshness、readiness，再恢復 worker；驗證 lease／
  idempotency 不重複 Domain write。

### Wave 4：漸進 release rehearsal 與 rollback

- 在 test project 對新 revision 執行 0% smoke → 5% → 25% → 100% 的受控 traffic rehearsal；只有 Service
  使用 traffic split，Worker Pool 以 revision instance allocation／restart evidence 驗證，不以 HTTP
  traffic 取代。
- 回到上一 immutable digest，重新做 readiness／read-only smoke，並保留 candidate、log、config／secret
  version、DB backup／restore rehearsal與 rollback receipt。
- 本波仍不得切換 production、套 production schema、上傳正式資料或啟用真實 LINE／銀行 side effect。

## 5. Gate 結果表與停止條件

| Gate | PASS 條件 | 現在狀態 |
|---|---|---|
| G0 scope isolation | test project、test NAS DB、operator／budget／cleanup 全部明確 | `NOT_RUN` |
| G1 artifact / supply-chain | digest、scan、SBOM、config schema、secret-name inventory 完整 | `NOT_RUN` |
| G2 network / DB isolation | API-only + mTLS；其餘 runtime、internet 皆拒絕 3306 | `NOT_RUN` |
| G3 identity / edge | IAP、OIDC negative matrix、URL allowlist、no shared-key fallback | `NOT_RUN` |
| G4 runtime / observability | worker、monitor、queue／DLQ、structured safe log、alerts | `NOT_RUN` |
| G5 outage / recovery | single-tunnel DB outage fail closed、復原後 safe replay | `NOT_RUN` |
| G6 rollout / rollback | progressive rehearsal、immutable rollback、去敏 receipt | `NOT_RUN` |

任一 gate 失敗、target 不明、unexpected public DB reachability、secret exposure、OIDC bypass、schema drift、
non-idempotent replay、未預期 external side effect 或預算超出上限時，立即停止該 wave，保存去敏 evidence，
不嘗試以 shared key、MFA bypass、直接 NAS 登入或在 source DB 上修補來繼續。

## 6. 後續 Work Package 的最小 write set

本計畫獲人工確認後，仍須另立 exact-scope Work Package，至少明列：infra-as-code／Cloud configuration
artifact、container build definition、Cloud Run services／worker pool／job、VPC／VPN／firewall、Secret Manager
binding、IAM、Scheduler／PubSub／Eventarc、test fixture／verifier、receipt、rollback／cleanup。不得把這份
計畫直接當作任何 `gcloud`、Terraform、Cloud Console 或 NAS mutation 授權。

## 7. 完成定義

只有 G0–G6 均有可追溯、去敏的 test-project evidence，並取得人工確認後，本計畫才可標示
`completed-test-validated`。這不等於 production deployment 或 production cutover；兩者仍需獨立的
target-specific execution approval、release approval 與 post-start receipt。
