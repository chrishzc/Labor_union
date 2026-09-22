import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { OrderActualStartPanel } from '../../../../../../../components/OrderActualStartPanel';
import { ordersQueryClient } from '../../../../../../../api/orders/order_query_client';
import { orderActualStartClient } from '../../../../../../../api/orders/order_actual_start_client';
import { ApiHttpError } from '../../../../../../../api/shared/typed_errors';

afterEach(() => vi.restoreAllMocks());

it('explains the planned-date bootstrap and routes back to service-date confirmation', async () => {
  vi.spyOn(ordersQueryClient, 'getActualStart').mockResolvedValue({
    case_no: 'MOCK-1', current_actual_start_date: null, planned_start_date: '2026-09-14',
    service_data_locked: false, order_version: 1, scheduling_version: 0,
    scheduling_generation: 0, client_finance_version: 0, payroll_version: 0,
  });
  vi.spyOn(orderActualStartClient, 'preview').mockRejectedValue(
    new ApiHttpError(409, 'scheduling_assignments_required', '實際開工日變更需要人員先處理阻擋原因。'),
  );
  const apply = vi.spyOn(orderActualStartClient, 'apply');
  const onOpenServiceDates = vi.fn();
  render(<OrderActualStartPanel caseNo="MOCK-1" onOpenServiceDates={onOpenServiceDates} />);
  fireEvent.click(screen.getByRole('button', { name: '讀取實際開始日' }));
  fireEvent.click(await screen.findByRole('button', { name: '檢查實際開始日影響' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('尚未建立正式月嫂指派');
  expect(screen.getByRole('alert')).toHaveTextContent('請先以「計畫開始日」精算並確認正式服務日期');
  expect(screen.getByRole('alert')).toHaveTextContent('系統會一併重排服務日期與排班');
  expect(screen.getByRole('alert')).toHaveTextContent('本次未變更日期');
  fireEvent.click(screen.getByRole('button', { name: '前往精算並確認服務日期' }));
  expect(onOpenServiceDates).toHaveBeenCalledOnce();
  expect(screen.queryByRole('button', { name: '確認實際開始日' })).not.toBeInTheDocument();
  expect(apply).not.toHaveBeenCalled();
});
