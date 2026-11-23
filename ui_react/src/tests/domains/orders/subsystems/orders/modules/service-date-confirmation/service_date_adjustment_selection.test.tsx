import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { OrderServiceDateAdjustment } from '../../../../../../../components/OrderServiceDateAdjustment';
import type { ServiceDateAdjustmentQuery } from '../../../../../../../api/orders/order_mutation_schemas';

const mutations = vi.hoisted(() => ({ preview: vi.fn(), apply: vi.fn() }));
vi.mock('../../../../../../../api/orders/order_mutation_client', () => ({
  previewServiceDateAdjustment: mutations.preview,
  applyServiceDateAdjustment: mutations.apply,
}));

type Day = ServiceDateAdjustmentQuery['days'][number];
const first: Day = { service_date: '2026-10-01', staff_id: 3, hours_override: 4, service_hours: 4 };
const second: Day = { ...first, service_date: '2026-10-02' };
const independent: Day = { ...first, service_date: '2026-10-03' };
const other: Day = { ...first, service_date: '2026-10-04' };
const original: Day = { ...first, service_date: '2026-10-05', hours_override: null, service_hours: 8 };
const merged: Day = { ...first, service_date: '2026-10-06', hours_override: 8, service_hours: 8 };
const query: ServiceDateAdjustmentQuery = {
  days: [first, second, independent, other],
  staff: [{ staff_id: 3, staff_name: '陳月嫂' }],
  pairs: [{ receipt_id: 41, removed: [original], inserted: [first, second] }],
  total_hours: 16,
  contracted_daily_hours: 8,
  first_schedule_days: [],
};
const preview = {
  order_version: 1, scheduling_version: 5, confirmed_version: null, preview_fingerprint: 'a'.repeat(64),
  removed: [independent, other], inserted: [merged],
};

beforeEach(() => {
  mutations.preview.mockReset().mockResolvedValue(preview);
  mutations.apply.mockReset().mockResolvedValue({ receipt_id: 42, scheduling_version: 6, confirmed_version: null });
});

function editor() {
  render(<OrderServiceDateAdjustment caseNo="ADJUST-SELECTION" query={query}
    onCancel={vi.fn()} onSaved={vi.fn().mockResolvedValue(undefined)} />);
  return within(screen.getByRole('group', { name: '合併或分裂日期' }));
}

function chooseTarget(adjust: ReturnType<typeof editor>) {
  fireEvent.change(adjust.getByLabelText('目標日期 1'), { target: { value: merged.service_date } });
  fireEvent.change(adjust.getByRole('combobox', { name: /^月嫂 1/ }), { target: { value: '3' } });
}

it('離開復原配對後只合併新選取的兩個服務日', async () => {
  const adjust = editor();
  fireEvent.click(adjust.getByRole('button', { name: `服務日期 ${first.service_date}` }));
  expect(adjust.getByRole('region', { name: '復原原來的服務日期' })).toBeInTheDocument();

  fireEvent.click(adjust.getByRole('button', { name: `服務日期 ${independent.service_date}` }));
  expect(adjust.queryByRole('region', { name: '復原原來的服務日期' })).not.toBeInTheDocument();
  for (const day of [first, second]) {
    expect(adjust.getByRole('button', { name: `服務日期 ${day.service_date}` })).toHaveAttribute('aria-pressed', 'false');
  }
  expect(adjust.getByRole('button', { name: '儲存日期調整' })).toBeDisabled();

  fireEvent.click(adjust.getByRole('button', { name: `服務日期 ${other.service_date}` }));
  chooseTarget(adjust);
  fireEvent.click(adjust.getByRole('button', { name: '儲存日期調整' }));
  await waitFor(() => expect(mutations.apply).toHaveBeenCalledTimes(1));
  expect(mutations.preview).toHaveBeenCalledWith('ADJUST-SELECTION', {
    source_dates: [independent.service_date, other.service_date],
    targets: [{ service_date: merged.service_date, staff_id: 3 }], reverse_receipt_id: null,
  });
});

it.each([first.service_date, second.service_date])('選取 %s 仍可復原整組分裂日期', async source => {
  mutations.preview.mockResolvedValue({ ...preview, removed: [first, second], inserted: [original] });
  const adjust = editor();
  fireEvent.click(adjust.getByRole('button', { name: `服務日期 ${source}` }));
  for (const day of [first, second]) {
    expect(adjust.getByRole('button', { name: `服務日期 ${day.service_date}` })).toHaveAttribute('aria-pressed', 'true');
  }
  expect(adjust.getByRole('region', { name: '復原原來的服務日期' })).toHaveTextContent(original.service_date);
  fireEvent.click(adjust.getByRole('button', { name: '儲存日期調整' }));
  await waitFor(() => expect(mutations.apply).toHaveBeenCalledTimes(1));
  expect(mutations.preview).toHaveBeenCalledWith('ADJUST-SELECTION', {
    source_dates: [source], targets: [], reverse_receipt_id: 41,
  });
});

it('指定新日期時可合併一個分裂結果與另一個服務日', async () => {
  const adjust = editor();
  fireEvent.click(adjust.getByRole('button', { name: `服務日期 ${first.service_date}` }));
  fireEvent.click(adjust.getByRole('button', { name: '改為指定新日期' }));
  fireEvent.click(adjust.getByRole('button', { name: `服務日期 ${independent.service_date}` }));
  expect(adjust.queryByRole('region', { name: '復原原來的服務日期' })).not.toBeInTheDocument();
  chooseTarget(adjust);
  fireEvent.click(adjust.getByRole('button', { name: '儲存日期調整' }));
  await waitFor(() => expect(mutations.apply).toHaveBeenCalledTimes(1));
  expect(mutations.preview).toHaveBeenCalledWith('ADJUST-SELECTION', {
    source_dates: [first.service_date, independent.service_date],
    targets: [{ service_date: merged.service_date, staff_id: 3 }], reverse_receipt_id: null,
  });
});
