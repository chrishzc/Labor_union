/** Root absence gates the whole application, including cached/development sessions. */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { FirstRootSetupGate } from '../pages/FirstRootSetup';
import { sessionClient } from '../api/auth/session_client';

const PASSWORD = 'synthetic-root-password';
const enrollment = {
  challenge_type: 'mfa_enrollment', challenge_id: 'setup-enrollment', challenge_token: 'm'.repeat(32),
  expires_at: new Date(Date.now() + 600000).toISOString(),
  provisioning_uri: 'otpauth://totp/mock?secret=JBSWY3DPEHPK3PXP',
};
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), {
  status, headers: { 'Content-Type': 'application/json' },
});
let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  fetchMock = vi.fn();
  vi.stubGlobal('fetch', fetchMock);
  sessionClient.clearSession();
});
afterEach(() => { vi.unstubAllGlobals(); vi.unstubAllEnvs(); sessionClient.clearSession(); });

function renderGate() {
  const child = vi.fn(() => <p>管理端登入畫面</p>);
  const Child = child;
  render(<FirstRootSetupGate><Child /></FirstRootSetupGate>);
  return child;
}

async function fill(password = PASSWORD, confirmation = password) {
  await screen.findByLabelText('帳號');
  fireEvent.change(screen.getByLabelText('帳號'), { target: { value: 'first-root' } });
  fireEvent.change(screen.getByLabelText('顯示名稱'), { target: { value: '管理員' } });
  fireEvent.change(screen.getByLabelText('密碼（至少 10 個字元）'), { target: { value: password } });
  fireEvent.change(screen.getByLabelText('再次輸入密碼'), { target: { value: confirmation } });
  fireEvent.click(screen.getByRole('button', { name: '建立最高管理員' }));
}

describe('shared first-root setup', () => {
  it('blocks application mounting until MySQL reports an existing root', async () => {
    let resolve!: (response: Response) => void;
    fetchMock.mockReturnValue(new Promise<Response>(done => { resolve = done; }));
    const child = renderGate();
    expect(child).not.toHaveBeenCalled();
    expect(screen.getByRole('status')).toBeInTheDocument();
    resolve(json({ required: false }));
    expect(await screen.findByText('管理端登入畫面')).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/admin/setup', expect.objectContaining({ cache: 'no-store' }));
  });

  it('creates root then binds TOTP, saves recovery codes and only then returns to login', async () => {
    vi.stubEnv('VITE_PUBLIC_PATH_PREFIX', '/test');
    fetchMock.mockResolvedValueOnce(json({ required: true }))
      .mockResolvedValueOnce(json({ created: true, enrollment }, 201))
      .mockResolvedValueOnce(json({ success: true, data: { recovery_codes: ['MOCK-RECOVERY'] } }));
    const clear = vi.spyOn(sessionClient, 'clearSession');
    const child = renderGate();
    await fill();
    expect(await screen.findByRole('heading', { name: '綁定您的驗證器' })).toBeInTheDocument();
    expect(child).not.toHaveBeenCalled();
    expect(clear).toHaveBeenCalled();
    expect(fetchMock).toHaveBeenNthCalledWith(2, '/test/api/v1/admin/setup', expect.objectContaining({
      method: 'POST', body: JSON.stringify({ username: 'first-root', display_name: '管理員', password: PASSWORD }),
    }));
    expect(document.querySelector('input[type="password"]')).toBeNull();
    expect(JSON.stringify(window.sessionStorage)).not.toContain(PASSWORD);
    expect(JSON.stringify(window.localStorage)).not.toContain(PASSWORD);
    expect(screen.getByRole('img', { name: '驗證器綁定 QR Code' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '前往登入' })).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('六位數驗證碼'), { target: { value: '123456' } });
    fireEvent.click(screen.getByRole('button', { name: '確認綁定驗證器' }));
    expect(await screen.findByRole('heading', { name: '驗證器綁定完成' })).toBeInTheDocument();
    expect(child).not.toHaveBeenCalled();
    expect(sessionClient.isAuthenticated()).toBe(false);
    expect(screen.getByText('MOCK-RECOVERY')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '已保存復原碼，返回登入' }));
    expect(await screen.findByText('管理端登入畫面')).toBeInTheDocument();
    clear.mockRestore();
  });

  it('requires matching passwords before sending a creation request', async () => {
    fetchMock.mockResolvedValueOnce(json({ required: true }));
    renderGate();
    await fill(PASSWORD, 'different-password');
    expect(screen.getByRole('alert')).toHaveTextContent('兩次輸入的密碼不一致');
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('keeps the application closed on status failure and allows a manual retry', async () => {
    fetchMock.mockResolvedValueOnce(json({ detail: 'database unavailable' }, 503))
      .mockResolvedValueOnce(json({ required: false }));
    const child = renderGate();
    expect(await screen.findByRole('alert')).toHaveTextContent('無法讀取帳號設定狀態');
    expect(child).not.toHaveBeenCalled();
    expect(screen.queryByLabelText('帳號')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '重新確認' }));
    expect(await screen.findByText('管理端登入畫面')).toBeInTheDocument();
  });

  it('rechecks a concurrent creation conflict and enters login only after root exists', async () => {
    fetchMock.mockResolvedValueOnce(json({ required: true }))
      .mockResolvedValueOnce(json({ detail: '最高管理員已建立，請直接登入。' }, 410))
      .mockResolvedValueOnce(json({ required: false }));
    renderGate();
    await fill();
    expect(await screen.findByText('管理端登入畫面')).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it('clears submitted passwords on failure without automatically retrying a write', async () => {
    fetchMock.mockResolvedValueOnce(json({ required: true }))
      .mockResolvedValueOnce(json({ detail: '請使用 HTTPS 網址開啟管理介面後設定帳號。' }, 426));
    const child = renderGate();
    await fill();
    expect(await screen.findByRole('alert')).toHaveTextContent('HTTPS');
    await waitFor(() => expect(screen.getByLabelText('密碼（至少 10 個字元）')).toHaveValue(''));
    expect(screen.getByLabelText('再次輸入密碼')).toHaveValue('');
    expect(child).not.toHaveBeenCalled();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('stops initial setup after QR expiry without returning to login', async () => {
    fetchMock.mockResolvedValueOnce(json({ required: true }))
      .mockResolvedValueOnce(json({ created: true, enrollment: { ...enrollment, expires_at: '2000-01-01T00:00:00Z' } }, 201));
    const child = renderGate();
    await fill();
    await screen.findByRole('heading', { name: '綁定您的驗證器' });
    fireEvent.change(screen.getByLabelText('六位數驗證碼'), { target: { value: '123456' } });
    fireEvent.click(screen.getByRole('button', { name: '確認綁定驗證器' }));
    expect(await screen.findByRole('heading', { name: '初始設定已逾時' })).toBeInTheDocument();
    expect(screen.queryByRole('img', { name: '驗證器綁定 QR Code' })).not.toBeInTheDocument();
    expect(child).not.toHaveBeenCalled();
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(sessionClient.isAuthenticated()).toBe(false);
  });

  it('stops initial setup when the server expires the challenge', async () => {
    fetchMock.mockResolvedValueOnce(json({ required: true }))
      .mockResolvedValueOnce(json({ created: true, enrollment }, 201))
      .mockResolvedValueOnce(json({ detail: { code: 'mfa_challenge_expired', message: 'MFA 綁定已失效或驗證碼錯誤' } }, 409));
    const child = renderGate();
    await fill();
    await screen.findByRole('heading', { name: '綁定您的驗證器' });
    fireEvent.change(screen.getByLabelText('六位數驗證碼'), { target: { value: '123456' } });
    fireEvent.click(screen.getByRole('button', { name: '確認綁定驗證器' }));
    expect(await screen.findByRole('heading', { name: '初始設定已逾時' })).toBeInTheDocument();
    expect(child).not.toHaveBeenCalled();
    expect(screen.queryByRole('img', { name: '驗證器綁定 QR Code' })).not.toBeInTheDocument();
    expect(sessionClient.isAuthenticated()).toBe(false);
  });
});
