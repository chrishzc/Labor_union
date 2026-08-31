/**
 * File: order_service_completion_actions.test.tsx
 * Description: 驗證 Orders 服務完成的business-first Preview／Confirm／Apply與closed error。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiHttpError } from '../api/shared/typed_errors';
import { orderServiceCompletionClient } from '../api/orders/order_service_completion_client';
import { OrderServiceCompletionActions } from '../components/OrderServiceCompletionActions';

vi.mock('../api/orders/order_service_completion_client', () => ({
  orderServiceCompletionClient: { preview: vi.fn(), apply: vi.fn() },
}));

const preview = {
  case_no: 'CASE-001',
  expected_order_version: 4,
  resulting_order_version: 5,
  current_status: '服務中',
  completion_instant: '2026-08-31T10:00:00+08:00',
  evaluation_at: '2026-08-31T10:00:00+08:00',
  official_service_dates: ['2026-08-30', '2026-08-31'],
  fingerprint: 'a'.repeat(64),
};

const receipt = {
  case_no: 'CASE-001',
  idempotency_key: 'completion-key',
  order_version: 5,
  lifecycle_event_id: 77,
  completion_instant: preview.completion_instant,
  evaluation_at: preview.evaluation_at,
  command_fingerprint: 'b'.repeat(64),
};

describe('OrderServiceCompletionActions', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(orderServiceCompletionClient.preview).mockResolvedValue(preview);
    vi.mocked(orderServiceCompletionClient.apply).mockResolvedValue(receipt);
  });

  it('keeps non-service cases read-only with business guidance', () => {
    render(<OrderServiceCompletionActions caseNo="CASE-001" orderStatus="訂單完成" onCompleted={vi.fn()} />);
    expect(screen.getByText(/客戶帳務與服務人員款項流程/)).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/Client Finance|Staff Payables|owner|lifecycle controls/i);
    expect(orderServiceCompletionClient.preview).not.toHaveBeenCalled();
  });

  it('preserves Preview confirmation gating and completion readback', async () => {
    const onCompleted = vi.fn();
    render(<OrderServiceCompletionActions caseNo="CASE-001" orderStatus="服務中" onCompleted={onCompleted} />);
    expect(screen.getByText(/核對正式排班/)).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/lifecycle controls|fingerprint|idempotency|receipt/i);

    fireEvent.click(screen.getByRole('button', { name: '檢查服務完成影響' }));
    await screen.findByText('服務完成內容已檢查');
    const apply = screen.getByRole('button', { name: '確認套用服務完成' });
    expect(apply).toBeDisabled();
    fireEvent.change(screen.getByLabelText('完工確認原因'), { target: { value: '已核對最後服務日' } });
    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.click(apply);

    await screen.findByText('服務完成已登記並完成回讀。');
    expect(orderServiceCompletionClient.apply).toHaveBeenCalledWith('CASE-001', preview, '已核對最後服務日', expect.any(String));
    await waitFor(() => expect(onCompleted).toHaveBeenCalledOnce());
  });

  it('fails closed without exposing provider error details', async () => {
    vi.mocked(orderServiceCompletionClient.preview).mockRejectedValueOnce(
      new ApiHttpError(500, 'orders_backend_failed', 'raw SQL connection failed', true),
    );
    render(<OrderServiceCompletionActions caseNo="CASE-001" orderStatus="服務中" onCompleted={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: '檢查服務完成影響' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('服務完成處理暫時無法使用');
    expect(screen.getByRole('alert')).not.toHaveTextContent(/orders_backend_failed|raw SQL/i);
  });
});
