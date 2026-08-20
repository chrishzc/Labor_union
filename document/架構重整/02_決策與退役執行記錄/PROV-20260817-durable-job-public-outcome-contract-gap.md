---
doc_type: gap
declared_status: proposed
identity: PROV-20260817-durable-job-public-outcome-contract-gap
date: 2026-08-17
owner: Global Durable Jobs Integration Owner
domain: Global / Jobs
approval_required: 人工核准獨立 durable-job public outcome successor Work Package
---

# Durable Job payload equality／typed outcome public contract gap

## Gap

現行generic job public view仍允許raw receipt/error，且相同Idempotency-Key不一定比較canonical command
payload。Finance Import與Staff Payout若只修改各自route/schema，無法證明same-key mismatch、worker retry分類、
terminal receipt、outcome_unknown或PII redaction，測試綠燈也不能把`202 JobAccepted`稱為業務成功。

## Successor必須凍結

- command fingerprint = command type＋version＋canonical payload＋actor policy；same key/same fingerprint回原job，
  任一差異typed 409。
- worker error分類：validation/conflict/domain-blocked/idempotency為terminal；只有正式unavailable且retryable可重試。
- strict discriminated public status／terminal receipt／terminal error；禁止raw command payload、traceback、完整銀行資料、
  provider payload與內部錯誤字串。
- retry exhaustion保留最後去敏typed error、attempt count與safe result reference。
- bounded-domain job endpoint只能解碼自己domain的command type；generic job route不得成為React raw payload旁路。
- provider call transaction外；job accepted、provider success、Domain receipt三者不得混為同一狀態。

## Frozen successor chain

本gap不得再以單一monolithic writer同時修改worker、repository、caller與public route。successor責任固定拆成：

1. `PROV-20260817-durable-job-persistence-caller-adoption-decision-work-package`選定persistence方案；
   目前推薦Option A existing-column canonicalization，但在人工核准前不構成production授權。
2. `PROV-20260817-durable-job-core-persistence-worker-contract-work-package`唯一擁有
   `shared_kernel/durable_job_queue.py`、Jobs core contracts／ports、worker與MySQL repository。
3. `PROV-20260817-durable-job-caller-integration-bridge-work-package`提供唯一outer UoW／application composition。
4. 六個enqueue owner依
   `PROV-20260817-durable-job-caller-adoption-gap`列出的exact bounded successor採用Core；Finance Import與
   Staff Payout分別由自己的Phase 4 hardening包擁有route，禁止另開平行writer。
5. 只有前四層全部PASS，`PROV-20260817-durable-job-public-outcome-contract-work-package`才可只修改
   `api/routes/jobs.py`、`api/schemas/jobs.py`、`api/dependencies/jobs.py`，完成masked public observation。
6. React Jobs client/page必須再後置於public outcome PASS，不得直接讀raw receipt/error/payload。

各層focused tests、disposable MySQL replay/crash tests、scenario與evidence依各自exact Work Package所有；
shared README／正式規格／evidence index只由Integration Owner late-bind。

如Core證明既有tables無法保存canonical fingerprint或typed terminal outcome，固定`DB_SCOPE_REQUIRED`，另走完整
DB gate；不得在Bridge、caller、Finance／Staff Payout或public observation工作包偷加欄位。

## DB gate

| Gate | Status | Evidence |
|---|---|---|
| Scope gate | BLOCKED | durable payload／outcome persistence尚未凍結 |
| Change inventory | NOT_RUN | 尚未判定是否需schema |
| Static release gate | NOT_RUN | 尚無release |
| Descriptor gate | NOT_RUN | 尚無object delta |
| Read-only plan gate | NOT_RUN | 尚無plan |
| Engine verification gate | NOT_RUN | 尚未核准 |
| Developer acceptance gate | NOT_RUN | 不操作既有資料庫 |

結論：`DB_CHANGE_NOT_READY`。
