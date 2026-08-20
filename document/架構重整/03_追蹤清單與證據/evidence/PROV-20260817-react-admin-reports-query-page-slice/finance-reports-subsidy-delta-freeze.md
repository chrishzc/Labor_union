# `finance_reports.py` Subsidy Delta Freeze

本包在已凍結Finance AP delta之後，只追加：

1. `GovernmentSubsidyReport*View` imports。
2. Quarterly／annual preview GET的`require_admin`。
3. `_subsidy_report_row/partition/view`與server masking helpers。
4. Quarterly／annual response model由raw dict改為strict redacted view。

未改：AP preview/masking、AP export/archive、quarterly/annual export、legacy summary、XLSX response與reconciliation formula。後續writer必須fresh-read並保留兩組delta。

