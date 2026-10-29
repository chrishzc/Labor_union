import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { paymentDestinationClient } from '../api/client_finance/payment_destination_client';
import { PaymentDestinationConfigurationPanel } from '../components/PaymentDestinationConfigurationPanel';
import { sessionClient } from '../api/auth/session_client';
import { transport } from '../api/shared/transport';
import { ApiDecodeError } from '../api/shared/typed_errors';

vi.mock('../api/client_finance/payment_destination_client', () => ({
  paymentDestinationClient: { query: vi.fn(), preview: vi.fn(), apply: vi.fn() },
}));

describe('Payment destination transport contract', () => {
  const destination = { configured: false, account_display: null, revision: 0 };
  afterEach(() => vi.restoreAllMocks());

  it.each([
    { success: true, message: 'Success' },
    { success: true, message: 'Success', data: null },
    { success: true, message: 'Success', data: { ...destination, revision: undefined } },
    { success: true, message: 'Success', data: { ...destination, unexpected: true } },
    { success: false, message: 'Rejected', data: destination },
  ])('rejects unusable destination envelopes', async (raw) => {
    const actual = await vi.importActual<typeof import('../api/client_finance/payment_destination_client')>('../api/client_finance/payment_destination_client');
    vi.spyOn(sessionClient, 'getToken').mockReturnValue('destination-test');
    vi.spyOn(transport, 'get').mockResolvedValue(raw);
    await expect(actual.paymentDestinationClient.query()).rejects.toBeInstanceOf(ApiDecodeError);
  });

  it('accepts an unconfigured destination without guessing an account', async () => {
    const actual = await vi.importActual<typeof import('../api/client_finance/payment_destination_client')>('../api/client_finance/payment_destination_client');
    vi.spyOn(sessionClient, 'getToken').mockReturnValue('destination-test');
    vi.spyOn(transport, 'get').mockResolvedValue({ success: true, message: 'Success', data: destination });
    expect(await actual.paymentDestinationClient.query()).toEqual(destination);
  });
});

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
    expect(paymentDestinationClient.apply).toHaveBeenCalledWith(expect.objectContaining({ preview_fingerprint: 'a'.repeat(64) }), note.trim(), expect.any(String));
    expect(await screen.findByText(/已更新/)).toBeInTheDocument();
    expect(window.alert).not.toHaveBeenCalled();
  });
});
