/** Verify the real page composes the approved role-scoped revocation flow. */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { LineManagementPage } from '../../../../../../pages/LineManagementPage';
import { BINDING_PAGE_FIXTURE, BOUND_IDENTITY_FIXTURE, REVOCATION_PREVIEW_FIXTURE, REVOCATION_REQUEST_FIXTURE, FIXTURE_LINE_USER_ID } from '../../../../../fixtures/line_identity/line_identity_contract_fixtures';
afterEach(() => vi.restoreAllMocks());
describe('LINE 身分解除 successor', () => {
  it('經過角色限定明細、Preview、確認與 Apply 後重新查回停用狀態', async () => {
    const identity = {
      listBindings: vi.fn().mockResolvedValue(BINDING_PAGE_FIXTURE),
      getBinding: vi.fn().mockResolvedValueOnce(BOUND_IDENTITY_FIXTURE).mockResolvedValue({ ...BOUND_IDENTITY_FIXTURE, status: 'revocation_pending', version: 8, revocation_request_id: 901, revocation_status: 'pending_menu_reset' }),
      previewRevocation: vi.fn().mockResolvedValue(REVOCATION_PREVIEW_FIXTURE),
      applyRevocation: vi.fn().mockResolvedValue(REVOCATION_REQUEST_FIXTURE),
    };
    render(<LineManagementPage lineIdentity={identity} customerService={{}} />);
    fireEvent.click(screen.getByRole('button', { name: '身分與授權' }));
    fireEvent.click(await screen.findByRole('button', { name: '查看測試客戶甲的客戶身分' }));
    await screen.findByText('U123••••cdef');
    fireEvent.click(screen.getByRole('button', { name: '解除此身分' }));
    fireEvent.change(screen.getByRole('textbox', { name: '解除原因' }), { target: { value: '客戶已確認解除' } });
    fireEvent.click(screen.getByRole('button', { name: '下一步：確認' }));
    expect(await screen.findByRole('button', { name: '確認解除此身分' })).toBeDisabled();
    fireEvent.click(screen.getByRole('checkbox')); fireEvent.click(screen.getByRole('button', { name: '確認解除此身分' }));
    await within(screen.getByRole('dialog')).findByText('身分已停用');
    expect(identity.previewRevocation).toHaveBeenCalledWith(FIXTURE_LINE_USER_ID, expect.objectContaining({ subjectType: 'customer' }));
    expect(identity.applyRevocation).toHaveBeenCalledWith(FIXTURE_LINE_USER_ID, expect.objectContaining({ expected_version: 7, reason: '客戶已確認解除' }), expect.objectContaining({ subjectType: 'customer' }));
    expect(identity.getBinding).toHaveBeenCalledTimes(2);
    expect(document.body.textContent).not.toContain(FIXTURE_LINE_USER_ID);
    expect(document.body.textContent).not.toContain(REVOCATION_PREVIEW_FIXTURE.provider_menu_id);
    expect(screen.queryByRole('button', { name: /人工完成/ })).not.toBeInTheDocument();
  });
  it('明細失敗可重新查詢，恢復前不提供解除操作', async () => {
    const identity = { listBindings: vi.fn().mockResolvedValue(BINDING_PAGE_FIXTURE), getBinding: vi.fn().mockRejectedValueOnce(new Error('private error')).mockResolvedValue(BOUND_IDENTITY_FIXTURE), previewRevocation: vi.fn(), applyRevocation: vi.fn() };
    render(<LineManagementPage lineIdentity={identity} customerService={{}} />);
    fireEvent.click(screen.getByRole('button', { name: '身分與授權' })); fireEvent.click(await screen.findByRole('button', { name: '查看測試客戶甲的客戶身分' }));
    await screen.findByRole('alert'); expect(screen.queryByRole('button', { name: '解除此身分' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '重新查詢綁定狀態' }));
    await screen.findByRole('button', { name: '解除此身分' });
    await waitFor(() => expect(identity.getBinding).toHaveBeenCalledTimes(2)); expect(identity.previewRevocation).not.toHaveBeenCalled();
  });
});
