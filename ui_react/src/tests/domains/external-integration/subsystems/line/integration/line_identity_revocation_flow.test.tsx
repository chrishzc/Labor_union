/** Verify the real page composes the approved role-scoped revocation flow. */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { LineManagementPage } from '../../../../../../pages/LineManagementPage';
import type { LineIdentityBindingView } from '../../../../../../api/line_identity/line_identity_schemas';
import { BINDING_PAGE_FIXTURE, BOUND_IDENTITY_FIXTURE, REVOCATION_PREVIEW_FIXTURE, REVOCATION_REQUEST_FIXTURE, FIXTURE_LINE_USER_ID } from '../../../../../fixtures/line_identity/line_identity_contract_fixtures';

const pendingBinding: LineIdentityBindingView = {
  ...BOUND_IDENTITY_FIXTURE,
  status: 'revocation_pending',
  version: 8,
  revocation_request_id: 901,
  revocation_status: 'pending_menu_reset',
};

async function confirmRevocation() {
  const row = await screen.findByRole('row', { name: /測試客戶甲/ });
  fireEvent.click(within(row).getByRole('button', { name: '解除綁定' }));
  const dialog = await screen.findByRole('dialog', { name: '是否確認解除綁定？' });
  fireEvent.click(within(dialog).getByRole('button', { name: '確認解除綁定' }));
}

afterEach(() => vi.restoreAllMocks());
describe('LINE 身分解除 successor', () => {
  it('從綁定清單依角色提交解除，Preview／Apply 後重新查回停用狀態', async () => {
    vi.spyOn(window, 'fetch').mockRejectedValue(new Error('unexpected network request'));
    const identity = {
      listBindings: vi.fn().mockResolvedValueOnce(BINDING_PAGE_FIXTURE).mockResolvedValue({ ...BINDING_PAGE_FIXTURE, items: [pendingBinding] }),
      getBinding: vi.fn().mockResolvedValue(pendingBinding),
      previewRevocation: vi.fn().mockResolvedValue(REVOCATION_PREVIEW_FIXTURE),
      applyRevocation: vi.fn().mockResolvedValue(REVOCATION_REQUEST_FIXTURE),
    };
    render(<LineManagementPage lineIdentity={identity} />);
    expect(identity.applyRevocation).not.toHaveBeenCalled();
    await confirmRevocation();
    await screen.findByText('訪客選單回復中');
    expect(identity.previewRevocation).toHaveBeenCalledWith(FIXTURE_LINE_USER_ID, expect.objectContaining({ subjectType: 'customer' }));
    expect(identity.applyRevocation).toHaveBeenCalledExactlyOnceWith(FIXTURE_LINE_USER_ID, expect.objectContaining({ expected_version: 7 }), expect.objectContaining({ subjectType: 'customer' }));
    expect(identity.getBinding).toHaveBeenCalledExactlyOnceWith(FIXTURE_LINE_USER_ID, expect.objectContaining({ subjectType: 'customer' }));
    expect(document.body.textContent).not.toContain(FIXTURE_LINE_USER_ID);
    expect(document.body.textContent).not.toContain(REVOCATION_PREVIEW_FIXTURE.provider_menu_id);
    expect(screen.queryByRole('button', { name: /人工完成/ })).not.toBeInTheDocument();
  });
  it('解除後讀回失敗可重新查詢，重新查詢前無法再次提交', async () => {
    vi.spyOn(window, 'fetch').mockRejectedValue(new Error('unexpected network request'));
    const identity = {
      listBindings: vi.fn().mockResolvedValueOnce(BINDING_PAGE_FIXTURE).mockResolvedValue({ ...BINDING_PAGE_FIXTURE, items: [pendingBinding] }),
      getBinding: vi.fn().mockRejectedValueOnce(new Error('private error')).mockResolvedValue(pendingBinding),
      previewRevocation: vi.fn().mockResolvedValue(REVOCATION_PREVIEW_FIXTURE),
      applyRevocation: vi.fn().mockResolvedValue(REVOCATION_REQUEST_FIXTURE),
    };
    render(<LineManagementPage lineIdentity={identity} />);
    await confirmRevocation();
    await screen.findByRole('alert');
    expect(screen.getByRole('button', { name: '解除綁定' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: '重新查詢綁定狀態' }));
    await screen.findByText('訪客選單回復中');
    await waitFor(() => expect(identity.getBinding).toHaveBeenCalledTimes(2));
    expect(identity.previewRevocation).toHaveBeenCalledTimes(1);
    expect(identity.applyRevocation).toHaveBeenCalledTimes(1);
  });
});
