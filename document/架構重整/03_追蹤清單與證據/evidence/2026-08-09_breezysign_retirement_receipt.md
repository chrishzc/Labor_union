---
scope: BreezySign retirement
status: retired-by-user-direction
verified_at: 2026-08-09
---

# BreezySign 退役收據

使用者明確要求移除 BreezySign 功能。現行 runtime、schema、正式架構基線、部署 public-edge
allowlist、系統地圖與管理端重整計畫已移除該 provider 的功能、route、domain 和 contract。

驗收範圍：

- production code、`db/schema.sql` 與 `db/schema_parts/` 不含 provider reference；
- `orders.contract_id` 已改為 provider-neutral `orders.contract_identity`；既有資料庫只可經
  `scripts/migrate_order_contract_identity.py` 進行一次 fail-closed rename，完成後不保留舊欄位；
- `01_規格基線/`、`document/架構重整/README.md` 與 `system_map.yaml` 不再把它列為現行能力；
- historical source、decision package 與 writer-inventory snapshot 保留原始內容，以維持退役
  追溯與不可變稽核證據，不能被當成 runtime 或規格 SSOT。

驗證（2026-08-09）：

- `tests/test_breezysign_retirement_boundary.py`、`tests/test_migrate_order_contract_identity.py`、
  `tests/test_contract_context_router.py`、`tests/test_order_detail_query.py` 與 LINE／Access 邊界
  tests 合計 `23 passed`；
- active runtime、schema 與 current documentation 的 provider-name 與舊欄位掃描均為零命中；
- 受影響 Python modules 已通過 `py_compile`。
- BreezySign 退役完成當下重新生成的 `formal_baseline_v1.json` 為 647 writer findings、
  legacy runtime callers 為 0；後續 Access／Knowledge implementation 另更新 current baseline。
