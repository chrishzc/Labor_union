# Durable Job Option A decision receipt

日期：2026-08-21
核准原文：`核准此 exact Durable Job Persistence / Caller Adoption Decision Work Package，採用 Option A`

## Result

- Selected：`Option A / existing-column canonicalization`。
- Output：`DECISION_COMPLETE_OPTION_A_CONDITIONAL`。
- Equality：command type＋version＋canonical object payload＋immutable submitted actor；correlation僅觀測。
- Key：lowercase ASCII、DB前reject uppercase、不得silent normalize。
- Serialization：UTF-8、sorted keys、compact separators、finite JSON、`1`與`1.0` typed-distinct。
- Transaction：canonical repository 0 hidden commit；application composition唯一outer UoW owner。
- Sequence：Core → Bridge → six owners/eight commands → masked public outcome → React consumers。

## G0–G6

| Gate | Status | Evidence |
|---|---|---|
| G0 | PASS | exact approval、HEAD f9240b9、dirty preserved、docs-only allowlist |
| G1 | PASS | `persistence-caller-matrix.md`涵蓋schema／command／repository／worker／public view |
| G2 | PASS | 六owner／八command inventory完整 |
| G3 | PASS | JOB-DURABLE-001／JOB-QUEUE-LIFECYCLE-002均標SUPPLEMENT |
| G4 | PASS | 每項列真MySQL驗證方法；結果仍`PENDING_ENGINE`，未以Python冒充 |
| G5 | PASS | 唯一Option A結果與successor順序已凍結 |
| G6 | PASS | scoped UTF-8／diff／inbound／allowlist驗證見整合交付 |

本包production／test／SQL／React／validation／DB／runtime writes均為0。Docs decision完成不代表engine或runtime完成。

DB gates：Scope `PASS`、Change Inventory `PASS`；Static Release、Descriptor、Read-only Plan、Engine Verification、
Developer Acceptance均`NOT_RUN`。結論：`DB_CHANGE_NOT_READY`。
