import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { AlertGroupSecurity, type RuntimeTargetClient } from '../../../../../../../pages/line_management/AlertGroupSecurity';

function client(): RuntimeTargetClient {
  return { listTargets: vi.fn().mockResolvedValue([{ target_id: 7, target_kind: 'group', display_label: '舊群組', state: 'active', minimum_status: 'warning', current_version: 'v7', updated_at: '2026-10-22' }]),
    getPreferences: vi.fn(), updatePreferences: vi.fn(), previewResetGroup: vi.fn(), resetGroup: vi.fn(), previewSetEnabled: vi.fn(), setEnabled: vi.fn() };
}
describe('retired group alerts', () => {
  it('hides legacy groups, registration guidance and simulated group messages without mutations', async () => {
    const api = client(); render(<AlertGroupSecurity client={api} />);
    await screen.findByText('目前沒有已設定的管理員通知對象。');
    expect(screen.queryByText('舊群組')).not.toBeInTheDocument();
    expect(screen.queryByText(/設定異常通知群組|群組訊息推播分類|檢視群組訊息效果/)).not.toBeInTheDocument();
    expect(api.getPreferences).not.toHaveBeenCalled(); expect(api.resetGroup).not.toHaveBeenCalled(); expect(api.setEnabled).not.toHaveBeenCalled();
  });
  it('reports failed reads without pretending no targets exist', async () => {
    const api = client(); vi.mocked(api.listTargets).mockRejectedValue(new Error('failure'));
    render(<AlertGroupSecurity client={api} />); await screen.findByRole('alert');
    expect(screen.queryByText('目前沒有已設定的管理員通知對象。')).not.toBeInTheDocument();
  });
  it('keeps admin preview/apply and readback on the existing writer', async () => {
    const api = client(); const target = { target_id: 8, target_kind: 'admin_user' as const, display_label: '管理員通知對象', state: 'active' as const, minimum_status: 'warning' as const, current_version: 'v8', updated_at: '2026-10-22' };
    vi.mocked(api.listTargets).mockResolvedValue([target]);
    vi.mocked(api.previewSetEnabled).mockResolvedValue({ operation: 'disable', target_id: 8, previous_state: 'active', resulting_state: 'disabled', current_version: 'v8', preview_fingerprint: 'preview', apply_ready: true });
    vi.mocked(api.setEnabled).mockResolvedValue({ receipt_id: 'receipt', resulting_state: 'disabled' } as Awaited<ReturnType<RuntimeTargetClient['setEnabled']>>);
    render(<AlertGroupSecurity client={api} />); fireEvent.click(await screen.findByRole('button', { name: '停用通知' }));
    await waitFor(() => expect(api.setEnabled).toHaveBeenCalledWith(8, expect.objectContaining({ preview_fingerprint: 'preview', enabled: false })));
    await screen.findByText(/已重新查詢並確認最新狀態/); expect(api.resetGroup).not.toHaveBeenCalled();
  });
});
