import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { paymentDestinationClient } from '../api/client_finance/payment_destination_client';
import { PaymentDestinationConfigurationPanel } from '../components/PaymentDestinationConfigurationPanel';

vi.mock('../api/client_finance/payment_destination_client', () => ({
  paymentDestinationClient: { query: vi.fn(), preview: vi.fn(), apply: vi.fn() },
}));

describe('PaymentDestinationConfigurationPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(paymentDestinationClient.query)
      .mockResolvedValueOnce({ configured: false, account_display: null, revision: 0 })
      .mockResolvedValueOnce({ configured: true, account_display: '822-123456789', revision: 1 });
    vi.mocked(paymentDestinationClient.preview).mockResolvedValue({
      current: { configured: false, account_display: null, revision: 0 },
      candidate_account_display: '822-123456789', expected_revision: 0, preview_fingerprint: 'a'.repeat(64),
    });
    vi.mocked(paymentDestinationClient.apply).mockResolvedValue({ account_display: '822-123456789', resulting_revision: 1, preview_fingerprint: 'a'.repeat(64) });
  });

  it('requires preview and explicit confirmation before applying the union collection account', async () => {
    render(<PaymentDestinationConfigurationPanel reload={0} />);
    const input = await screen.findByLabelText('工會／代收付帳戶');
    fireEvent.change(input, { target: { value: '822-123456789' } });
    fireEvent.click(screen.getByRole('button', { name: '檢查設定影響' }));
    await screen.findByText('契約將顯示：822-123456789');
    expect(paymentDestinationClient.apply).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText('更新原因'), { target: { value: '建立正式代收付帳戶' } });
    fireEvent.click(screen.getByLabelText('我已核對帳戶內容，確認套用'));
    fireEvent.click(screen.getByRole('button', { name: '確認更新帳戶' }));
    await waitFor(() => expect(paymentDestinationClient.apply).toHaveBeenCalledTimes(1));
    expect(await screen.findByText(/已更新/)).toBeInTheDocument();
  });
});
