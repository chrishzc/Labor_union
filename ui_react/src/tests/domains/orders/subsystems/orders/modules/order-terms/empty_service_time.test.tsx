// @vitest-environment happy-dom
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  OrderTermsInputSchema,
  OrderTermsPreviewPayloadSchema,
  OrderTermsPreviewSchema,
  OrderTermsQuerySchema,
  OrderTermsReceiptSchema,
  orderTermsMutationClient,
} from '../../../../../../../api/orders/order_terms_mutation_client';
import { OrderTermsMutationPanel } from '../../../../../../../components/OrderTermsMutationPanel';

vi.mock('../../../../../../../api/orders/order_terms_mutation_client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../../../../../api/orders/order_terms_mutation_client')>();
  return {
    ...actual,
    orderTermsMutationClient: { query: vi.fn(), preview: vi.fn(), apply: vi.fn() },
  };
});

const emptyTime = { start_time: null, end_time: null, end_day_offset: null };

function queryFixture() {
  return OrderTermsQuerySchema.parse({
    case_no: 'ISSUE-337-TEST',
    order_version: 3,
    scheduling_version: 2,
    scheduling_generation: 1,
    client_finance_version: 4,
    payroll_version: 5,
    service_data_locked: false,
    confirmed_service_dates: [],
    confirmed_service_date_version: null,
    assignments: [],
    terms: {
      planned_start_date: '2026-10-01',
      service_days: 5,
      service_hours_per_day: 8,
      requires_cooking: null,
      floor_fee_ntd: 0,
      service_time: { ...emptyTime },
    },
  });
}

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(orderTermsMutationClient.preview).mockImplementation(async (_caseNo, payload) => {
    const parsed = OrderTermsPreviewPayloadSchema.parse(payload);
    const current = queryFixture();
    return OrderTermsPreviewSchema.parse({
      before: current.terms,
      after: parsed.proposed_terms,
      order_version: 3,
      scheduling_version: 2,
      scheduling_generation: 1,
      client_finance_version: 4,
      payroll_version: 5,
      scheduling: {},
      client_finance_impact: {},
      payroll_impact: {},
      lifecycle_impact: {},
      requires_formal_apply: false,
      preview_fingerprint: 'a'.repeat(64),
    });
  });
});

afterEach(cleanup);

const previewButton = () => screen.getByRole('button', { name: '檢查訂單條款變更' });

async function submittedTerms() {
  await waitFor(() => expect(orderTermsMutationClient.preview).toHaveBeenCalledTimes(1));
  return vi.mocked(orderTermsMutationClient.preview).mock.calls[0][1].proposed_terms;
}

describe('Issue #337 empty service time', () => {
  it('accepts an all-null tuple while rejecting a partial tuple', () => {
    const input = queryFixture().terms;
    expect(OrderTermsInputSchema.parse(input).service_time).toEqual(emptyTime);
    expect(OrderTermsInputSchema.safeParse({
      ...input,
      service_time: { ...emptyTime, start_time: '09:00:00' },
    }).success).toBe(false);
  });

  it('lets a date-only edit reach preview without inventing service times', async () => {
    const query = queryFixture();
    render(<OrderTermsMutationPanel caseNo={query.case_no} query={query} />);

    fireEvent.change(screen.getByLabelText('Beta 計畫服務開始日'), { target: { value: '2026-10-02' } });
    expect(previewButton()).toHaveProperty('disabled', false);
    fireEvent.click(previewButton());

    expect(await submittedTerms()).toEqual({ ...query.terms, planned_start_date: '2026-10-02' });
  });

  it('blocks a half-filled time tuple before sending preview', () => {
    const query = queryFixture();
    render(<OrderTermsMutationPanel caseNo={query.case_no} query={query} />);

    fireEvent.change(screen.getByLabelText('Beta 每日開始時間'), { target: { value: '09:00' } });

    expect(previewButton()).toHaveProperty('disabled', true);
    fireEvent.click(previewButton());
    expect(orderTermsMutationClient.preview).not.toHaveBeenCalled();
  });

  it('still calculates half-hour durations when time is filled', async () => {
    const query = queryFixture();
    render(<OrderTermsMutationPanel caseNo={query.case_no} query={query} />);

    fireEvent.change(screen.getByLabelText('Beta 每日開始時間'), { target: { value: '09:00' } });
    fireEvent.change(screen.getByLabelText('Beta 每日結束時間'), { target: { value: '13:30' } });
    fireEvent.click(previewButton());

    const proposed = await submittedTerms();
    expect(proposed.service_hours_per_day).toBe(4.5);
    expect(proposed.service_time).toEqual({
      start_time: '09:00:00',
      end_time: '13:30:00',
      end_day_offset: 0,
    });
  });

  it('preserves saved hours and seconds during an unrelated edit', async () => {
    const query = queryFixture();
    query.terms.service_hours_per_day = 7.5;
    query.terms.service_time = {
      start_time: '09:00:30',
      end_time: '17:00:30',
      end_day_offset: 0,
    };
    render(<OrderTermsMutationPanel caseNo={query.case_no} query={query} />);

    fireEvent.change(screen.getByLabelText('Beta 計畫服務開始日'), { target: { value: '2026-10-02' } });
    fireEvent.click(previewButton());

    expect(await submittedTerms()).toEqual({ ...query.terms, planned_start_date: '2026-10-02' });
  });

  it('reads an all-null result back and permits another edit', async () => {
    const query = queryFixture();
    const refreshed = {
      ...query,
      order_version: 4,
      terms: { ...query.terms, planned_start_date: '2026-10-02' },
    };
    const onObserved = vi.fn();
    vi.mocked(orderTermsMutationClient.query).mockResolvedValue(refreshed);
    vi.mocked(orderTermsMutationClient.apply).mockResolvedValue(OrderTermsReceiptSchema.parse({
      case_no: query.case_no,
      order_version: 4,
      scheduling_version: 2,
      scheduling_generation: 1,
      client_finance_version: 4,
      payroll_version: 5,
      lifecycle_status: '洽談中',
      service_data_lock_formed: false,
      cancelled_assignment_ids: [],
      created_assignment_keys: [],
      official_service_day_count: 0,
      official_service_hours: 0,
      preview_fingerprint: 'a'.repeat(64),
    }));
    render(<OrderTermsMutationPanel caseNo={query.case_no} query={query} onObserved={onObserved} />);

    fireEvent.change(screen.getByLabelText('Beta 計畫服務開始日'), { target: { value: '2026-10-02' } });
    fireEvent.click(previewButton());
    fireEvent.click(await screen.findByRole('button', { name: '確認保存訂單條款' }));

    await waitFor(() => expect(onObserved).toHaveBeenCalledTimes(1));
    expect(vi.mocked(orderTermsMutationClient.apply).mock.calls[0][1].proposed_terms.service_time).toEqual(emptyTime);
    expect(vi.mocked(orderTermsMutationClient.apply).mock.calls[0][1].reason).toBeUndefined();
    expect(vi.mocked(orderTermsMutationClient.apply).mock.calls[0][1].requires_formal_apply).toBe(false);
    expect(vi.mocked(orderTermsMutationClient.apply).mock.calls[0][2].idempotencyKey).toBeUndefined();
    expect(screen.getByLabelText('Beta 每日開始時間')).toHaveProperty('value', '');
    fireEvent.change(screen.getByLabelText('Beta 計畫服務開始日'), { target: { value: '2026-10-03' } });
    expect(previewButton()).toHaveProperty('disabled', false);
  });
});
