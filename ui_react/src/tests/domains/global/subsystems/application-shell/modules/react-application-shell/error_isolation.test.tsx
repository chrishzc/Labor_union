/** Page crashes and server errors must leave authenticated navigation usable. */
import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from '../../../../../../../App';
import { sessionClient } from '../../../../../../../api/auth/session_client';

vi.mock('../../../../../../../pages/OrderWorkbenchV2Page', () => ({
  OrderWorkbenchV2Page: () => <h1>測試待辦內容</h1>,
}));
vi.mock('../../../../../../../pages/ClientRegistryPage', () => ({
  ClientRegistryPage: () => <h1>測試客戶內容</h1>,
}));
vi.mock('../../../../../../../pages/StaffPage', async () => {
  const { useState } = await import('react');
  const { useUnsavedDraft } = await import('../../../../../../../components/UnsavedChanges');
  return { StaffPage: function TestStaffPage() {
    const [crashed, setCrashed] = useState(false);
    useUnsavedDraft('測試進行中操作', { value: 'pending' }, { baseline: { value: '' }, busy: true });
    if (crashed) throw new Error('PRIVATE_RENDER_DETAIL');
    return <button onClick={() => setCrashed(true)}>模擬畫面錯誤</button>;
  } };
});

beforeEach(() => {
  vi.restoreAllMocks();
  vi.spyOn(console, 'error').mockImplementation(() => undefined);
  sessionClient.setSession('synthetic-error-isolation-session', {
    id: 1, username: 'tester', display_name: '測試管理員', role: 'system_admin',
    capabilities: ['system.administration'], is_root: true, access_control_version: 1,
  });
  vi.spyOn(globalThis, 'fetch').mockImplementation(async () => new Response('{}', {
    status: 503, headers: { 'content-type': 'application/json' },
  }));
  window.history.replaceState(null, '', '#staff');
});

afterEach(() => {
  sessionClient.clearSession();
  window.history.replaceState(null, '', '#');
  vi.restoreAllMocks();
});

describe('Application error isolation', () => {
  it('contains a page crash, releases its busy guard, and resets when navigating back', async () => {
    render(<App />);
    fireEvent.click(screen.getByRole('button', { name: '模擬畫面錯誤' }));
    expect(await screen.findByText('畫面載入發生異常')).toBeInTheDocument();
    expect(screen.queryByText('PRIVATE_RENDER_DETAIL')).not.toBeInTheDocument();
    expect(sessionClient.isAuthenticated()).toBe(true);
    fireEvent.click(screen.getByTitle('待辦看板'));
    expect(await screen.findByRole('heading', { name: '測試待辦內容' })).toBeInTheDocument();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    fireEvent.click(screen.getByTitle('月嫂名冊'));
    expect(await screen.findByRole('button', { name: '模擬畫面錯誤' })).toBeInTheDocument();
    expect(screen.queryByText('畫面載入發生異常')).not.toBeInTheDocument();
  });

  it('retries just the failed content without reloading the shell or logging out', async () => {
    render(<App />);
    fireEvent.click(screen.getByRole('button', { name: '模擬畫面錯誤' }));
    fireEvent.click(await screen.findByRole('button', { name: '重新嘗試' }));
    expect(screen.getByRole('button', { name: '模擬畫面錯誤' })).toBeInTheDocument();
    expect(screen.getByTitle('待辦看板')).toBeInTheDocument();
    expect(sessionClient.isAuthenticated()).toBe(true);
  });

  it.each([500, 501, 502, 503, 504, 507, 599])('HTTP %s from shared shell queries leaves session and real hash navigation intact', async status => {
    vi.mocked(globalThis.fetch).mockImplementation(async () => new Response('{}', {
      status, headers: { 'content-type': 'application/json' },
    }));
    window.history.replaceState(null, '', '#order-workbench-v2');
    render(<App />);
    await act(async () => {});
    fireEvent.click(screen.getByTitle('客戶名冊'));
    expect(await screen.findByRole('heading', { name: '測試客戶內容' })).toBeInTheDocument();
    expect(sessionClient.isAuthenticated()).toBe(true);
    expect(screen.queryByText('畫面載入發生異常')).not.toBeInTheDocument();
    fireEvent.click(screen.getByTitle('待辦看板'));
    expect(await screen.findByRole('heading', { name: '測試待辦內容' })).toBeInTheDocument();
  });
});
