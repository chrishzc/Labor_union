/**
 * File: LoginPage.test.tsx
 * Description: 驗證雙階段登入、TOTP 錯誤狀態與機密安全衛生。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { LoginPage } from '../pages/LoginPage';
import { sessionClient } from '../api/auth/session_client';
import {
  MOCK_STAGE1_RESPONSE,
  MOCK_STAGE2_ENVELOPE,
  MOCK_401_INVALID_CREDENTIALS_PAYLOAD,
  MOCK_403_MFA_ENROLLMENT_PAYLOAD,
  MOCK_429_RATE_LIMITED_PAYLOAD,
  MOCK_503_AUTH_UNAVAILABLE_PAYLOAD,
} from './fixtures/auth/two_step_auth_contract_fixtures';

const createStage1Envelope = (
  expiresAt = new Date(Date.now() + 5 * 60 * 1000).toISOString()
) => ({
  success: true,
  message: '請輸入驗證器代碼',
  data: {
    ...MOCK_STAGE1_RESPONSE,
    expires_at: expiresAt,
  },
  error: null,
});

const createNestedGlobalError = (
  category: 'conflict' | 'unavailable',
  code: string,
  message: string,
  retryable: boolean
) => ({
  detail: {
    error: {
      category,
      code,
      message,
      field_errors: [],
      domain_blockers: [],
      retryable,
      correlation_id: 'login-test-correlation-001',
      current_version: null,
    },
  },
});

describe('LoginPage Component: Phase 2C Two-Step Authentication Flow', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    vi.restoreAllMocks();
    sessionClient.clearSession();
    window.localStorage.clear();
    window.sessionStorage.clear();
  });

  afterEach(() => {
    sessionClient.clearSession();
    window.localStorage.clear();
    window.sessionStorage.clear();
    globalThis.fetch = originalFetch;
  });

  it('初始渲染應呈現 Stage 1 帳號密碼登入介面且按鈕與輸入框正常', () => {
    render(<LoginPage />);

    expect(screen.getByRole('heading', { name: '月子工會管理系統' })).toBeInTheDocument();
    expect(screen.getByText('請輸入您的帳號密碼以登入後台')).toBeInTheDocument();
    expect(screen.getByLabelText('帳號 (Username)')).toBeInTheDocument();
    expect(screen.getByLabelText('密碼 (Password)')).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: /下一步：進行雙重驗證/ })
    ).toBeInTheDocument();
    expect(screen.getByText(/記住帳號/)).toBeInTheDocument();
    expect(screen.getByText(/忘記密碼？/)).toBeInTheDocument();
  });

  it('Stage 1 欄位校驗：未輸入帳號時提交應提示「請輸入帳號」且不發起網路請求', () => {
    const fetchSpy = vi.fn();
    globalThis.fetch = fetchSpy;

    render(<LoginPage />);

    const usernameInput = screen.getByLabelText('帳號 (Username)');
    fireEvent.change(usernameInput, { target: { value: '' } });

    const submitBtn = screen.getByRole('button', { name: /下一步：進行雙重驗證/ });
    fireEvent.click(submitBtn);

    expect(screen.getByText(/請輸入帳號/)).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: /雙重身分驗證/ })).not.toBeInTheDocument();
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it('Stage 1 欄位校驗：未輸入密碼時提交應提示「請輸入密碼」且不發起網路請求', () => {
    const fetchSpy = vi.fn();
    globalThis.fetch = fetchSpy;

    render(<LoginPage />);

    const usernameInput = screen.getByLabelText('帳號 (Username)');
    const passwordInput = screen.getByLabelText('密碼 (Password)');

    fireEvent.change(usernameInput, { target: { value: 'admin_user' } });
    fireEvent.change(passwordInput, { target: { value: '' } });

    const submitBtn = screen.getByRole('button', { name: /下一步：進行雙重驗證/ });
    fireEvent.click(submitBtn);

    expect(screen.getByText(/請輸入密碼/)).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: /雙重身分驗證/ })).not.toBeInTheDocument();
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it('Stage 1 欄位校驗：純空白字元帳號密碼提交應即時阻擋', () => {
    const fetchSpy = vi.fn();
    globalThis.fetch = fetchSpy;

    render(<LoginPage />);

    const usernameInput = screen.getByLabelText('帳號 (Username)');
    const passwordInput = screen.getByLabelText('密碼 (Password)');

    fireEvent.change(usernameInput, { target: { value: '   ' } });
    fireEvent.change(passwordInput, { target: { value: '   ' } });

    fireEvent.click(screen.getByRole('button', { name: /下一步：進行雙重驗證/ }));

    expect(screen.getByText(/請輸入帳號/)).toBeInTheDocument();
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it('Stage 1 Sunny Day：輸入正確帳密發送挑戰，成功時密碼立即清空並轉移至 Stage 2', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => createStage1Envelope(),
    });

    render(<LoginPage />);

    const usernameInput = screen.getByLabelText('帳號 (Username)');
    const passwordInput = screen.getByLabelText('密碼 (Password)');

    fireEvent.change(usernameInput, { target: { value: 'admin_test' } });
    fireEvent.change(passwordInput, { target: { value: 'ValidPassword123!' } });

    const submitBtn = screen.getByRole('button', { name: /下一步：進行雙重驗證/ });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /雙重身分驗證 \(2FA\)/ })).toBeInTheDocument();
    });

    expect(screen.getByText('請開啟 Authenticator 隨身驗證器，輸入 6 位動態碼')).toBeInTheDocument();
    expect(document.getElementById('totp-0')).toBeInTheDocument();
    expect(document.getElementById('totp-5')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /驗證並登入系統/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /返回重新輸入帳密/ })).toBeInTheDocument();

    // Verify Stage 1 request was sent to correct endpoint
    expect(globalThis.fetch).toHaveBeenCalledWith(
      '/api/v1/admin/auth/login/challenges',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({
          username: 'admin_test',
          password: 'ValidPassword123!',
        }),
      })
    );
  });

  it('Stage 1 載入中狀態：請求中時輸入框與按鈕應被停用且顯示「處理中...」', async () => {
    let resolveFetch: (val: any) => void;
    const pendingPromise = new Promise((resolve) => {
      resolveFetch = resolve;
    });

    globalThis.fetch = vi.fn().mockReturnValue(pendingPromise);

    render(<LoginPage />);

    fireEvent.change(screen.getByLabelText('帳號 (Username)'), { target: { value: 'admin' } });
    fireEvent.change(screen.getByLabelText('密碼 (Password)'), { target: { value: 'secret' } });

    const submitBtn = screen.getByRole('button', { name: /下一步：進行雙重驗證/ });
    fireEvent.click(submitBtn);

    expect(screen.getByRole('button', { name: '處理中...' })).toBeDisabled();
    expect(screen.getByLabelText('帳號 (Username)')).toBeDisabled();
    expect(screen.getByLabelText('密碼 (Password)')).toBeDisabled();

    // Resolve promise
    resolveFetch!({
      ok: true,
      status: 200,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => createStage1Envelope(),
    });

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /雙重身分驗證/ })).toBeInTheDocument();
    });
  });

  it('Stage 1 錯誤處理：401 帳密錯誤應留在 Stage 1、顯示「帳號或密碼錯誤」、清空密碼並保留帳號', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      statusText: 'Unauthorized',
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => MOCK_401_INVALID_CREDENTIALS_PAYLOAD,
    });

    render(<LoginPage />);

    fireEvent.change(screen.getByLabelText('帳號 (Username)'), { target: { value: 'wrong_user' } });
    fireEvent.change(screen.getByLabelText('密碼 (Password)'), { target: { value: 'wrong_pass' } });

    fireEvent.click(screen.getByRole('button', { name: /下一步：進行雙重驗證/ }));

    await waitFor(() => {
      expect(screen.getByText(/帳號或密碼錯誤/)).toBeInTheDocument();
    });

    expect(screen.getByRole('heading', { name: '月子工會管理系統' })).toBeInTheDocument();
    const usernameInput = screen.getByLabelText('帳號 (Username)') as HTMLInputElement;
    const passwordInput = screen.getByLabelText('密碼 (Password)') as HTMLInputElement;
    expect(usernameInput.value).toBe('wrong_user');
    expect(passwordInput.value).toBe('');
  });

  it('Stage 1 錯誤處理：403 MFA 尚未綁定應顯示安全脫敏訊息且絕對不可洩漏 provisioning_uri 或 secret', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 403,
      statusText: 'Forbidden',
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => MOCK_403_MFA_ENROLLMENT_PAYLOAD,
    });

    const { container } = render(<LoginPage />);

    fireEvent.change(screen.getByLabelText('帳號 (Username)'), { target: { value: 'unbound_admin' } });
    fireEvent.change(screen.getByLabelText('密碼 (Password)'), { target: { value: 'pass123' } });

    fireEvent.click(screen.getByRole('button', { name: /下一步：進行雙重驗證/ }));

    await waitFor(() => {
      expect(
        screen.getByText(/此帳號需先完成 MFA 綁定；React 綁定流程尚未啟用。/)
      ).toBeInTheDocument();
    });

    // Zero secret leak verification
    expect(container.innerHTML).not.toContain('otpauth');
    expect(container.innerHTML).not.toContain('JBSWY3DPEHPK3PXP');
    expect(container.innerHTML).not.toContain('mfa-enroll-challenge');

    const passwordInput = screen.getByLabelText('密碼 (Password)') as HTMLInputElement;
    expect(passwordInput.value).toBe('');
  });

  it('Stage 1 錯誤處理：429 頻率限制應顯示「登入嘗試過於頻繁，請稍後再試」且清空密碼', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 429,
      statusText: 'Too Many Requests',
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () =>
        createNestedGlobalError(
          'unavailable',
          'login_rate_limited',
          '登入嘗試過於頻繁，請稍後再試',
          true
        ),
    });

    render(<LoginPage />);

    fireEvent.change(screen.getByLabelText('帳號 (Username)'), { target: { value: 'rate_limited_user' } });
    fireEvent.change(screen.getByLabelText('密碼 (Password)'), { target: { value: 'pass123' } });

    fireEvent.click(screen.getByRole('button', { name: /下一步：進行雙重驗證/ }));

    await waitFor(() => {
      expect(screen.getByText(/登入嘗試過於頻繁，請稍後再試/)).toBeInTheDocument();
    });

    const passwordInput = screen.getByLabelText('密碼 (Password)') as HTMLInputElement;
    expect(passwordInput.value).toBe('');
  });

  it('Stage 1 錯誤處理：503 服務不可用應顯示「系統驗證服務暫時無法使用，請稍後再試」', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 503,
      statusText: 'Service Unavailable',
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => MOCK_503_AUTH_UNAVAILABLE_PAYLOAD,
    });

    render(<LoginPage />);

    fireEvent.change(screen.getByLabelText('帳號 (Username)'), { target: { value: 'admin' } });
    fireEvent.change(screen.getByLabelText('密碼 (Password)'), { target: { value: 'pass' } });

    fireEvent.click(screen.getByRole('button', { name: /下一步：進行雙重驗證/ }));

    await waitFor(() => {
      expect(screen.getByText(/系統驗證服務暫時無法使用，請稍後再試/)).toBeInTheDocument();
    });
  });

  it('Stage 1 錯誤處理：網路中斷異常應提示「網路連線異常，請檢查網路後重試」', async () => {
    globalThis.fetch = vi.fn().mockRejectedValue(new Error('Network disconnected'));

    render(<LoginPage />);

    fireEvent.change(screen.getByLabelText('帳號 (Username)'), { target: { value: 'admin' } });
    fireEvent.change(screen.getByLabelText('密碼 (Password)'), { target: { value: 'pass' } });

    fireEvent.click(screen.getByRole('button', { name: /下一步：進行雙重驗證/ }));

    await waitFor(() => {
      expect(screen.getByText(/網路連線異常，請檢查網路後重試/)).toBeInTheDocument();
    });
  });

  it('Stage 2 欄位校驗：TOTP 長度不足 6 位數時提交應顯示錯誤且不發起請求', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => createStage1Envelope(),
    });

    render(<LoginPage />);

    fireEvent.change(screen.getByLabelText('帳號 (Username)'), { target: { value: 'admin' } });
    fireEvent.change(screen.getByLabelText('密碼 (Password)'), { target: { value: 'pass' } });
    fireEvent.click(screen.getByRole('button', { name: /下一步：進行雙重驗證/ }));

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /雙重身分驗證/ })).toBeInTheDocument();
    });

    // Enter only 3 digits
    fireEvent.change(document.getElementById('totp-0')!, { target: { value: '1' } });
    fireEvent.change(document.getElementById('totp-1')!, { target: { value: '2' } });
    fireEvent.change(document.getElementById('totp-2')!, { target: { value: '3' } });

    const fetchSpy = vi.fn();
    globalThis.fetch = fetchSpy;

    const verifyBtn = screen.getByRole('button', { name: /驗證並登入系統/ });
    fireEvent.click(verifyBtn);

    expect(screen.getByText(/請完整輸入 6 位數 TOTP 動態安全碼/)).toBeInTheDocument();
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it('Stage 2 TOTP 輸入行為：單格輸入過濾非數字字元', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => createStage1Envelope(),
    });

    render(<LoginPage />);

    fireEvent.change(screen.getByLabelText('帳號 (Username)'), { target: { value: 'admin' } });
    fireEvent.change(screen.getByLabelText('密碼 (Password)'), { target: { value: 'pass' } });
    fireEvent.click(screen.getByRole('button', { name: /下一步：進行雙重驗證/ }));

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /雙重身分驗證/ })).toBeInTheDocument();
    });

    const totp0 = document.getElementById('totp-0') as HTMLInputElement;
    // Enter alphabetic character -> should be ignored
    fireEvent.change(totp0, { target: { value: 'a' } });
    expect(totp0.value).toBe('');

    // Enter valid digit -> accepted
    fireEvent.change(totp0, { target: { value: '7' } });
    expect(totp0.value).toBe('7');
  });

  it('Stage 2 Sunny Day：輸入有效 6 位 TOTP 碼驗證成功，觸發 onLoginSuccess 回呼並清空 TOTP 狀態', async () => {
    const handleSuccess = vi.fn();

    globalThis.fetch = vi.fn().mockImplementation(async (url: string | URL | Request) => {
      const urlStr = typeof url === 'string' ? url : url.toString();
      if (urlStr.includes('/verify')) {
        return {
          ok: true,
          status: 200,
          headers: new Headers({ 'content-type': 'application/json' }),
          json: async () => MOCK_STAGE2_ENVELOPE,
        };
      }
      return {
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => createStage1Envelope(),
      };
    });

    render(<LoginPage onLoginSuccess={handleSuccess} />);

    // Stage 1
    fireEvent.change(screen.getByLabelText('帳號 (Username)'), { target: { value: 'admin_test' } });
    fireEvent.change(screen.getByLabelText('密碼 (Password)'), { target: { value: 'ValidPassword123!' } });
    fireEvent.click(screen.getByRole('button', { name: /下一步：進行雙重驗證/ }));

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /雙重身分驗證/ })).toBeInTheDocument();
    });

    // Stage 2: Fill 6 digits
    for (let i = 0; i < 6; i++) {
      fireEvent.change(document.getElementById(`totp-${i}`)!, {
        target: { value: String(i + 1) },
      });
    }

    const verifyBtn = screen.getByRole('button', { name: /驗證並登入系統/ });
    fireEvent.click(verifyBtn);

    await waitFor(() => {
      expect(handleSuccess).toHaveBeenCalledWith('admin_test');
    });

    // In-memory token should now be set in sessionClient
    expect(sessionClient.isAuthenticated()).toBe(true);
    expect(sessionClient.getToken()).toBe('bearer-test-access-token-xyz-12345-67890');
    expect(sessionClient.getUser()?.username).toBe('admin_test');
  });

  it('Stage 2 載入中狀態：驗證請求中時 TOTP 輸入框與按鈕應被停用且顯示「驗證中...」', async () => {
    let resolveVerify: (val: any) => void;
    const verifyPromise = new Promise((resolve) => {
      resolveVerify = resolve;
    });

    globalThis.fetch = vi.fn().mockImplementation(async (url: string | URL | Request) => {
      const urlStr = typeof url === 'string' ? url : url.toString();
      if (urlStr.includes('/verify')) {
        return verifyPromise;
      }
      return {
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => createStage1Envelope(),
      };
    });

    render(<LoginPage />);

    fireEvent.change(screen.getByLabelText('帳號 (Username)'), { target: { value: 'admin' } });
    fireEvent.change(screen.getByLabelText('密碼 (Password)'), { target: { value: 'pass' } });
    fireEvent.click(screen.getByRole('button', { name: /下一步：進行雙重驗證/ }));

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /雙重身分驗證/ })).toBeInTheDocument();
    });

    for (let i = 0; i < 6; i++) {
      fireEvent.change(document.getElementById(`totp-${i}`)!, {
        target: { value: '1' },
      });
    }

    const verifyBtn = screen.getByRole('button', { name: /驗證並登入系統/ });
    fireEvent.click(verifyBtn);

    expect(screen.getByRole('button', { name: '驗證中...' })).toBeDisabled();
    expect(document.getElementById('totp-0')).toBeDisabled();
    expect(document.getElementById('totp-5')).toBeDisabled();

    // Resolve
    resolveVerify!({
      ok: true,
      status: 200,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => MOCK_STAGE2_ENVELOPE,
    });

    await waitFor(() => {
      expect(sessionClient.isAuthenticated()).toBe(true);
    });
  });

  it('Stage 2 錯誤處理：401 動態碼錯誤應留在 Stage 2、顯示「驗證碼錯誤或無效」並清空 6 位輸入框', async () => {
    globalThis.fetch = vi.fn().mockImplementation(async (url: string | URL | Request) => {
      const urlStr = typeof url === 'string' ? url : url.toString();
      if (urlStr.includes('/verify')) {
        return {
          ok: false,
          status: 401,
          statusText: 'Unauthorized',
          headers: new Headers({ 'content-type': 'application/json' }),
          json: async () => MOCK_401_INVALID_CREDENTIALS_PAYLOAD,
        };
      }
      return {
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => createStage1Envelope(),
      };
    });

    render(<LoginPage />);

    fireEvent.change(screen.getByLabelText('帳號 (Username)'), { target: { value: 'admin' } });
    fireEvent.change(screen.getByLabelText('密碼 (Password)'), { target: { value: 'pass' } });
    fireEvent.click(screen.getByRole('button', { name: /下一步：進行雙重驗證/ }));

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /雙重身分驗證/ })).toBeInTheDocument();
    });

    for (let i = 0; i < 6; i++) {
      fireEvent.change(document.getElementById(`totp-${i}`)!, {
        target: { value: '8' },
      });
    }

    fireEvent.click(screen.getByRole('button', { name: /驗證並登入系統/ }));

    await waitFor(() => {
      expect(screen.getByText(/驗證碼錯誤或無效/)).toBeInTheDocument();
    });

    // Still in Stage 2
    expect(screen.getByRole('heading', { name: /雙重身分驗證/ })).toBeInTheDocument();

    // All 6 TOTP inputs are wiped
    for (let i = 0; i < 6; i++) {
      const box = document.getElementById(`totp-${i}`) as HTMLInputElement;
      expect(box.value).toBe('');
    }
  });

  it('Stage 2 錯誤處理：Challenge 逾期應自動退回 Stage 1 並提示「驗證階段已過期，請重新輸入帳號密碼」', async () => {
    globalThis.fetch = vi.fn().mockImplementation(async (url: string | URL | Request) => {
      const urlStr = typeof url === 'string' ? url : url.toString();
      if (urlStr.includes('/verify')) {
        return {
          ok: false,
          status: 401,
          statusText: 'Unauthorized',
          headers: new Headers({ 'content-type': 'application/json' }),
          json: async () =>
            createNestedGlobalError(
              'conflict',
              'challenge_expired',
              'Challenge 驗證已過期，請重新發起挑戰',
              false
            ),
        };
      }
      return {
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => createStage1Envelope(),
      };
    });

    render(<LoginPage />);

    fireEvent.change(screen.getByLabelText('帳號 (Username)'), { target: { value: 'admin_expired' } });
    fireEvent.change(screen.getByLabelText('密碼 (Password)'), { target: { value: 'pass' } });
    fireEvent.click(screen.getByRole('button', { name: /下一步：進行雙重驗證/ }));

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /雙重身分驗證/ })).toBeInTheDocument();
    });

    for (let i = 0; i < 6; i++) {
      fireEvent.change(document.getElementById(`totp-${i}`)!, {
        target: { value: '1' },
      });
    }

    fireEvent.click(screen.getByRole('button', { name: /驗證並登入系統/ }));

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: '月子工會管理系統' })).toBeInTheDocument();
      expect(screen.getByText(/驗證階段已過期，請重新輸入帳號密碼/)).toBeInTheDocument();
    });

    const usernameInput = screen.getByLabelText('帳號 (Username)') as HTMLInputElement;
    expect(usernameInput.value).toBe('admin_expired');
  });

  it('Stage 2 客戶端過期檢測：本地 expires_at 超時提交時即刻阻擋並退回 Stage 1', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => ({
        success: true,
        message: '請輸入驗證器代碼',
        data: {
          challenge_id: 'ch-expired-id',
          challenge_token: 'tok-32chars-minimum-expired-token-12345678',
          expires_at: new Date(Date.now() - 10000).toISOString(), // 10 seconds ago
        },
        error: null,
      }),
    });

    render(<LoginPage />);

    fireEvent.change(screen.getByLabelText('帳號 (Username)'), { target: { value: 'admin' } });
    fireEvent.change(screen.getByLabelText('密碼 (Password)'), { target: { value: 'pass' } });
    fireEvent.click(screen.getByRole('button', { name: /下一步：進行雙重驗證/ }));

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /雙重身分驗證/ })).toBeInTheDocument();
    });

    for (let i = 0; i < 6; i++) {
      fireEvent.change(document.getElementById(`totp-${i}`)!, {
        target: { value: '1' },
      });
    }

    const fetchSpy = vi.fn();
    globalThis.fetch = fetchSpy;

    fireEvent.click(screen.getByRole('button', { name: /驗證並登入系統/ }));

    expect(screen.getByRole('heading', { name: '月子工會管理系統' })).toBeInTheDocument();
    expect(screen.getByText(/驗證階段已過期，請重新輸入帳號密碼/)).toBeInTheDocument();
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it('Stage 2 錯誤處理：429 頻率限制應留在 Stage 2 並提示「驗證嘗試過於頻繁，請稍後再試」', async () => {
    globalThis.fetch = vi.fn().mockImplementation(async (url: string | URL | Request) => {
      const urlStr = typeof url === 'string' ? url : url.toString();
      if (urlStr.includes('/verify')) {
        return {
          ok: false,
          status: 429,
          statusText: 'Too Many Requests',
          headers: new Headers({ 'content-type': 'application/json' }),
          json: async () => MOCK_429_RATE_LIMITED_PAYLOAD,
        };
      }
      return {
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => createStage1Envelope(),
      };
    });

    render(<LoginPage />);

    fireEvent.change(screen.getByLabelText('帳號 (Username)'), { target: { value: 'admin' } });
    fireEvent.change(screen.getByLabelText('密碼 (Password)'), { target: { value: 'pass' } });
    fireEvent.click(screen.getByRole('button', { name: /下一步：進行雙重驗證/ }));

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /雙重身分驗證/ })).toBeInTheDocument();
    });

    for (let i = 0; i < 6; i++) {
      fireEvent.change(document.getElementById(`totp-${i}`)!, {
        target: { value: '5' },
      });
    }

    fireEvent.click(screen.getByRole('button', { name: /驗證並登入系統/ }));

    await waitFor(() => {
      expect(screen.getByText(/驗證嘗試過於頻繁，請稍後再試/)).toBeInTheDocument();
    });

    expect(screen.getByRole('heading', { name: /雙重身分驗證/ })).toBeInTheDocument();
  });

  it('點擊「返回重新輸入帳密」按鈕：應清除 Stage 2 狀態、清除錯誤訊息並返回 Stage 1', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => createStage1Envelope(),
    });

    render(<LoginPage />);

    fireEvent.change(screen.getByLabelText('帳號 (Username)'), { target: { value: 'custom_admin' } });
    fireEvent.change(screen.getByLabelText('密碼 (Password)'), { target: { value: 'secret' } });
    fireEvent.click(screen.getByRole('button', { name: /下一步：進行雙重驗證/ }));

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /雙重身分驗證/ })).toBeInTheDocument();
    });

    const backBtn = screen.getByRole('button', { name: /返回重新輸入帳密/ });
    fireEvent.click(backBtn);

    expect(screen.getByRole('heading', { name: '月子工會管理系統' })).toBeInTheDocument();
    const usernameInput = screen.getByLabelText('帳號 (Username)') as HTMLInputElement;
    const passwordInput = screen.getByLabelText('密碼 (Password)') as HTMLInputElement;
    expect(usernameInput.value).toBe('custom_admin');
    expect(passwordInput.value).toBe('');
  });

  it('機密安全防護 (Secret Hygiene)：全流程中 localStorage / sessionStorage / DOM 均不洩漏任何機密', async () => {
    const setItemSpy = vi.spyOn(Storage.prototype, 'setItem');

    globalThis.fetch = vi.fn().mockImplementation(async (url: string | URL | Request) => {
      const urlStr = typeof url === 'string' ? url : url.toString();
      if (urlStr.includes('/verify')) {
        return {
          ok: true,
          status: 200,
          headers: new Headers({ 'content-type': 'application/json' }),
          json: async () => MOCK_STAGE2_ENVELOPE,
        };
      }
      return {
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => createStage1Envelope(),
      };
    });

    const { container } = render(<LoginPage />);

    // Stage 1
    fireEvent.change(screen.getByLabelText('帳號 (Username)'), { target: { value: 'admin_test' } });
    fireEvent.change(screen.getByLabelText('密碼 (Password)'), { target: { value: 'ValidPassword123!' } });
    fireEvent.click(screen.getByRole('button', { name: /下一步：進行雙重驗證/ }));

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /雙重身分驗證/ })).toBeInTheDocument();
    });

    // Stage 2
    for (let i = 0; i < 6; i++) {
      fireEvent.change(document.getElementById(`totp-${i}`)!, {
        target: { value: String(i + 1) },
      });
    }

    fireEvent.click(screen.getByRole('button', { name: /驗證並登入系統/ }));

    await waitFor(() => {
      expect(sessionClient.isAuthenticated()).toBe(true);
    });

    // Storage Audit
    expect(window.localStorage.getItem('token')).toBeNull();
    expect(window.localStorage.getItem('access_token')).toBeNull();
    expect(window.localStorage.getItem('challenge_token')).toBeNull();
    expect(window.sessionStorage.getItem('token')).toBeNull();
    expect(window.sessionStorage.getItem('access_token')).toBeNull();
    expect(window.sessionStorage.getItem('challenge_token')).toBeNull();

    const writtenKeys = setItemSpy.mock.calls.map((call) => call[0]);
    expect(writtenKeys).not.toContain('token');
    expect(writtenKeys).not.toContain('access_token');
    expect(writtenKeys).not.toContain('challenge_token');

    // DOM Audit: No secret token in HTML markup
    expect(container.innerHTML).not.toContain('tok-stage1-secret');
    expect(container.innerHTML).not.toContain('bearer-test-access-token');
  });
});
