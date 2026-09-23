import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { HistoricalRestartArrangementPanel } from '../../../../../../../components/HistoricalRestartArrangementPanel';
import type { ServiceDateConfirmationQueryView } from '../../../../../../../api/orders/order_mutation_schemas';

const calls = vi.hoisted(() => ({
  preview: vi.fn(),
  apply: vi.fn(),
  query: vi.fn(),
}));

vi.mock('../../../../../../../api/orders/order_mutation_client', () => ({
  ordersMutationClient: {
    previewHistoricalArrangement: calls.preview,
    applyHistoricalArrangement: calls.apply,
    getServiceDates: calls.query,
  },
}));

const dates: ServiceDateConfirmationQueryView = {
  case_no: 'HIST-ARRANGE',
  order_version: 3,
  scheduling_version: 7,
  contracted_service_days: 4,
  suggested_dates: [],
  selectable_dates: ['2026-09-06', '2026-09-07', '2026-09-08', '2026-09-09', '2026-09-10', '2026-09-11'],
  current_version: 2,
  current_dates: ['2026-09-08', '2026-09-09', '2026-09-10', '2026-09-11'],
  bound_staff: [
    { staff_id: 12, staff_name: '王月嫂' },
    { staff_id: 13, staff_name: '李月嫂' },
  ],
  arrangement_pending: true,
};

beforeEach(() => {
  Object.values(calls).forEach((call) => call.mockReset());
});

it('多月嫂必須明確逐日分段，正式回讀後才標示完成', async () => {
  const observed = vi.fn();
  calls.preview.mockResolvedValue({
    case_no: dates.case_no,
    order_version: 3,
    scheduling_version: 7,
    confirmed_version: 2,
    segments: [
      { staff_id: 12, assigned_start_date: '2026-09-06', assigned_end_date: '2026-09-09', service_dates: dates.current_dates.slice(0, 2) },
      { staff_id: 13, assigned_start_date: '2026-09-10', assigned_end_date: '2026-09-11', service_dates: dates.current_dates.slice(2) },
    ],
    preview_fingerprint: 'a'.repeat(64),
  });
  calls.apply.mockResolvedValue({
    case_no: dates.case_no,
    scheduling_version: 8,
    generation_number: 5,
    assignment_ids: [101, 102],
    preview_fingerprint: 'a'.repeat(64),
  });
  calls.query.mockResolvedValue({ ...dates, scheduling_version: 8, arrangement_pending: false });
  render(<HistoricalRestartArrangementPanel caseNo={dates.case_no} dates={dates} onObserved={observed} />);

  fireEvent.click(screen.getByRole('button', { name: '預覽正式安排' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('請明確指定');
  for (const day of dates.current_dates.slice(0, 2)) {
    fireEvent.change(screen.getByLabelText(`${day} 月嫂`), { target: { value: '12' } });
  }
  for (const day of dates.current_dates.slice(2)) {
    fireEvent.change(screen.getByLabelText(`${day} 月嫂`), { target: { value: '13' } });
  }
  fireEvent.click(screen.getByRole('button', { name: '預覽正式安排' }));
  await waitFor(() => expect(calls.preview).toHaveBeenCalledWith(
    dates.case_no,
    [
      { staff_id: 12, service_dates: dates.current_dates.slice(0, 2) },
      { staff_id: 13, service_dates: dates.current_dates.slice(2) },
    ],
  ));
  fireEvent.click(await screen.findByRole('button', { name: '建立正式安排' }));
  await waitFor(() => expect(observed).toHaveBeenCalledWith({
    ...dates, scheduling_version: 8, arrangement_pending: false,
  }));
});

it('套用結果不明時保留原冪等鍵重試，不建立第二個安排命令', async () => {
  const single = {
    ...dates,
    bound_staff: [dates.bound_staff[0]],
  };
  calls.preview.mockResolvedValue({
    case_no: single.case_no,
    order_version: 3,
    scheduling_version: 7,
    confirmed_version: 2,
    segments: [{
      staff_id: 12,
      assigned_start_date: '2026-09-06',
      assigned_end_date: '2026-09-11',
      service_dates: single.current_dates,
    }],
    preview_fingerprint: 'b'.repeat(64),
  });
  calls.apply.mockRejectedValueOnce(new Error('網路中斷')).mockResolvedValue({
    case_no: single.case_no,
    scheduling_version: 8,
    generation_number: 5,
    assignment_ids: [101],
    preview_fingerprint: 'b'.repeat(64),
  });
  calls.query.mockResolvedValue({ ...single, scheduling_version: 8, arrangement_pending: false });
  render(<HistoricalRestartArrangementPanel caseNo={single.case_no} dates={single} onObserved={vi.fn()} />);
  fireEvent.click(screen.getByRole('button', { name: '預覽正式安排' }));
  fireEvent.click(await screen.findByRole('button', { name: '建立正式安排' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('網路中斷');
  fireEvent.click(screen.getByRole('button', { name: '以原操作確認結果' }));
  await waitFor(() => expect(calls.apply).toHaveBeenCalledTimes(2));
  expect(calls.apply.mock.calls[0][2].idempotencyKey).toBe(calls.apply.mock.calls[1][2].idempotencyKey);
});
