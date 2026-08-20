/**
 * @file session_client.ts
 * @description 記憶體管理員會話客戶端，提供兩步驟認證挑戰、驗證、權限查詢與會話狀態管理。
 */
import { z } from 'zod';
import { decodeEnvelope } from '../shared/runtime_decoder';
import { transport, type RequestOptions } from '../shared/transport';
import {
  AdminPasswordChallengeRequestSchema,
  AdminPasswordChallengeResponseSchema,
  type AdminPasswordChallengeResponse,
  AdminFactorVerificationRequestSchema,
  AdminPublicSchema,
  type AdminPublic,
  type AdminPublicInput,
  AdminSessionResponseSchema,
  type AdminSessionResponse,
  AdminRefreshResponseSchema,
  type AdminRefreshResponse,
} from './two_step_auth_schemas';

export * from './two_step_auth_schemas';

// Legacy single-step schema retained for backward compatibility
export const AdminLoginRequestSchema = z.object({
  username: z.string().min(1, '請輸入帳號').max(100),
  password: z.string().min(1, '請輸入密碼').max(256),
});
export type AdminLoginRequest = z.infer<typeof AdminLoginRequestSchema>;

// Session storage keys for local browser persistence across page refreshes
const STORAGE_KEY_TOKEN = 'union_admin_session_token';
const STORAGE_KEY_USER = 'union_admin_session_user';

function getInitialToken(): string | null {
  try {
    if (typeof window !== 'undefined' && window.sessionStorage) {
      return window.sessionStorage.getItem(STORAGE_KEY_TOKEN);
    }
  } catch {
    // ignore in environments without sessionStorage
  }
  return null;
}

function getInitialUser(): AdminPublic | null {
  try {
    if (typeof window !== 'undefined' && window.sessionStorage) {
      const raw = window.sessionStorage.getItem(STORAGE_KEY_USER);
      if (raw) {
        return AdminPublicSchema.parse(JSON.parse(raw));
      }
    }
  } catch {
    // ignore parse errors or missing storage
  }
  return null;
}

let inMemoryToken: string | null = getInitialToken();
let inMemoryUser: AdminPublic | null = getInitialUser();

export const sessionClient = {
  /**
   * 取得當前記憶體中的存取權杖 (Bearer Token)
   */
  getToken(): string | null {
    return inMemoryToken;
  },

  /**
   * 取得當前記憶體中的登入管理員主體資訊
   */
  getUser(): AdminPublic | null {
    return inMemoryUser;
  },

  /**
   * 取得當前記憶體中的登入管理員主體資訊（相容舊版介面）
   */
  getCurrentUser(): AdminPublic | null {
    return inMemoryUser;
  },

  /**
   * 檢查當前是否處於已認證狀態
   */
  isAuthenticated(): boolean {
    return inMemoryToken !== null;
  },

  /**
   * 設定記憶體會話狀態（寫入 Bearer Token 與管理員主體，並同步至 sessionStorage）
   */
  setSession(
    token: string | null,
    user: AdminPublic | AdminPublicInput | null
  ): void {
    inMemoryToken = token;
    if (user) {
      inMemoryUser = AdminPublicSchema.parse(user);
    } else {
      inMemoryUser = null;
    }

    try {
      if (typeof window !== 'undefined' && window.sessionStorage) {
        if (token) {
          window.sessionStorage.setItem(STORAGE_KEY_TOKEN, token);
        } else {
          window.sessionStorage.removeItem(STORAGE_KEY_TOKEN);
        }
        if (inMemoryUser) {
          window.sessionStorage.setItem(STORAGE_KEY_USER, JSON.stringify(inMemoryUser));
        } else {
          window.sessionStorage.removeItem(STORAGE_KEY_USER);
        }
      }
    } catch {
      // ignore in environments without storage
    }
  },

  /**
   * 清除記憶體與 sessionStorage 會話狀態
   */
  clearSession(): void {
    inMemoryToken = null;
    inMemoryUser = null;
    try {
      if (typeof window !== 'undefined' && window.sessionStorage) {
        window.sessionStorage.removeItem(STORAGE_KEY_TOKEN);
        window.sessionStorage.removeItem(STORAGE_KEY_USER);
      }
    } catch {
      // ignore
    }
  },

  /**
   * 第一階段：發起帳號密碼挑戰 (Stage 1 Password Challenge)
   * POST /api/v1/admin/auth/login/challenges
   */
  async issuePasswordChallenge(
    username: string,
    password: string,
    options?: Omit<RequestOptions, 'method' | 'body'>
  ): Promise<AdminPasswordChallengeResponse> {
    const validated = AdminPasswordChallengeRequestSchema.parse({
      username,
      password,
    });
    const raw = await transport.post(
      '/api/v1/admin/auth/login/challenges',
      validated,
      options
    );
    return decodeEnvelope(AdminPasswordChallengeResponseSchema, raw);
  },

  /**
   * 第二階段：驗證 TOTP 動態碼並建立會話 (Stage 2 Factor Verification)
   * POST /api/v1/admin/auth/login/challenges/{challenge_id}/verify
   */
  async verifyPasswordChallenge(
    challengeId: string,
    challengeToken: string,
    factorCode: string,
    options?: Omit<RequestOptions, 'method' | 'body'>
  ): Promise<AdminSessionResponse> {
    if (!challengeId || typeof challengeId !== 'string') {
      throw new Error('缺少 challenge_id 參數');
    }
    const validated = AdminFactorVerificationRequestSchema.parse({
      challenge_token: challengeToken,
      factor_code: factorCode,
    });
    const urlPath = `/api/v1/admin/auth/login/challenges/${encodeURIComponent(
      challengeId
    )}/verify`;
    const raw = await transport.post(urlPath, validated, options);
    const sessionData = decodeEnvelope(AdminSessionResponseSchema, raw);

    this.setSession(sessionData.access_token, sessionData.admin);

    return sessionData;
  },

  /**
   * 查詢當前登入者個人檔案資訊
   * GET /api/v1/admin/auth/me
   */
  async fetchCurrentUser(
    options?: Omit<RequestOptions, 'method' | 'body'>
  ): Promise<AdminPublic> {
    if (!inMemoryToken) {
      throw new Error('未登入或 Session 已清除');
    }
    const raw = await transport.get('/api/v1/admin/auth/me', {
      ...options,
      token: inMemoryToken,
    });
    const user = decodeEnvelope(AdminPublicSchema, raw);
    this.setSession(inMemoryToken, user);
    return user;
  },

  /**
   * 查詢當前登入者個人檔案（別名）
   */
  async getProfile(
    options?: Omit<RequestOptions, 'method' | 'body'>
  ): Promise<AdminPublic> {
    return this.fetchCurrentUser(options);
  },

  /**
   * 展延或刷新存取權杖
   * POST /api/v1/admin/auth/refresh
   */
  async refreshSession(
    options?: Omit<RequestOptions, 'method' | 'body'>
  ): Promise<AdminRefreshResponse> {
    if (!inMemoryToken) {
      throw new Error('未登入或 Session 已清除');
    }
    const raw = await transport.post('/api/v1/admin/auth/refresh', undefined, {
      ...options,
      token: inMemoryToken,
    });
    const refreshData = decodeEnvelope(AdminRefreshResponseSchema, raw);
    this.setSession(
      refreshData.access_token || inMemoryToken,
      refreshData.admin || inMemoryUser
    );
    return refreshData;
  },

  /**
   * 展延或刷新存取權杖（相容舊版別名）
   */
  async refreshToken(
    options?: Omit<RequestOptions, 'method' | 'body'>
  ): Promise<AdminRefreshResponse> {
    return this.refreshSession(options);
  },

  /**
   * 登出並使後端會話失效，清除前端記憶體狀態
   * POST /api/v1/admin/auth/logout
   */
  async logout(
    options?: Omit<RequestOptions, 'method' | 'body'>
  ): Promise<void> {
    try {
      if (inMemoryToken) {
        await transport.post('/api/v1/admin/auth/logout', undefined, {
          ...options,
          token: inMemoryToken,
        });
      }
    } catch {
      // 忽略登出時的網路連線失敗，確保前端記憶體會話一定能完整清除
    } finally {
      this.clearSession();
    }
  },

  /**
   * 單一步驟登入（相容性維護，生產環境強制採用兩步驟認證）
   * @deprecated 請改用 issuePasswordChallenge 與 verifyPasswordChallenge
   */
  async login(
    credentials: AdminLoginRequest,
    options?: Omit<RequestOptions, 'method' | 'body'>
  ): Promise<AdminSessionResponse> {
    const validated = AdminLoginRequestSchema.parse(credentials);
    const raw = await transport.post(
      '/api/v1/admin/auth/login',
      validated,
      options
    );
    const sessionData = decodeEnvelope(AdminSessionResponseSchema, raw);

    inMemoryToken = sessionData.access_token;
    inMemoryUser = sessionData.admin;

    return sessionData;
  },

  /**
   * BLOCKED_AUTH_RESTORE_DECISION:
   * 基礎架構階段不進行非安全的 localStorage 持久化還原，
   * 需待後端 HttpOnly Cookie 與 CSRF 方案於 Access Work Package 完善。
   */
  async restoreSession(): Promise<AdminPublic | null> {
    return null;
  },
};

export const issuePasswordChallenge = sessionClient.issuePasswordChallenge.bind(sessionClient);
export const verifyPasswordChallenge = sessionClient.verifyPasswordChallenge.bind(sessionClient);
export const fetchCurrentUser = sessionClient.fetchCurrentUser.bind(sessionClient);
export const getProfile = sessionClient.getProfile.bind(sessionClient);
export const refreshSession = sessionClient.refreshSession.bind(sessionClient);
export const refreshToken = sessionClient.refreshToken.bind(sessionClient);
export const logout = sessionClient.logout.bind(sessionClient);
export const setSession = sessionClient.setSession.bind(sessionClient);
export const clearSession = sessionClient.clearSession.bind(sessionClient);
export const getToken = sessionClient.getToken.bind(sessionClient);
export const getUser = sessionClient.getUser.bind(sessionClient);
export const isAuthenticated = sessionClient.isAuthenticated.bind(sessionClient);

export default sessionClient;
