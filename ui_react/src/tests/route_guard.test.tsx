/**
 * @file route_guard.test.tsx
 * @description 驗證路由認證守衛、深層連結阻擋、URL Hash 雙向同步與登出狀態遷移。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { App } from '../App';
import { sessionClient } from '../api/auth/session_client';

describe('Route Guard & Shell Hash Navigation', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    vi.restoreAllMocks();
    sessionClient.clearSession();
    window.location.hash = '';

    globalThis.fetch = vi.fn().mockImplementation(async (url: string | URL | Request) => {
      const urlStr = typeof url === 'string' ? url : url.toString();

      if (urlStr.includes('/api/v1/admin/auth/login/challenges') && urlStr.includes('/verify')) {
        return {
          ok: true,
          status: 200,
          headers: new Headers({ 'content-type': 'application/json' }),
          json: async () => ({
            success: true,
            message: '登入成功',
            data: {
              access_token: 'bearer-guard-access-token',
              token_type: 'bearer',
              expires_at: '2099-12-31T23:59:59Z',
              admin: {
                id: 1,
                username: 'admin',
                display_name: '系統管理員',
                role: 'system_admin',
                capabilities: ['system.administration'],
                is_root: true,
                access_control_version: 1,
              },
            },
            error: null,
          }),
        };
      }

      if (urlStr.includes('/api/v1/admin/auth/login/challenges')) {
        return {
          ok: true,
          status: 200,
          headers: new Headers({ 'content-type': 'application/json' }),
          json: async () => ({
            success: true,
            message: '請輸入驗證器代碼',
            data: {
              challenge_id: 'ch-guard-test-12345',
              challenge_token: 'tok-guard-test-32chars-minimum-abcdef123456',
              expires_at: '2099-12-31T23:59:59Z',
            },
            error: null,
          }),
        };
      }

      if (urlStr.includes('/api/v1/admin/auth/logout')) {
        return {
          ok: true,
          status: 200,
          headers: new Headers({ 'content-type': 'application/json' }),
          json: async () => ({
            success: true,
            message: '已成功登出',
            data: { logged_out: true },
            error: null,
          }),
        };
      }

      // Default telemetry/metrics endpoint
      return {
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
      };
    });
  });

  afterEach(() => {
    sessionClient.clearSession();
    window.location.hash = '';
    globalThis.fetch = originalFetch;
  });

  it('未認證時應阻擋受保護的工作區並渲染 LoginPage', () => {
    render(<App />);

    expect(
      screen.getByRole('heading', { name: '月子工會管理系統' })
    ).toBeInTheDocument();
    expect(screen.queryByText('營運作業 (Operations)')).not.toBeInTheDocument();
  });

  it('未認證時即使存取深層 Hash (如 #finance) 仍受路由守衛攔截', () => {
    window.location.hash = '#finance';
    render(<App />);

    expect(
      screen.getByRole('heading', { name: '月子工會管理系統' })
    ).toBeInTheDocument();
    expect(screen.queryByText('帳務中心')).not.toBeInTheDocument();
  });

  it('登入成功後應解鎖主版面並呈現預設待辦看板', async () => {
    render(<App />);

    // Stage 1
    fireEvent.change(screen.getByLabelText('帳號 (Username)'), { target: { value: 'admin' } });
    fireEvent.change(screen.getByLabelText('密碼 (Password)'), { target: { value: 'secret' } });
    fireEvent.click(screen.getByRole('button', { name: /下一步：進行雙重驗證/ }));

    // Stage 2
    await waitFor(() => {
      expect(document.getElementById('totp-0')).toBeInTheDocument();
    });

    for (let i = 0; i < 6; i++) {
      fireEvent.change(document.getElementById(`totp-${i}`)!, {
        target: { value: '9' },
      });
    }

    fireEvent.click(screen.getByRole('button', { name: /驗證並登入系統/ }));

    await waitFor(() => {
      expect(screen.getByText('營運作業 (Operations)')).toBeInTheDocument();
      expect(screen.getByText('帳務作業 (Finance)')).toBeInTheDocument();
      expect(screen.getByText('稽核與系統 (Audit & System)')).toBeInTheDocument();
    });
  });

  it('在已認證狀態下，點擊側邊欄應切換頁面並同步更新 URL Hash', async () => {
    sessionClient.setSession('valid-token', {
      id: 1,
      username: 'admin',
      display_name: '系統管理員',
      role: 'system_admin',
      capabilities: ['system.administration'],
    });

    render(<App />);

    expect(screen.getByText('營運作業 (Operations)')).toBeInTheDocument();

    const ordersNav = screen.getByTitle('訂單管理');
    fireEvent.click(ordersNav);

    expect(window.location.hash).toBe('#orders');
  });

  it('切換頂部主作業區分頁應切換側邊欄與頁面視圖', async () => {
    sessionClient.setSession('valid-token', {
      id: 1,
      username: 'admin',
      display_name: '系統管理員',
      role: 'system_admin',
      capabilities: ['system.administration'],
    });

    render(<App />);

    const financeTab = screen.getByRole('button', { name: /帳務作業/ });
    fireEvent.click(financeTab);

    expect(screen.getByTitle('帳務中心')).toBeInTheDocument();
  });

  it('觸發 hashchange 事件時應響應式更新對應頁面視圖', async () => {
    sessionClient.setSession('valid-token', {
      id: 1,
      username: 'admin',
      display_name: '系統管理員',
      role: 'system_admin',
      capabilities: ['system.administration'],
    });

    render(<App />);

    act(() => {
      window.location.hash = '#scheduling';
      window.dispatchEvent(new HashChangeEvent('hashchange'));
    });

    await waitFor(() => {
      const activeNav = screen.getByTitle('排班日曆');
      expect(activeNav).toHaveClass('active');
    });
  });

  it('點擊登出按鈕應清除會話、卸載主版面並跳轉至 #login', async () => {
    sessionClient.setSession('valid-token', {
      id: 1,
      username: 'admin',
      display_name: '系統管理員',
      role: 'system_admin',
      capabilities: ['system.administration'],
    });

    render(<App />);

    const logoutBtn = screen.getByTitle('點擊登出系統');
    await act(async () => {
      fireEvent.click(logoutBtn);
    });

    await waitFor(() => {
      expect(sessionClient.isAuthenticated()).toBe(false);
      expect(window.location.hash).toBe('#login');
      expect(screen.getByRole('heading', { name: '月子工會管理系統' })).toBeInTheDocument();
    });
  });
});
