---
doc_type: work-package
declared_status: approved
identity: PROV-20260817-react-admin-phase5a-entry-governance-rollback
date: 2026-08-17
owner: Integration Owner
specification: PROV-20260817-react-admin-phase5a-entry-governance-rollback
spec_path: PROV-20260817-react-admin-phase5a-entry-governance-rollback-specification.md
authority: awaiting-exact-human-approval
approval_required: 核准此 exact Phase 5A Work Package
approval_evidence: user-replied-核准此-exact-Phase-5A-Work-Package
prerequisites: none; inventory/rollback foundation is independent of page/Global/Scenario/DB/cutover readiness
base_branch: main
base_head: late-bound-at-approval
dirty_baseline: integration-owner-must-capture-before-writer
base_drift_rule: registry/queue/Streamlit/React route drift requires fresh inventory before edits
ui_execution_mode: browser-optional-for-foundation; required later for each entry switch
---

# React Phase 5A：Entry inventory／rollback foundation Work Package

## 0. Activation and ceiling

Existing exact phrase is retained:

> 核准此 exact Phase 5A Work Package

Approval authorizes only the `ui-react` discovery kind, exact 10 Streamlit + 11 React inventory, Data Import discovery,
fixed rollback resolver and validation. It does not authorize navigation switching, replacement disposition, dual-run,
hosting, cutover, business-page changes or retirement.

No bounded page, Global runtime, Scenario, DB, deployment or browser business-data PASS is a prerequisite. Their status
is recorded by later entry-specific packages and cannot turn an existing route into a nonexistent entry.

## 1. Exact inventory and rollback matrix

The Contract Scout freezes:

- 10 `ui:*` identities from `ui/app.py::PAGE_REGISTRY`, including `ui:09_data_import.py`;
- 11 `ui-react:#*` identities from NAV/Page map/App render witnesses;
- `#login` as auth guard state, not an administrative entry;
- all 11 React → Streamlit mappings from the specification;
- one-to-many group `staff-scheduling`: `#staff` and `#scheduling` share `ui:03_calendar.py` but use distinct fixed views;
- exact deep links, including `/?entry=scheduling&view=calendar` and
  `/?entry=scheduling&view=staff-directory`.

Queue total is not hard-coded. Unrelated API/CLI drift is preserved and reported but does not block this UI foundation.

## 2. Exact write set after approval

### Registry/discovery

- `validation/scenarios/react_admin_entrypoints.json`
- `scripts/generate_entrypoint_review_queue.py`
- `tests/test_entrypoint_review_queue.py`
- `document/架構重整/03_追蹤清單與證據/evidence/entrypoint_review_queue_v1.jsonl`

Generator changes are limited to runtime `PAGE_REGISTRY` Streamlit discovery, exact React manifest merge and preservation
of reviewed/non-UI rows. It must add Data Import without inventing a module-level title.

### Streamlit rollback resolver

- `ui/app.py`
- `ui/nav_helper.py` only if fixed subview state cannot remain local to `ui/app.py`
- `tests/test_react_streamlit_entry_rollback.py`
- `tests/test_access_control_ui_app_test.py` only for exact auth/deep-link regression

No Streamlit business page is modified. The resolver may set only the fixed module/subview state declared by the
mapping; it cannot pass arbitrary query payload into a page.

### React inventory verifier

- `ui_react/src/tests/react_entrypoint_registry.test.ts`
- `ui_react/src/App.tsx` only if required to replace prototype-unsafe hash membership with exact own-set membership

`ui_react/src/components/MasterLayout.tsx` and `ui_react/src/components/navigation.ts` are read-only registry witnesses.
They are not normalized or redesigned in this foundation.

### Integration-owned docs/evidence

- existing specification and Work Package
- `document/架構重整/01_規格基線/19_Global_Entry_Point_Governance.md` bounded `ui-react` amendment
- `document/架構重整/01_規格基線/15_正式規格索引與裁決總表.md` one-line amendment registration
- `document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase5a-entry-governance-rollback/`

Shared `02/README.md` and React main plan are intentionally deferred to Integration handoff and are not modified by
this docs-refinement turn.

## 3. Execution order

```text
fresh inventory freeze
→ registry/generator candidate || rollback resolver candidate || React verifier candidate
→ Integration semantic merge (queue single writer)
→ focused validators
→ optional shell-only browser proof
→ foundation receipt; no switch receipt
```

Writers have mutually exclusive paths. Queue, manifest, indexes and evidence have one Integration writer.

## 4. Acceptance gates

| Gate | PASS condition |
|---|---|
| G0 | exact approval, dirty baseline, exact write set, 0 business/DB/navigation-switch edits |
| G1 | independent inventory equals 10 Streamlit + 11 React; Data Import present; no duplicate/prototype identity |
| G2 | queue preserves unrelated rows; React candidates remain `review_required`; source drift remains reviewable |
| G3 | all 11 fixed rollback URLs resolve to exact module/subview; Staff/Scheduling group stays two entries |
| G4 | unknown/extra/duplicate/multi-value/secret-bearing query fails closed; auth state preserves only sanitized target |
| G5 | Python/Vitest validators, strict UTF-8 and diff checks pass |
| G6 | receipt lists 21 identities, mapping and `no navigation switch`; browser shell evidence may remain `NOT_RUN` |

G6 does not require all business pages, Global, Scenario or DB gates to pass. Browser becomes mandatory only when a
later package proposes switching a specific entry.

## 5. Required focused commands

```powershell
.venv\Scripts\python.exe -m pytest -p no:cacheprovider `
  tests/test_entrypoint_review_queue.py `
  tests/test_react_streamlit_entry_rollback.py `
  tests/test_access_control_ui_app_test.py `
  --basetemp .pytest_tmp/phase5a-entry -q
```

```powershell
cd ui_react
npm test -- src/tests/react_entrypoint_registry.test.ts `
  src/tests/route_guard.test.tsx src/tests/challenger_auth_navigation.test.tsx
npm run build
```

No command may update navigation, mutate DB, generate fake business data or retire an entry.

## 6. Anti-laziness / safety

- expected UI set is independent of the generator under test;
- no fake title to make `09_data_import.py` discoverable;
- no `in` membership for hash allowlists;
- no one-to-one assumption that collapses `#staff` into `#scheduling`;
- no base-URL-only rollback; module and fixed subview must both be asserted;
- no hard-coded queue total or requirement to fix unrelated API/CLI drift;
- no candidate `active/replacement/cutover-ready/retired` status;
- no browser/business-page success claim from source scans or component mocks.

## 7. Evidence

If the evidence directory is created during execution, it contains:

- `contract-inventory.md` (21 identities + 11 rollback mappings);
- `candidate-change-inventory.md`;
- `verification-receipt.md`;
- `browser-rollback-receipt.md` (`NOT_RUN` is permitted for foundation);
- `open-findings.md`.

There is currently no Phase 5A evidence-matrix draft to update; this turn does not create a competing matrix.

## 8. DB gate

| Gate | Status |
|---|---|
| Scope | `PASS` |
| Change inventory | `PASS` (0 schema/seed/backfill/destructive) |
| Static release / Descriptor / Read-only plan / Engine / Developer acceptance | `NOT_RUN` |

Conclusion: `DB_CHANGE_NOT_READY`; Phase 5A remains a non-DB inventory/rollback foundation.
