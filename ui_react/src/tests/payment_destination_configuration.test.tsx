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
    window.alert = vi.fn();
    vi.mocked(paymentDestinationClient.query)
      .mockResolvedValueOnce({ configured: false, account_display: null, revision: 0 })
      .mockResolvedValueOnce({ configured: true, account_display: '822-123456789', revision: 1 });
    vi.mocked(paymentDestinationClient.preview).mockResolvedValue({
      current: { configured: false, account_display: null, revision: 0 },
      candidate_account_display: '822-123456789', expected_revision: 0, preview_fingerprint: 'a'.repeat(64),
    });
    vi.mocked(paymentDestinationClient.apply).mockResolvedValue({ account_display: '822-123456789', resulting_revision: 1, preview_fingerprint: 'a'.repeat(64) });
  });

  it.each(['', '   ', '建立正式代收付帳戶'])('saves in one click with optional notes %j', async (note) => {
    render(<PaymentDestinationConfigurationPanel reload={0} />);
    const input = await screen.findByLabelText('工會／代收付帳戶');
    fireEvent.change(input, { target: { value: '822-123456789' } });
    fireEvent.change(screen.getByLabelText('備註（選填）'), { target: { value: note } });
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
    expect(paymentDestinationClient.apply).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: '儲存帳戶' }));
    await waitFor(() => expect(paymentDestinationClient.apply).toHaveBeenCalledOnce());
    expect(paymentDestinationClient.apply).toHaveBeenCalledWith(expect.objectContaining({ preview_fingerprint: 'a'.repeat(64) }), note.trim());
    expect(await screen.findByText(/已更新/)).toBeInTheDocument();
    expect(window.alert).not.toHaveBeenCalled();
  });
});
