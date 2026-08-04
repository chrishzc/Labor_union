# INV2-EVID-02-R2 Unresolved Findings

## Row 56: infrastructure/mysql/case_architecture_bootstrap_repository.py / _select_optional_row
- Dynamic SQL scanner flag: actual SQL appears to be a SELECT (read) but uses string concatenation suffix (_lock_suffix). Needs strong model review to confirm read-only nature and correct writer_type.

## Row 57: infrastructure/mysql/case_architecture_bootstrap_repository.py / _select_order
- Dynamic SQL scanner flag: actual SQL appears to be a SELECT (read) but uses string concatenation suffix (_lock_suffix). Needs strong model review to confirm read-only nature and correct writer_type.

## Row 58: infrastructure/mysql/case_architecture_bootstrap_repository.py / _select_rate_policy
- Dynamic SQL scanner flag: actual SQL appears to be a SELECT (read) but uses string concatenation suffix (_lock_suffix). Needs strong model review to confirm read-only nature and correct writer_type.

## Row 59: infrastructure/mysql/case_architecture_bootstrap_repository.py / _select_root_event
- Dynamic SQL scanner flag: actual SQL appears to be a SELECT (read) but uses string concatenation suffix (_lock_suffix). Needs strong model review to confirm read-only nature and correct writer_type.

## Row 64: infrastructure/mysql/case_import_repository.py / _case_exists
- Dynamic SQL scanner flag: actual SQL appears to be a SELECT (read). Needs strong model review to confirm read-only nature.

## Row 65: infrastructure/mysql/case_import_repository.py / _case_exists
- Dynamic SQL scanner flag: actual SQL appears to be a SELECT (read). Needs strong model review to confirm read-only nature.

## Row 68: infrastructure/mysql/case_import_repository.py / _load_rate_policy
- Dynamic SQL: actual SQL appears to be a SELECT (read). Needs strong model review.

## Row 77: infrastructure/mysql/client_receipt_reconciliation_repository.py / _advance_account_version
- Multiple _advance_account_version functions exist across repositories; needs strong model review to confirm this specific instance.

## Row 81: infrastructure/mysql/client_receipt_reconciliation_repository.py / _load_account_version
- _load_account_version contains INSERT IGNORE (upsert semantics) to initialize account row; this is conditional and idempotent. Needs strong model review.

## Row 91: infrastructure/mysql/client_refund_reversal_repository.py / _load_account_version
- _load_account_version has INSERT IGNORE (upsert semantics); needs strong model review to determine if this is initialization or mutation.


All findings maintain effective_disposition=blocked, approved_to_remove=false.
No formal semantic disposition or removal authority in this batch.