import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { OrderActualStartPanel } from '../../../../../../../components/OrderActualStartPanel';
import { ordersQueryClient } from '../../../../../../../api/orders/order_query_client';
import { orderActualStartClient } from '../../../../../../../api/orders/order_actual_start_client';

afterEach(() => vi.restoreAllMocks());

it('saves an actual start date before formal assignment without downstream roots', async () => {
  vi.spyOn(ordersQueryClient, 'getActualStart')
    .mockResolvedValueOnce({
    case_no: 'MOCK-1', current_actual_start_date: null, planned_start_date: '2026-09-14',
    service_data_locked: false, order_version: 1, scheduling_version: null,
    scheduling_generation: null, client_finance_version: null, payroll_version: null,
    has_formal_assignments: false,
  })
    .mockResolvedValueOnce({
      case_no: 'MOCK-1', current_actual_start_date: '2026-09-15', planned_start_date: '2026-09-14',
      service_data_locked: false, order_version: 2, scheduling_version: null,
      scheduling_generation: null, client_finance_version: null, payroll_version: null,
      has_formal_assignments: false,
    });
  vi.spyOn(orderActualStartClient, 'preview').mockResolvedValue({
    operation: 'date_only', case_no: 'MOCK-1', before_actual_start_date: null,
    after_actual_start_date: '2026-09-15', order_version: 1, scheduling_version: null,
    scheduling_generation: null, client_finance_version: null, payroll_version: null,
    preview_fingerprint: 'a'.repeat(64),
  });
  const apply = vi.spyOn(orderActualStartClient, 'apply').mockResolvedValue({
    operation: 'date_only', case_no: 'MOCK-1', actual_start_date: '2026-09-15',
    order_version: 2, scheduling_version: null, scheduling_generation: null,
    client_finance_version: null, payroll_version: null,
    preview_fingerprint: 'a'.repeat(64), changed: true,
  });
  const onOpenServiceDates = vi.fn();
  render(<OrderActualStartPanel caseNo="MOCK-1" onOpenServiceDates={onOpenServiceDates} />);
  fireEvent.click(screen.getByRole('button', { name: '讀取實際開始日' }));
  fireEvent.change(await screen.findByLabelText('Beta 實際開始日期'), { target: { value: '2026-09-15' } });
  fireEvent.click(await screen.findByRole('button', { name: '確認實際開始日' }));
  expect(await screen.findByText('實際開始日已完成正式回讀：2026-09-15')).toBeInTheDocument();
  expect(apply).toHaveBeenCalledWith('MOCK-1', {
    operation: 'date_only', new_actual_start_date: '2026-09-15',
    expected_order_version: 1, preview_fingerprint: 'a'.repeat(64),
  }, { idempotencyKey: expect.any(String) });
  expect(onOpenServiceDates).not.toHaveBeenCalled();
});

it('recovers a date-only unknown outcome by owner readback without a permanent receipt', async () => {
  vi.spyOn(ordersQueryClient, 'getActualStart')
    .mockResolvedValueOnce({
      case_no: 'MOCK-2', current_actual_start_date: null, planned_start_date: '2026-09-14',
      service_data_locked: false, order_version: 1, scheduling_version: null,
      scheduling_generation: null, client_finance_version: null, payroll_version: null,
      has_formal_assignments: false,
    })
    .mockResolvedValueOnce({
      case_no: 'MOCK-2', current_actual_start_date: '2026-09-15', planned_start_date: '2026-09-14',
      service_data_locked: false, order_version: 2, scheduling_version: null,
      scheduling_generation: null, client_finance_version: null, payroll_version: null,
      has_formal_assignments: false,
    });
  vi.spyOn(orderActualStartClient, 'preview').mockResolvedValue({
    operation: 'date_only', case_no: 'MOCK-2', before_actual_start_date: null,
    after_actual_start_date: '2026-09-15', order_version: 1, scheduling_version: null,
    scheduling_generation: null, client_finance_version: null, payroll_version: null,
    preview_fingerprint: 'b'.repeat(64),
  });
  const apply = vi.spyOn(orderActualStartClient, 'apply').mockRejectedValue(new Error('network lost after save'));
  render(<OrderActualStartPanel caseNo="MOCK-2" />);
  fireEvent.click(screen.getByRole('button', { name: '讀取實際開始日' }));
  fireEvent.change(await screen.findByLabelText('Beta 實際開始日期'), { target: { value: '2026-09-15' } });
  fireEvent.click(screen.getByRole('button', { name: '確認實際開始日' }));
  fireEvent.click(await screen.findByRole('button', { name: '以原操作重新確認實際開始日' }));

  expect(await screen.findByText('實際開始日已完成正式回讀：2026-09-15')).toBeInTheDocument();
  expect(apply).toHaveBeenCalledTimes(1);
});
