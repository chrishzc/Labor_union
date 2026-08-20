---
doc_type: gap-package
declared_status: proposed
identity: PROV-20260817-durable-job-persistence-caller-adoption-decision-gap
date: 2026-08-17
owner: Global Durable Jobs / Domain Integration Owners
domain: Global / Jobs / Finance Import / Staff Payables / Scheduling / Government Subsidy
source_work_package: PROV-20260817-durable-job-public-outcome-contract
approval_required: 核准 Durable Job persistence與caller adoption方案後另立exact successor
scenario_governance: Part_00_全域測試資料治理與Scenario契約.md
ui_execution_mode: not-applicable
---

# Durable Job persistence／caller adoption決策缺口

## 0. Business scenario

同一Idempotency-Key與完全相同的command必須回同一job；相同key但payload、command type、version或actor policy
任一不同，必須穩定回typed 409。Worker的accepted／processing／terminal receipt／terminal error必須可去敏查詢，
且不得把job accepted冒充Domain完成。

## 1. Current evidence

- `background_jobs`目前保存`command_identity`、`command_type`、`command_version`、raw JSON
  `command_payload`／`receipt_payload`／`error_payload`，沒有獨立canonical fingerprint欄。
- `command_identity`使用case-insensitive collation，但Global`IdempotencyKey`沒有lowercase契約；`Key`與`key`
  在memory視為不同、MySQL卻可能碰撞。Option A若不先拒絕uppercase或建立DB successor，不能宣稱exact equality。
- `BackgroundJobRepository.enqueue_command()`只依unique `command_identity`辨識duplicate，未比較payload／type／
  version／actor policy，且repository直接`commit()`／`rollback()`，與單一outer UoW規則漂移。
- Assignment Plan、Finance Import、Government Subsidy、Payroll Rebuild、Staff Payout routes會捕捉
  `JobIdempotencyConflict`並回傳既有job，因此same-key/different-payload可能被誤判為合法replay。
- public Job view仍包含raw `dict[str, Any]` receipt/error；worker可能將`str(error)`寫入可查詢payload。
- disposable MySQL job tests在無engine時會skip；skip不能作為payload equality／rollback完成證據。

## 2. Required human／architecture decision

必須選定並凍結一個方案：

1. **Existing-column canonicalization**：證明可由現有command columns與canonical JSON穩定重建fingerprint，
   並以closed typed serialization安全使用現有receipt/error JSON；0 schema change。推薦子裁決為canonical Durable
   Job key只接受lowercase ASCII且uppercase在進DB前拒絕，不silent normalize；若不接受此語意則Option A FAIL。
2. **Additive persistence successor**：新增canonical fingerprint／typed outcome metadata；另立schema release、descriptor、
   preserve-data upgrade與完整DB gate，不能塞進原Global Job工作包。

兩方案都必須裁決caller adoption：是由所有durable enqueue routes同批接收typed mismatch，或由一個不依賴FastAPI的
shared application port提供closed replay／mismatch result。不得讓repository拋HTTP exception，也不得讓未更新caller
把mismatch變成500。

## 3. Frozen exact successor split

- `PROV-20260817-durable-job-core-persistence-worker-contract-work-package`：canonical equality、no-hidden-commit
  port、typed terminal storage與repository／worker tests。
- `PROV-20260817-durable-job-caller-integration-bridge-work-package`：唯一outer UoW／application composition。
- `PROV-20260817-durable-job-caller-adoption-gap`：列出六個enqueue owner、八種command type與各自exact bounded
  successor；不得再建立未指名的generic caller writer。
- `PROV-20260817-durable-job-public-outcome-contract-work-package`：所有caller採用後才執行masked bounded GET
  view；不得回raw command／provider／PII payload，也不得反向修改Core或caller。

未凍結上述split與write sets前，不得修改production。

## 4. Acceptance for closing this gap

1. 現有欄位是否足夠的逐欄persistence matrix與真MySQL查核。
2. 全部durable enqueue callers inventory，含exception/replay/current HTTP outcome。
3. canonical fingerprint、actor policy、correlation、same-key replay與mismatch的唯一owner。
   必須包含`Key`／`key`、JSON `1`／`1.0`、NaN/Infinity、Unicode、null、object/array order與immutable actor identity。
4. outer UoW／commit owner；repository hidden commit的退場方式。
5. terminal receipt/error closed union、redaction與unknown command處置。
6. `JOB-DURABLE-001`、`JOB-QUEUE-LIFECYCLE-002`到fixture／expected／receipt的lineage。
7. 無MySQL engine或任何pytest skip時固定`BLOCKED_ENGINE_EVIDENCE`。

## 5. DB gate

| Gate | Status | Evidence／reason |
|---|---|---|
| Scope | BLOCKED | persistence方案與schema需求未裁決 |
| Change Inventory | BLOCKED | 尚未選existing-column或additive schema方案 |
| Static Release | NOT_RUN | 只有選additive方案才適用 |
| Descriptor | NOT_RUN | 同上 |
| Read-only Plan | NOT_RUN | 同上 |
| Engine Verification | BLOCKED | disposable MySQL evidence尚未取得 |
| Developer Acceptance | NOT_RUN | 不得操作既有資料庫 |

結論：`DB_CHANGE_NOT_READY`。
