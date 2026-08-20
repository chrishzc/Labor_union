---
doc_type: work-package
declared_status: blocked
identity: PROV-20260817-durable-job-public-outcome-contract
date: 2026-08-17
owner: Global Durable Jobs Integration Owner
domain: Global / Jobs
source_gap: PROV-20260817-durable-job-public-outcome-contract-gap
prerequisites: PROV-20260817-durable-job-core-persistence-worker-contract PASS; PROV-20260817-durable-job-caller-integration-bridge PASS; PROV-20260817-durable-job-assignment-plan-caller-adoption PASS; PROV-20260817-react-admin-phase4a-finance-import-public-contract-hardening PASS; PROV-20260817-durable-job-government-subsidy-caller-adoption PASS; PROV-20260817-durable-job-payroll-rebuild-caller-adoption PASS; PROV-20260817-react-admin-phase4b-staff-payout-public-contract-hardening PASS; PROV-20260817-durable-job-orders-auto-completion-caller-adoption PASS
approval_required: 核准此 exact Durable Job Public Outcome Contract Work Package
scenario_governance: Part_00_全域測試資料治理與Scenario契約.md
scenario_lineage: ../03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase3-6-planning/phase4-scenario-lineage-matrix.md
scenario_adoption: JOB-DURABLE-001; JOB-QUEUE-LIFECYCLE-002
ui_execution_mode: not-applicable
base_branch: main
base_head: late-bound-at-approval
dirty_baseline: integration-owner-must-capture-before-writer
base_drift_rule: any relevant path drift requires fresh read and re-freeze before edits
---

# Durable Job public outcome contract 工作包

## 0. Scope

本包是Durable Job鏈的**最終server-masked public observation／integration gate**。它只在Core persistence／worker
契約已PASS，且六個enqueue owners／八種command types都完成caller adoption後，收斂generic public Query與安全取消
契約；不再擁有command equality、worker、repository或caller transaction實作。

不修改Finance Import／Staff Payout業務規則、不接React、不呼叫外部provider、不改DB/schema。六個exact caller
successor皆為hard prerequisites，不得以文件中寫「RESOLVED」或舊receipt代替真正的PASS evidence。任一caller
仍吞掉same-key/different-payload conflict、任何public view仍暴露raw payload／
receipt／provider資料時，本包固定blocked。

## 1. Exact production write set

- `api/routes/jobs.py`
- `api/schemas/jobs.py`
- `api/dependencies/jobs.py`

`shared_kernel/durable_job_queue.py`、`subsystems/jobs/contracts.py`、`subsystems/jobs/ports.py`、
`subsystems/jobs/durable_job_worker.py`與`infrastructure/mysql/background_job_repository.py`均為已凍結Core輸入，
本包只能唯讀；若public route需要改動它們，固定`CORE_CONTRACT_AMENDMENT_REQUIRED`。

## 2. Exact test／scenario write set

- `tests/test_durable_job_public_outcome_contract.py`（new）
- `tests/test_jobs_cancellation_route.py`
- `tests/test_jobs_public_outcome_route.py`（new）
- `validation/scenarios/durable_job_public_outcome.json`（read-only consume；由Phase4 Scenario Lineage唯一擁有）
- 本工作包、source gap、正式Global規格、`02/README.md`與evidence只由Integration Owner更新。

Evidence固定落在
`document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-durable-job-public-outcome-contract/`，
至少包含`contract-field-matrix.md`、`candidate-change-inventory.md`、`verification-receipt.md`、
`disposable-mysql-receipt.md`與`open-findings.md`。

禁止修改domain-specific route/schema/client/page、shared auth/transport、package/lockfile、DB/schema/migration。

## 3. Frozen invariants

- `command_fingerprint = command_type + command_version + canonical_payload + actor_policy`；correlation ID不影響
  business equality，但必須可觀測。same key/same fingerprint回同job identity；任一差異typed 409。
- public status使用closed literal；terminal outcome為discriminated receipt/error union，0 `Any`／raw map／traceback。
- validation/conflict/domain_blocked/idempotency為terminal；只有正式unavailable且`retryable=true`可重試。
- exhaustion保留最後去敏typed error、attempt count與safe result reference；不能只留message/traceback。
- provider call在transaction外；accepted、processing、provider acknowledged、Domain receipt不可合併成paid/imported/success。
- bounded-domain successor只能查自己的command types；generic route不得回raw command payload。

## 4. Mutually exclusive lanes

1. Contract Scout（Luna，唯讀）：table/route/worker/error inventory與field matrix。
2. Route Writer（Terra）：只改route/schema/dependency與route tests；Core contracts全為唯讀輸入。
3. Auditor（Luna，唯讀）：fresh commands、write-set、PII/raw/skip掃描；不寫receipt。
4. Integration Owner：唯一文件／scenario／evidence writer。

任一lane發現需DB或domain-specific path即停工，不得擴張。

## 5. G0–G8

- G0 exact approval、dirty collision inventory、0 DB/domain/React/provider drift。
- G1 endpoint×field×nullable×error×redaction×command equality矩陣freeze。
- G2 逐一證明六個enqueue owners／八種command types已採用Core equality；本包不得用route adapter掩蓋未採用caller。
- G3 public terminal/retryable/exhaustion closed union與safe result reference通過；provider acknowledgement不等於Domain成功。
- G4 public outcome strict、bounded、masked；extra/missing/null/raw payload fail closed。
- G5 provider 0 call；accepted不冒充Domain success。
- G6 引用Core與caller-adoption的fresh disposable MySQL receipt；本包另驗public route不寫入、取消命令除外且遵守Core UoW。
- G7 existing Finance Import/Staff Payout job tests只作regression，不把domain結果升格為Global authority。
- G8 focused/full tests、UTF-8、diff、secret/PII、skip/todo/weak assertion與write-set audit。

G2、G3與G6必須包含safe negative control：相同key不同payload在修復前可被錯誤接受或缺少typed outcome的案例
必須先被測試捕捉，再以最終candidate通過。Writer自建fixture不能是唯一證據；結果需同時追到
`JOB-DURABLE-001`／`JOB-QUEUE-LIFECYCLE-002`及真disposable MySQL rows。禁止`.skip`、`.todo`、`.only`、
snapshot-only或以generic HTTP 200代替terminal outcome驗證。

## 6. DB gate

| Gate | Status | Evidence |
|---|---|---|
| Scope gate | BLOCKED | Core、caller adoption與masked public observation鏈尚未全部PASS；不得先改production |
| Change inventory | NOT_RUN | 核准後先做static inventory |
| Static release gate | NOT_RUN | 無release write set |
| Descriptor gate | NOT_RUN | 無schema變更 |
| Read-only plan gate | NOT_RUN | 不適用 |
| Engine verification gate | NOT_RUN | disposable MySQL為必要runtime evidence |
| Developer acceptance gate | NOT_RUN | 不操作既有資料庫 |

結論：`DB_CHANGE_NOT_READY`。
