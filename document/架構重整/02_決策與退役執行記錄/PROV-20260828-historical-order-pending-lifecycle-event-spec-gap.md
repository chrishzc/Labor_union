# Historical Orders 待補件來源狀態 lifecycle event 相容契約

- `spec_gap_id`: `PROV-20260828-historical-order-pending-lifecycle-event`
- `authority_status`: `CONFIRMED-2026-08-28`
- `spec_status`: `SPEC_READY`
- `implementation_status`: `in-progress`
- `owner`: Orders／Global Migration
- `authority`: 2026-08-28 使用者回報另一台主機以真實歷史資料執行確認匯入時回傳 500，並要求修復既有歷史匯入。

## 1. 問題與根因

Orders 的 canonical lifecycle 包含 `待補件`。歷史訂單匯入命中既有 `待補件` Order 並採納
`0／1／2` 時，immutable lifecycle event 必須如實保存 `before_status=待補件`。既有
`chk_order_lifecycle_state_event_before_status` 卻只允許 `洽談中／訂單成立／服務中／訂單完成／訂單取消`，
因此 MySQL 以 error 3819 拒絕 event INSERT；同一 row 的 Order UPDATE 由 outer UoW rollback，但 API
目前把錯誤暴露成未分類 500。

此問題不是 workbook parser 錯誤。`OrderLifecycleStatus` 能成功載入該 Order，且 constraint 允許集合與
Domain enum 的唯一差集就是 `待補件`；不能把 before status 改寫成 after status 或其他值來繞過 constraint。

## 2. Required behavior

- `HOPE-R1`: lifecycle event 的 before status check 必須接受`待補件`且不得移除既有五種狀態；
  after status仍只允許`洽談中／訂單成立／服務中／訂單完成／訂單取消`，不得把`待補件`放寬成結果狀態。
- `HOPE-R2`: preserve-data 升級只能替換 before status check constraint；不得更新、刪除或 backfill 既有
  lifecycle event／Order／receipt rows。
- `HOPE-R3`: historical adoption 從 `待補件` 採納 `0／1／2` 時，event 必須保存真實
  `before_status=待補件` 與相應 after status；Order、event、receipt、workbook cursor仍由既有單一 outer
  UoW 原子提交。
- `HOPE-R4`: 未升級或 constraint drift 的環境必須 fail closed；API 回傳可辨識的 service-unavailable
  error，不得回傳 raw MySQL traceback，也不得把失敗列標成 committed。
- `HOPE-R5`: same-key replay、different-workbook conflict與 `0／1／2／invalid` counts守恆維持不變。

## 3. DB change inventory

| Class | Source artifact | Target／effect | Replay／rollback／unresolved |
|---|---|---|---|
| `schema-only` | 新 additive successor | 替換 `order_lifecycle_state_events` 的 before status check，加入`待補件`；after status check不變 | exact successor可重播略過；source backup＋discard candidate rollback；partial／drift fail closed |
| `system-seed` | none | none | none |
| `business-row-backfill` | none | none | 禁止隱式 row migration |
| `destructive` | none | 不刪 table、column、index、event 或業務資料 | constraint replacement只在 candidate／核准本機升級路徑執行 |

## 4. Acceptance

| ID | Acceptance |
|---|---|
| `HOPE-A1` | Static descriptor可區分 predecessor、exact successor、partial／drift；release hash、assembly、catalog與read-only plan互相一致。 |
| `HOPE-A2` | fresh `lu_test_*` bootstrap後，`待補件→取消／完成／洽談中` event INSERT全部成功，before status均為`待補件`。 |
| `HOPE-A3` | previous supported source含代表性既有 rows時，dump→candidate→apply→verify保存 row count／fingerprint，checks為exact且沒有backfill。 |
| `HOPE-A4` | historical workbook Apply對三筆`待補件` Order的`0／1／2`完整成功；Order、event、receipt、cursor與replay readback exact。 |
| `HOPE-A5` | predecessor／drift環境的Apply零提交並回typed 503；不洩漏SQL或原始個資。 |

## 5. Boundaries

- 不修改 status mapping、generic status editor、Client／Scheduling／Finance／Staff roots或 provider。
- 不操作 `union_db`／production；engine evidence只使用 disposable／allowlisted `lu_test_*`。
- 本修正是既有六欄狀態契約的 DB compatibility successor；不重開已完成的 parser／counts scope。
