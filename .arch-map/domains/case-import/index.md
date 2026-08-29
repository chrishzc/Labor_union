# Domain: case-import

## Responsibility
擁有 HCM／BeClass intake validation、source review 與 formal case bootstrap boundaries；不以來源列直接旁路寫入其他 Domain roots。

## Subsystems
- `case-import` — typed intake/review/bootstrap workflows; path: `subsystems/case-import/index.md`

## External relationships
- outbound: `orders` — accepted source becomes formal case/order bootstrap through owner boundary。
- outbound: `anomalies` — only eligible review/projection evidence is emitted。

## Contracts
- `document/架構重整/01_規格基線/15_正式規格索引與裁決總表.md` — current HCM/BeClass/import decisions
- `document/架構重整/01_規格基線/00_Global_共同契約.md` — Global mutation contract

## Verification routing
- default_boundary: Domain
- test_root: `tests/domains/case_import/`
- integration_root: `tests/subsystems/case_import/`.
- remaining_layout_gap: protected legacy import-contract paths only; see Test Map.
