---
doc_type: implementation-specification
declared_status: proposed
identity: PROV-20260817-react-admin-phase5a-entry-governance-rollback
date: 2026-08-17
owner: Global Entry Point Governance
authority: awaiting-exact-human-approval
formal_contract_amendment: add-ui-react-entry-kind-and-entry-specific-streamlit-rollback
approval_required: 核准此 exact Phase 5A Work Package
prerequisites: none; this is an inventory/rollback foundation and does not require bounded page, Global runtime, Scenario, DB, deployment, or cutover PASS
base_branch: main
base_head: late-bound-at-approval
dirty_baseline: integration-owner-must-capture-before-writer
base_drift_rule: relevant registry, queue, Streamlit or React route drift requires fresh read and re-freeze
---

# React Phase 5A：Entry inventory 與 entry-specific rollback foundation 規格

## 1. Purpose and boundary

Phase 5A only establishes discoverable UI identities and deterministic rollback targets. It does **not** switch
navigation, mark React as replacement, retire Streamlit, deploy hosting, change business routes, or require every
bounded page to be query/mutation complete.

The foundation may proceed while individual page slices, Global runtime gates, Scenario controlled data, DB gates,
browser data or Phase 4 high-side-effect flows remain incomplete. Those conditions belong to each later per-entry
readiness/cutover package and cannot block truthful discovery of an entry that already exists.

## 2. Fresh inventory facts

### Streamlit: 10 external page identities

`ui/app.py::PAGE_REGISTRY` is the runtime authority and currently registers exactly:

1. `ui:01_data_browser.py`
2. `ui:02_orders.py`
3. `ui:03_calendar.py`
4. `ui:04_finance.py`
5. `ui:05_form_management.py`
6. `ui:06_finance_alerts.py`
7. `ui:07_line_management.py`
8. `ui:08_system_status.py`
9. `ui:09_access_management.py`
10. `ui:09_data_import.py`

The current generator scans `ui/pages/*.py` and depends on module-level title detection, so it can omit
`09_data_import.py` even though runtime `PAGE_REGISTRY` can load it. Phase 5A discovery must read/parse the registry
or a generated-independent exact manifest and add the Data Import identity; adding a fake module title is prohibited.

### React: 11 protected administrative identities

The exact React hashes discovered from `MasterLayout.NAV_ITEMS` and `App` render wiring are:

`#order-tracker`, `#orders`, `#scheduling`, `#staff`, `#data-import`, `#line-management`, `#reports`, `#finance`,
`#anomalies`, `#data-browser`, `#account-management`.

They become queue identities `ui-react:#<hash-without-#>` and start as `review_required`. `#login` is an auth guard
state, not a twelfth administrative entry. Exact set membership must reject prototype names and unknown hashes.

## 3. One-to-many replacement group

Entry discovery is not forced into one React ↔ one Streamlit pairing. `#scheduling` and `#staff` are two independent
React entries that share one Streamlit runtime module `ui.pages.03_calendar`; they form the explicit
`staff-scheduling` replacement group. Their rollback deep links remain distinct by fixed subview:

- `#scheduling` → `/?entry=scheduling&view=calendar`
- `#staff` → `/?entry=scheduling&view=staff-directory`

The grouping does not merge their page readiness, tests, owner or cutover decision. Either React entry can stay
blocked while the other proceeds through later readiness. The shared Streamlit module is only the rollback target.

## 4. Frozen React → Streamlit rollback mapping

| React entry | Streamlit identity | Exact rollback deep link | Group |
|---|---|---|---|
| `ui-react:#order-tracker` | `ui:05_form_management.py` | `/?entry=form-management&view=order-tracker` | order-workbench |
| `ui-react:#orders` | `ui:02_orders.py` | `/?entry=orders` | orders |
| `ui-react:#scheduling` | `ui:03_calendar.py` | `/?entry=scheduling&view=calendar` | staff-scheduling |
| `ui-react:#staff` | `ui:03_calendar.py` | `/?entry=scheduling&view=staff-directory` | staff-scheduling |
| `ui-react:#data-import` | `ui:09_data_import.py` | `/?entry=data-import` | data-import |
| `ui-react:#line-management` | `ui:07_line_management.py` | `/?entry=line-management` | line |
| `ui-react:#reports` | `ui:08_system_status.py` | `/?entry=system-status&view=reports` | reports-system |
| `ui-react:#finance` | `ui:04_finance.py` | `/?entry=finance` | finance |
| `ui-react:#anomalies` | `ui:06_finance_alerts.py` | `/?entry=anomalies` | anomalies |
| `ui-react:#data-browser` | `ui:01_data_browser.py` | `/?entry=data-browser` | data-browser |
| `ui-react:#account-management` | `ui:09_access_management.py` | `/?entry=access-management` | access |

This mapping is a rollback contract, not replacement approval. A later per-entry package may refine a fixed subview
only with an exact amendment; arbitrary query passthrough is forbidden.

## 5. Deep-link validation

The Streamlit shell accepts only templates in the frozen mapping. Validation rules:

- exactly one scalar lower-case `entry` value;
- `view` is absent unless the selected mapping declares one, then it must equal the exact declared scalar;
- no other query keys, duplicates, multi-values, blank, case drift, fragment payload, token, case number or PII;
- resolver maps a fixed identity to `PAGE_REGISTRY` module plus optional fixed session-state subview;
- unknown/malformed input fails closed to login/safe default without loading a business page;
- unauthenticated input is retained only in sanitized internal navigation state and applied after successful login;
- sidebar navigation updates/clears the deep link so an old rollback query cannot override a later user choice.

Tests assert the actual loaded module identity and, for the shared calendar module, the exact fixed subview. Checking
only page title or port 8501 is insufficient.

## 6. Queue/discovery contract

- Independent expected inventory contains exactly 10 Streamlit + 11 React UI identities.
- Streamlit entries retain their current disposition; discovery does not reclassify them.
- React entries start `review_required`, preserve both App and NAV witnesses, and cannot be auto-promoted to
  `active`, `replacement`, `cutover-ready` or `retired`.
- Generator adds missing `ui:09_data_import.py` from runtime registry discovery.
- Existing API/CLI rows and unrelated drift are preserved byte-for-byte/semantically merged; Phase 5A does not need
  to close all non-UI queue drift to establish UI inventory.
- An already reviewed row cannot overwrite canonical `entry_id`, kind or source; source disappearance remains
  `review_required` with `review_reason: source_drift` and original witnesses.
- Queue count is an observed result, not a hard-coded acceptance number; fresh unrelated entry discovery is reported,
  not silently deleted or absorbed.

## 7. Verification ceiling

Phase 5A foundation acceptance proves:

1. 10 Streamlit + 11 React identities are independently discoverable and non-duplicated;
2. Data Import is included;
3. Staff/Scheduling one-to-many group and all 11 fixed rollback links validate;
4. malformed/prototype/secret-bearing routes fail closed;
5. no navigation switch, replacement receipt or retirement is produced.

It does not require any page's API contract, mutation Scenario, DB engine, production hosting or browser business data
to PASS. Real browser evidence, when available, validates shell routing only—not business-page completion.

## 8. Out of scope

Any React/Streamlit business page edit, backend/domain/API/DB, package/lockfile, CORS/hosting/deployment, launcher,
navigation switch, dual-run, mutation, cutover, retirement, or claim that a page is production-ready.

## 9. DB gate

| Gate | Status | Reason |
|---|---|---|
| Scope | `PASS` | docs/registry/rollback foundation; 0 DB |
| Change inventory | `PASS` | schema/seed/backfill/destructive all zero |
| Static release | `NOT_RUN` | no release |
| Descriptor | `NOT_RUN` | no DB object |
| Read-only plan | `NOT_RUN` | no migration |
| Engine verification | `NOT_RUN` | not a DB task |
| Developer acceptance | `NOT_RUN` | no DB operation |

Conclusion: `DB_CHANGE_NOT_READY`; this does not block the entry inventory/rollback foundation.
