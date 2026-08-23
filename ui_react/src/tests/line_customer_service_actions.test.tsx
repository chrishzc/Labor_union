/**
 * File: line_customer_service_actions.test.tsx
 * Description: 驗證客服操作元件依最新版本接手工單並建立可選結案的 durable LINE 回覆任務。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { adaptCustomerServiceDetail } from '../adapters/customer_service/customer_service_adapter';
import type { CustomerServiceActionsClient } from '../api/customer_service/customer_service_client';
import { LineCustomerServiceActions } from '../components/LineCustomerServiceActions';
import { CUSTOMER_SERVICE_DETAIL_FIXTURE } from './fixtures/customer_service/customer_service_contract_fixtures';

afterEach(() => vi.restoreAllMocks());

describe('LINE 客服完整操作面板', () => {
  it('waiting 工單可接手，再以更新後版本建立 LINE 回覆並結案', async () => {
    const waitingDetail = {
      ...CUSTOMER_SERVICE_DETAIL_FIXTURE,
      ticket: {
        ...CUSTOMER_SERVICE_DETAIL_FIXTURE.ticket,
        status: 'waiting' as const,
        version: 1,
      },
    };
    const handlingDetail = {
      ...waitingDetail,
      ticket: { ...waitingDetail.ticket, status: 'handling' as const, version: 2 },
    };
    const resolvedDetail = {
      ...handlingDetail,
      ticket: { ...handlingDetail.ticket, status: 'resolved' as const, version: 3 },
    };
    const updateTicket = vi.fn().mockResolvedValue(handlingDetail);
    const replyTicket = vi.fn().mockResolvedValue(resolvedDetail);
    const client: CustomerServiceActionsClient = { updateTicket, replyTicket };
    const onCommitted = vi.fn();

    render(
      <LineCustomerServiceActions
        detail={adaptCustomerServiceDetail(waitingDetail)}
        client={client}
        onCommitted={onCommitted}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: '開始處理' }));
    await screen.findByText('工單已進入處理中。');
    expect(updateTicket).toHaveBeenCalledWith(
      31,
      expect.objectContaining({
        status: 'handling',
        expected_version: 1,
        idempotency_key: expect.stringMatching(/^line-ticket-handling-/),
      }),
      expect.objectContaining({ signal: expect.any(AbortSignal) })
    );

    fireEvent.change(screen.getByRole('textbox', { name: 'LINE 回覆內容' }), {
      target: { value: '工會已完成處理，謝謝您的等候。' },
    });
    fireEvent.click(screen.getByRole('checkbox', { name: '回覆後結案' }));
    fireEvent.click(screen.getByRole('button', { name: '建立 LINE 回覆發送任務' }));

    await screen.findByText('LINE 回覆已排入發送佇列，工單已結案。');
    expect(replyTicket).toHaveBeenCalledWith(
      31,
      expect.objectContaining({
        resolve: true,
        expected_version: 2,
        idempotency_key: expect.stringMatching(/^line-ticket-reply-/),
      }),
      expect.objectContaining({ signal: expect.any(AbortSignal) })
    );
    expect(updateTicket.mock.calls[0][1].idempotency_key).not.toBe(
      replyTicket.mock.calls[0][1].idempotency_key
    );
    await waitFor(() => expect(onCommitted).toHaveBeenCalledTimes(2));
  });

  it('備註未變更或回覆空白時不允許送出，修改後以同狀態更新', async () => {
    const updatedDetail = {
      ...CUSTOMER_SERVICE_DETAIL_FIXTURE,
      ticket: {
        ...CUSTOMER_SERVICE_DETAIL_FIXTURE.ticket,
        internal_note: '持續追蹤客戶資料',
        version: 5,
      },
    };
    const updateTicket = vi.fn().mockResolvedValue(updatedDetail);
    const client: CustomerServiceActionsClient = {
      updateTicket,
      replyTicket: vi.fn(),
    };
    render(
      <LineCustomerServiceActions
        detail={adaptCustomerServiceDetail(CUSTOMER_SERVICE_DETAIL_FIXTURE)}
        client={client}
      />
    );

    expect(screen.getByRole('button', { name: '儲存內部備註' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '建立 LINE 回覆發送任務' })).toBeDisabled();
    fireEvent.change(screen.getByRole('textbox', { name: '內部備註' }), {
      target: { value: '持續追蹤客戶資料' },
    });
    fireEvent.click(screen.getByRole('button', { name: '儲存內部備註' }));
    await screen.findByText('內部備註已更新。');
    expect(updateTicket).toHaveBeenCalledWith(
      31,
      expect.objectContaining({ status: 'handling', expected_version: 4 }),
      expect.any(Object)
    );
  });
});
