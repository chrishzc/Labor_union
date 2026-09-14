# Module: numeric-and-fingerprint-contracts

## Parent
- domain: `global`
- subsystem: `shared-kernel`

## Responsibility
提供跨 Domain 可重用、無副作用的數值精度驗證與 canonical fingerprint encoding；不定義業務狀態或計算公式。

## Implementation
- primary:
  - `shared_kernel/validation.py`
  - `shared_kernel/fingerprints.py`

## Provenance
- Shared pure validation and fingerprint primitives — `source_observed` — current repository。

## Change triggers
Reconcile when accepted primitive types、canonical encoding or deterministic fingerprint behavior changes.
