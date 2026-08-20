# Order Tracker query page-slice evidence matrix draft

> Status: `DRAFT_INPUT_ONLY`。本文件是 proposed Work Package 的fresh source inventory與驗收輸入，
> 不是approval、contract freeze、runtime receipt或完成證據。

## 1. Identity and prerequisite

| Item | Value / current observation |
|---|---|
| Work Package | `PROV-20260817-react-admin-order-tracker-query-page-slice` |
| Page | `#order-tracker` / `OrderTrackerPage` |
| Required predecessor | `PROV-20260817-react-admin-orders-query-page-slice` must be `completed/query-real-data-validated` |
| Predecessor current observation | `declared_status: in-progress`; local candidate evidence exists, browser receipt仍awaiting |
| Reused client | existing eight-GET `ordersQueryClient`; Tracker calls `getOrderSummaries` only |
| Canonical missing-lineage owner | `PROV-20260817-react-admin-phase3e-order-operational-timeline-gap` |
| Completion ceiling | `query-real-data-validated` |
| DB policy | zero DB change; existing DB browser GET observation only |

## 2. Fresh live-drift inventory

| Source／symbol | Current behavior | Required disposition | Test evidence required |
|---|---|---|---|
| `order_tracker_adapter.ts::mapOrderStatusToWorkflowStage` dependency | maps raw `order_status` to one of seven stages | remove Tracker import/call/runtime dependency; summary adapter remains read-only predecessor input | same summary with varied raw status never changes stage slots |
| `generateSopChecklist` | stage index generates completed/in-progress/pending and fixed notes | remove; retain 11 names with null status/timestamp and unavailable lineage | all 11 slots present, none has progress icon/status |
| `generateNotificationsHistory` | generates `NTF-*`, fixed timestamps, success rows and message bodies | remove; render one timeline unavailable sentinel | no notification row／timestamp／message; tab costs 0 GET |
| `adaptTrackerOrderCard.waitingFor` | stage-derived operational reminder | replace with unavailable sentinel | no status-dependent waiting text |
| `depositAmount: 0`／settlement story | numeric/default or stage story implies known accounting state | remove; three owner slots separately unavailable | service/client-finance/staff-payroll slots all present and independent |
| `ordersByStage`／`stageCounts` | assigns cards and counts locally | replace with seven unavailable slots + separate unclassified loaded summaries | seven counts `—`; no card in stage section |
| `empty-stage-box` | empty array shown as “目前無案件停留於此階段” | replace with typed stage projection unavailable | no `0筆`／no empty-business claim |
| `OrderTrackerPage` initial request | one summaries query with request-id stale guard | retain via completed eight-GET client; add AbortSignal/strict request budget where client interface allows | initial 1 GET, retry 1 GET, stale discard |
| Drawer open／tabs | local state | retain; 0 request | spy/network counts unchanged |
| manual replay | disabled but lacks stable control id | retain native disabled and add `order-tracker.notifications.replay` | click 0 request/dialog |

Fresh source hashes at docs/scout time:

- `OrderTrackerPage.tsx`: `81C0674EE0570666CFF2D812442844779E9ECC69DFD6CBEFB6252B38A375F1FD`
- `order_tracker_adapter.ts`: `DDE73B371BCAF43AE57B0E21BF6664F7F04D3C2AAFB0B4BAB40D6823E8879904`
- `order_tracker_real_data.test.tsx`: `E94E739B88BBEC9659C14C107F439D4163B9544834149F7F46E3C86FE22A8EAD`

## 3. Server summary → DOM matrix

| Typed source | Tracker DOM | Allowed transformation | Forbidden meaning |
|---|---|---|---|
| `case_no` | `order-tracker.card.<encoded-case-no>` | safe DOM encoding only | random/index identity |
| `client_name` | card/drawer client label | direct display | fixed fallback client story |
| `order_status` | raw status label | label explicitly says non-stage | seven-stage mapping/count/SOP progress |
| `staff_name: string|null` | assigned staff summary | null → `—`/unavailable | matching/recommendation/willingness conclusion |
| `identity_status: string|null` | optional raw identity label if retained | null → unavailable | blocker/action eligibility |
| `start_date/end_date` | planned date fields | direct display only | duration/buffer/stage calculation |
| `actual_start_date/actual_end_date` | actual date fields | direct display only | completion/waiting/settlement inference |
| `service_days: int|null` | service-day label | nullable formatting only | local recomputation |
| `total_employer_self_pay_payable: int|null` | payable amount label | NTD formatting only | paid/settled/deposit conclusion |
| absent phone/address | preserved slots | explicit unavailable | fake value or another endpoint guess |

## 4. Seven-stage visual slots

| Slot ID | Presentation label | Count | Content disposition |
|---|---|---|---|
| `intake_terms` | 1. 進件與補件 | `—` | typed stage projection unavailable |
| `matching_willingness` | 2. 媒合與徵詢意願 | `—` | typed stage projection unavailable |
| `client_review` | 3. 推薦客戶與確認 | `—` | typed stage projection unavailable |
| `contract_deposit` | 4. 雙邊簽約與定金 | `—` | typed stage projection unavailable |
| `date_confirmation` | 5. 確認實際服務日期 | `—` | typed stage projection unavailable |
| `active_service` | 6. 正式服務履約 | `—` | typed stage projection unavailable |
| `settlement_payout` | 7. 完工結案與請款 | `—` | typed stage projection unavailable |

Loaded summary cards render only under `order-tracker.unclassified-orders` with an explicit “待後端階段投影”
heading. This is not an eighth business stage.

## 5. SOP／LINE／settlement slots

| Surface | Required visible state | Prohibited content |
|---|---|---|
| SOP steps 1–11 | names retained; status/timestamp null; typed root-fact lineage unavailable | completed/in-progress/pending, progress icons, fixed notes, stage-derived text |
| LINE tab | one case-scoped timeline unavailable sentinel | `NTF-*`, fixed timestamps, success/failed badges, recipient/payload/message/provider errors |
| Manual replay | native disabled, stable control id, 0 request | handler, alert/confirm, fake retry success |
| Service completion | independent unavailable slot | infer from status/end date/SOP stage |
| Client finance settlement | independent unavailable slot | infer from deposit/amount/contract completion |
| Staff payroll settlement | independent unavailable slot | infer from another settlement/stage |

## 6. Request-budget matrix

| UI event | GET max | Non-GET max | Expected target |
|---|---:|---:|---|
| Initial render | 1 | 0 | `/api/v1/orders/summaries` |
| Explicit retry | 1 per click | 0 | same summaries GET |
| Stage navigation | 0 | 0 | local scroll |
| Open/close Drawer | 0 | 0 | loaded summary only |
| SOP／LINE tab switch | 0 | 0 | local presentation |
| Disabled replay／any other action | 0 | 0 | none |

No background polling, prefetch, per-card fan-out, automatic retry or StrictMode duplicate request is allowed.

## 7. Test matrix

| Claim | Required test / negative control | Status before execution |
|---|---|---|
| no stage derivation | varied raw statuses produce identical seven unavailable slots | `NOT_RUN` |
| seven slots preserved | exact seven stable slot IDs/count `—`/unavailable text | `NOT_RUN` |
| loaded cards unclassified | summary cards only in unclassified region | `NOT_RUN` |
| 11 step integrity | exact 11 names, all lineage unavailable, no status/timestamp | `NOT_RUN` |
| no fake LINE | no generated rows/NTF/timestamp/message; tab 0 request | `NOT_RUN` |
| three settlement owners | three separate unavailable slots | `NOT_RUN` |
| request budget | initial one GET; drawer/tabs/nav zero; retry max one | `NOT_RUN` |
| error/state | success/empty/error/auth/timeout/abort/stale/reload | `NOT_RUN` |
| mutation safety | disabled replay, 0 POST/PUT/PATCH/DELETE/dialog | `NOT_RUN` |
| predecessor regression | eight-GET client/strict decoder and OrdersPage tests remain green | `NOT_RUN` |

## 8. Browser receipt checklist

| Step | Required evidence |
|---:|---|
| 1 | real account/password→TOTP; token omitted from evidence |
| 2 | `#order-tracker` initial Network has at most one summaries GET and zero non-GET |
| 3 | response summary fields match a loaded unclassified card DOM |
| 4 | seven navigator/sections visible; counts `—`; unavailable sentinel; no card allocated |
| 5 | Drawer open costs 0 request; 11 SOP slots all unavailable |
| 6 | LINE tab costs 0 request; no fake record; replay disabled |
| 7 | three settlement slots distinct and unavailable |
| 8 | retry/reload/auth expiry/stale behavior recorded; no anonymous fallback |

## 9. Gate template

| Gate | Status | Evidence requirement |
|---|---|---|
| G0 prerequisite/scope | BLOCKED | Orders Query completed + exact Tracker approval + fresh dirty baseline |
| G1 adapter no-derivation | NOT_RUN | focused adapter/static tests |
| G2 request/state behavior | NOT_RUN | focused page budget/error/stale tests |
| G3 UI preservation | NOT_RUN | stable DOM slot assertions |
| G4 static/regression | NOT_RUN | focused+Orders regression, build/lint/UTF-8/diff/secret/write-set |
| G5 real browser GET | NOT_RUN | TOTP Network↔DOM receipt |

## 10. DB gate

| Gate | Status | Reason |
|---|---|---|
| Scope gate | BLOCKED | awaiting exact approval and Orders Query completed predecessor |
| Change inventory | PASS | zero schema／seed／backfill／destructive change |
| Static release gate | NOT_RUN | no DB release |
| Descriptor gate | NOT_RUN | no DB object change |
| Read-only plan gate | NOT_RUN | no migration plan |
| Engine verification gate | NOT_RUN | query-only slice; browser GET is not engine evidence |
| Developer acceptance gate | NOT_RUN | existing DB not mutated |

Conclusion: `DB_CHANGE_NOT_READY`。本draft不授權production、mutation、DB、cutover或retirement。

