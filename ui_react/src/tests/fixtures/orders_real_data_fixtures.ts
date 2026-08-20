/**
 * File: orders_real_data_fixtures.ts
 * Description: 提供八個核准 Orders GET 的 deterministic strict contract fixtures。
 */
import type {
  ActualStart,
  AssignmentPlan,
  ContractCompletion,
  FormManagementContext,
  OrderCalendarDetail,
  OrderDetail,
  OrderSummaryItem,
  OrderSummaryPage,
  OrderTerms,
} from '../../api/orders/order_query_schemas';

const summary = (
  caseNo: string,
  clientName: string,
  orderStatus: string,
  staffName: string | null,
  offset: number
): OrderSummaryItem => ({
  case_no: caseNo,
  client_name: clientName,
  order_status: orderStatus,
  staff_name: staffName,
  identity_status: 'regular',
  start_date: `2026-09-${String(offset).padStart(2, '0')}`,
  end_date: `2026-10-${String(offset).padStart(2, '0')}`,
  actual_start_date: orderStatus === '服務中' || orderStatus === '已結案'
    ? `2026-09-${String(offset).padStart(2, '0')}`
    : null,
  actual_end_date: orderStatus === '已結案'
    ? `2026-10-${String(offset).padStart(2, '0')}`
    : null,
  service_days: 30,
  total_employer_self_pay_payable: 90_000 + offset,
});

export const mockSummaryItems: OrderSummaryItem[] = [
  summary('ORD-2026-0801', '陳雅婷', '待補件', null, 1),
  summary('ORD-2026-0802', '林美玲', '洽談中', null, 2),
  summary('ORD-2026-0803', '黃怡君', '推薦確認', '林美惠', 3),
  summary('ORD-2026-0804', '張淑芬', '簽約中', '張秀珍', 4),
  summary('ORD-2026-0805', '李佩玲', '已簽約', '王小芬', 5),
  summary('ORD-2026-0806', '王心凌', '服務中', '何美美', 6),
  summary('ORD-2026-0807', '許瑋甯', '已結案', '林心如', 7),
];

export const realisticOrderSummaryPage: OrderSummaryPage = {
  items: mockSummaryItems,
  next_cursor: null,
  etag: 'a'.repeat(64),
};

export const realisticOrderDetail: OrderDetail = {
  case_no: 'ORD-2026-0801',
  client_id: 101,
  staff_id: null,
  client_name: '陳雅婷',
  staff_name: null,
  order_status: '待補件',
  identity_status: 'regular',
  cancel_reason: null,
  line_group_id: 'GROUP-0801',
  contract_identity: 'CT-2026-0801',
  actual_start_date: null,
  actual_end_date: null,
  deposit_date: null,
  start_date: '2026-09-01',
  end_date: '2026-09-30',
  service_days: 30,
  service_hours_per_day: 9,
  deposit_service_days: 5,
  floor_fee: 2_000,
  custom_rest_dates: '週日休假（共 4 天）',
};

export const realisticOrderCalendarDetail: OrderCalendarDetail = {
  case_no: 'ORD-2026-0801',
  service_mode: '週休1日',
};

export const realisticOrderTerms: OrderTerms = {
  case_no: 'ORD-2026-0801',
  order_version: 1,
  scheduling_version: 2,
  scheduling_generation: 3,
  client_finance_version: 4,
  payroll_version: 5,
  service_data_locked: false,
  terms: {
    planned_start_date: '2026-09-01',
    service_days: 30,
    service_hours_per_day: 9,
    requires_cooking: true,
    floor_fee_ntd: 2_000,
    service_time: {
      start_time: '08:30:00',
      end_time: '17:30:00',
      end_day_offset: 0,
    },
  },
};

export const realisticFormManagementContext: FormManagementContext = {
  case_no: 'ORD-2026-0801',
  service_time: '08:30-17:30',
  service_type: '到府服務',
  delivery_type: null,
  residence_type: '公寓',
  city: '台北市',
  identity_status: 'regular',
};

export const realisticActualStart: ActualStart = {
  case_no: 'ORD-2026-0801',
  current_actual_start_date: null,
  planned_start_date: '2026-09-01',
  service_data_locked: false,
  order_version: 1,
  scheduling_version: 2,
  scheduling_generation: 3,
  client_finance_version: 4,
  payroll_version: 5,
};

export const realisticContractCompletion: ContractCompletion = {
  case_no: 'ORD-2026-0801',
  order_version: 1,
  client_finance_version: 4,
  contract_identity: 'CT-2026-0801',
  contract_completed: false,
  lifecycle_status: '待補件',
  deposit_settled: false,
  service_time_terms_complete: true,
  completion_available: false,
  domain_blockers: ['DEPOSIT_UNSETTLED', 'STAFF_CONTRACT_UNSIGNED'],
};

export const realisticAssignmentPlan: AssignmentPlan = {
  case_no: 'ORD-2026-0801',
  order_version: 1,
  scheduling_version: 2,
  scheduling_generation: 3,
  client_finance_version: 4,
  payroll_version: 5,
  contracted_service_days: 30,
  service_hours_per_day: 9,
  service_started: false,
  assignments: [
    {
      assignment_id: 501,
      candidate_key: null,
      staff_id: 88,
      sequence: 1,
      assigned_start_date: '2026-09-01',
      assigned_end_date: '2026-09-15',
      official_service_dates: ['2026-09-01', '2026-09-02'],
      actual_hours: null,
      lineage_source_assignment_ids: [],
    },
  ],
};
