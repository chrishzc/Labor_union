// @vitest-environment happy-dom
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { OrderTermsMutationPanel } from '../components/OrderTermsMutationPanel';
import { OrderTermsSchema, type OrderTerms } from '../api/orders/order_query_schemas';
import { OrderTermsQuerySchema, OrderTermsPreviewSchema } from '../api/orders/order_terms_mutation_client';

vi.mock('../api/scheduling/schedule_precision_client', () => ({
  schedulePrecisionClient: { calculate: vi.fn() },
}));
afterEach(cleanup);

const query = (): OrderTerms => ({
  case_no: 'case-336', order_version: 3,
  scheduling_version: 0, scheduling_generation: 0,
  client_finance_version: null, payroll_version: null,
  service_data_locked: false,
  terms: {
    planned_start_date: '2026-09-22', service_days: 2,
    service_hours_per_day: 4.5, requires_cooking: null, floor_fee_ntd: 0,
    service_time: { start_time: '09:00:00', end_time: '13:30:00', end_day_offset: 0 },
  },
  confirmed_service_dates: [], confirmed_service_date_version: null, assignments: [],
});

describe('#336 Query-only decoupling', () => {
  it('both Query clients accept absent account versions without inventing zero', () => {
    expect(OrderTermsSchema.parse(query()).client_finance_version).toBeNull();
    expect(OrderTermsQuerySchema.parse(query()).payroll_version).toBeNull();
    expect(OrderTermsQuerySchema.parse({ ...query(), payroll_version: 0 }).payroll_version).toBe(0);
  });

  it('does not weaken the financial versions of the unchanged impact Preview', () => {
    const q = query();
    expect(OrderTermsPreviewSchema.safeParse({
      before: q.terms, after: q.terms, order_version: 3,
      scheduling_version: 0, scheduling_generation: 0,
      client_finance_version: null, payroll_version: null,
      scheduling: {}, client_finance_impact: {}, payroll_impact: {}, lifecycle_impact: {},
      preview_fingerprint: 'a'.repeat(64),
    }).success).toBe(false);
  });

  it('preserves a draft when only account versions change', () => {
    const q = query();
    const view = render(<OrderTermsMutationPanel caseNo={q.case_no} query={q} />);
    const start = () => screen.getByLabelText('Beta 計畫服務開始日') as HTMLInputElement;
    fireEvent.change(start(), { target: { value: '2026-10-02' } });
    view.rerender(<OrderTermsMutationPanel caseNo={q.case_no}
      query={{ ...q, client_finance_version: 4, payroll_version: 7 }} />);
    expect(start().value).toBe('2026-10-02');
    view.rerender(<OrderTermsMutationPanel caseNo={q.case_no}
      query={{ ...q, client_finance_version: 5, payroll_version: 8 }} />);
    expect(start().value).toBe('2026-10-02');
  });

  it('still observes a changed order version', () => {
    const q = query();
    const view = render(<OrderTermsMutationPanel caseNo={q.case_no} query={q} />);
    fireEvent.change(screen.getByLabelText('Beta 計畫服務開始日'), { target: { value: '2026-10-02' } });
    view.rerender(<OrderTermsMutationPanel caseNo={q.case_no} query={{
      ...q, order_version: 4, terms: { ...q.terms, planned_start_date: '2026-10-04' },
    }} />);
    expect((screen.getByLabelText('Beta 計畫服務開始日') as HTMLInputElement).value).toBe('2026-10-04');
  });
});
