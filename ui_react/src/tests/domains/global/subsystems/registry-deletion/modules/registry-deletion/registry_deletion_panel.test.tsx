/** RD-A1/A5: shared root presentation, deliberate confirmation and ambiguous replay. */
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { RegistryDeletionPanel } from '../../../../../../../components/RegistryDeletionPanel';
import { registryDeletionClient } from '../../../../../../../api/registry_deletion_client';
import { sessionClient } from '../../../../../../../api/auth/session_client';
import { ApiHttpError, ApiNetworkError } from '../../../../../../../api/shared/typed_errors';

vi.mock('../../../../../../../api/registry_deletion_client', () => ({ registryDeletionClient: { preview: vi.fn(), apply: vi.fn() } }));
const preview = { kind: 'case' as const, identity: '7', version: 2, client_version: 4, blockers: [] as string[] };
const root = { id: 1, username: 'root', display_name: 'Root', role: 'system_admin' as const, is_root: true, linked_line_user_id: null, capabilities: [], access_control_version: 1 };

function mount(disabled = false) {
  const onDeleted = vi.fn(), onBusyChange = vi.fn();
  const view = render(<RegistryDeletionPanel kind="case" identity="7" label="案件 CASE-7" disabled={disabled} onDeleted={onDeleted} onBusyChange={onBusyChange} />);
  return { ...view, onDeleted, onBusyChange };
}
async function inspect() {
  fireEvent.click(await screen.findByRole('button', { name: '刪除此案件' }));
  await screen.findByRole('button', { name: '確認永久刪除' });
}

describe('root registry deletion', () => {
  beforeEach(() => {
    vi.restoreAllMocks(); vi.clearAllMocks();
    vi.spyOn(sessionClient, 'getUser').mockReturnValue(root);
    vi.spyOn(sessionClient, 'getToken').mockReturnValue('synthetic-session');
    vi.spyOn(sessionClient, 'fetchCurrentUser').mockResolvedValue(root);
    vi.mocked(registryDeletionClient.preview).mockResolvedValue(preview);
    vi.mocked(registryDeletionClient.apply).mockResolvedValue({ kind: 'case', identity: '7', deleted: true, replayed: false });
  });

  it.each([null, { ...root, is_root: false }, { ...root, id: null }])('hides deletion without a persisted root fact', async user => {
    vi.mocked(sessionClient.getUser).mockReturnValue(user);
    if (user) vi.mocked(sessionClient.fetchCurrentUser).mockResolvedValue(user);
    else vi.mocked(sessionClient.getToken).mockReturnValue(null);
    mount();
    await screen.findByText('目前登入帳號沒有永久刪除權限。');
    expect(screen.queryByText('永久刪除')).not.toBeInTheDocument();
    expect(registryDeletionClient.preview).not.toHaveBeenCalled();
  });

  it('shows the root action after fresh verification even when cached root is missing', async () => {
    vi.mocked(sessionClient.getUser).mockReturnValue({ ...root, is_root: false });
    mount();
    expect(await screen.findByRole('button', { name: '刪除此案件' })).toBeInTheDocument();
    expect(sessionClient.fetchCurrentUser).toHaveBeenCalled();
  });

  it('does not trust a cached root flag when the backend says the user is not root', async () => {
    vi.mocked(sessionClient.fetchCurrentUser).mockResolvedValue({ ...root, is_root: false });
    mount();
    await screen.findByText('目前登入帳號沒有永久刪除權限。');
    expect(screen.queryByRole('button', { name: '刪除此案件' })).not.toBeInTheDocument();
  });

  it('explains a failed authority lookup and allows a fresh retry', async () => {
    vi.mocked(sessionClient.fetchCurrentUser).mockRejectedValueOnce(new ApiNetworkError()).mockResolvedValueOnce(root);
    mount();
    fireEvent.click(await screen.findByRole('button', { name: '重新確認刪除權限' }));
    expect(await screen.findByRole('button', { name: '刪除此案件' })).toBeInTheDocument();
  });

  it('requires inspection and explicit confirmation, then reports success once', async () => {
    const { onDeleted } = mount();
    expect(registryDeletionClient.apply).not.toHaveBeenCalled();
    await inspect();
    expect(registryDeletionClient.apply).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: '確認永久刪除' }));
    await waitFor(() => expect(onDeleted).toHaveBeenCalledTimes(1));
  });

  it('shows blockers and never offers confirmation', async () => {
    vi.mocked(registryDeletionClient.preview).mockResolvedValue({ ...preview, blockers: ['已有月嫂或客戶簽回，禁止刪除'] });
    mount();
    fireEvent.click(await screen.findByRole('button', { name: '刪除此案件' }));
    expect(await screen.findByText('已有月嫂或客戶簽回，禁止刪除')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '確認永久刪除' })).not.toBeInTheDocument();
    expect(registryDeletionClient.apply).not.toHaveBeenCalled();
  });

  it('keeps the record after a signature recorded after preview and requires new inspection', async () => {
    vi.mocked(registryDeletionClient.apply).mockRejectedValue(new ApiHttpError(409, 'registry_deletion_signed', '已有月嫂或客戶簽回，禁止永久刪除。'));
    const { onDeleted } = mount(); await inspect();
    fireEvent.click(screen.getByRole('button', { name: '確認永久刪除' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('已有月嫂或客戶簽回');
    expect(onDeleted).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: '刪除此案件' })).toBeInTheDocument();
  });

  it('locks ambiguous outcomes and reconciles using the exact same command', async () => {
    vi.mocked(registryDeletionClient.apply).mockRejectedValueOnce(new ApiNetworkError()).mockResolvedValueOnce({ kind: 'case', identity: '7', deleted: true, replayed: true });
    const { onDeleted, onBusyChange } = mount(); await inspect();
    fireEvent.click(screen.getByRole('button', { name: '確認永久刪除' }));
    const retry = await screen.findByRole('button', { name: '重新確認刪除結果' });
    expect(onDeleted).not.toHaveBeenCalled();
    expect(onBusyChange).toHaveBeenLastCalledWith(true);
    expect(screen.queryByRole('button', { name: '取消' })).not.toBeInTheDocument();
    fireEvent.click(retry);
    await waitFor(() => expect(onDeleted).toHaveBeenCalledOnce());
    expect(vi.mocked(registryDeletionClient.apply).mock.calls[0]).toEqual(vi.mocked(registryDeletionClient.apply).mock.calls[1]);
  });

  it('prevents double confirmation while the first request is pending', async () => {
    let finish!: () => void;
    vi.mocked(registryDeletionClient.apply).mockImplementation(() => new Promise(resolve => { finish = () => resolve({ kind: 'case', identity: '7', deleted: true, replayed: false }); }));
    mount(); await inspect();
    const confirm = screen.getByRole('button', { name: '確認永久刪除' });
    fireEvent.click(confirm); fireEvent.click(confirm);
    expect(registryDeletionClient.apply).toHaveBeenCalledTimes(1);
    await act(async () => finish());
  });
});
