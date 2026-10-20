import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { useState, type ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from '../../../../../../../App';
import { sessionClient } from '../../../../../../../api/auth/session_client';
import { useUnsavedDraft } from '../../../../../../../components/UnsavedChanges';

vi.mock('../../../../../../../components/StaffIdentityProvider', async original => ({
  ...await original<typeof import('../../../../../../../components/StaffIdentityProvider')>(),
  StaffIdentityProvider: ({ children }: { children: ReactNode }) => children,
}));
vi.mock('../../../../../../../components/MasterLayout', async original => ({
  ...await original<typeof import('../../../../../../../components/MasterLayout')>(),
  MasterLayout: ({ children, onSelectPage, onSelectSection, onLogout }: {
    children: ReactNode; onSelectPage: (page: string) => void; onSelectSection: (section: string) => void; onLogout: () => void;
  }) => <><button onClick={() => onSelectPage('staff')}>主選單月嫂</button><button onClick={() => onSelectSection('finance')}>主分區帳務</button><button onClick={onLogout}>確認登出</button>{children}</>,
}));
vi.mock('../../../../../../../pages/ClientRegistryPage', () => ({ ClientRegistryPage: () => <EditablePage /> }));
vi.mock('../../../../../../../pages/OrderWorkbenchV2Page', () => ({ OrderWorkbenchV2Page: () => <EditablePage /> }));
vi.mock('../../../../../../../pages/StaffPage', () => ({ StaffPage: () => <h1>月嫂頁面</h1> }));
vi.mock('../../../../../../../pages/FinancePage', () => ({ FinancePage: () => <h1>帳務頁面</h1> }));
vi.mock('../../../../../../../pages/LoginPage', () => ({ LoginPage: () => <h1>登入頁面</h1> }));

function EditablePage() {
  const [text, setText] = useState('原始值');
  useUnsavedDraft('編輯中的頁面', { '欄位': text });
  return <label>編輯欄位<input value={text} onChange={event => setText(event.target.value)} /></label>;
}
const warning = () => screen.getByRole('dialog', { name: '尚有未儲存的變更' });
const edit = () => fireEvent.change(screen.getByLabelText('編輯欄位'), { target: { value: '尚未儲存' } });

describe('App 未儲存變更導航', () => {
  beforeEach(() => {
    window.history.replaceState(null, '', '#clients?case=TEST');
    vi.spyOn(sessionClient, 'isAuthenticated').mockReturnValue(true);
    vi.spyOn(sessionClient, 'logout').mockResolvedValue();
  });

  it('主選單切頁先保留編輯頁；取消保留網址與內容，捨棄才切換', async () => {
    render(<App />); edit();
    fireEvent.click(screen.getByRole('button', { name: '主選單月嫂' }));
    await screen.findByRole('dialog', { name: '尚有未儲存的變更' });
    expect(window.location.hash).toBe('#clients?case=TEST');
    expect(screen.getByLabelText('編輯欄位')).toHaveValue('尚未儲存');
    fireEvent.click(within(warning()).getByRole('button', { name: '繼續編輯' }));
    expect(screen.queryByRole('heading', { name: '月嫂頁面' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '主選單月嫂' }));
    await screen.findByRole('dialog', { name: '尚有未儲存的變更' });
    fireEvent.click(within(warning()).getByRole('button', { name: '捨棄變更並離開' }));
    await screen.findByRole('heading', { name: '月嫂頁面' });
    expect(window.location.hash).toBe('#staff');
  });

  it('直接 hash／瀏覽器歷史導航也會在卸載前攔截', async () => {
    render(<App />); edit();
    await act(async () => {
      const oldURL = window.location.href;
      window.history.replaceState(null, '', '#finance');
      window.dispatchEvent(new HashChangeEvent('hashchange', { oldURL, newURL: window.location.href }));
    });
    expect(warning()).toBeInTheDocument();
    expect(screen.getByLabelText('編輯欄位')).toHaveValue('尚未儲存');
    fireEvent.click(within(warning()).getByRole('button', { name: '捨棄變更並離開' }));
    await screen.findByRole('heading', { name: '帳務頁面' });
  });

  it('登出不會先清除會話；確認捨棄後才呼叫原登出流程', async () => {
    render(<App />); edit();
    fireEvent.click(screen.getByRole('button', { name: '確認登出' }));
    expect(sessionClient.logout).not.toHaveBeenCalled();
    fireEvent.click(within(warning()).getByRole('button', { name: '繼續編輯' }));
    expect(sessionClient.logout).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: '確認登出' }));
    fireEvent.click(within(warning()).getByRole('button', { name: '捨棄變更並離開' }));
    await screen.findByRole('heading', { name: '登入頁面' });
    expect(sessionClient.logout).toHaveBeenCalledOnce();
  });

  it('乾淨頁面切換主分區不顯示警告，也不重複切換', async () => {
    render(<App />);
    fireEvent.click(screen.getByRole('button', { name: '主分區帳務' }));
    await waitFor(() => expect(screen.getByRole('heading', { name: '帳務頁面' })).toBeInTheDocument());
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });
});
