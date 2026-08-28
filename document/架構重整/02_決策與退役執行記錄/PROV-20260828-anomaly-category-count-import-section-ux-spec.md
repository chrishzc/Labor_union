# 異常分類數量與匯入待辦區隔規格

- `spec_id`: `PROV-20260828-anomaly-category-count-import-section-ux`
- `declared_status`: `approved`
- `authority_status`: `CONFIRMED-2026-08-28`
- `terminal_status`: `SPEC_READY`
- `owner`: Anomalies UI projection；Import Warning 只擁有匯入待辦。
- `effect_ceiling`: React 分類／顯示與 focused tests；不改 API、Domain、DB、provider 或異常狀態。

## 1. 問題與根事實

2026-08-28 人工指出：異常頁只有「全部」顯示數量，其他分類無法直覺判斷工作量；
且「匯入資料待辦」在媒合、排班、帳務等無關分類下仍顯示，造成分類語意混雜。

Current React 已同時持有 typed anomaly summaries 與 typed import-warning tasks，本修正可由現有資料
deterministic 投影，不需新 public API。

## 2. 已採用行為

1. 八個分類 tab 均以 `分類 (N)` 顯示數量，包含零。
2. `N` 以目前 status filter 為基礎再依分類計算；切換 status 必須同步更新所有 tab 數量。
3. `全部` 的數量是目前 status filter 下的 anomaly cards 總數；不把另一資料源的
   import-warning tasks 暗中加進 anomaly count。
4. `匯入資料待辦` section 只在 selected category 為 `全部` 或 `匯入資料` 時 render。
5. `媒合推薦`、`排班調度`、`客戶帳務`、`月嫂薪資`、`政府補助`、`其他` 下不得 render
   import-warning title、loading、error、empty state 或 cards。
6. 分類計數與 list 必須使用同一 category/status predicate，不得出現 tab 數量與可見項目不一致。
7. 不改變 KPI、claim/tracking 語意、owner correction、pagination 或 import-warning 的獨立狀態機。

## 3. 驗收

- Module：每個 category tab 均有數量，status 切換後計數重算，count 與 visible cards 一致。
- Negative：選媒合／排班／帳務／薪資／補助／其他時，DOM 內不存在
  `anomalies.import-warnings`；選全部／匯入時依實際 loading/error/empty/data 顯示。
- Regression：異常分類、status filter、load-more 與 import-warning drawer 既有 tests 全數通過。
- Browser：no-auth 真頁面驗證分類數量與 section 顯示邊界，console error 為零。

```yaml
convergence:
  status: READY
  blockers: []
```
