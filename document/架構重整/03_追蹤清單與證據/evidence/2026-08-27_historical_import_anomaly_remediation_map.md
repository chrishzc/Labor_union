# 歷史訂單匯入與人工異常修復映射

- 日期：2026-08-27
- Current items：`CUR-P0-HISTORICAL-IMPORT-01`、`CUR-P0-ANOMALY-RECOVERY-01`、`CUR-ANOMALY-MANUAL-REMEDIATION-01`
- 結果：`passed`（static owner／predicate mapping）；runtime completion 仍為 `in-progress`
- Authority：使用者要求匯入完整歷史檔後，真正異常都能由 UI 人工修正；修正必須改正 owner root，再由 fresh predicate 自動解除。

## 1. Source contract 與不可推定事項

目前 Historical Orders workbook v1 只接受 `case_no`、`client_name`、status `0/1/2`、案件起訖日期、
一或兩位月嫂姓名，以及可選的每位月嫂服務區間。status mapping 固定為
`0=訂單取消`、`1=訂單完成`、`2=洽談中`；來源沒有獨立的「服務中」值或 boolean。

| Source | Owner adoption | 可以形成 | 不可直接形成 |
|---|---|---|---|
| `case_no + client_name` | Orders | 精確匹配既有 Order | 建立新 Client／Order；`unmatched_case` 固定零 mutation、零 anomaly |
| status／案件起訖日期 | Orders historical adoption | historical assertion、nullable date root、immutable evidence | 服務中、Step 11 completion、LINE／簽章／付款事實 |
| 月嫂姓名 | Orders resolution，後續交 Scheduling owner | pairing evidence；唯一 identity／區間可形成 formal owner command 的候選 | 直接建立 official service、Payroll、settlement |
| 個別月嫂區間 | Scheduling owner | typed workflow 通過後的 assignment／official service facts | 多月嫂缺個別區間時猜測日期、工時、assignment 或薪資 |

目前 `historical_order_adoption_repository.py` 仍直接寫 `case_staff_assignments`；這與 Global
跨 Domain typed-port owner boundary 不一致，標記為 `live-drift`，不得當成 Scheduling 正式採納或
服務中證據。

## 2. 可能出現的異常範圍

歷史 workbook 直接合法產生的 canonical anomaly 只有 `HISTORICAL-ORDER-001`。精確匹配後若
status／日期／月嫂／assignment evidence 有問題，可由 Orders historical review remediation 處理；
找不到案件是 `unmatched_case`，不建立 alert。

只有在後續 Scheduling typed workflow 正式採納 assignment／actual-service roots 後，真實衝突才可能形成
`SCHEDULE-001`、`SCHEDULE-002`、`SCHEDULE-003` 或 `SCHEDULE-006`。`SCHEDULE-005` 是已裁決的
preference-only false positive，固定退役。status=完成但 owner roots 不完整時，HOB-E projector 應顯示
具體 missing-root blocker，例如 Orders actual start 或 Scheduling official service facts 缺失；不得把
status assertion 當成完成或製造 Finance／Staff Payables／LINE 異常。

BeClass／HCM integrity、LINE、Finance、Staff Payables、Government Subsidy 等異常都有自己的 owner root；
不能由此歷史 workbook 直接產生。42-code catalog 的 33 個 active anomaly 是全產品目標，不是一次歷史匯入
應同時觸發的清單。

## 3. 人工修復閉環與 current evidence

固定流程為 `anomaly detail → owner Query → Preview → Confirm → Apply → receipt／fresh owner readback →
predicate recheck`。禁止 tracking close、generic resolve、任意 status editor或直接改 alert table。

| Scenario | Owner UI／command | Current evidence |
|---|---|---|
| `HISTORICAL-ORDER-001` source review | Orders historical review Query／Preview／Apply | MySQL Apply／replay／outbox／active removal passed；no-auth Browser 尚須以正式 versioned scenario重驗 |
| 無 actual service，要更換月嫂 | WP-HOB-B replacement successor | approved；workflow／persistence／API／React/runtime仍未完成 |
| 已有 actual service，要更換月嫂 | WP-HOB-C Scheduling substitution | 核心規則已核准；不得要求新契約／簽回，runtime與 optional-note DB slice仍未完成 |
| status=完成／要進 Step 11 | WP-HOB-E owner-terminal completion | F-04 terminal scenario passed；其他 missing-root correction與H-03/A-02等scenario仍未完成 |
| 取消 | WP-HOB-D cancellation owner flow | 三分支與Finance direction已核准；完整真MySQL/API/Browser仍未完成 |
| Scheduling 真衝突 | Scheduling-specific owner Q/P/A | `SCHEDULE-001/002/003/006`仍有SPEC_GAP或缺Apply，不得用現有導航冒充修復 |

## 4. Final acceptance oracle

1. 完整歷史資料不亂報：洽談中不推成服務中；完成 assertion 不推成 Step 11；不存在的 LINE、簽章、付款、allocation、official service 不得被補造。
2. 真衝突可人工修正：detail 顯示 exact owner、field/root、identity、version、fingerprint、reason/evidence 與合法入口。
3. Apply 後 fresh recheck：原 root predicate 消失才移除 alert；仍缺其他事實時建立具體 successor blocker。
4. stale、identity drift、readback failure、timeout／outcome unknown、權限不足都維持 active，且使用原 idempotency identity調和，不盲送。
5. versioned scenario 必須分別覆蓋 historical review、replacement、substitution、cancellation、completion與Scheduling conflict；F-04不得代替其他分支。

## 5. Evidence sources

- `01_規格基線/01_Orders_Domain.md` §3.7–3.8
- `01_規格基線/02_Assignments_Scheduling_Domain.md` Historical Order Adoption
- `02_決策與退役執行記錄/PROV-20260827-historical-order-operational-baseline-spec.md`
- `02_決策與退役執行記錄/PROV-20260827-historical-order-operational-work-packages.md`
- `02_決策與退役執行記錄/PROV-20260826-all-anomaly-manual-remediation-spec-gap.md`
- `03_追蹤清單與證據/evidence/2026-08-27_anomaly_rulebook_oracle_matrix.md`
- `subsystems/orders/historical_order_workbook.py`
- `infrastructure/mysql/historical_order_adoption_repository.py`

本輪 mapping 為唯讀規格／source 稽核，沒有 DB、schema、migration、provider 或 production effect。
