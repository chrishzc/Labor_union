import { useState } from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { OrderActualStartPanel } from '../../../../../../../components/OrderActualStartPanel';
import { ordersQueryClient } from '../../../../../../../api/orders/order_query_client';
import { orderActualStartClient } from '../../../../../../../api/orders/order_actual_start_client';
import { ApiHttpError } from '../../../../../../../api/shared/typed_errors';
import { orderMutationFlowStore } from '../../../../../../../adapters/orders/order_mutation_flow_store';
import { UnsavedChangesProvider, useUnsavedNavigation } from '../../../../../../../components/UnsavedChanges';

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
  fireEvent.change(await screen.findByLabelText('更正實際開始日期'), { target: { value: '2026-09-15' } });
  fireEvent.click(await screen.findByRole('button', { name: '儲存實際開始日' }));
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
  fireEvent.change(await screen.findByLabelText('更正實際開始日期'), { target: { value: '2026-09-15' } });
  fireEvent.click(screen.getByRole('button', { name: '儲存實際開始日' }));
  fireEvent.click(await screen.findByRole('button', { name: '以原操作重新確認實際開始日' }));

  expect(await screen.findByText('實際開始日已完成正式回讀：2026-09-15')).toBeInTheDocument();
  expect(apply).toHaveBeenCalledTimes(1);
});

function setupDateOnly(caseNo: string) {
  const facts = {
    case_no: caseNo, current_actual_start_date: null, planned_start_date: '2026-09-14',
    service_data_locked: false, order_version: 1, scheduling_version: null,
    scheduling_generation: null, client_finance_version: null, payroll_version: null,
    has_formal_assignments: false,
  };
  const query = vi.spyOn(ordersQueryClient, 'getActualStart').mockResolvedValue(facts);
  vi.spyOn(orderActualStartClient, 'preview').mockResolvedValue({
    ...facts, operation: 'date_only', before_actual_start_date: null,
    after_actual_start_date: '2026-09-15', preview_fingerprint: 'c'.repeat(64),
  });
  return { facts, query, apply: vi.spyOn(orderActualStartClient, 'apply') };
}

async function startSave() {
  fireEvent.click(screen.getByRole('button', { name: '讀取實際開始日' }));
  fireEvent.change(await screen.findByLabelText('更正實際開始日期'), { target: { value: '2026-09-15' } });
  fireEvent.click(screen.getByRole('button', { name: '儲存實際開始日' }));
}

it('unlocks after a definite database constraint rejection', async () => {
  const { apply } = setupDateOnly('CONSTRAINT-REJECT');
  apply.mockRejectedValue(new ApiHttpError(422, 'actual_start_persistence_constraint_violation', '本次未套用'));
  const onBusyChange = vi.fn();
  render(<OrderActualStartPanel caseNo="CONSTRAINT-REJECT" onBusyChange={onBusyChange} />);
  await startSave();
  expect(await screen.findByRole('alert')).toHaveTextContent('本次未套用');
  expect(screen.getByRole('button', { name: '讀取實際開始日' })).toBeEnabled();
  expect(orderMutationFlowStore.getActualStart('CONSTRAINT-REJECT')).toBeUndefined();
  expect(onBusyChange).toHaveBeenLastCalledWith(false);
});

it('releases an old unknown operation when same-key recovery confirms a constraint rejection', async () => {
  const { apply } = setupDateOnly('CONSTRAINT-RECOVER');
  apply.mockRejectedValueOnce(new Error('connection lost'))
    .mockRejectedValueOnce(new ApiHttpError(422, 'actual_start_persistence_constraint_violation', '本次未套用'));
  render(<OrderActualStartPanel caseNo="CONSTRAINT-RECOVER" />);
  await startSave();
  fireEvent.click(await screen.findByRole('button', { name: '以原操作重新確認實際開始日' }));
  await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('本次未套用'));
  expect(apply.mock.calls[1]).toEqual(apply.mock.calls[0]);
  expect(screen.getByRole('button', { name: '讀取實際開始日' })).toBeEnabled();
  expect(orderMutationFlowStore.getActualStart('CONSTRAINT-RECOVER')).toBeUndefined();
});

it('keeps the original command blocked when recovery is denied before its result is known', async () => {
  const { apply } = setupDateOnly('UNKNOWN-FORBIDDEN');
  apply.mockRejectedValueOnce(new Error('connection lost'))
    .mockRejectedValueOnce(new ApiHttpError(403, 'forbidden', '權限不足'));
  render(<OrderActualStartPanel caseNo="UNKNOWN-FORBIDDEN" />);
  await startSave();
  fireEvent.click(await screen.findByRole('button', { name: '以原操作重新確認實際開始日' }));
  await waitFor(() => expect(apply).toHaveBeenCalledTimes(2));
  expect(await screen.findByRole('alert')).toHaveTextContent('結果仍未確認');
  expect(orderMutationFlowStore.getActualStart('UNKNOWN-FORBIDDEN')?.status).toBe('outcome_unknown');
  expect(screen.getByRole('button', { name: '讀取實際開始日' })).toBeDisabled();
});

it('does not invent an empty reason change and supports saving from the leave dialog', async () => {
  const { facts, query, apply } = setupDateOnly('SAVE-LEAVE');
  query.mockResolvedValueOnce(facts).mockResolvedValue({ ...facts, current_actual_start_date: '2026-09-15', order_version: 2 });
  apply.mockResolvedValue({
    operation: 'date_only', case_no: 'SAVE-LEAVE', actual_start_date: '2026-09-15',
    order_version: 2, scheduling_version: null, scheduling_generation: null,
    client_finance_version: null, payroll_version: null,
    preview_fingerprint: 'c'.repeat(64), changed: true,
  });
  const leave = vi.fn();
  function Page() {
    const { requestLeave } = useUnsavedNavigation();
    return <><OrderActualStartPanel caseNo="SAVE-LEAVE" /><button onClick={() => requestLeave(leave)}>離開案件</button></>;
  }
  render(<UnsavedChangesProvider><Page /></UnsavedChangesProvider>);
  fireEvent.click(screen.getByRole('button', { name: '讀取實際開始日' }));
  const input = await screen.findByLabelText('更正實際開始日期');
  fireEvent.click(screen.getByRole('button', { name: '離開案件' }));
  expect(leave).toHaveBeenCalledTimes(1);
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  fireEvent.change(input, { target: { value: '2026-09-15' } });
  fireEvent.change(screen.getByLabelText('原因（選填）'), { target: { value: '客戶確認日期' } });
  fireEvent.click(screen.getByRole('button', { name: '離開案件' }));
  fireEvent.click(await screen.findByRole('button', { name: '儲存變更並離開' }));
  await waitFor(() => expect(leave).toHaveBeenCalledTimes(2));
  expect(apply).toHaveBeenCalledTimes(1);
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
});

it('allows leaving an unknown outcome and reopening it with the original command', async () => {
  const { apply } = setupDateOnly('DEFER-UNKNOWN');
  let rejectApply!: (error: Error) => void;
  apply.mockImplementationOnce(() => new Promise((_, reject) => { rejectApply = reject; }))
    .mockRejectedValue(new Error('still unavailable'));
  function Page() {
    const [open, setOpen] = useState(true);
    const { requestLeave } = useUnsavedNavigation();
    return open
      ? <OrderActualStartPanel caseNo="DEFER-UNKNOWN" onLeavePending={() => requestLeave(() => setOpen(false))} />
      : <button onClick={() => setOpen(true)}>重新開啟案件</button>;
  }
  render(<UnsavedChangesProvider><Page /></UnsavedChangesProvider>);
  await startSave();
  await waitFor(() => expect(apply).toHaveBeenCalledTimes(1));
  expect(screen.queryByRole('button', { name: '保留原操作並返回待辦看板' })).not.toBeInTheDocument();
  await act(async () => rejectApply(new Error('connection lost')));
  const original = orderMutationFlowStore.getActualStart('DEFER-UNKNOWN')?.command;
  fireEvent.click(await screen.findByRole('button', { name: '保留原操作並返回待辦看板' }));
  const discard = await screen.findByRole('button', { name: '捨棄變更並離開' });
  expect(discard).toBeEnabled();
  fireEvent.click(discard);
  expect(orderMutationFlowStore.getActualStart('DEFER-UNKNOWN')?.command).toBe(original);
  fireEvent.click(await screen.findByRole('button', { name: '重新開啟案件' }));
  fireEvent.click(await screen.findByRole('button', { name: '以原操作重新確認實際開始日' }));
  await waitFor(() => expect(apply).toHaveBeenCalledTimes(2));
  await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('結果仍未確認'));
  expect(apply.mock.calls[1]).toEqual(apply.mock.calls[0]);
});
