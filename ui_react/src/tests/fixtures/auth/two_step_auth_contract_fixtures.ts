/**
 * @file two_step_auth_contract_fixtures.ts
 * @description 提供兩步驟認證與會話管理之契約測試資料與錯誤回應 Mock Fixtures。
 */
import type {
  AdminPasswordChallengeRequest,
  AdminPasswordChallengeResponse,
  AdminFactorVerificationRequest,
  AdminPublic,
  AdminSessionResponse,
  AdminRefreshResponse,
} from '../../../api/auth/two_step_auth_schemas';

export const MOCK_STAGE1_REQUEST: AdminPasswordChallengeRequest = {
  username: 'admin_test',
  password: 'ValidPassword123!',
};

export const MOCK_STAGE1_RESPONSE: AdminPasswordChallengeResponse = {
  challenge_id: 'ch-test-uuid-9999-aaaa-bbbb',
  challenge_token: 'tok-stage1-secret-32chars-minimum-length-abc123',
  expires_at: '2026-08-16T07:38:00Z',
};

export const MOCK_STAGE1_ENVELOPE = {
  success: true,
  message: '請輸入驗證器代碼',
  data: MOCK_STAGE1_RESPONSE,
  error: null,
};

export const MOCK_ADMIN_PUBLIC: AdminPublic = {
  id: 10,
  username: 'admin_test',
  display_name: '測試系統管理員',
  role: 'system_admin',
  linked_line_user_id: 'U1234567890abcdef',
  capabilities: ['system.administration', 'orders.read', 'orders.write'],
  is_root: true,
  access_control_version: 2,
};

export const MOCK_STAGE2_REQUEST: AdminFactorVerificationRequest = {
  challenge_token: 'tok-stage1-secret-32chars-minimum-length-abc123',
  factor_code: '123456',
};

export const MOCK_STAGE2_RESPONSE: AdminSessionResponse = {
  access_token: 'bearer-test-access-token-xyz-12345-67890',
  token_type: 'bearer',
  expires_at: '2026-08-16T09:33:00Z',
  admin: MOCK_ADMIN_PUBLIC,
};

export const MOCK_STAGE2_ENVELOPE = {
  success: true,
  message: '登入成功',
  data: MOCK_STAGE2_RESPONSE,
  error: null,
};

export const MOCK_ME_ENVELOPE = {
  success: true,
  message: 'Success',
  data: MOCK_ADMIN_PUBLIC,
  error: null,
};

export const MOCK_REFRESH_RESPONSE: AdminRefreshResponse = {
  access_token: 'bearer-refreshed-token-9999-aaaa-bbbb',
  token_type: 'bearer',
  expires_at: '2026-08-16T11:33:00Z',
  admin: MOCK_ADMIN_PUBLIC,
};

export const MOCK_REFRESH_ENVELOPE = {
  success: true,
  message: 'Success',
  data: MOCK_REFRESH_RESPONSE,
  error: null,
};

export const MOCK_LOGOUT_ENVELOPE = {
  success: true,
  message: '已成功登出',
  data: { logged_out: true },
  error: null,
};

export const MOCK_401_INVALID_CREDENTIALS_PAYLOAD = {
  detail: {
    code: 'invalid_credentials_or_factor',
    message: '帳號、密碼或驗證碼錯誤',
    retryable: false,
  },
};

export const MOCK_403_MFA_ENROLLMENT_PAYLOAD = {
  detail: {
    code: 'mfa_enrollment_required',
    message: '請完成 MFA 綁定後再登入',
    retryable: false,
    challenge: {
      id: 'mfa-enroll-challenge-id',
      token: 'mfa-enroll-challenge-token-32chars',
      provisioning_uri:
        'otpauth://totp/LaborUnion:admin_test?secret=JBSWY3DPEHPK3PXP',
      expires_at: '2026-08-16T07:38:00Z',
    },
  },
};

export const MOCK_429_RATE_LIMITED_PAYLOAD = {
  detail: {
    code: 'login_rate_limited',
    message: '登入嘗試過於頻繁，請稍後再試',
    retryable: true,
  },
};

export const MOCK_503_AUTH_UNAVAILABLE_PAYLOAD = {
  detail: {
    code: 'admin_auth_unavailable',
    message: '管理員登入儲存服務暫時無法使用',
    retryable: true,
  },
};
