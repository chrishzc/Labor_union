# Task 96 SP2-Q 階段交接 receipt

- `date`: `2026-08-27`
- `scope`: `WP-HOB-E / SP2-Q internal typed contract and Staff Payables read adapter`
- `status`: `passed`（internal source candidate）；WP-HOB-E整包仍`in-progress`
- `db_change`: `NO_DB_CHANGE`

## 已完成

1. 人工裁決已固定：採用`SP2-Q`；open／partially recovered溢付款追回異常持續存在，但在原義務
   已結清且payout／allocation／recovery lineage完整時，不單獨阻擋Step 11。
2. Staff Payables不建立case scalar或`MAX(version)`；改以排序、去重、具source kind／identity／version
   的向量穿過oracle result與fingerprint。
3. 單statement adapter讀取Payroll case、obligation/current event、staff account、projection、完整跨案
   payout／return／reversal links、bank evidence與適用recovery roots/events。
4. 缺來源、版本漂移、非法amount/hash/reversal shape、allocation不完整、recovery lineage不一致或owner
   失敗都fail closed為`UNAVAILABLE`；open recovery本身不增加open obligation。

## 最終本機證據

- `.venv/bin/python -m pytest ...`：`78 passed`。
- Python compile：`passed`。
- `git diff --check`：`passed`。
- 真MySQL：`lu_test_task96_scenarios_20260827`對38欄、五個case參數的單statement SELECT解析／執行
  `passed`（不存在case、0 rows、零寫入）。
- DB gate：schema／seed／backfill／destructive均`NOT_APPLICABLE`；未操作`union_db`或production。

## DDH 動態調整紀錄

1. E4三條Luna High唯讀盤點lane建立HOB-A／HOB-B／其他優先工作gap map。
2. E3 exact patch producer未產patch且零寫入；依同revision不可重試規則降為E2主代理writer。
3. 第一個E3雙verifier wave找出bank、projection version、return／reversal、recovery與fingerprint缺口；
   terminal後回E2修正。
4. 第二個E3雙verifier wave再找出Orders fingerprint、unavailable分類與malformed source反例；terminal後
   回E2修正。
5. 所有實際子代理均為`gpt-5.6-luna`／`high`，全部read-only、零changed files。

## 下一個session首要工作

1. 先以fresh Luna High獨立驗證目前修正版；不得沿用修正前review宣稱PASS。
2. 若PASS，再實作HOB-E API typed view／dependency wiring、projector與React顯示；不得讓raw dict穿透。
3. 以正式commands建立Staff Payables正向case，跑cross-owner MySQL／API／React，再以enabled
   persisted-human Browser驗證Step 11與異常解除；不得直接seed派生root。
4. 之後回到WP-HOB-A persistence vertical slice及WP-HOB-B pre-service replacement successor。

## 清理裁決

- 正式tests、規格、決策、此receipt與所有未知dirty paths為durable，保留。
- 沒有找到可證明失效的正式test檔；本輪新增tests皆直接保護SP2-Q裁決，不刪除。
- `scratch/task96-sp2q-20260827`、`scratch/task96-sp2q-verify-20260827`、
  `scratch/task96-sp2q-final-verify-20260827`是已reconcile且內容已萃取至本receipt的bounded transient；
  已依使用者本輪明確授權精確刪除，readback確認三個路徑均不存在；`passed`。
