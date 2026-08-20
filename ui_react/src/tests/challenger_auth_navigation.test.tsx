/**
 * @file challenger_auth_navigation.test.tsx
 * @description 實證挑戰者測試套件：對 URL Hash 導航、ErrorBoundary 容錯防護及 Session 認證邊界進行對抗性壓力測試。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import React, { useState } from 'react';
import { App } from '../App';
import { ErrorBoundary } from '../components/ErrorBoundary';
import { sessionClient } from '../api/auth/session_client';
import { PAGE_SECTION_MAP } from '../components/MasterLayout';
import { LoginPage } from '../pages/LoginPage';

describe('Adversarial Challenge: URL Hash Navigation & Routing', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    vi.restoreAllMocks();
    sessionClient.clearSession();
    window.location.hash = '';

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => ({
        success: true,
        data: {
          started_at: '2026-08-09T00:00:00Z',
          request_count: 10,
          average_response_time_ms: 15.0,
          p50_response_time_upper_bound_ms: 10,
          p95_response_time_upper_bound_ms: 20,
          maximum_response_time_ms: 80.0,
        },
        error: null,
      }),
    });
  });

  afterEach(() => {
    sessionClient.clearSession();
    window.location.hash = '';
    globalThis.fetch = originalFetch;
  });

  const authenticateSession = () => {
    sessionClient.setSession('test-auth-token-12345', {
      id: 1,
      username: 'admin',
      display_name: '系統管理員',
      role: 'system_admin',
      capabilities: ['system.administration'],
    });
  };

  it('[Hash-1] 空 Hash (#) 與空字串應乾淨回退至預設待辦看板 (#order-tracker)', async () => {
    authenticateSession();

    window.location.hash = '#';
    const { unmount } = render(<App />);

    await waitFor(() => {
      const activeNav = screen.getByTitle('待辦看板');
      expect(activeNav).toHaveClass('active');
    });

    unmount();

    window.location.hash = '';
    render(<App />);

    await waitFor(() => {
      const activeNav = screen.getByTitle('待辦看板');
      expect(activeNav).toHaveClass('active');
    });
  });

  it('[Hash-2] 未知或不存在的路由 (#unknown-page-999) 應乾淨回退至待辦看板', async () => {
    authenticateSession();

    window.location.hash = '#unknown-page-999';
    render(<App />);

    await waitFor(() => {
      const activeNav = screen.getByTitle('待辦看板');
      expect(activeNav).toHaveClass('active');
      expect(screen.getByText('待辦看板')).toBeInTheDocument();
    });
  });

  it('[Hash-3] 帶有斜線前綴的 Hash (#/finance) 應被正則解析並對應至正確頁面與分頁', async () => {
    authenticateSession();

    window.location.hash = '#/finance';
    render(<App />);

    await waitFor(() => {
      const financeTab = screen.getByRole('button', { name: /帳務作業/ });
      expect(financeTab).toHaveClass('active');
      const financeNav = screen.getByTitle('帳務中心');
      expect(financeNav).toHaveClass('active');
    });
  });

  it('[Hash-4] 未登入狀態下，無論存取何種已知或惡意 Hash，均嚴格阻擋並渲染 LoginPage', async () => {
    const attackHashes = [
      '#orders',
      '#finance',
      '#anomalies',
      '#account-management',
      '#scheduling',
      '#staff',
      '#data-import',
      '#line-management',
      '#reports',
      '#data-browser',
      '#<script>alert(1)</script>',
      '#../../etc/passwd',
      '#undefined',
      '#null',
      '#constructor',
      '#%20%20%20',
      '#orders?filter=urgent&sort=desc',
    ];

    for (const testHash of attackHashes) {
      window.location.hash = testHash;
      const { unmount } = render(<App />);

      expect(
        screen.getByRole('heading', { name: '月子工會管理系統' })
      ).toBeInTheDocument();
      expect(screen.queryByText('營運作業 (Operations)')).not.toBeInTheDocument();
      expect(screen.queryByText('帳務作業 (Finance)')).not.toBeInTheDocument();
      expect(screen.queryByText('稽核與系統 (Audit & System)')).not.toBeInTheDocument();

      unmount();
    }
  });

  it('[Hash-5] 連續高頻快速切換 Hash (100 次切換壓力) 不應導致狀態紊亂或畫面崩潰', async () => {
    authenticateSession();
    render(<App />);

    const routes = Object.keys(PAGE_SECTION_MAP);

    await act(async () => {
      for (let i = 0; i < 100; i++) {
        const targetRoute = routes[i % routes.length];
        window.location.hash = `#${targetRoute}`;
        window.dispatchEvent(new HashChangeEvent('hashchange'));
      }
    });

    const finalRoute = routes[99 % routes.length];
    const finalSection = PAGE_SECTION_MAP[finalRoute as keyof typeof PAGE_SECTION_MAP];

    await waitFor(() => {
      const expectedTabName =
        finalSection === 'operations'
          ? /營運作業/
          : finalSection === 'finance'
          ? /帳務作業/
          : /稽核與系統/;
      expect(screen.getByRole('button', { name: expectedTabName })).toHaveClass('active');
    });
  });

  it('[Hash-6] 原型污染屬性探針 (#toString, #valueOf, #hasOwnProperty) 在認證後存取不應造成未處理異常', async () => {
    authenticateSession();

    const protoProbes = ['#toString', '#valueOf', '#hasOwnProperty', '#isPrototypeOf'];
    for (const probe of protoProbes) {
      window.location.hash = probe;
      const { unmount } = render(<App />);

      // Must render App shell without throw
      expect(screen.getByText(/月子工會管理系統/)).toBeInTheDocument();
      unmount();
    }
  });
});

describe('Adversarial Challenge: ErrorBoundary Component', () => {
  const originalConsoleError = console.error;
  beforeEach(() => {
    console.error = vi.fn();
  });
  afterEach(() => {
    console.error = originalConsoleError;
  });

  const BuggyChild: React.FC<{ shouldThrow: boolean; errorMessage?: string }> = ({
    shouldThrow,
    errorMessage = 'Deliberate Component Crash',
  }) => {
    if (shouldThrow) {
      throw new Error(errorMessage);
    }
    return <div data-testid="healthy-child">Healthy Content Rendered</div>;
  };

  it('[EB-1] 子元件拋出渲染例外時，ErrorBoundary 應成功捕獲並呈現防護降級 UI 與錯誤訊息', () => {
    render(
      <ErrorBoundary>
        <BuggyChild shouldThrow={true} errorMessage="Adversarial Failure Mode" />
      </ErrorBoundary>
    );

    expect(screen.getByText('畫面載入發生異常')).toBeInTheDocument();
    expect(screen.getByText('Adversarial Failure Mode')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '重新嘗試' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '重新載入頁面' })).toBeInTheDocument();
    expect(screen.queryByTestId('healthy-child')).not.toBeInTheDocument();
  });

  it('[EB-2] 自訂 fallback prop 時，應優先呈現自訂降級視圖', () => {
    render(
      <ErrorBoundary fallback={<div data-testid="custom-fallback-ui">Custom Recovery View</div>}>
        <BuggyChild shouldThrow={true} />
      </ErrorBoundary>
    );

    expect(screen.getByTestId('custom-fallback-ui')).toBeInTheDocument();
    expect(screen.queryByText('畫面載入發生異常')).not.toBeInTheDocument();
  });

  it('[EB-3] 點擊「重新嘗試」按鈕後，若底層錯誤已排除，應成功重設狀態並恢復正常渲染', () => {
    const TestContainer: React.FC = () => {
      const [hasBug, setHasBug] = useState(true);
      return (
        <div>
          <button onClick={() => setHasBug(false)} data-testid="fix-bug-btn">
            Fix Bug
          </button>
          <ErrorBoundary>
            <BuggyChild shouldThrow={hasBug} errorMessage="Temporary Failure" />
          </ErrorBoundary>
        </div>
      );
    };

    render(<TestContainer />);

    // Initially in error state
    expect(screen.getByText('畫面載入發生異常')).toBeInTheDocument();
    expect(screen.queryByTestId('healthy-child')).not.toBeInTheDocument();

    // Fix the bug condition
    fireEvent.click(screen.getByTestId('fix-bug-btn'));

    // Click retry in ErrorBoundary
    fireEvent.click(screen.getByRole('button', { name: '重新嘗試' }));

    // Should recover
    expect(screen.queryByText('畫面載入發生異常')).not.toBeInTheDocument();
    expect(screen.getByTestId('healthy-child')).toBeInTheDocument();
  });

  it('[EB-4] 巢狀 ErrorBoundary 應具備區域隔離能力，內部崩潰不影響外層正常區塊', () => {
    render(
      <div data-testid="parent-container">
        <div data-testid="outer-healthy-area">Outer Healthy Area</div>
        <ErrorBoundary>
          <div data-testid="inner-isolated-area">
            <ErrorBoundary>
              <BuggyChild shouldThrow={true} errorMessage="Inner Crash" />
            </ErrorBoundary>
          </div>
        </ErrorBoundary>
      </div>
    );

    expect(screen.getByTestId('outer-healthy-area')).toBeInTheDocument();
    expect(screen.getByText('Inner Crash')).toBeInTheDocument();
    expect(screen.getByText('畫面載入發生異常')).toBeInTheDocument();
  });
});

describe('Adversarial Challenge: Auth Boundary & Session Storage Audit', () => {
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

  it('[Auth-1] 嚴格資安審計：整個認證流程中絕不可向 localStorage / sessionStorage 寫入任何 Token', async () => {
    const setItemSpy = vi.spyOn(Storage.prototype, 'setItem');

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => ({
        success: true,
        message: 'Success',
        data: {
          access_token: 'secret-jwt-token-alpha-99',
          token_type: 'bearer',
          expires_at: '2026-08-16T12:00:00Z',
          admin: {
            id: 1,
            username: 'admin',
            display_name: '管理員',
            role: 'system_admin',
            capabilities: ['system.administration'],
          },
        },
        error: null,
      }),
    });

    // Perform login
    await sessionClient.login({ username: 'admin', password: 'password123' });

    expect(sessionClient.isAuthenticated()).toBe(true);
    expect(sessionClient.getToken()).toBe('secret-jwt-token-alpha-99');

    // Storage Audit
    expect(window.localStorage.getItem('token')).toBeNull();
    expect(window.localStorage.getItem('access_token')).toBeNull();
    expect(window.localStorage.getItem('auth')).toBeNull();
    expect(window.sessionStorage.getItem('token')).toBeNull();
    expect(window.sessionStorage.getItem('access_token')).toBeNull();

    // Verify setItem was never called on Storage for auth tokens
    const storageKeysWritten = setItemSpy.mock.calls.map((call) => call[0]);
    expect(storageKeysWritten).not.toContain('token');
    expect(storageKeysWritten).not.toContain('access_token');
    expect(storageKeysWritten).not.toContain('jwt');
  });

  it('[Auth-2] 嚴格落實 BLOCKED_AUTH_RESTORE_DECISION：restoreSession 必須恆傳回 null', async () => {
    const restored = await sessionClient.restoreSession();
    expect(restored).toBeNull();
  });

  it('[Auth-3] 登出後記憶體 Token 必須徹底清空，且即使後端登出端點回傳 500 錯誤仍保證客戶端清空', async () => {
    sessionClient.setSession('temp-token-xyz', {
      id: 99,
      username: 'temp_user',
      display_name: '臨時用戶',
      role: 'staff',
      capabilities: [],
    });

    expect(sessionClient.isAuthenticated()).toBe(true);

    // Mock logout endpoint returning 500 Internal Server Error
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      statusText: 'Internal Server Error',
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => ({
        detail: {
          code: 'server_error',
          message: 'Logout failed on server',
          retryable: false,
        },
      }),
    });

    await sessionClient.logout();

    // In-memory token and user must be immediately wiped
    expect(sessionClient.isAuthenticated()).toBe(false);
    expect(sessionClient.getToken()).toBeNull();
    expect(sessionClient.getCurrentUser()).toBeNull();
  });

  it('[Auth-4] 未登入狀態下呼叫 fetchCurrentUser 或 refreshToken 應立即拒絕並拋出明確例外', async () => {
    sessionClient.clearSession();

    await expect(sessionClient.fetchCurrentUser()).rejects.toThrow('未登入或 Session 已清除');
    await expect(sessionClient.refreshToken()).rejects.toThrow('未登入或 Session 已清除');
  });

  it('[Auth-5] 登入請求參數校驗：空帳號或空密碼應在客戶端即刻被 Zod 阻擋而不發起網路請求', async () => {
    const fetchSpy = vi.fn();
    globalThis.fetch = fetchSpy;

    await expect(
      sessionClient.login({ username: '', password: 'password123' })
    ).rejects.toThrow(/請輸入帳號/);

    await expect(
      sessionClient.login({ username: 'admin', password: '' })
    ).rejects.toThrow(/請輸入密碼/);

    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it('[Auth-6] 多並行登入與會話切換壓力測試：最後成功的登入應正確覆寫記憶體狀態且無競態殘留', async () => {
    globalThis.fetch = vi.fn().mockImplementation(async (_url, options) => {
      const body = JSON.parse(options.body);
      return {
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({
          success: true,
          message: 'Success',
          data: {
            access_token: `token-for-${body.username}`,
            token_type: 'bearer',
            expires_at: '2026-08-16T12:00:00Z',
            admin: {
              id: body.username === 'userA' ? 10 : 20,
              username: body.username,
              display_name: body.username,
              role: 'system_admin',
              capabilities: [],
            },
          },
          error: null,
        }),
      };
    });

    // Trigger two concurrent login attempts
    const [resA, resB] = await Promise.all([
      sessionClient.login({ username: 'userA', password: 'passA' }),
      sessionClient.login({ username: 'userB', password: 'passB' }),
    ]);

    expect(resA.access_token).toBe('token-for-userA');
    expect(resB.access_token).toBe('token-for-userB');

    // Memory session should hold the latest resolved user
    expect(sessionClient.isAuthenticated()).toBe(true);
    expect(sessionClient.getToken()).toMatch(/^token-for-user[AB]$/);
  });

  it('[Auth-7] fetchCurrentUser 與 refreshToken 必須正確夾帶 Bearer Token 請求頭', async () => {
    sessionClient.setSession('bearer-test-token-777', {
      id: 5,
      username: 'token_user',
      display_name: 'Token User',
      role: 'staff',
      capabilities: [],
    });

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => ({
        success: true,
        message: 'Success',
        data: {
          id: 5,
          username: 'token_user',
          display_name: 'Token User',
          role: 'staff',
          capabilities: [],
        },
        error: null,
      }),
    });

    await sessionClient.fetchCurrentUser();

    expect(globalThis.fetch).toHaveBeenCalledWith(
      '/api/v1/admin/auth/me',
      expect.objectContaining({
        headers: expect.objectContaining({
          Authorization: 'Bearer bearer-test-token-777',
        }),
      })
    );
  });

  it('[Auth-8] LoginPage 表單防護：純空格帳號密碼提交應即時阻擋', () => {
    render(<LoginPage />);

    const usernameInput = screen.getByLabelText('帳號 (Username)');
    const passwordInput = screen.getByLabelText('密碼 (Password)');

    fireEvent.change(usernameInput, { target: { value: '   ' } });
    fireEvent.change(passwordInput, { target: { value: '   ' } });

    fireEvent.click(screen.getByRole('button', { name: /下一步：進行雙重驗證/ }));

    expect(screen.getByText(/請輸入帳號/)).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: /雙重身分驗證/ })).not.toBeInTheDocument();
  });
});
