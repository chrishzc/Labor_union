# Field Authority Live Audit — 2026-08-10

## Scope and method

- Scope: the database tables and fields listed under
  `document/文件整併工作區/06_欄位權威性與計算邏輯盤點`.
- Evidence: version-controlled schema and source references, plus read-only
  `information_schema` queries against the configured candidate database
  `union_db_candidate_20260803_v5`.
- This record does not authorize a migration, data mutation, or retirement.

## Coverage baseline

- The inventory contains 58 table documents.  Six names have no corresponding
  live base table: `audit_logs`, `client_payment_transaction_adjustment_allocations`,
  `crawler_logs`, `faq`, `finance_import_reclassification_events`, and
  `staff_availability`.
- The candidate database also has live base tables without matching inventory
  documents.  They include current Orders, Client Finance, Payroll, Scheduling,
  Anomalies, background-job, outbox, receipt, and event tables.  The inventory
  is therefore not sufficient evidence that every live field has been audited.

## Confirmed field findings

### `orders.contract_id` → `orders.contract_identity`

- **Live schema / database objects:** no live column, view, or routine references
  the exact legacy `contract_id` name.
- **Replacement:** `orders.contract_identity` is live and is referenced by the
  canonical `v_order_details` view, order-detail projection, contract context,
  and contract-completion workflow.
- **Remaining source references:** the only production-code occurrences are the
  explicitly named legacy migration `scripts/migrate_order_contract_identity.py`.
- **Documentation drift:** the following documents still describe
  `orders.contract_id` as a current field and must be corrected before they are
  treated as architecture evidence:
  - `document/文件整併工作區/06_欄位權威性與計算邏輯盤點/01_客戶與訂單生命週期/orders.md`
  - `document/管理端UI/系統異常警示中心規格書.md`
  - `document/文件整併工作區/01_管理端UI與排班_無損合併稿.md`

### `subsidy_eligibility`

- **Live schema:** no such column exists in the candidate database.
- **Residual writer:** `scripts/generate_fake_data.py` still includes
  `UPDATE orders SET subsidy_eligibility = %s`; running it against the current
  candidate schema will fail with an unknown-column error.
- **Replacement direction:** the project documents and current schema use
  `clients.identity_status` with a controlled policy mapping; the residual
  generator has not been migrated to that model.

## Inventory-to-schema drift

- `orders`: inventory lists legacy `contract_id`; live schema has
  `contract_identity`.
- `financial_adjustments` and `financial_adjustment_staff_allocations`: inventory
  lists `amount_delta`; live schema has `amount_delta_ntd`.
- `staff_actual_transfers` and `staff_monthly_settlement_details`: inventory lists
  columns absent from the candidate database.
- Several inventory records omit live columns, including records for
  `assignment_schedule_leave_substitution_events`, `case_staff_assignments`,
  `finance_alert_events`, `finance_alerts`, `staff_schedule`, and
  `system_alerts`.

### Interpretation of the first schema differences

- `financial_adjustments.amount_delta` and
  `financial_adjustment_staff_allocations.amount_delta` are documented as
  proposed semantic field names.  The live canonical columns are the integer
  NTD names `amount_delta_ntd`; API schemas and the MySQL repository use those
  names.  The inventory must be updated to distinguish its proposal text from
  the live contract.
- `staff_monthly_settlement_details.financial_adjustment_staff_allocation_id`
  and `staff_actual_transfers.finance_import_row_id` are explicitly marked as
  proposed additions in their inventory documents.  They are not missing
  migrations proven by this audit; they are unimplemented design decisions and
  must not be presented as current schema.

### `clients.service_time` / `orders.service_hours_per_day`

- The current HCM import adapter does not derive hours by taking the first
  number in a free-form string.  It requires an explicit hours token and
  exactly two clock values, then persists typed Order terms through the case
  import workflow.
- The raw-data Browser still visually marks `clients.service_time`,
  `service_days`, `service_start_date`, and `service_type` as editable.  Its
  supported server-side source-correction whitelist rejects those fields, and
  the legacy direct PATCH route is retired.  This is a UI-permission metadata
  drift: the Browser can offer an edit that the owning Orders command boundary
  will not accept.

## Database-object integrity sweep

- The candidate database currently exposes one view, `v_order_details`.  A
  read-only `SELECT 1 FROM v_order_details LIMIT 0` succeeds after the
  `contract_identity` migration and view rebuild.
- No trigger refers to either exact legacy name `contract_id` or
  `subsidy_eligibility`.

## Classification note

The terms `legacy`, `已退役`, and `長期考慮移除` in the inventory cannot by
themselves prove a column should be removed.  For example,
`finance_import_reprocess_runs.changed_count` and `request_summary` are live,
immutable historical-run receipts; the document’s reference to retirement is
about an older event model, not those current columns.  Every finding must be
classified by its table-qualified name, authoritative owner, and live call
chain.

## Grep-first retirement sweep

The first pass searches the whole repository, including Python, SQL, migrations,
tests, and documents. A hit is then classified; a name is not removable merely
because it contains `legacy` or is documented as a future retirement candidate.

### Retired staff-profile fields still drive live behaviour

The inventory says `staff.weekly_rest_days`, `care_babies`,
`service_regions`, and `special_skills` are redundant and that the corresponding
1:N tables are their SSOT. Grep confirms that retirement has not happened:

- `infrastructure/mysql/matching_recommendation_repository.py` selects
  `care_babies` for candidate eligibility, while only regions come from
  `staff_regions`.
- `infrastructure/mysql/mysql_adapter.py` merges `staff.service_regions` with
  `staff_regions`, and rejects twin cases based on `care_babies`.
- `infrastructure/mysql/matching_notification_repository.py` and
  `subsystems/scheduling/matching_line_cards.py` render the old fields.
- `infrastructure/mysql/admin_command_repository.py`,
  `subsystems/access/source_data_correction.py`, and the Data Browser still
  permit editing the legacy fields.

This is an execution/SSOT conflict, not merely stale prose. The required next
check is to trace each replacement child table through import, correction,
matching, notification, and presentation before designing a cutover.

### Retired tables clean in production source

No non-test production reader or writer was found for `audit_logs`,
`crawler_logs`, `faq`, or `staff_availability`; remaining hits are retirement
comments and the existing governance-report generator. This is consistent with
their documented retired status.

## Orders-domain baseline drift

Read-only `information_schema.columns` inspection of the candidate `orders`
table returned the four current columns `staff_payment_due_date`,
`service_start_time`, `service_end_time`, and `service_end_day_offset` in
addition to the base `db/schema.sql` columns. The last three are supplied by
`db/schema_parts/105_order_service_time_terms.sql`; the due date is introduced
by `db/schema_parts/110_order_terms_workflow.sql`.

`db/schema.sql` itself is a database-rebuild baseline but does not declare any
of these four columns. Consequently, rebuilding from that file without the
ordered schema-part release sequence produces a database incompatible with
current repositories, including `infrastructure/mysql/order_terms_read_model.py`,
`infrastructure/mysql/order_auto_completion_job_repository.py`, and payroll
repositories.

The inventory additionally says `orders.staff_payment_due_date` is absent and
only proposed, while the configured candidate has the column and production
repositories read it. This is documented-current-state drift, not an approved
reason to remove the live column.

The service-time terms have a complete call chain: case import persists them,
the terms read/write model and lifecycle command envelope validate/read them,
and the auto-completion job uses end time plus day offset. Their presence in the
candidate is therefore required by current behaviour.

### Broken legacy matching-recommendation reader

The registered route `GET /api/v1/matches/recommend-staff` calls
`subsystems/scheduling/matching_recommendation_application.py`, whose MySQL
repository selects `orders.planned_start_date` and `orders.planned_end_date`.
Neither column exists in the configured candidate. A read-only invocation of
`load_request_facts('115000001')` reproduced
`OperationalError (1054, "Unknown column 'o.planned_start_date' in 'field list'")`.
The route catches this as an internal query error, so clients receive a generic
500 rather than a typed retired-route response. No current Streamlit caller was
found, but the registered API remains callable and must either be migrated to
the agreed planned-date fields or explicitly retired with a replacement route.

### `matching_records` is not yet historical-only

The inventory marks `matching_records` as replaced by matching plans and
events. Its writer route is correctly retired (HTTP 410), but two live readers
remain: `GET /api/v1/orders/{case_no}/matches` returns the old record shape and
the anomaly outbox source joins `matching_records` to determine unfinished
information/resume reminders. The latter means the table still affects active
alerts. It cannot be dropped or treated as read-only archival data until those
read paths are explicitly migrated to matching-plan events or retired.

`staff_bookings` is different: the production-source sweep found only raw Data
Browser access and migration/fixture support, not a current business reader or
writer. Its removal still requires data-retention review, but it does not have
the same active-process dependency found for `matching_records`.

## Staff-profile replacement-chain audit

The replacement tables `staff_regions`, `staff_time_slots`,
`staff_cooking_skills`, `staff_weekly_rest`, and `staff_baby_types` are written
by `scripts/imports/import_staff_beclass.py` and read for Data Browser display.
Static production-source search found no canonical matching-plan or assignment
workflow that consumes cooking skills, weekly-rest options, or baby types.

The only recommendation query that reads `staff_regions` and `staff_time_slots`
is the already broken legacy `/matches/recommend-staff` path. It still reads
`staff.care_babies` rather than `staff_baby_types`, and it does not consult
`staff_cooking_skills` or `staff_weekly_rest`. The older
`mysql_adapter.get_recommended_staff_for_order` also merges legacy JSON regions
and uses `care_babies` as an eligibility filter.

Therefore the child tables are currently an imported/displayed capability
catalogue, not the effective matching SSOT asserted by the inventory. Removing
the legacy staff fields before migrating a live matching-plan reader would lose
existing behaviour; retaining them without a clear authority boundary continues
to allow conflicting edits.

## Payroll-transfer historical compatibility audit

For the inventory candidates in `staff_actual_transfers`, source search found
no current production writer for `payment_phase`, `source_bank`,
`source_account`, `external_reference`, or `review_status`; the only concrete
writer found is fake-data generation. This supports their classification as
historical compatibility fields, subject to database retention review.

`raw_import_reference` is an exception: the Finance Import reprocessing safety
check queries `staff_actual_transfers` for the canonical string
`finance_import_row:{row_id}` before it allows a reprocess. It prevents
reclassification of an import row that already has a formal staff transfer.
The field is still an active guard despite being documented as a future
replacement candidate; it must not be removed until the proposed direct
`finance_import_row_id` relation exists and this guard has moved to it.

## Lifecycle event and control-table audit

The lifecycle inventory contains many `長期考慮移除` classifications. They are
not presently unused fields:

- `order_lifecycle_state_events.before_status`, `business_date`, and
  `facts_snapshot` are written by cancellation, contract completion, reopen,
  auto-completion, and impact writers. The command envelope reads the event by
  idempotency key to validate replay.
- `order_lifecycle_control_events.payload_hash` and `payload_snapshot` are
  compared during idempotent replay. The typed command boundary rejects a
  payload mismatch; removal would require a replacement replay representation,
  not a simple schema deletion.
- `order_lifecycle_control_state.control_key`, `scope`, `state`, and
  `current_event_id` are loaded under lock for lifecycle evaluation and are
  joined to control events by the actual-start, reopen, and auto-completion
  workflows. The remaining duplicated projections (`reason`, `changed_by`,
  `changed_at`, etc.) may be candidates for later normalization, but are still
  written and validated as a coherent current-state record.

Accordingly, the inventory labels are future design intent, not evidence of
dead production columns. Any retirement needs a full event/replay migration
and an invariant-preserving replacement for the locked current-state query.

## Financial-adjustment naming and amount-chain audit

The `financial_adjustments.md` and
`financial_adjustment_staff_allocations.md` inventory documents describe
proposed `amount_delta` DECIMAL columns as `待建`. The live schema instead has
`amount_delta_ntd BIGINT NOT NULL` in both tables. This is not a missing
migration: `api/schemas/financial_adjustment.py` accepts and validates the NTD
integer field, the domain wraps it in `MoneyNTD`, and
`infrastructure/mysql/financial_adjustment_repository.py` writes and reads the
same name.

The live API validates that the sum of assignment allocation
`amount_delta_ntd` values equals the parent adjustment amount, while the domain
applies the same equality invariant using `MoneyNTD.amount`. Thus the current
call chain is unit-consistent. The drift is documentary: the proposal must be
clearly separated from the implemented integer-NTD contract so future readers
do not attempt an incompatible DECIMAL migration.

## Rebuild-baseline sweep beyond `orders`

Comparing candidate `information_schema.columns` with the table declarations
in `db/schema.sql` found additional live-only columns:

| Table | Live-only relative to `db/schema.sql` | Current evidence |
|---|---|---|
| `case_staff_assignments` | `candidate_key`, `generation_id` | scheduling generation and leave-substitution domain identity/lineage |
| `client_payment_transactions` | `finance_import_row_id` | client-finance ledger schema part and reconciliation relation |
| `staff_schedule` | `assignment_id`, `effective_marker`, `generation_id` | scheduling generation/current-projection API and calendar queries |
| `system_alerts` | `description`, `event_type` | legacy alert-to-current-projection migration compatibility |

All have matching schema-part definitions and active code references. They are
not unknown live drift, but `db/schema.sql` alone is not a sufficient rebuild
manifest. A fresh database built only from it will omit active scheduling,
finance, and alert columns. Release/rebuild documentation must specify the
ordered schema-part manifest as the authoritative bootstrap path.

## Missing-column static SQL sweep

The legacy terms `planned_start_date` and `planned_end_date` remain valid
*domain/API names*: current terms and availability readers correctly map them
to `orders.start_date` and `orders.end_date`. The only SQL source that treats
them as physical `orders` columns is the already reproduced broken
`matching_recommendation_repository` query.

The sweep also reconfirmed that exact `contract_id` production use is confined
to the one-time retirement migration. Remaining non-migration occurrences are
historical documentation and migration tests. `subsidy_eligibility` has one
unsafe executable residue in `scripts/generate_fake_data.py`; no current
database object or production request path uses it.

## Staff-payment compatibility projection audit

`staff_payments.amount_paid`, `due_date`, `paid_at`, and `payment_status` are
not independent financial SSOTs, but they remain active compatibility reads.
The `/api/v1/staff-payments` routes return `SELECT *`, the Order Finance UI
renders these fields, and scheduling/assignment queries use
`payment_status <> 'cancelled'` as a guard. They cannot be removed until those
API/UI/query consumers move to the formal obligation and payout event model.

The inventory's `staff_payments.notes` row says the field is always NULL and
has no writer. Read-only candidate evidence contradicts that statement: all 33
current rows have a non-empty `notes` value. The source is the candidate's
fixture generator: `scripts/generate_fake_data.py` inserts the literal
`fixture assignment payable`. This confirms the field has no current business
writer, but candidate data cannot prove it is production-empty. A retirement
decision still needs a production-data retention check rather than relying on
the fixture-derived candidate count.

## `finance_alerts` replacement drift

The `finance_alerts` inventory describes a live human-in-the-loop finance task
table, but the current Alert Center UI explicitly uses the canonical
`/api/v1/anomalies` registry and says `/api/v1/finance-alerts` is retired and
unmounted. Repository/source search found no production reader or writer for
either `finance_alerts` or `finance_alert_events`; `db/schema_parts/90` is the
remaining schema definition.

The candidate contains both tables but has zero alert rows and zero event rows.
`source_*` in the inventory is descriptive shorthand, not a literal missing
column: the live legacy table defines `source_domain`, `source_type`, and
`source_id`. The actual issue is that the inventory has not been updated to
state that the table is superseded by the anomaly registry. It must not be
removed without production retention evidence, but it has no identified
current-call-chain dependency in this repository.

`system_alerts` must not be conflated with `finance_alerts`: it is an active
rolling process-reminder projection. `subsystems/anomalies/system_alert_projection.py`
owns inserts, updates, query, claim, resolve, and cleanup. The candidate has
111 open rows. Its legacy `event_type` and `description` compatibility columns
are migration concerns, but the table itself is a live current-state reader and
writer dependency.

Read-only data evidence shows all 111 candidate `system_alerts` rows have NULL/
empty `event_type` and `description`, and the current projection source does
not select or write those fields. Thus the two columns are separable
compatibility-retirement candidates even though the enclosing table is active.

## Coverage status

This is an in-progress full audit, not a completion claim. Deep evidence chains
have been collected for Orders/Lifecycle, Staff profile and Scheduling legacy
paths, Client Finance adjustments and migration reviews, Payroll compatibility
projections, Finance Import legacy links, and the legacy/current alert split.
The remaining inventory domains still require the same table-qualified review
of Government Subsidy, LINE/media, Access/administration, Knowledge retrieval,
and the non-retirement current fields in the remaining scheduling and finance
tables. The risk list is therefore prioritized, not exhaustive.

## Government Subsidy initial chain check

`subsidy_claim_batches`, `subsidy_claim_batch_items`,
`government_subsidy_transactions`, and `government_subsidy_allocations` have
active repository writers/readers and multiple anomaly/reversal consumers.
The configured candidate has zero rows in all four, so it cannot provide
runtime-data evidence for their calculation invariants; nevertheless, they are
not unreferenced schema. No immediate field-name/schema mismatch was found in
this initial static chain pass. Detailed value/invariant validation remains
pending until representative non-fixture subsidy data or dedicated integration
fixtures are available.

## Payment-migration review table audit

`payment_migration_reviews` has no domain/API writer or reader in the current
source tree. Remaining references are the raw Data Browser, its generic table
adapter, API contract smoke inventory, and base schema. The configured candidate
contains zero rows. This supports its documentation as a completed historical
migration review mechanism; it needs only production retention confirmation
before a future drop, rather than an application-call-chain migration.

`client_payment_transaction_adjustment_allocations` is different: its inventory
document explicitly marks it as `待建`, and no live base table is expected. It
must not be reported as a missing migration until its proposed Client Finance
design receives implementation approval. `finance_import_reclassification_events`
is a true retired table: it is absent from the candidate, the release has an
explicit retirement DDL, and current documents name the replacement
classification events and reprocess receipts. Remaining hits are historical
documents and preservation/migration metadata.

## Prioritized evidence-backed risk list

1. **P0 — active request failure:** `/api/v1/matches/recommend-staff` queries
   non-existent physical `orders.planned_start_date/planned_end_date` and
   reproducibly raises MySQL 1054.
2. **P0 — deployment/rebuild inconsistency:** `db/schema.sql` omits active
   schema-part columns, including order service terms and scheduling/finance
   generation relations. Rebuilding from it alone yields an incompatible DB.
3. **P1 — competing staff-profile authority:** legacy `staff` JSON/value
   fields remain editable and affect matching while their intended child-table
   replacements are not consumed by canonical matching-plan workflows.
4. **P1 — unsafe obsolete writer:** fake-data generation writes removed
   `orders.subsidy_eligibility`, which fails against the current schema.
5. **P1 — migration sequencing hazard already observed:** a contract-column
   rename invalidates `v_order_details` unless its dependent view is rebuilt in
   the same migration unit.
6. **P2 — documentation/current-state drift:** `contract_id`, proposed
   `amount_delta`, absent `staff_payment_due_date`, and active/retired alert
   table descriptions conflict with the candidate and source evidence.
7. **P2 — deferred retirement work:** `matching_records` still has active data
   and readers; `staff_bookings`, `payment_migration_reviews`, and
   `finance_alerts` are candidate-empty/no-current-call-chain tables but require
   production-data retention evidence before destructive cleanup.

## `actual_hours_adjustments` audit

The candidate table is empty and has no current writer, but it is not fully
disconnected: `subsystems/scheduling/assignment_schedule_query.py` reads the
table to include historical actual-hours adjustments in assignment schedule
views. The Data Browser also exposes it read-only. It is a compatibility reader
dependency rather than an active write model; removal requires migrating that
historical schedule query or deliberately dropping the history from its output.

## Monthly-settlement legacy subsidy fields

Source search found `legacy_subsidy_payable` and `legacy_subsidy_status` only
in `scripts/generate_fake_data.py`, not in current API/domain/repository paths.
The candidate has 18 settlement-detail rows, with three non-zero legacy subsidy
amounts and matching non-`not_applicable` statuses; the same fixture generator
creates those values. They are correctly classified as historical compatibility
data, but test/candidate data deliberately exercises the old branch. No current
business code should be inferred from their non-zero presence.

The candidate has 18 `staff_actual_transfers`, all linked through
`raw_import_reference` and all in the normal `payment_phase`. This reinforces
the reprocess safety dependency: although the phase is historical compatibility,
the raw string relation is not empty historical debris and must be replaced by a
direct relation before retirement.

## Client legacy identity and sensitive-source fields

`clients.line_id` and `clients.ip_address` are still accepted by the Case Import
model and displayed by Data Browser/Form Management, but source search found no
current LINE integration workflow that consumes `clients.line_id`. The candidate
has 53 clients: 50 with legacy `line_id`, 50 with source `ip_address`, and zero
with `line_user_id`. This demonstrates that migration to the canonical LINE
platform identity is incomplete for the candidate dataset; `line_id` cannot be
silently repurposed as `line_user_id`. It should remain a historical source
snapshot until an explicit identity-link review/migration is completed.

The `clients.ip_address` field is likewise an imported historical source fact,
not the admin-session audit IP used by security workflows. Its Data Browser
exposure is a privacy/retention concern, but no current business calculation
uses it.

### Static no-production-hit candidate subset

A word-boundary scan across `api`, `domains`, `infrastructure`, `subsystems`,
`ui`, and `line` found no production-code occurrence of
`staff_actual_transfers.payment_phase`, `source_bank`, `source_account`, or
`staff_monthly_settlement_details.legacy_subsidy_payable`,
`legacy_subsidy_status`, and `review_note`. Their remaining uses are schema,
fixtures, and historical data. This is stronger retirement evidence than their
labels alone, but removal still requires a table-qualified production data and
backward-compatibility review.

## `staff_bookings` retired-table verification

The configured candidate contains zero `staff_bookings` rows. The full source
sweep finds only raw Data Browser presentation, its generic table adapter, and
the API smoke inventory; there is no current business reader or writer. This
confirms the inventory's retirement direction for this table. As with other
empty candidate tables, a destructive drop remains subject to production data
retention verification.

In contrast, `matching_records` contains 22 candidate rows, 14 of which have
no caregiver response. Together with its legacy-history API and process-reminder
anomaly reader, this is concrete evidence that the table remains operationally
relevant despite new writes being retired. It needs a data and reader migration
to matching-plan events before it can join the retired-table set.

## LINE rich menu / media: active chain, but current-version scope conflicts with the authority document

The candidate has two `line_rich_menu_publications` rows and zero `media_assets`
rows. This is an active persisted workflow, not a removable legacy table: the
UI manager calls the typed LINE client, which calls `api/routes/line_rich_menus.py`,
then `subsystems/line/rich_menu_publication_workflow.py`. Uploaded/generated
images follow the same route into `subsystems/line/media_archive.py` and
`media_assets`.

The implementation atomically reads and clears the current record with
`WHERE menu_config_id=%s` (`rich_menu_publication_workflow.py:620-634`). The
authority inventory for `line_rich_menu_publications` instead records the
approved scope as one current publication per `audience_role`, and explicitly
identifies the implementation as able to leave multiple current records for one
role. Therefore two configurations sharing a role can both remain
`is_current=TRUE`; the following publication can get its previous-menu link
from the wrong version chain. The inventory defers its final LINE behavior
decision until the external API is connected and tested, so this audit records
the mismatch without changing it. The zero media count is environment state,
not retirement evidence, because its archive/write and read/delete paths are
present.

## Administration/audit and retired knowledge tables

`admin_users`, `admin_sessions`, and `admin_audit_logs` are active access-domain
SSOT tables. Their live candidate counts are respectively `0`, `0`, and `699`;
the empty user/session counts are environment state rather than retirement
evidence. Authentication creates and revokes sessions in
`subsystems/access/authentication_session.py`, capability grants revoke the
affected sessions in `infrastructure/mysql/admin_capability_grant_repository.py`,
and the request audit projection writes/queries `admin_audit_logs` through the
access subsystem. This is a complete, non-generic business chain.

The retired inventory is corroborated for the similarly named but distinct
`audit_logs`, `crawler_logs`, and `faq`: all three base tables are absent from
the configured candidate and have no production caller in `api`, `domains`,
`infrastructure`, `subsystems`, or `ui`. This avoids a false conclusion that
the actively used `admin_audit_logs` table was retired merely because the old
generic `audit_logs` name was removed.

## LINE task inventory is split between an obsolete queue shape and the canonical delivery aggregate

All five candidate tables named by the older LINE inventory are present but
empty: `line_confirmation_requests`, `line_tasks`, `line_task_attempts`,
`line_users`, and `line_webhook_events`. Identity confirmation, user lifecycle,
and webhook handling still directly use the first, fourth, and fifth tables;
their empty counts cannot establish retirement.

There is, however, a material task-model drift. `api/routes/line_tasks.py` and
the UI task manager use the typed `LineDeliveryTask` application/domain model,
whereas the older `subsystems/line/delivery_task_workflow.py` still inserts the
legacy `line_tasks` row shape. A complete source scan found no runtime writer
or reader for `line_task_attempts`, despite its inventory defining it as the
attempt-event authority. Before enabling external LINE delivery, the team must
choose one task/attempt model and either migrate the legacy enqueue path or
restore an explicit writer/reader contract for the table. Otherwise the task
management UI can report a different queue from the producer.

### Candidate schema deployment gap: canonical LINE delivery tables are missing

The above drift is immediately executable: the task-management API's repository
queries `line_delivery_tasks` and `line_delivery_attempt_events`
(`infrastructure/mysql/line_delivery_task_repository.py:600-630`), both
introduced by `db/schema_parts/154_line_integration_inbox_delivery.sql`.
Against `union_db_candidate_20260803_v5`, a read-only `SELECT COUNT(*) FROM
line_delivery_tasks` fails with MySQL `1146` (table does not exist), while the
old `line_tasks`/`line_task_attempts` tables still exist. This is the same class
of schema/application release skew as the earlier order-view failure: enabling
or visiting the canonical task-management query will return a database error.
No migration was applied in this audit; any repair must first decide how to
preserve/migrate the legacy queue and attempts.

## Systematic schema-part baseline comparison: candidate is materially behind the versioned runtime model

A read-only parser collected all `CREATE TABLE` names from `db/schema.sql` and
every `db/schema_parts/*.sql`, then compared that 212-table set with the 152
base tables in the configured candidate's `information_schema`. The candidate
is missing **60** versioned tables (and has no untracked extra base table).
Of the 60, **59 are referenced by current Python source** in `api`, `domains`,
`infrastructure`, `subsystems`, `ui`, or `scripts`; this is not an inventory of
unused future proposals.

The missing, currently referenced groups are:

- access and idempotency: `admin_capability_grants`, `admin_command_receipts`,
  `access_control_events`, `access_control_apply_receipts`;
- knowledge runtime: `knowledge_items`, `knowledge_item_versions`,
  `knowledge_item_events`, `knowledge_indexes`, `knowledge_jobs`,
  `knowledge_answer_requests`, `knowledge_answer_sources`,
  `knowledge_answer_receipts`, `knowledge_apply_receipts`;
- canonical LINE runtime: `line_delivery_tasks`,
  `line_delivery_attempt_events`, `line_inbox_events`,
  `line_platform_users`, `line_identity_*`, `line_order_group_*`,
  `line_configuration_*`, `line_domain_*`, `line_worker_heartbeats`,
  `line_rich_menu_publication_tasks`, `line_rich_menu_publish_previews`, and
  their receipt/audit/outbox tables;
- matching notification/response integration: `matching_notification_intents`,
  `matching_response_events`, `matching_line_interactions`;
- review, import, financial return/recovery, auto-completion, and provisional
  registration receipts/events listed in the reproducible command output.

This comparison detects deployment status, not permission to bulk-apply every
schema part: several parts contain data backfills or migrations and must be
reviewed in dependency order. It nevertheless establishes a release gate: code
paths that use any of these canonical tables need a candidate schema bootstrap
or an explicit compatibility adapter before being treated as available.

### Concrete callers affected by the missing-table baseline

- The registered knowledge routes (`api/routes/knowledge_retrieval.py`) delegate
  to `infrastructure/mysql/knowledge_retrieval_repository.py`, which performs
  reads/writes across the missing `knowledge_items`, versions, events, indexes,
  jobs, answer requests/sources/receipts, and apply-receipt tables. The whole
  knowledge runtime is therefore unavailable on the candidate, not merely one
  optional index field.
- Capability-aware authentication and the administrative capability command
  paths query missing `admin_capability_grants`, `admin_command_receipts`,
  `access_control_events`, and `access_control_apply_receipts`. Depending on
  whether a login/action reaches the capability lookup, this can turn a normal
  authorization request into a database error. It must be validated after the
  dependency-ordered schema deployment, not hidden with a fallback that would
bypass access-control SSOT.

The authority inventory itself has not caught up with the new knowledge
runtime: its `10_知識與擷取紀錄` directory contains only the retired
`crawler_logs` and `faq` records, while the nine live knowledge-table contracts
above have no per-table/field inventory document. This is a documentation
coverage failure, so a claim that every knowledge field has been reviewed would
currently be false even before deployment is repaired.

Across the entire authority-inventory directory, there are 69 Markdown files
but only 63 filenames exactly matching a versioned database table. The current
212-table schema set therefore has **149 tables without an exact per-table
inventory document**. These are predominantly the newer event, receipt,
outbox, projection, control-state, scheduling, payroll, access, LINE, and
knowledge tables. The gap means the requested field-by-field audit cannot be
claimed complete from the existing documents; the remaining review must derive
each such table's fields and caller chain from the schema and code, then either
add its inventory record or explicitly classify it as a migration/retention
artifact.

## Mechanical inventory-field versus candidate-column sweep

For every inventory document whose filename maps to a candidate base table, a
read-only parser extracted backticked first-column field names and compared them
with `information_schema.columns`. It found only five documented-but-absent
fields: `orders.contract_id`, `financial_adjustments.amount_delta`,
`financial_adjustment_staff_allocations.amount_delta`,
`staff_actual_transfers.finance_import_row_id`, and
`staff_monthly_settlement_details.financial_adjustment_staff_allocation_id`.

Classification matters: `orders.contract_id` is the genuine retired-name
documentation residue; the candidate and live repositories now use
`contract_identity`. The other four are explicitly labelled proposal/待建 in
their own inventory documents. Their current implementations use the deployed
integer-currency names `amount_delta_ntd`, or retain historical string raw-link
fields pending an approved direct-FK migration. They are design-versus-runtime
gaps, not a missing migration that may be applied implicitly. This sweep gives
a reproducible guard against treating future design columns as current schema
or, conversely, overlooking a true stale old-field reference.

The reverse sweep (candidate columns absent from the corresponding inventory
field table) identified documented-table coverage gaps as well. Confirmed
important examples are: `orders.contract_identity` and
`staff_payment_due_date`; scheduling runtime keys
`case_staff_assignments.candidate_key/generation_id` and
`staff_schedule.effective_marker/generation_id`; and the canonical
integer-money/identity fields on `financial_adjustments` and its allocations
(`amount_delta_ntd`, `adjustment_identity`, `adjustment_scope`, and
`source_event_identity`). These are not safely ignorable unnamed columns: the
repositories use them in current workflows.

Other omissions require field-level classification before changing documents:
government claim/transaction audit and idempotency fields, active finance-alert
projection fields, and active access/LINE metadata are not all represented in
the old table sheets. Conversely, `system_alerts.event_type` and `description`
are the already identified empty historical fields, so their absence from the
current projection document supports retirement review rather than a missing
runtime deployment. The raw reverse-sweep also exposes old LINE table sheets
whose legacy queue fields differ wholesale from the canonical delivery model;
that is recorded above as a model migration, not a field-by-field rename.

### Scheduling fields omitted from the inventory are active control data

`case_staff_assignments.candidate_key/generation_id` and
`staff_schedule.effective_marker/generation_id` are not decorative migration
columns. Candidate data has 35 populated assignment keys/generations out of 36
rows, and 764 populated schedule effective markers with 739 generation IDs.
The scheduling bootstrap writer assigns them, current-projection repositories
read them, and payroll, order completion, subsidy, leave-substitution, and
anomaly queries rely on their generation/effective semantics. Removing or
rebuilding these fields from the old inventory would break the current
projection SSOT.

`assignment_schedule_leave_substitution_events.batch_key` and
`batch_item_index` are likewise active idempotency/event-design fields in the
leave-substitution workflow and repository, even though this candidate has no
event rows. They must be documented as command-batch identity/order fields,
not classified as unused just because their current candidate count is zero.

## Financial-adjustment / subsidy field chain

The deployed financial-adjustment tables intentionally use immutable integer
NTD values (`amount_delta_ntd`) plus adjustment identity/scope/source fields,
as defined in `db/schema_parts/133_financial_adjustments.sql` and used by
`infrastructure/mysql/financial_adjustment_repository.py`. The inventory's
`amount_delta` is explicitly a pre-implementation DECIMAL proposal, so it is
not a candidate-column defect. The candidate currently has zero adjustment and
government-subsidy transaction/allocation/claim rows; their repositories and
the finance-import/anomaly safeguards nevertheless form active source chains.

There is an actual API/UI coverage gap: `api/routes/financial_adjustment.py`
registers typed query, preview, apply, cancel, and reversal endpoints, but a
source sweep found no Streamlit API client or page caller for
`financial-adjustment` / `financial_adjustment`. Thus the feature is exposed
to authenticated API consumers but is not reachable from the current admin UI.
This is a presentation-boundary omission, not evidence that the underlying
money or idempotency fields are unused.

## Database-object sweep: trigger protection is deployed only with its underlying schema generation

The candidate has one view, `v_order_details`; its read was previously verified
after the contract-identity repair. The versioned SQL defines no stored
procedure/function. A mechanical trigger-name comparison found the candidate
has the older trigger set but is missing the trigger pairs for the same missing
new-generation tables: knowledge, canonical LINE, BeClass review, historical
reprocess, return/recovery, matching response, and order auto-completion
receipts/events. This is expected from the missing-table baseline, but it has a
separate business consequence: even if a missing table were manually created,
its append-only / anti-update / anti-delete invariants would remain absent
until the corresponding trigger part is installed. Schema repair therefore
must verify tables and protection triggers as one dependency unit.

### Reproducible candidate-missing table appendix

The following table is generated by comparing all versioned `CREATE TABLE`
names to candidate `information_schema.tables`; the second number is exact
word-boundary source occurrence count across current Python source roots.

| Missing candidate table | Current source occurrences |
|---|---:|
| `access_control_apply_receipts` | 2 |
| `access_control_events` | 1 |
| `admin_audit_log_archive` | 1 |
| `admin_capability_grants` | 5 |
| `admin_command_receipts` | 2 |
| `beclass_import_review_events` | 3 |
| `beclass_import_review_outbox` | 4 |
| `beclass_import_review_receipts` | 2 |
| `beclass_import_review_rows` | 4 |
| `client_deposit_reversal_apply_receipts` | 2 |
| `client_refund_return_review_events` | 1 |
| `client_refund_return_review_receipts` | 2 |
| `client_subsidy_advance_recoveries` | 4 |
| `client_subsidy_return_claim_item_links` | 4 |
| `finance_import_historical_reprocess_receipts` | 2 |
| `finance_import_ingestion_attempts` | 3 |
| `historical_owner_selection_events` | 1 |
| `knowledge_answer_receipts` | 4 |
| `knowledge_answer_requests` | 8 |
| `knowledge_answer_sources` | 2 |
| `knowledge_apply_receipts` | 1 |
| `knowledge_indexes` | 10 |
| `knowledge_item_events` | 1 |
| `knowledge_item_versions` | 4 |
| `knowledge_items` | 10 |
| `knowledge_jobs` | 12 |
| `line_alert_delivery_intents` | 2 |
| `line_command_receipts` | 2 |
| `line_configuration_current` | 3 |
| `line_configuration_revisions` | 4 |
| `line_delivery_attempt_events` | 3 |
| `line_delivery_tasks` | 21 |
| `line_domain_audit_events` | 1 |
| `line_domain_outbox` | 7 |
| `line_friend_state_events` | 2 |
| `line_identity_binding_events` | 3 |
| `line_identity_bindings` | 4 |
| `line_identity_flows` | 5 |
| `line_identity_migration_anomalies` | 0 |
| `line_inbox_events` | 8 |
| `line_media_records` | 3 |
| `line_order_group_binding_events` | 3 |
| `line_order_group_bindings` | 8 |
| `line_order_group_migration_anomalies` | 0 |
| `line_order_group_participants` | 4 |
| `line_order_group_runtime_events` | 3 |
| `line_platform_users` | 3 |
| `line_review_decision_events` | 2 |
| `line_review_requests` | 5 |
| `line_rich_menu_publication_step_receipts` | 1 |
| `line_rich_menu_publication_tasks` | 10 |
| `line_rich_menu_publish_previews` | 6 |
| `line_webhook_security_receipts` | 1 |
| `line_worker_heartbeats` | 2 |
| `matching_line_interactions` | 3 |
| `matching_notification_intents` | 5 |
| `matching_response_events` | 5 |
| `order_auto_completion_apply_receipts` | 2 |
| `provisional_client_registrations` | 3 |
| `provisional_registration_conflicts` | 1 |

## Verified retirement candidate: client subsidy-return compatibility fields

The uniquely named `client_payments` fields `subsidy_refund_at`,
`subsidy_refund_due_date`, `subsidy_refund_receivable`,
`subsidy_refund_refunded`, `subsidy_return_review_reason`, and
`subsidy_return_review_status` have no production writer/reader in `api`,
`domains`, `infrastructure`, `subsystems`, or `ui`, other than Data Browser
labels for the two review fields. Candidate evidence is also empty: all 50 rows
have null dates/reason and zero monetary values; there are no non-default review
statuses. The only remaining code references are inventory/baseline generator
scripts. This is materially stronger retirement evidence than a document
label—subject only to production-history retention confirmation before DDL—and
is distinct from the active government subsidy transaction model.

## `actual_hours_adjustments`: writes retired, historical reader still active

The candidate has zero `actual_hours_adjustments` rows and no production writer;
only Data Browser exposes it as a raw table. It is not yet safe to drop:
`subsystems/scheduling/assignment_schedule_query.py` still queries the table
to compute `has_actual_hours_adjustments` and to return an adjustment-history
payload for assignment schedules. This matches the inventory's intended
historical-audit role. Before retirement, that schedule query/API contract must
be changed (or historical rows migrated to an approved immutable event store),
then production retention verified. An empty candidate alone is insufficient.

## Knowledge runtime is an exposed UI path blocked by missing schema

Knowledge retrieval has a complete UI chain:
`ui/pages/07_line_management.py` exposes the capability-gated "知識內容"
workspace, `ui/components/knowledge_management.py` renders item/index/job and
question workflows, and `ui/api_clients/knowledge_retrieval_api_client.py`
calls the registered `/api/v1/knowledge` routes. Those routes use the missing
knowledge repository tables. Thus opening the workspace with the appropriate
capability will encounter database failure on the candidate; this is a concrete
UI-visible deployment defect, not a dormant feature. Its absence from the
authority-inventory table sheets remains a separate documentation gap.

Read-only runtime reproduction confirms the static conclusion:
`query_published_knowledge('test')` in
`infrastructure/mysql/knowledge_retrieval_repository.py` raises PyMySQL
`ProgrammingError (1146, "...knowledge_items doesn't exist")` against the
configured candidate. No API server, UI session, DDL, or DML was involved.

The missing `admin_capability_grants` also blocks the authenticated path before
any knowledge query: `authentication_session._principal_from_row()` always
selects active grants while creating or resolving an admin session. Therefore
any enabled real admin account would fail session creation/validation with table
1146 on this candidate, regardless of role defaults. The current zero
`admin_users` rows prevent a live login reproduction but do not reduce the
static certainty of this mandatory query chain.

## Assignment historical-period fields remain operational inputs

`case_staff_assignments.original_assigned_start_date` and
`original_assigned_end_date` are populated on all 36 candidate assignment rows
and are directly selected/returned by
`subsystems/scheduling/assignment_schedule_query.py`. `planned_hours` is
populated on 33 rows and is read by contract, client-finance, and scheduling
queries. They cannot be removed merely because newer scheduling generations
exist. `replacement_reason` and `replaced_assignment_id` happen to be empty in
this candidate, but the replacement writer updates the former and reminder /
contract query paths expose it; these must remain schema-compatible until the
replacement workflow is retired or migrated.

## Release-manifest integrity gap explains the candidate schema skew

`db/cutover_releases/labor_union_2026_08_09_line_stage10_v1.json` declares
`labor_union_2026_08_09_v9.json` as its required migration manifest, but the
referenced file is absent from `db/cutover_releases`. The checked-in cumulative
migration script instead names parts 147, 148, 150, 151, and 152; the candidate
is missing the principal tables from that group (`admin_capability_grants`,
knowledge tables, canonical LINE support tables, and ingestion attempts), and
also later LINE/knowledge tables.

This is evidence of a broken deployment chain, not permission to run the
cumulative script: it performs DDL and may contain data-moving statements. A
repair plan must first restore/define an ordered manifest with preconditions,
data preservation, table/trigger postchecks, and restart/smoke requirements;
otherwise an operator cannot prove which subset of schema parts was actually
applied to a candidate.

## Finance-alert names are not the current system-alert UI SSOT

The candidate has zero `finance_alerts` and `finance_alert_events` rows but 111
`system_alerts` rows. The Streamlit 「異常警示中心」 explicitly calls
`/api/v1/anomalies` through `AnomalyRegistryApiClient`, and its module header
states that the old `/api/v1/finance-alerts` and `/api/v1/system-alerts` routes
are retired/unmounted. `system_alerts` remains a separate mutable
process-reminder projection with active writer/query/claim/resolve paths in
`subsystems/anomalies/system_alert_projection.py`; it must not be dropped with
the empty immutable finance-alert tables. This confirms that the two unused
legacy columns `system_alerts.event_type`/`description` are column retirement
candidates within an otherwise active table, rather than evidence that all
system alerts are obsolete.

## Staff profile JSON/legacy fields and normalized child tables are still dual-write/dual-read

All 53 candidate staff rows have `care_babies`; 50 have non-empty
`service_regions`, `weekly_rest_days`, and `special_skills`. The normalized
child tables are also populated (`staff_baby_types=74`, `staff_regions=149`,
`staff_weekly_rest=97`, `staff_cooking_skills=77`). This is not a completed
normalization.

The old columns remain live in matching recommendation/notification/LINE-card
rendering, contract context, Data Browser and source-correction allowlists; the
BeClass import and generic adapter also construct them. Current matching
recommendation additionally reads `care_babies` to filter twin-care capacity,
whereas its normalized reads cover regions/time slots. A field-by-field
retirement must first establish which child table is the matching SSOT for each
concept, migrate every reader/writer, and prove values parity; deleting one side
now would silently change recommendations and UI cards.

The parity check finds a concrete semantic split: after normalizing JSON lists,
`service_regions` matches `staff_regions` for all candidate staff and
`special_skills` matches `staff_cooking_skills` for all of them, but
`weekly_rest_days` differs from `staff_weekly_rest` for 50 staff. For example,
the legacy value `['Sunday', 'Saturday']` coexists with child rows
`連續服務`, `週休1日`, and `週休2日`; the child table models preference options,
not the same weekday set. It cannot be used as a transparent replacement for
the old field without a business mapping decision. This is direct evidence of
two different concepts sharing a misleadingly similar name.

## Client LINE identity: legacy imported ID is not a replaceable platform identity

Candidate clients have 50 populated `line_id` values and zero populated
`line_user_id` values. `line_id` remains confined to HCM import and raw UI/Data
Browser display; all active messaging, matching communication, group binding,
and identity-review workflows use `line_user_id` and the newer canonical LINE
identity tables. The canonical tables are themselves absent from the candidate
release. Therefore a rename/backfill from `line_id` to `line_user_id` would be
an unsupported identity assertion, not a schema migration. It requires a
verified platform-binding workflow and conflict review before any historical
column retirement.

## `payment_migration_reviews` is an empty historical-review table candidate

`payment_migration_reviews` has zero candidate rows. No production business
reader/writer exists; the only source references are Data Browser/generic-table
maintenance and API smoke inventory. This supports the inventory's historical
review/retirement classification. As always, a production retention check is
required before DDL, but there is no current payment command or query contract
to migrate from this table.

## Previously closed retirement set is corroborated in the candidate

`staff_availability`, generic `audit_logs`, and `crawler_logs` are absent from
candidate `information_schema.tables`. A production-source scan finds no caller
for them; the sole match is the field-authority review script's closed-set
metadata. This corroborates the documents' retirement state and distinguishes
them from active similarly named tables such as `admin_audit_logs`.

## Static zero-caller field sweep: candidates require semantic review, not auto-drop

An exact word-boundary scan of all candidate column names against production
Python source surfaced a small set with no direct name occurrence. Candidate
data is empty for the event/snapshot fields on leave-substitution events,
finance alerts, government subsidy reversal target type, legacy LINE task
attempts/users, and assignment-change audits. This is useful retirement or
coverage evidence, but not proof: several are fields of currently empty
event tables, and a repository can read them through `SELECT *` or map them
through a typed snapshot.

One live-data example reinforces the rule: all 18 `staff_actual_transfers`
have null `reversal_of_transfer_id` and no direct source-name hit, but it is
the documented immutable causal link reserved for future reversal transactions.
It cannot be removed just because this candidate contains no reversals. The
scan is therefore recorded as a prioritization list; only the subsidy-return
fields above met the combined no-caller + no-data + obsolete-replacement bar.

## Per-field source-name coverage for every documented, existing candidate column

For each inventory field that actually exists in the candidate, an exact
word-boundary source scan found a name hit for all but this finite set:

- `assignment_schedule_leave_substitution_events.schedule_snapshot` and
  `payroll_snapshot`;
- `order_assignment_change_audits.order_after_snapshot`,
  `assignment_plan_snapshot`, and `applied_by`;
- `client_payments.subsidy_refund_due_date` and `subsidy_refund_at`;
- `staff_actual_transfers.reversal_of_transfer_id`;
- `finance_alert_events.event_snapshot`, `finance_alerts.alert_key`;
- `line_task_attempts.attempt_no` and `finished_at`;
- `line_users.onboarding_completed_at`.

This is a mechanical coverage result, not a proof that the remaining fields are
unused (raw `SELECT *` and serialization can bypass a field-name scan). It
confirms, however, that no additional unreferenced documented candidate fields
were hidden outside the already reviewed legacy/event categories. The two
client subsidy-return dates are part of the verified retirement set; the
transfer reversal ID remains required causal schema; the rest need their
empty-event or canonical-model migration classification before any removal.

## Inventory-scope completion baseline

The requested authority-inventory directory has 69 Markdown stems. Of these,
63 exactly map to a versioned table and all 63 currently map to a candidate
base table; those are covered by the two-way field/schema and per-field source
name sweeps above. The remaining six are intentionally non-current table
records: retired `audit_logs`, `crawler_logs`, `faq`, `staff_availability`, and
`finance_import_reclassification_events`, plus the explicitly not-yet-created
`client_payment_transaction_adjustment_allocations` proposal. Candidate
metadata confirms the first five are absent; part 153 explicitly drops the
reclassification-events table, and no source/schema table exists for the
allocation proposal.

This is distinct from broader architecture coverage: the candidate contains 89
tables without an exact inventory sheet, and the versioned target has 149 such
tables. They are documented schema/inventory debt already identified above,
not omitted rows of the user-named inventory scope.

## Why unit pytest did not catch the candidate schema failures

`tests/test_order_detail_query.py` and `tests/test_order_summary_query.py`
inject `SimpleNamespace` repository stubs with hand-built row dictionaries.
They validate service shape and type contracts, but execute neither the MySQL
SQL nor the candidate view/schema. The migration tests similarly validate fake
cursor statements and expected SQL text. This explains why a valid unit suite
did not detect missing `orders.contract_identity`, an outdated
`v_order_details`, missing `knowledge_items`, or the canonical LINE delivery
tables in the actual candidate.

The prevention gap is a release-level read-only schema gate: bootstrap a
disposable database from the exact ordered release manifest (including views
and triggers), then run representative repository reads for every registered
UI/API domain. Existing schema-contract tests are useful but are not a
substitute for that gate, especially while the manifest itself has a missing
dependency reference.
