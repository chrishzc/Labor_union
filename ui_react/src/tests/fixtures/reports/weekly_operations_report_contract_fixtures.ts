/**
 * File: weekly_operations_report_contract_fixtures.ts
 * Description: 提供營運週報三分頁 strict、canonical且含歷史缺欄位的測試契約 fixture。
 */
import type { WeeklyOperationsReport } from '../../../api/reports/weekly_operations_report_schemas';
import { SUBSIDY_REPORT_RESPONSE } from './subsidy_report_query_contract_fixtures';

export const WEEKLY_OPERATIONS_REPORT: WeeklyOperationsReport = {
  schema_version: 'operations-report.v3',
  period: {
    start_date: '2026-08-20',
    end_date: '2026-08-26',
    timezone: 'Asia/Taipei',
    period_label: '2026-08-20～2026-08-26',
  },
  generated_at: '2026-08-23T12:00:00+08:00',
  source_revision: 'weekly-operations-fixture-revision',
  summary: {
    application_count: 2,
    general_eligible_count: 1,
    general_ineligible_count: null,
    subsidized_eligible_count: 0,
    subsidized_ineligible_count: null,
    rejection_unpartitioned_count: 1,
    order_established_count: 1,
    negotiating_count: 0,
    cancelled_count: 0,
    incomplete_count: 1,
  },
  case_rows: [
    {
      case_no: 'CASE-WEEK-001',
      applicant_name: '王**',
      application_date: '2026-08-20',
      identity_status: '一般市民',
      review_result: 'general_eligible',
      order_status: '服務中',
      service_days: 10,
      service_hours_per_day: 8,
      planned_start_date: '2026-08-17',
      planned_end_date: '2026-08-28',
      district: '板橋區',
      data_quality_codes: [],
      week_start_date: '2026-08-17',
      week_end_date: '2026-08-23',
      week_label: '2026-08-17 ~ 2026-08-23',
    },
    {
      case_no: 'CASE-WEEK-LEGACY',
      applicant_name: '李**',
      application_date: '2026-08-24',
      identity_status: null,
      review_result: 'rejected_unpartitioned',
      order_status: null,
      service_days: null,
      service_hours_per_day: null,
      planned_start_date: null,
      planned_end_date: null,
      district: null,
      data_quality_codes: ['historical_order_missing'],
      week_start_date: '2026-08-24',
      week_end_date: '2026-08-30',
      week_label: '2026-08-24 ~ 2026-08-30',
    },
  ],
  subsidy_partitions: SUBSIDY_REPORT_RESPONSE.data.partitions,
  service_rows: [{
    assignment_id: 701,
    case_no: 'CASE-WEEK-001',
    client_name: '王**',
    staff_name: '陳**',
    service_start_date: '2026-08-17',
    service_end_date: '2026-08-28',
    period_start_date: '2026-08-17',
    period_end_date: '2026-08-23',
    service_hours_per_day: 8,
    weekly_work_days: 5,
    weekly_hours: 40,
    order_status: '服務中',
    completed: false,
    data_quality_codes: [],
  }],
  weekly_metrics: [
    { week_start_date: '2026-08-17', week_end_date: '2026-08-23', promotion_count: 12, inquiry_count: 8, updated_at: '2026-08-23T12:00:00+08:00' },
    { week_start_date: '2026-08-24', week_end_date: '2026-08-30', promotion_count: null, inquiry_count: 0, updated_at: null },
  ],
  data_quality_issues: [
    { code: 'historical_order_missing', field: 'order_status', row_count: 1, message: '歷史案件缺少訂單資料' },
  ],
};

export const WEEKLY_OPERATIONS_RESPONSE = {
  success: true,
  message: '成功取得營運週報',
  data: WEEKLY_OPERATIONS_REPORT,
  error: null,
};
