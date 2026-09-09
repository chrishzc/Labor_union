import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { LineUnboundPairingWorkbench } from '../../../../../../components/LineUnboundPairingWorkbench';

describe('LINE 手動歸戶工作台', () => {
  it('遮罩敏感識別值，並要求核對兩側資料後才允許配對', async () => {
    const pairProvisionalRegistration = vi.fn().mockResolvedValue({
      case_no: 'CASE-101',
      client_id: 7,
      client_name: '王小美',
      line_user_id: 'U1234567890abcdef',
      status: 'bound',
    });
    const client = {
      listUnboundCandidates: vi.fn().mockResolvedValue({
        orders: [{
          case_no: 'CASE-101',
          client_id: 7,
          client_name: '王小美',
          client_phone: '0912345678',
          start_date: null,
          status: 'active',
        }],
        provisional_registrations: [{
          registration_id: 31,
          name: '王小美',
          phone: '0912345678',
          line_user_id: 'U1234567890abcdef',
          client_id: null,
          submitted_at: '2026-09-09T09:00:00+08:00',
        }],
      }),
      pairProvisionalRegistration,
    };

    render(<LineUnboundPairingWorkbench client={client} />);

    await screen.findByText('CASE-101');
    expect(screen.queryByText('0912345678')).not.toBeInTheDocument();
    expect(screen.getAllByText('09••••678')).toHaveLength(2);

    const orderTable = screen.getByRole('table', { name: '尚未綁定 LINE 的訂單' });
    const provisionalTable = screen.getByRole('table', { name: '待配對的 LINE 產婦登記' });
    fireEvent.click(within(orderTable).getByRole('button', { name: '選取' }));
    fireEvent.click(within(provisionalTable).getByRole('button', { name: '選取' }));

    expect(screen.getByText('U123••••••cdef')).toBeInTheDocument();
    const submit = screen.getByRole('button', { name: '確認手動配對並綁定' });
    expect(submit).toBeDisabled();

    fireEvent.click(screen.getByRole('checkbox', { name: /我已核對兩側姓名/ }));
    expect(submit).toBeEnabled();
    fireEvent.click(submit);

    await waitFor(() => expect(pairProvisionalRegistration).toHaveBeenCalledTimes(1));
    expect(pairProvisionalRegistration).toHaveBeenCalledWith(expect.objectContaining({
      provisional_registration_id: 31,
      target_case_no: 'CASE-101',
    }));
  });
});
