# Module: read-projection-cache

## Parent
- domain: `global`
- subsystem: `shared-kernel`

## Responsibility
提供不參與正式交易或 Preview／Apply 決策的執行緒安全 TTL 唯讀投影快取、同鍵單飛（single-flight）防擊穿合併，以及選用的本機 Redis 二層快取後端（含短逾時與斷線冷卻自動退回記憶體快取）。

## Implementation
- primary:
  - `shared_kernel/ttl_cache.py`
  - `shared_kernel/performance.py`
- adapter:
  - `infrastructure/cache/__init__.py`
  - `infrastructure/cache/redis_projection_cache.py`

## Contracts
- `document/架構重整/01_規格基線/12_Global_效能與UX體感架構.md` §3（G15）— 快取僅能加速唯讀 Query／ViewModel 投影，嚴禁參與正式 Command／Preview／Apply fresh-fact 驗證；提交成功後以明確鍵或命名前綴同步失效 L1 與 L2，Redis 不可用時無副作用退回 L1／DB。

## Verification
- default_boundary: Module
- test_root: `tests/domains/global/subsystems/shared-kernel/modules/read-projection-cache/`
- higher_boundary: `tests/test_g15_cache_boundary_contract.py`

## Provenance
- G15 read-only projection cache boundary — `architecture_declared` — `12_Global_效能與UX體感架構.md`。
- L1 single-flight TTL cache and optional Redis backend — `source_observed` — current repository。

## Change triggers
Reconcile when `ExternalCacheBackend` protocol、TTL／single-flight semantics、Redis key prefix／cooldown policy or canonical test root changes.
