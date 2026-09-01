# 歷史訂單生命週期與服務天數帳務工作包

- 狀態：`in-progress`
- Authority：2026-09-01 人工要求先建立正式規格，並以該規格為依據開始執行。
- SSOT：[27_歷史訂單生命週期與服務天數帳務正式規格](../01_規格基線/27_歷史訂單生命週期與服務天數帳務正式規格.md)
- Effect ceiling：repository-local edit／test；不套用 DB、不 reset、不 deploy、不 commit／push、不執行銀行或其他 external effect。

## 1. Scenario 與 owner

把舊系統 workbook 的可採納列推進 Orders 歷史生命週期；以逐月嫂人工確認天數建立歷史單薪帳務；
在雙邊實際結清後投影帳務完成；未服務或服務中案件可重啟正常天數精算。

- Orders：歷史 lifecycle、來源採納、歷史天數事實與 outer UoW owner。
- Scheduling：只擁有正式逐日服務日期；歷史 count path 不寫 `staff_schedule`。
- Payroll／Client Finance／Staff Payables：各自擁有義務、核銷與結清 facts。
- API／React／MySQL：typed transport、presentation、port implementation。

## 2. Exact write set

- `domains/orders/historical_adoption.py`、`domains/orders/lifecycle.py`、新增歷史天數 domain model。
- `subsystems/orders/historical_*` 與必要 Orders lifecycle／typed facts consumers。
- 歷史帳務所需的 Payroll／Client Finance／Staff Payables application ports 與 adapters。
- `api/routes|schemas|dependencies` 下單一歷史服務帳務 resource。
- `ui_react/src` 下單一歷史服務帳務工作區；保留既有使用者 dirty changes。
- additive `db/schema_parts`、fresh schema assembly、preserve-data release／descriptor／manifest 與 schema tests。
- 對應 `.arch-map` leaf／index 及 owner-local／cross-domain tests。
- 本工作包與 current 正式規格索引的最小同步。

不在 write set：正常訂單公式重寫、正式逐日排班 backfill、銀行資料偽造、production／`union_db`、
legacy 大範圍清理、unrelated refactor。

## 3. 執行步驟

1. Orders 純規則：五種來源結果、四個歷史 lifecycle、strict business-date completion。
2. 歷史天數：逐 assignment 正整數、exact set、單薪時數、樓層費比例與最大餘數分配。
3. Persistence：append-only event／receipt、current projection、owner versions、idempotency、outbox；更新 Orders ENUM 與 lifecycle checks。
4. Cross-domain Q/P/A：同一 outer UoW 建立或調整 Client Finance／Payroll obligations。
5. Query／API／UI：同一 resource 顯示 server-owned impact；支援確認天數與重啟精算。
6. Settlement projector：只在 Client Finance 與全部 Staff Payables balance 為零時進帳務完成。
7. Verification：Static → owner Module → cross-domain → migration metadata／fresh／preserve candidate → React → Arch Map closure。

## 4. DB change inventory

| 類別 | Source → target | Data effect | Replay／rollback | Unresolved policy |
|---|---|---|---|---|
| schema-only | `orders.status`、lifecycle event checks → 加入四個歷史狀態 | 保留所有既有列，只擴張合法值 | preserve release forward-only；rollback 使用 source backup／discard candidate | parent column 非 released predecessor／exact 即 fail closed |
| schema-only | absent → 歷史天數 event／projection／receipt／outbox | 不 backfill、不建立業務列 | absent 建立；exact no-op；candidate 可丟棄 | partial／drift fail closed |
| system-seed | 無 | 無 | 不適用 | 不得新增 |
| business-row-backfill | 無 | 無 | 不適用 | 不得推測歷史天數 |
| destructive | 無 | 無 | 不適用 | 禁止 |

DB gate 在 disposable MySQL fresh bootstrap 與 preserve-data candidate 尚未取得真 engine evidence前固定
`DB_CHANGE_NOT_READY`；不得把 focused unit tests 當成可套用 DB 的授權。

## 5. Acceptance mapping

| Formal acceptance | Package step | Direct oracle |
|---|---|---|
| 1–6 workbook／日期分類 | 1 | Orders historical-adoption owner tests＋API preview contract |
| 7–9 天數、超額樓層費、單薪 | 2、4 | Orders／Payroll／Client Finance owner tests |
| 10–11 真實結清 | 4、6 | Client Finance／Staff Payables settlement tests＋Orders projector test |
| 12 multi-caregiver fail closed | 2、4 | exact assignment-set domain／application tests |
| 13–15 precision restart／禁止倒退 | 1、5 | Orders／Scheduling Q/P/A tests |
| 16 atomic rollback | 4 | cross-domain transaction failure-injection test |

## 6. Stop condition

全部正式 acceptance 具 current deterministic evidence，schema gate 如實標示 `PASS | BLOCKED | NOT_RUN`，
final diff 無越界且 Arch Map closure 完成；若需要 production DB／外部付款／deploy，立即停止並另取 Authority。
