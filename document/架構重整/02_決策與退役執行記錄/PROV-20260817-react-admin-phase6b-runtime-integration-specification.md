---
doc_type: implementation-specification
declared_status: proposed
identity: PROV-20260817-react-admin-phase6b-runtime-integration
date: 2026-08-17
owner: Global Deployment / Runtime Monitoring
authority: awaiting-exact-human-approval-and-hard-prerequisite-receipts
approval_required: 核准此 exact Phase 6B-RUN Work Package
prerequisites: fresh Phase5B PASS receipt; closed Phase6B-HOST release-approval receipt
absorbs: PROV-20260817-react-admin-phase6b-run-phase5b-prerequisite-amendment
base_branch: main
base_head: late-bound-at-approval
dirty_baseline: integration-owner-must-capture-before-writer
base_drift_rule: any relevant path drift requires fresh read and re-freeze before edits
---

# Phase 6B-RUN：React production runtime integration 規格

## 0. Minimal RUN integration（最新優先裁決）

本節取代本文任何把RUN擴張到ngrok、migration rehearsal、DB observation、alert intent、entry switch或source治理的舊讀法。
RUN只負責把已由HOST核准的immutable React artifact接入launcher與monitor的獨立read-only health probes。

Hard prerequisites只有：

1. Phase5B minimal three-service dual-run具有fresh PASS receipt；舊receipt、文件存在或單獨5173 ready不算。
2. Phase6B-HOST具有closed release-approval receipt，內含typed artifact-health contract、current／previous bindings、
   manifest/API compatibility identity、browser與rollback rehearsal。只有implementation tests PASS不算HOST release-approved。

Phase5A rollback能力由Phase5B fresh receipt傳遞驗證，不再作RUN另一個直接activation dependency。任一hard prerequisite
缺失、stale或identity不一致固定`RUN_HARD_PREREQUISITE_MISSING`並停止所有RUN寫入與runtime動作。

### Minimal responsibility

- Launcher只消費HOST本機typed selector attestation；不得複製manifest parser、讀mtime、猜directory或建立第二套validator。
- API ready後，monitor只經closed Private Operations typed client讀目前mounted artifact health；launcher與monitor是兩個分開probe，
  不得以任一結果代替另一個，也不得用generic HTTP 200認證React。
- Rollback rehearsal只做`current → previous → current` artifact selector與presentation restart／health observation；
  不回滾API、schema、Domain data、receipt、outbox、anomaly或任何business row。
- Entry queue在RUN前後以同一檔案digest、row count、entry IDs與statuses驗證完全不變；RUN只讀queue，禁止generator。
- 0 Streamlit／React source deletion、move、retire或edit；0 dependency removal；Streamlit 8501 rollback runtime保留。
- 0 DB/schema/migration/seed/backfill、0 monitor observation write、0 alert intent、0 provider。RUN receipt只保存去敏probe結果。

### Minimal completion

完成只證明：HOST typed artifact health被launcher與monitor分別正確消費，two-artifact rehearsal通過，queue hash不變且
source/dependency零變更。它不代表entry cutover、Streamlit retirement、Phase6A ready或final dependency cleanup。

## Business scenario

Phase6B-HOST只建立可驗證的`/admin/` immutable artifact。本 minimal RUN 只讓 launcher／preflight／smoke
與 monitor 以兩個獨立的 read-only probe 消費該 artifact 的 typed identity／health，同時保留 Streamlit 8501
作逐entry rollback。ngrok、migration rehearsal、DB observation 與 provider caller 不在本包；不得因本包
修改或接管它們。這份 RUN 仍不刪除 Streamlit，也不切換任何 entry。

## Activation boundary

必須先完成並驗證Phase5A exact rollback、Phase5B controlled dual-run與Phase6B-HOST，且人工明確核准本exact package。Phase5B local Vite 5173 evidence不能代替
production `/admin/` artifact evidence；Phase6B-HOST artifact tests也不能代替launcher／monitor接管。

## Frozen runtime contract

- production runtime只接受已由Phase6B-HOST validator確認的current／previous artifact identity。啟動前先用HOST
  本機validator驗兩個binding；API啟動後再用Private Operations endpoint驗active mounted attestation，兩階段不可互換。
- 新增明確`artifact-runtime` profile；一般local Streamlit development仍可不配置production artifact，且React
  observation標為disabled/unknown而非healthy。只有artifact-runtime profile要求selector attestation並在任何
  child／Docker／DB/API side effect前驗證。不得把local launcher靜默升格為production deployment entry。
- launcher啟動順序固定為API＋validated `/admin/` artifact readiness，再保留Streamlit 8501 rollback；monitor在
  兩者ready後啟動。不得以API healthy推定React或Streamlit healthy。
- React production health固定檢查`/admin/` root marker、artifact release identity與一個listed asset；不得只驗
  TCP或任意2xx。
- rollback只切current／previous artifact selector；不回滾API、schema、Domain data、receipt、outbox或anomaly。
- launcher與monitor必須在各自receipt中保存同一artifact release identity；identity不一致、selector未知、
  previous缺失或API compatibility drift固定fail closed。ngrok／migration rehearsal不在本包。
- Streamlit launcher、health與10個entry-specific rollback URL均保留。Phase6C逐entry retirement前不得移除
  `streamlit run`、8501 probe或相關dependency。
- 本 minimal RUN 的 monitor probe 為 read-only，不寫既有 observation、LINE alert intent、DB 或 provider；
  monitor side-effect policy 不在本包內重開。
- normal launcher的停止語意必須明確；只能終止自己記錄的PID tree／process group，不得掃port殺未知process。
- dedicated `react-admin` probe必須同時驗`/admin/` 200、HTML content type、root marker、selected release/
  manifest identity、listed asset digest及API compatibility identity；generic `_http_probe`不得認證React。
- ngrok 與 migration rehearsal 不由本 minimal RUN 啟動、修改或宣稱已接管；任何 future caller adoption 必須
  另立 exact successor package，不得以本 RUN receipt 代替。
- pre-child gate只能呼HOST本機selector validator，因Private Operations endpoint尚未存在；post-API monitor只能
  經service-auth Private Operations client讀active mounted projection，不得重跑本機selector驗證冒充runtime observation。

## Readiness／rollback evidence

1. preflight唯讀回傳artifact identities、API compatibility、planned commands、ports、health predicates、
   Streamlit rollback disposition與optional workers。
2. dry-run為0 process、0 Docker、0 DB/API call。
3. 本 minimal RUN 不執行 controlled DB smoke；其 runtime probe 必須維持 0 DB、0 observation、0 alert intent、
   0 provider side effect。Phase5B 的既有 GET-only smoke receipt 只作 hard prerequisite，不在此重跑或改寫。
4. 真browser完成password→TOTP，開啟`/admin/#<route>`、呼叫同源API，再切到對應Streamlit rollback URL。
5. two-artifact rehearsal切current→previous→current；每次都驗root marker／asset digest／API compatibility，
   且Domain data與既有receipts不變。
6. 本包不建立或改寫 health／observation rows；任何既有歷史資料均只讀保留，不能用資料列變化冒充 artifact
   rollback proof。
7. 每份runtime receipt至少含caller/run ID、profile、selector、完整非敏感artifact attestation、root/asset/
   compatibility結果、Streamlit rollback URL/result、owned PIDs/process group與execution time；不得含path、secret或PII。
8. current→previous→current以前後既有Domain／receipt fingerprint證明 presentation selector 變更沒有造成
   business data 變更；本 minimal RUN 不產生 observation／alert-intent rows，不能用「無任何row變動」以外的
   未宣告副作用冒充成功。
9. RUN release approval receipt必填`package_identity`、`base_ref`、`host_release_approval_receipt`、
   `phase5a_receipt`、`phase5b_receipt`、pre-child local attestation、post-API private attestation、runtime caller
   inventory revision、browser/rollback rehearsal、queue integrity、`approved_by`、`approved_at`及closed outcome。

## Out of scope

Cloud vendor／host profile、traffic cutover、DB schema/migration/seed/backfill、React page/API contract、entry status
transition、Streamlit source/dependency刪除、真LINE provider發送。

## Completion boundary

本規格完成只代表production artifact已被runtime callers一致管理；Phase6A仍須獨立驗證全部entries、
forward-data與retirement manifest。任何Streamlit retirement仍需Phase6C逐entry exact approval。
