/**
 * File: subsidy_report_query_contract_fixtures.ts
 * Description: 提供補助季度／年度strict redacted query fixtures。
 */
export const SUBSIDY_REPORT_RESPONSE = { success: true, message: 'ok', error: null, data: { period_kind: 'quarterly' as const, application_year: 2026, quarter: 1, generated_at: '2026-08-17T12:00:00+08:00', source_revision: 'reconciliation_register_query_v1', total_row_count: 1, total_amount_ntd: 12000, partitions: [{ citizen_kind: 'general' as const, row_count: 1, total_amount_ntd: 12000, rows: [{ serial_number: 1, case_no: 'CASE-RPT-001', eligibility: '一般市民', service_start: '2026-01-01', service_end: '2026-01-10', subsidy_hours: '40', subsidy_days: '5', service_days: 10, subsidy_amount_ntd: 12000, unit_price_ntd: 300, employer_name_masked: '王**', staff_name_masked: '陳**', identity_card_masked: 'A*********', address_masked: '地址已遮罩' as const }] }, { citizen_kind: 'subsidized' as const, row_count: 0, total_amount_ntd: 0, rows: [] }] } };
