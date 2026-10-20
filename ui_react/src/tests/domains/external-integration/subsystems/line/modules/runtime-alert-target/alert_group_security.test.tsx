import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { AlertGroupSecurity, type RuntimeTargetClient } from '../../../../../../../pages/line_management/AlertGroupSecurity';

const rules = {
  customer_service: true, dispatch_matching: true, staff_leave_urgent: true,
  system_health: false, contract_signing: true,
};

function client(): RuntimeTargetClient {
  return {
    listTargets: vi.fn().mockResolvedValue([{
      target_id: 7, target_kind: 'group', display_label: '隔離測試群組', state: 'active',
      minimum_status: 'warning', current_version: 'version-7', updated_at: '2026-10-19T00:00:00Z',
    }]),
    getPreferences: vi.fn().mockResolvedValue(rules),
    updatePreferences: vi.fn(), previewResetGroup: vi.fn(), resetGroup: vi.fn(),
    previewSetEnabled: vi.fn(), setEnabled: vi.fn(),
  };
}

describe('fixed alert group rules', () => {
  it('ignores legacy cached choices and retains previews without editing or saving', async () => {
    localStorage.setItem('line_alert_msg_categories', JSON.stringify({ ...rules, system_health: true }));
    const targetClient = client();
    const { unmount } = render(<AlertGroupSecurity client={targetClient} />);
    await waitFor(() => expect(targetClient.getPreferences).toHaveBeenCalledWith(7, expect.anything()));
    await waitFor(() => expect(screen.queryByText('正在載入群組推播規則…')).not.toBeInTheDocument());
    const section = screen.getByRole('region', { name: '群組訊息推播分類與即時預覽' });
    expect(within(section).queryByRole('checkbox')).not.toBeInTheDocument();
    expect(within(section).getAllByText('固定規則')).toHaveLength(5);
    expect(within(section).getAllByText('⚪ 已過濾 (不發送)')).toHaveLength(1);
    fireEvent.click(within(section).getAllByRole('button', { name: /檢視群組訊息效果/ })[3]);
    expect(targetClient.updatePreferences).not.toHaveBeenCalled();
    expect(targetClient.setEnabled).not.toHaveBeenCalled();
    expect(JSON.parse(localStorage.getItem('line_alert_msg_categories')!).system_health).toBe(true);
    unmount();
    localStorage.removeItem('line_alert_msg_categories');
  });

  it('reports a failed rules read without claiming it saved preferences', async () => {
    const targetClient = client();
    vi.mocked(targetClient.getPreferences!).mockRejectedValue(new Error('unavailable'));
    render(<AlertGroupSecurity client={targetClient} />);
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());
    expect(screen.queryByText(/已儲存|同步儲存至資料庫/)).not.toBeInTheDocument();
    expect(targetClient.updatePreferences).not.toHaveBeenCalled();
  });
});
