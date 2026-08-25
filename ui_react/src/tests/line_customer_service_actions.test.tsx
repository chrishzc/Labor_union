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

const UPDATE_FINGERPRINT = 'a'.repeat(64);
const REPLY_FINGERPRINT = 'b'.repeat(64);

describe('LINE 客服完整操作面板', () => {
  it('waiting 工單以 Preview／Apply 接手，再以更新後版本建立 LINE 回覆並結案', async () => {
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
    const previewUpdate = vi.fn().mockResolvedValue({
      ticket_id: 31,
      before_status: 'waiting',
      after_status: 'handling',
      current_version: 1,
      expected_version: 1,
      blockers: [],
      preview_fingerprint: UPDATE_FINGERPRINT,
      apply_ready: true,
    });
    const applyUpdate = vi.fn().mockResolvedValue({
      ticket_id: 31,
      resulting_status: 'handling',
      resulting_version: 2,
      preview_fingerprint: UPDATE_FINGERPRINT,
      replayed: false,
      readback: handlingDetail,
    });
    const previewReply = vi.fn().mockResolvedValue({
      ticket_id: 31,
      before_status: 'handling',
      after_status: 'resolved',
      current_version: 2,
      expected_version: 2,
      reply_character_count: 17,
      will_enqueue_delivery: true,
      preview_fingerprint: REPLY_FINGERPRINT,
      apply_ready: true,
    });
    const applyReply = vi.fn().mockResolvedValue({
      ticket_id: 31,
      resulting_status: 'resolved',
      resulting_version: 3,
      preview_fingerprint: REPLY_FINGERPRINT,
      delivery_enqueued: true,
      delivery_delivered: false,
      replayed: false,
      readback: resolvedDetail,
    });
    const client: CustomerServiceActionsClient = {
      previewUpdate,
      applyUpdate,
      previewReply,
      applyReply,
    };
    const onCommitted = vi.fn();

    render(
      <LineCustomerServiceActions
        detail={adaptCustomerServiceDetail(waitingDetail)}
        client={client}
        onCommitted={onCommitted}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: '預覽開始處理' }));
    await screen.findByText('待處理 → 處理中');
    expect(applyUpdate).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('checkbox', { name: '我已確認狀態與備註內容' }));
    fireEvent.click(screen.getByRole('button', { name: '確認套用客服操作' }));
    await screen.findByText('工單已進入處理中。');
    expect(previewUpdate).toHaveBeenCalledWith(
      31,
      expect.objectContaining({
        status: 'handling',
        expected_version: 1,
      }),
      expect.objectContaining({
        signal: expect.any(AbortSignal),
        correlationId: expect.stringMatching(/^line-ticket-handling-preview-/),
      })
    );
    expect(applyUpdate).toHaveBeenCalledWith(
      31,
      expect.objectContaining({
        status: 'handling',
        expected_version: 1,
        preview_fingerprint: UPDATE_FINGERPRINT,
      }),
      expect.objectContaining({
        idempotencyKey: expect.stringMatching(/^line-ticket-handling-apply-/),
      })
    );

    fireEvent.change(screen.getByRole('textbox', { name: 'LINE 回覆內容' }), {
      target: { value: '工會已完成處理，謝謝您的等候。' },
    });
    fireEvent.click(screen.getByRole('checkbox', { name: '回覆後結案' }));
    fireEvent.click(screen.getByRole('button', { name: '預覽 LINE 回覆' }));
    await screen.findByText('處理中 → 已結案');
    expect(applyReply).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('checkbox', { name: '我已確認回覆內容與工單狀態' }));
    fireEvent.click(screen.getByRole('button', { name: '確認建立 LINE 回覆任務' }));

    await screen.findByText('客服回覆已保存並建立 delivery task，工單已結案；LINE 尚未送達。');
    expect(previewReply).toHaveBeenCalledWith(
      31,
      expect.objectContaining({ resolve: true, expected_version: 2 }),
      expect.objectContaining({ correlationId: expect.stringMatching(/^line-ticket-reply-preview-/) })
    );
    expect(applyReply).toHaveBeenCalledWith(
      31,
      expect.objectContaining({
        resolve: true,
        expected_version: 2,
        idempotency_key: expect.stringMatching(/^line-ticket-reply-apply-/),
        preview_fingerprint: REPLY_FINGERPRINT,
      }),
      expect.objectContaining({ signal: expect.any(AbortSignal) })
    );
    await waitFor(() => expect(onCommitted).toHaveBeenCalledTimes(2));
  });

  it('備註與回覆空白時不允許預覽，修改後以同狀態 Preview／Apply', async () => {
    const updatedDetail = {
      ...CUSTOMER_SERVICE_DETAIL_FIXTURE,
      ticket: {
        ...CUSTOMER_SERVICE_DETAIL_FIXTURE.ticket,
        internal_note: '持續追蹤客戶資料',
        version: 5,
      },
    };
    const previewUpdate = vi.fn().mockResolvedValue({
      ticket_id: 31,
      before_status: 'handling',
      after_status: 'handling',
      current_version: 4,
      expected_version: 4,
      blockers: [],
      preview_fingerprint: UPDATE_FINGERPRINT,
      apply_ready: true,
    });
    const applyUpdate = vi.fn().mockResolvedValue({
      ticket_id: 31,
      resulting_status: 'handling',
      resulting_version: 5,
      preview_fingerprint: UPDATE_FINGERPRINT,
      replayed: false,
      readback: updatedDetail,
    });
    const client: CustomerServiceActionsClient = {
      previewUpdate,
      applyUpdate,
      previewReply: vi.fn(),
      applyReply: vi.fn(),
    };
    render(
      <LineCustomerServiceActions
        detail={adaptCustomerServiceDetail(CUSTOMER_SERVICE_DETAIL_FIXTURE)}
        client={client}
      />
    );

    expect(screen.getByRole('button', { name: '預覽更新內部備註' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '預覽 LINE 回覆' })).toBeDisabled();
    fireEvent.change(screen.getByRole('textbox', { name: '內部備註' }), {
      target: { value: '持續追蹤客戶資料' },
    });
    fireEvent.click(screen.getByRole('button', { name: '預覽更新內部備註' }));
    await screen.findByText('處理中 → 處理中');
    fireEvent.click(screen.getByRole('checkbox', { name: '我已確認狀態與備註內容' }));
    fireEvent.click(screen.getByRole('button', { name: '確認套用客服操作' }));
    await screen.findByText('內部備註已更新。');
    expect(previewUpdate).toHaveBeenCalledWith(
      31,
      expect.objectContaining({ status: 'handling', expected_version: 4 }),
      expect.any(Object)
    );
    expect(applyUpdate).toHaveBeenCalledWith(
      31,
      expect.objectContaining({
        status: 'handling',
        expected_version: 4,
        preview_fingerprint: UPDATE_FINGERPRINT,
      }),
      expect.objectContaining({ idempotencyKey: expect.any(String) })
    );
    expect(screen.getByText(/客服工單已更新為「處理中」/)).toBeInTheDocument();
  });
});
