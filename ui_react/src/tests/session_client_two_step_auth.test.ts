/**
 * File: session_client_two_step_auth.test.ts
 * Description: 驗證兩步驟認證、嚴格解碼、記憶體隔離與錯誤碼傳遞。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { ZodError } from 'zod';
import {
  sessionClient,
  issuePasswordChallenge,
  verifyPasswordChallenge,
  fetchCurrentUser,
  getProfile,
  refreshSession,
  refreshToken,
  logout,
  setSession,
  clearSession,
  getToken,
  getUser,
  isAuthenticated,
  AdminPasswordChallengeRequestSchema,
  AdminPasswordChallengeResponseSchema,
  AdminFactorVerificationRequestSchema,
  AdminPublicSchema,
  AdminSessionResponseSchema,
  AdminRefreshResponseSchema,
} from '../api/auth/session_client';
import {
  ApiHttpError,
  ApiDecodeError,
} from '../api/shared/typed_errors';
import {
  MOCK_STAGE1_REQUEST,
  MOCK_STAGE1_RESPONSE,
  MOCK_STAGE1_ENVELOPE,
  MOCK_STAGE2_REQUEST,
  MOCK_STAGE2_RESPONSE,
  MOCK_STAGE2_ENVELOPE,
  MOCK_ADMIN_PUBLIC,
  MOCK_ME_ENVELOPE,
  MOCK_REFRESH_RESPONSE,
  MOCK_REFRESH_ENVELOPE,
  MOCK_LOGOUT_ENVELOPE,
  MOCK_401_INVALID_CREDENTIALS_PAYLOAD,
  MOCK_403_MFA_ENROLLMENT_PAYLOAD,
  MOCK_503_AUTH_UNAVAILABLE_PAYLOAD,
} from './fixtures/auth/two_step_auth_contract_fixtures';

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
      correlation_id: 'session-test-correlation-001',
      current_version: null,
    },
  },
});

describe('SessionClient & Two-Step Auth Test Suite', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    vi.restoreAllMocks();
    sessionClient.clearSession();
  });

  afterEach(() => {
    sessionClient.clearSession();
    globalThis.fetch = originalFetch;
  });

  // ==========================================================================
  // 1. Stage 1: Password Challenge (POST /login/challenges)
  // ==========================================================================
  describe('Stage 1: Password Challenge Flow', () => {
    it('成功發起挑戰應回傳 challenge_id, challenge_token, expires_at 且不建立會話', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => MOCK_STAGE1_ENVELOPE,
      });

      const response = await sessionClient.issuePasswordChallenge(
        MOCK_STAGE1_REQUEST.username,
        MOCK_STAGE1_REQUEST.password
      );

      expect(response).toEqual(MOCK_STAGE1_RESPONSE);
      expect(sessionClient.isAuthenticated()).toBe(false);
      expect(sessionClient.getToken()).toBeNull();
      expect(sessionClient.getUser()).toBeNull();

      expect(globalThis.fetch).toHaveBeenCalledWith(
        '/api/v1/admin/auth/login/challenges',
        expect.objectContaining({
          method: 'POST',
          headers: expect.objectContaining({
            'Content-Type': 'application/json',
          }),
          body: JSON.stringify(MOCK_STAGE1_REQUEST),
        })
      );
    });

    it('獨立匯出之 issuePasswordChallenge 函式應正常運作', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => MOCK_STAGE1_ENVELOPE,
      });

      const response = await issuePasswordChallenge(
        MOCK_STAGE1_REQUEST.username,
        MOCK_STAGE1_REQUEST.password
      );

      expect(response.challenge_id).toBe(MOCK_STAGE1_RESPONSE.challenge_id);
    });

    it('空帳號或密碼應於客戶端立即阻擋並拋出 Zod 驗證錯誤', async () => {
      const fetchSpy = vi.fn();
      globalThis.fetch = fetchSpy;

      await expect(
        sessionClient.issuePasswordChallenge('', 'some-password')
      ).rejects.toThrow(ZodError);

      await expect(
        sessionClient.issuePasswordChallenge('admin', '')
      ).rejects.toThrow(ZodError);

      expect(fetchSpy).not.toHaveBeenCalled();
    });

    it('後端回傳 401 invalid_credentials_or_factor 應拋出 typed ApiHttpError', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 401,
        statusText: 'Unauthorized',
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => MOCK_401_INVALID_CREDENTIALS_PAYLOAD,
      });

      const promise = sessionClient.issuePasswordChallenge(
        'wrong_user',
        'wrong_password'
      );

      await expect(promise).rejects.toThrow(ApiHttpError);
      try {
        await promise;
      } catch (err) {
        const httpErr = err as ApiHttpError;
        expect(httpErr.status).toBe(401);
        expect(httpErr.code).toBe('invalid_credentials_or_factor');
        expect(httpErr.message).toBe('帳號、密碼或驗證碼錯誤');
        expect(httpErr.retryable).toBe(false);
      }
    });

    it('後端回傳 403 mfa_enrollment_required 應拋出包含正確 error code 之 ApiHttpError', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 403,
        statusText: 'Forbidden',
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => MOCK_403_MFA_ENROLLMENT_PAYLOAD,
      });

      try {
        await sessionClient.issuePasswordChallenge('new_user', 'password123');
        expect.unreachable('應拋出例外');
      } catch (err) {
        const httpErr = err as ApiHttpError;
        expect(httpErr.status).toBe(403);
        expect(httpErr.code).toBe('mfa_enrollment_required');
        expect(httpErr.message).toBe('請完成 MFA 綁定後再登入');
      }
    });

    it('後端回傳 429 login_rate_limited 應標記 retryable: true', async () => {
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

      try {
        await sessionClient.issuePasswordChallenge('admin', 'password');
        expect.unreachable('應拋出例外');
      } catch (err) {
        const httpErr = err as ApiHttpError;
        expect(httpErr.status).toBe(429);
        expect(httpErr.code).toBe('login_rate_limited');
        expect(httpErr.retryable).toBe(true);
      }
    });

    it('後端回傳 503 admin_auth_unavailable 應標記 retryable: true', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 503,
        statusText: 'Service Unavailable',
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => MOCK_503_AUTH_UNAVAILABLE_PAYLOAD,
      });

      try {
        await sessionClient.issuePasswordChallenge('admin', 'password');
        expect.unreachable('應拋出例外');
      } catch (err) {
        const httpErr = err as ApiHttpError;
        expect(httpErr.status).toBe(503);
        expect(httpErr.code).toBe('admin_auth_unavailable');
        expect(httpErr.retryable).toBe(true);
      }
    });
  });

  // ==========================================================================
  // 2. Stage 2: Factor Verification (POST /login/challenges/{id}/verify)
  // ==========================================================================
  describe('Stage 2: Factor Verification Flow', () => {
    it('驗證成功應解碼 AdminSessionResponse 並自動寫入記憶體會話', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => MOCK_STAGE2_ENVELOPE,
      });

      const challengeId = 'ch-test-uuid-9999-aaaa-bbbb';
      const sessionData = await sessionClient.verifyPasswordChallenge(
        challengeId,
        MOCK_STAGE2_REQUEST.challenge_token,
        MOCK_STAGE2_REQUEST.factor_code
      );

      expect(sessionData).toEqual(MOCK_STAGE2_RESPONSE);
      expect(sessionClient.isAuthenticated()).toBe(true);
      expect(sessionClient.getToken()).toBe(MOCK_STAGE2_RESPONSE.access_token);
      expect(sessionClient.getUser()).toEqual(MOCK_ADMIN_PUBLIC);

      expect(globalThis.fetch).toHaveBeenCalledWith(
        `/api/v1/admin/auth/login/challenges/${encodeURIComponent(challengeId)}/verify`,
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify(MOCK_STAGE2_REQUEST),
        })
      );
    });

    it('獨立匯出之 verifyPasswordChallenge 函式應正常運作', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => MOCK_STAGE2_ENVELOPE,
      });

      const sessionData = await verifyPasswordChallenge(
        'ch-1234',
        MOCK_STAGE2_REQUEST.challenge_token,
        '654321'
      );

      expect(sessionData.access_token).toBe(MOCK_STAGE2_RESPONSE.access_token);
      expect(isAuthenticated()).toBe(true);
      expect(getToken()).toBe(MOCK_STAGE2_RESPONSE.access_token);
      expect(getUser()).toEqual(MOCK_ADMIN_PUBLIC);
    });

    it('URL 包含特殊字元之 challenge_id 必須被正則安全轉義 (encodeURIComponent)', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => MOCK_STAGE2_ENVELOPE,
      });

      const rawChallengeId = 'id/with+special#chars?&';
      await sessionClient.verifyPasswordChallenge(
        rawChallengeId,
        MOCK_STAGE2_REQUEST.challenge_token,
        '123456'
      );

      const expectedEncoded = encodeURIComponent(rawChallengeId);
      expect(globalThis.fetch).toHaveBeenCalledWith(
        `/api/v1/admin/auth/login/challenges/${expectedEncoded}/verify`,
        expect.anything()
      );
    });

    it('缺少 challenge_id 應於呼叫前拋出例外', async () => {
      const fetchSpy = vi.fn();
      globalThis.fetch = fetchSpy;

      await expect(
        sessionClient.verifyPasswordChallenge(
          '',
          MOCK_STAGE2_REQUEST.challenge_token,
          '123456'
        )
      ).rejects.toThrow('缺少 challenge_id 參數');

      expect(fetchSpy).not.toHaveBeenCalled();
    });

    it('動態碼非 6 位數字 (如 5 位、7 位、含字母) 應於客戶端阻擋並拋出 Zod 驗證錯誤', async () => {
      const fetchSpy = vi.fn();
      globalThis.fetch = fetchSpy;

      const invalidCodes = ['12345', '1234567', 'abcdef', '12 456', '12-456'];
      for (const code of invalidCodes) {
        await expect(
          sessionClient.verifyPasswordChallenge(
            'ch-test',
            MOCK_STAGE2_REQUEST.challenge_token,
            code
          )
        ).rejects.toThrow(ZodError);
      }

      expect(fetchSpy).not.toHaveBeenCalled();
    });

    it('Stage 2 驗證失敗 (401 invalid_credentials_or_factor) 不應寫入 Session', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 401,
        statusText: 'Unauthorized',
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => MOCK_401_INVALID_CREDENTIALS_PAYLOAD,
      });

      await expect(
        sessionClient.verifyPasswordChallenge(
          'ch-test',
          MOCK_STAGE2_REQUEST.challenge_token,
          '999999'
        )
      ).rejects.toThrow(ApiHttpError);

      expect(sessionClient.isAuthenticated()).toBe(false);
      expect(sessionClient.getToken()).toBeNull();
      expect(sessionClient.getUser()).toBeNull();
    });
  });

  // ==========================================================================
  // 3. User Profile & Session Queries (GET /me)
  // ==========================================================================
  describe('User Profile (/me) Flow', () => {
    it('未認證時呼叫 fetchCurrentUser 或 getProfile 應直接拋出例外', async () => {
      const fetchSpy = vi.fn();
      globalThis.fetch = fetchSpy;

      await expect(sessionClient.fetchCurrentUser()).rejects.toThrow(
        '未登入或 Session 已清除'
      );
      await expect(sessionClient.getProfile()).rejects.toThrow(
        '未登入或 Session 已清除'
      );
      await expect(fetchCurrentUser()).rejects.toThrow(
        '未登入或 Session 已清除'
      );
      await expect(getProfile()).rejects.toThrow(
        '未登入或 Session 已清除'
      );

      expect(fetchSpy).not.toHaveBeenCalled();
    });

    it('已認證時呼叫 fetchCurrentUser 應正確夾帶 Bearer Token 並更新記憶體資訊', async () => {
      sessionClient.setSession('test-bearer-token', {
        id: 1,
        username: 'old_admin',
        display_name: '舊名稱',
        role: 'system_admin',
        capabilities: [],
      });

      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => MOCK_ME_ENVELOPE,
      });

      const updatedUser = await sessionClient.fetchCurrentUser();

      expect(updatedUser).toEqual(MOCK_ADMIN_PUBLIC);
      expect(sessionClient.getUser()).toEqual(MOCK_ADMIN_PUBLIC);
      expect(sessionClient.getCurrentUser()).toEqual(MOCK_ADMIN_PUBLIC);

      expect(globalThis.fetch).toHaveBeenCalledWith(
        '/api/v1/admin/auth/me',
        expect.objectContaining({
          method: 'GET',
          headers: expect.objectContaining({
            Authorization: 'Bearer test-bearer-token',
          }),
        })
      );
    });
  });

  // ==========================================================================
  // 4. Session Refresh Flow (POST /refresh)
  // ==========================================================================
  describe('Session Refresh (/refresh) Flow', () => {
    it('未認證時呼叫 refreshSession 或 refreshToken 應直接拋出例外', async () => {
      const fetchSpy = vi.fn();
      globalThis.fetch = fetchSpy;

      await expect(sessionClient.refreshSession()).rejects.toThrow(
        '未登入或 Session 已清除'
      );
      await expect(sessionClient.refreshToken()).rejects.toThrow(
        '未登入或 Session 已清除'
      );
      await expect(refreshSession()).rejects.toThrow(
        '未登入或 Session 已清除'
      );
      await expect(refreshToken()).rejects.toThrow(
        '未登入或 Session 已清除'
      );

      expect(fetchSpy).not.toHaveBeenCalled();
    });

    it('已認證時呼叫 refreshSession 應夾帶 Token 並更新 Token 與 User', async () => {
      sessionClient.setSession('initial-token', MOCK_ADMIN_PUBLIC);

      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => MOCK_REFRESH_ENVELOPE,
      });

      const result = await sessionClient.refreshSession();

      expect(result).toEqual(MOCK_REFRESH_RESPONSE);
      expect(sessionClient.getToken()).toBe(MOCK_REFRESH_RESPONSE.access_token);
      expect(sessionClient.getUser()).toEqual(MOCK_ADMIN_PUBLIC);

      expect(globalThis.fetch).toHaveBeenCalledWith(
        '/api/v1/admin/auth/refresh',
        expect.objectContaining({
          method: 'POST',
          headers: expect.objectContaining({
            Authorization: 'Bearer initial-token',
          }),
        })
      );
    });
  });

  // ==========================================================================
  // 5. Session Logout Flow (POST /logout)
  // ==========================================================================
  describe('Session Logout (/logout) Flow', () => {
    it('登出成功應呼叫後端 API 並清除記憶體會話', async () => {
      sessionClient.setSession('token-to-logout', MOCK_ADMIN_PUBLIC);

      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => MOCK_LOGOUT_ENVELOPE,
      });

      await sessionClient.logout();

      expect(sessionClient.isAuthenticated()).toBe(false);
      expect(sessionClient.getToken()).toBeNull();
      expect(sessionClient.getUser()).toBeNull();

      expect(globalThis.fetch).toHaveBeenCalledWith(
        '/api/v1/admin/auth/logout',
        expect.objectContaining({
          method: 'POST',
          headers: expect.objectContaining({
            Authorization: 'Bearer token-to-logout',
          }),
        })
      );
    });

    it('登出時後端拋出網路異常或 500 仍應安全清空前端記憶體', async () => {
      sessionClient.setSession('broken-token', MOCK_ADMIN_PUBLIC);

      globalThis.fetch = vi.fn().mockRejectedValue(new Error('Network offline'));

      await sessionClient.logout();

      expect(sessionClient.isAuthenticated()).toBe(false);
      expect(sessionClient.getToken()).toBeNull();
      expect(sessionClient.getUser()).toBeNull();
    });

    it('獨立匯出之 logout 函式應正常運作', async () => {
      setSession('token-to-logout', MOCK_ADMIN_PUBLIC);

      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => MOCK_LOGOUT_ENVELOPE,
      });

      await logout();

      expect(isAuthenticated()).toBe(false);
      expect(getToken()).toBeNull();
      expect(getUser()).toBeNull();
    });
  });

  // ==========================================================================
  // 6. Memory State & Helpers
  // ==========================================================================
  describe('Memory State & Invariant Management', () => {
    it('setSession 與 clearSession 應能正確操作記憶體狀態', () => {
      expect(sessionClient.isAuthenticated()).toBe(false);

      sessionClient.setSession('custom-token', {
        id: 5,
        username: 'manager_test',
        display_name: '業務主管',
        role: 'finance_reviewer',
        capabilities: ['finance.review'],
      });

      expect(sessionClient.isAuthenticated()).toBe(true);
      expect(sessionClient.getToken()).toBe('custom-token');
      expect(sessionClient.getUser()?.username).toBe('manager_test');
      expect(sessionClient.getUser()?.is_root).toBe(false); // default filled
      expect(sessionClient.getUser()?.access_control_version).toBe(1); // default filled

      sessionClient.clearSession();
      expect(sessionClient.isAuthenticated()).toBe(false);
      expect(sessionClient.getToken()).toBeNull();
      expect(sessionClient.getUser()).toBeNull();
    });

    it('獨立匯出之 getter / setter 函式應同步操作相同記憶體', () => {
      setSession('helper-token', MOCK_ADMIN_PUBLIC);

      expect(isAuthenticated()).toBe(true);
      expect(getToken()).toBe('helper-token');
      expect(getUser()).toEqual(MOCK_ADMIN_PUBLIC);

      clearSession();
      expect(isAuthenticated()).toBe(false);
      expect(getToken()).toBeNull();
      expect(getUser()).toBeNull();
    });

    it('restoreSession 應遵循 BLOCKED_AUTH_RESTORE_DECISION 回傳 null', async () => {
      const result = await sessionClient.restoreSession();
      expect(result).toBeNull();
    });
  });

  // ==========================================================================
  // 7. Strict Zod Schema & Runtime Decoder Defenses
  // ==========================================================================
  describe('Strict Zod Schema Validation & Adversarial Testing', () => {
    it('AdminPasswordChallengeRequestSchema 拒絕超長 username (>100) 或 password (>256)', () => {
      expect(() =>
        AdminPasswordChallengeRequestSchema.parse({
          username: 'a'.repeat(101),
          password: 'pass',
        })
      ).toThrow(ZodError);

      expect(() =>
        AdminPasswordChallengeRequestSchema.parse({
          username: 'admin',
          password: 'p'.repeat(257),
        })
      ).toThrow(ZodError);
    });

    it('AdminPasswordChallengeResponseSchema 拒絕非 ISO 8601 格式之 expires_at 或過短之 challenge_token', () => {
      expect(() =>
        AdminPasswordChallengeResponseSchema.parse({
          challenge_id: 'ch-1',
          challenge_token: 'short_token_less_than_32_chars',
          expires_at: '2026-08-16T07:38:00Z',
        })
      ).toThrow(ZodError);

      expect(() =>
        AdminPasswordChallengeResponseSchema.parse({
          challenge_id: 'ch-1',
          challenge_token: 'valid_token_that_has_over_32_characters_long_123',
          expires_at: '2026/08/16 07:38:00', // Non-ISO
        })
      ).toThrow(ZodError);
    });

    it('AdminFactorVerificationRequestSchema 拒絕長度非 6 或包含字母之 factor_code', () => {
      expect(() =>
        AdminFactorVerificationRequestSchema.parse({
          challenge_token: 'valid_token_that_has_over_32_characters_long_123',
          factor_code: '12345',
        })
      ).toThrow(ZodError);

      expect(() =>
        AdminFactorVerificationRequestSchema.parse({
          challenge_token: 'valid_token_that_has_over_32_characters_long_123',
          factor_code: '12345A',
        })
      ).toThrow(ZodError);
    });

    it('AdminPublicSchema 正確解析合法主體並補全預設值', () => {
      const parsed = AdminPublicSchema.parse({
        id: 1,
        username: 'root_user',
        display_name: '超級管理員',
        role: 'system_admin',
      });

      expect(parsed.capabilities).toEqual([]);
      expect(parsed.is_root).toBe(false);
      expect(parsed.access_control_version).toBe(1);
    });

    it('AdminSessionResponseSchema 拒絕缺少 admin 或 access_token 之回應', () => {
      expect(() =>
        AdminSessionResponseSchema.parse({
          access_token: '',
          token_type: 'bearer',
          expires_at: '2026-08-16T09:33:00Z',
          admin: MOCK_ADMIN_PUBLIC,
        })
      ).toThrow(ZodError);

      expect(() =>
        AdminSessionResponseSchema.parse({
          access_token: 'valid-token',
          token_type: 'bearer',
          expires_at: '2026-08-16T09:33:00Z',
        })
      ).toThrow(ZodError);
    });

    it('AdminRefreshResponseSchema 正確驗證刷新回應與時間格式', () => {
      const parsed = AdminRefreshResponseSchema.parse({
        access_token: 'refreshed-token',
        token_type: 'bearer',
        expires_at: '2026-08-16T12:00:00Z',
        admin: MOCK_ADMIN_PUBLIC,
      });
      expect(parsed.access_token).toBe('refreshed-token');
      expect(parsed.expires_at).toBe('2026-08-16T12:00:00Z');

      expect(() =>
        AdminRefreshResponseSchema.parse({
          expires_at: 'invalid-date-format',
        })
      ).toThrow(ZodError);
    });

    it('後端 Stage 2 回傳資料結構毀損時應由 decodeEnvelope 攔截並拋出 ApiDecodeError', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({
          success: true,
          data: {
            access_token: 'valid-token',
            // Corrupted: missing expires_at & admin
          },
        }),
      });

      await expect(
        sessionClient.verifyPasswordChallenge(
          'ch-1',
          MOCK_STAGE2_REQUEST.challenge_token,
          '123456'
        )
      ).rejects.toThrow(ApiDecodeError);
    });
  });
});
