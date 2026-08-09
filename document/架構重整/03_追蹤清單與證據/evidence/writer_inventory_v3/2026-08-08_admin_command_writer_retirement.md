# Admin Command Writer Retirement Receipt

## Scope

- Removed `mysql_adapter.update_order_full_details`.
- Removed `mysql_adapter.add_or_update_holiday` and `delete_holiday`.
- Removed `mysql_adapter.update_table_row` and the Data Browser maintenance writer.

## Replacement

- Orders client-name changes use `client_name_maintenance` Preview/Apply.
- Holiday changes use `holiday_maintenance` Preview/Apply.
- Both commands recheck the Preview fingerprint, save a durable
  `admin_command_receipts` row, and commit the owned fact and receipt together.
- Data Browser PATCH is retired with typed HTTP `410`; the page is read-only.

## Verification

- `generate_writer_inventory_v3_candidate.py`: `704 findings`, `17 unresolved`.
- Candidate and disposition validators pass with `37` reviewed records.
- Focused regression suite: `11 passed`.

## Boundary

This receipt proves only the listed legacy writer retirement. It does not
authorize removal of any remaining candidate finding.

## Human-confirmed Holiday write policy

Confirmed: holiday facts may be changed only through the typed `Preview -> Apply -> receipt` workflow. Legacy APIs, scripts, and generic maintenance tools must not directly insert, update, or delete `holidays` rows. This policy does not require a UI redesign; the existing holiday management page remains the presentation adapter for the typed endpoints.
## Human-confirmed Order Page 2 field boundary

Confirmed: Order Management Page 2 may change only the customer name through `client_name_maintenance` Preview -> Apply -> receipt. Customer phone, address, and other contact facts remain editable in their Client master-data workflow; Page 2 must not edit them. Service dates, service days, hours, fees, deposit facts, actual dates, assignments, and lifecycle facts remain owned by their respective typed workflows and are read-only on Page 2.
## Human-confirmed Data Browser source correction policy

Confirmed: Data Browser may correct only `clients`, `beclass_records`, and `staff` source facts through the typed source-correction `Preview -> Apply -> receipt` workflow. The correction UI must show differences, require a reason before Apply, and allow preview cancellation without persistence. It must use API-provided allowlists; the generic PATCH endpoint remains retired. Case identifiers, identity qualification, service terms, payment, scheduling, assignments, and LINE binding facts remain prohibited.