import type { PerformanceFilters, StaffPerformanceReport } from '../../../../../../../api/reports/staff_performance_client';

export function performanceFixture(filters: PerformanceFilters = { year: 2026, period: 'month', month: 11 }): StaffPerformanceReport {
  const first = filters.period === 'month' ? filters.month! : filters.period === 'quarter' ? (filters.quarter! - 1) * 3 + 1 : 1;
  const last = filters.period === 'month' ? first : filters.period === 'quarter' ? first + 2 : 12;
  const start = `${filters.year}-${String(first).padStart(2, '0')}-01`;
  const end = `${filters.year}-${String(last).padStart(2, '0')}-${new Date(Date.UTC(filters.year, last, 0)).getUTCDate()}`;
  const options = [{ staff_id: 2, union_no: 'U10', staff_name: '乙月嫂' }, { staff_id: 1, union_no: 'U2', staff_name: '甲月嫂' }];
  const primaryTotals = { case_count: 1, service_hours: 16.5, total_amount_ntd: 99000 };
  const secondaryTotals = { case_count: 0, service_hours: 8, total_amount_ntd: 0 };
  const point = { start_date: start, end_date: end, label: `${first}月`, totals: primaryTotals };
  const primary = { ...options[1], totals: primaryTotals, previous_totals: { case_count: 1, service_hours: 8, total_amount_ntd: 99000 },
    cases: [{ case_no: 'PERF-001', service_start: start, service_end: `${start.slice(0, 8)}02`, work_days: 2, service_hours: 16.5, total_amount_ntd: 99000,
      actual_start_date: start, primary_staff_id: 1, recognized_case_count: 1, recognized_amount_ntd: 99000 }], trend: [point] };
  const secondary = { ...options[0], totals: secondaryTotals, previous_totals: { case_count: 0, service_hours: 4, total_amount_ntd: 0 },
    cases: [{ ...primary.cases[0], work_days: 1, service_hours: 8, service_end: start, recognized_case_count: 0, recognized_amount_ntd: 0 }], trend: [{ ...point, totals: secondaryTotals }] };
  const rows = [primary, secondary].filter(row => !filters.staff_id || row.staff_id === filters.staff_id);
  const totals = { case_count: rows.reduce((sum, row) => sum + row.totals.case_count, 0),
    service_hours: rows.reduce((sum, row) => sum + row.totals.service_hours, 0), total_amount_ntd: rows.reduce((sum, row) => sum + row.totals.total_amount_ntd, 0) };
  return { schema_version: 'staff-performance.v2', period: filters.period, year: filters.year,
    month: filters.period === 'month' ? filters.month! : null, quarter: filters.period === 'quarter' ? filters.quarter! : null,
    start_date: start, end_date: end, through_date: end, previous_start_date: '2026-10-01', previous_end_date: '2026-10-31', generated_at: '2026-11-04T10:00:00+08:00',
    selected_staff_id: filters.staff_id ?? null, available_years: [2026, 2025], staff_options: options, service_staff_count: rows.length, totals,
    rows, trend: [{ ...point, totals }] };
}
