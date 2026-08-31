kind: test-index
schema_version: 2
architecture_map: ../index.md
test_root: tests/
global_root: layout_gap

# Test routing

Owner-local tests應進 owning Domain／Subsystem canonical root；`tests/` flat root只保留有明確 higher-boundary理由的 coverage。檔名不是 ownership 證據，必須以 direct SUT、owner contract、transaction boundary與 current consumer判定。

## Canonical owner roots
- `global/migration` — `tests/domains/global/subsystems/migration/`；map: `domains/global/index.md`
- `orders` — `tests/domains/orders/subsystems/orders/`；map: `domains/orders/index.md`
- `scheduling` — `tests/domains/scheduling/subsystems/scheduling/`；map: `domains/scheduling/index.md`
- `client-finance` — `tests/domains/client-finance/subsystems/client-finance/`；map: `domains/client-finance/index.md`
- `staff-payables` — `tests/domains/staff-payables/subsystems/staff-payables/`；map: `domains/staff-payables/index.md`
- `anomalies` — `tests/domains/anomalies/subsystems/anomalies/`；map: `domains/anomalies/index.md`
- `payroll` — `tests/domains/payroll/subsystems/payroll/`；map: `domains/payroll/index.md`
- `finance-import` — `tests/domains/finance-import/subsystems/finance-import/`；map: `domains/finance-import/index.md`
- `government-subsidy` — `tests/domains/government-subsidy/subsystems/government-subsidy/`；map: `domains/government-subsidy/index.md`
- `case-import` — `tests/subsystems/case_import/`；Domain-level higher boundary: `tests/domains/case_import/`；map: `domains/case-import/index.md`
- `access` — `tests/domains/external-integration/subsystems/access/`；map: `domains/external-integration/index.md`
- `line` — `tests/domains/external-integration/subsystems/line/`；map: `domains/external-integration/index.md`
- `contract-signing` — `tests/domains/contract-signing/subsystems/contract-signing/`；map: `domains/contract-signing/index.md`
- `global-reporting` — `tests/test_weekly_operations_report_contract.py`（path-sensitive cross-domain contract）；map: `domains/global/subsystems/reporting/index.md`

## Higher-boundary routing
Keep tests outside an owner root only when the test itself proves one of these boundaries:

- application composition／OpenAPI bootstrap crossing owner registration;
- true cross-domain workflow or shared integration behavior;
- release／schema／migration／fresh-assembly governance;
- disposable-MySQL or engine acceptance whose target spans more than one owner or release boundary;
- Task97／entry／writer／commit／CI governance;
- legacy UI or compatibility behavior with a documented current consumer/path-sensitive gate.

`ui_react/src/tests/challenger_auth_navigation.test.tsx` remains a Global application-shell higher-boundary test because one file jointly protects hash navigation、session/auth boundaries、nested ErrorBoundary isolation及closed crash presentation；它不是任何單一Domain owner-local root，也不得因其中一個oracle更新而重包。

Physical roots currently used for those cases include `tests/integration/`, `tests/e2e/`, `tests/hurl/` and selected documented flat `tests/test_*.py` files. `tests/fixtures/` remains shared legacy fixture storage; ownership must be resolved from consumers before moving/removing it. `tests/global/` is not currently present (`layout_gap`).

## Placement refresh — 2026-08-30
The HCM resubmission domain/workbook/workflow coverage is Case Import owner-local and now lives under `tests/subsystems/case_import/`. Its file-system assertion is relocation-safe and resolves the repository root from the canonical owner location. Existing explicit higher-boundary exceptions in owner Test Maps remain unchanged; do not mechanically move them merely to eliminate flat files.
