# CLIENTREFUND-001 客戶退款退匯異常人工修正工作包

- 狀態：`completed`
- package status：`COMPLETED_SOURCE`
- controlling spec：`PROV-20260827-client-refund-return-anomaly-remediation-spec.md`

## Reuse／necessity

| Candidate | Classification | 決策 |
|---|---|---|
| Finance Import correction Q/P/A/job | `required_now` | reuse，不新增command。 |
| Client Finance refund-return/reversal Q/P/A | `required_now` | reuse正式ledger owner與outer composition。 |
| anomaly detail/action/predicate | `required_now` | minimal glue＋guard strengthening。 |
| React finance correction surface | `required_now` | reuse；只補owner readback/active-list reconciliation與文案。 |
| generic resolve/new ledger editor/schema | `remove` | 會繞過owner或超出effect ceiling。 |

Research：`NO_RESEARCH`；current正式規格與live Q/P/A已涵蓋所有material decision。

## CRR-WP-A：Backend detail、binding與fresh predicate

- Scope：`domains/anomalies/registry.py`、`domains/anomalies/root_fact_projection.py`、`subsystems/anomalies/root_fact_projection_workflow.py`、`subsystems/anomalies/finance_import_anomaly_consumer.py`、`api/routes/anomaly_registry.py`、focused tests。
- Objective：公開具體安全detail、綁actual row identity，並只在exact formal reversal fresh readback成立時inactive。
- Exclusions：改Client Finance公式／commands、schema、generic correction semantics。

Steps：

1. registry宣告安全display fields；API allowlist與private snapshot fields一致，unknown仍fail closed。
2. Domain candidate與recovery query action一律綁 `finance-import-row:<id>`＋source version；synthetic alert identity只用fingerprint/source relation。
3. fresh guard驗證exact row、target refund entry、same case、exact amount及formal reversal linkage；缺任何事實fail closed。
4. tests覆蓋detail payload、actual/synthetic identity、wrong row/type/target/case/amount、missing/read failure、active→inactive reducer。

## CRR-WP-B：React terminal business reconciliation

- Scope：`ui_react/src/pages/AnomaliesPage.tsx`、相關adapter/tests；不改backend。
- Objective：receipt成功後重查active list，只有原fingerprint absent才顯示解除；其餘提供原job/root重新核對。

Steps：

1. exact action維持purpose固定、actual row binding、strict contract。
2. `fetchAnomalies`回傳fresh active snapshot；結果未知則不改completed。
3. job succeeded＋receipt但原alert仍active：顯示「帳務更正已提交，來源仍待核對」，保留重新查詢入口。
4. 原alert absent才顯示「異常已解除」；queued/running/stale/timeout維持未完成。
5. tests覆蓋receipt-only active、absent completion、query failure、queued、stale input、unknown version。

## CRR-WP-C：Integration與E3

1. Python focused與related refund/reversal/anomaly regression。
2. React focused/typecheck/build。
3. strict UTF-8、compile、`git diff --check`。
4. 若服務可用，以allowlisted `lu_test_*`跑existing disposable lifecycle與Browser；否則`NOT_RUN`。
5. Luna High/high E3 read-only verifier反證receipt-only、wrong linkage、synthetic binding、stale與無出口狀態。

## DDH projection

| 時點 | 模式 | 理由 |
|---|---|---|
| candidate audit | E4三條Luna High/high唯讀lanes | Finance、Ops、LINE/Gov可隔離；比較後只有CLIENTREFUND-001無Authority缺口。 |
| package ready | E4 backend writer＋React writer | write set完全分離；parent保留docs/integration。 |
| final candidate | E3 read-only verifier | writer不自證business terminal oracle。 |

Readiness result：`PACKAGE_READY`。

## Execution result（2026-08-27）

- Backend、React 與 source-level integration：`passed`。
- Luna High／high E3：round 1～3 均發現 P1 並回修；round 4 `PASS`，P0/P1=0。
- 真 MySQL／FastAPI／Browser：`not_run`；Docker Compose 與其他服務未啟動，未由本包自行啟動。
- DB inventory 維持四類皆 `none`；未新增 schema／migration／seed／backfill。
- Final receipt：`03_追蹤清單與證據/evidence/2026-08-27_client_refund_return_anomaly_remediation_receipt.md`。
