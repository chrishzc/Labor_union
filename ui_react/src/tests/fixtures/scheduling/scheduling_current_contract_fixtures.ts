/**
 * File: scheduling_current_contract_fixtures.ts
 * Description: 提供 current Scheduling 嚴格契約的去敏正向、空值與 drift 測試資料。
 */
import type {
  SchedulingCurrentProjection,
  SchedulingCurrentResponse,
} from '../../../api/scheduling/scheduling_current_schemas';

export const SCHEDULING_PROJECTION_READY: SchedulingCurrentProjection = {
  staff_id: 11,
  range_start: '2026-08-01',
  range_end: '2026-08-03',
  evaluated_at: '2026-08-01T09:00:00+08:00',
  assignments: [
    {
      assignment_id: 31,
      case_no: 'CASE-SCH-001',
      generation_id: 41,
      scheduling_version: 3,
      staff_id: 11,
      status: 'active',
      assigned_start_date: '2026-08-01',
      assigned_end_date: '2026-08-02',
      first_service_at: '2026-08-01T09:00:00+08:00',
      completion_at: '2026-08-02T18:00:00+08:00',
      official_service_day_count: 1,
      actual_hours: 8,
    },
  ],
  days: [
    {
      calendar_date: '2026-08-01',
      available: false,
      entries: [
        {
          occupancy_kind: 'official_workday',
          case_no: 'CASE-SCH-001',
          assignment_id: 31,
          assignment_status: 'active',
          lock_id: null,
          segment_id: null,
          availability_block_id: null,
          unavailability_kind: null,
        },
      ],
    },
    {
      calendar_date: '2026-08-02',
      available: false,
      entries: [
        {
          occupancy_kind: 'assignment_buffer',
          case_no: 'CASE-SCH-001',
          assignment_id: 31,
          assignment_status: 'active',
          lock_id: null,
          segment_id: null,
          availability_block_id: null,
          unavailability_kind: null,
        },
      ],
    },
    { calendar_date: '2026-08-03', available: true, entries: [] },
  ],
  case_versions: [{ case_no: 'CASE-SCH-001', scheduling_version: 3 }],
  projection_token: 'a'.repeat(64),
};

export const SCHEDULING_RESPONSE_READY: SchedulingCurrentResponse = {
  success: true,
  message: '成功取得目前排班投影',
  data: SCHEDULING_PROJECTION_READY,
  error: null,
};

export const SCHEDULING_PROJECTION_EMPTY: SchedulingCurrentProjection = {
  ...SCHEDULING_PROJECTION_READY,
  assignments: [],
  days: [],
  case_versions: [],
  projection_token: 'b'.repeat(64),
};

export const SCHEDULING_RESPONSE_EXTRA_FIELD = {
  ...SCHEDULING_RESPONSE_READY,
  leaked_business_state: true,
};

export const SCHEDULING_RESPONSE_DUPLICATE_DAY = {
  ...SCHEDULING_RESPONSE_READY,
  data: {
    ...SCHEDULING_PROJECTION_READY,
    days: [
      SCHEDULING_PROJECTION_READY.days[0],
      SCHEDULING_PROJECTION_READY.days[0],
    ],
  },
};
