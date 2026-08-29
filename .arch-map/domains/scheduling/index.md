# Domain: scheduling

## Responsibility
擁有 assignment generation、服務日、可服務／不可服務期間、請假代班與 matching coordination 的排班根事實。

## Subsystems
- `scheduling` — 編排 scheduling/matching/leave/substitution workflows; path: `subsystems/scheduling/index.md`

## External relationships
- depends_on: `orders` — case/lifecycle 與服務時段 boundary。
- depended_by: `payroll` — assignment/service facts 是薪資義務來源。
- depended_by: `external-integration` — LINE 請假／自助入口只建立或驅動 Scheduling-owned command。

## Contracts
- `document/架構重整/01_規格基線/02_Assignments_Scheduling_Domain.md` — Scheduling canonical Domain contract
- `document/架構重整/01_規格基線/24_Staff_Matching_Preferences與不可服務期間正式規格.md` — matching preferences／unavailability contract
- `document/架構重整/01_規格基線/00_Global_共同契約.md` — Global mutation contract

## Verification routing
- default_boundary: Domain
- test_root: unknown (`layout_gap`; no `tests/domains/scheduling/` observed)
- integration_root: `tests/integration/` (shared legacy root); see `.arch-map/tests/domains/scheduling/index.md`.
