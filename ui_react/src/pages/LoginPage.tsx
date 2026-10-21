/**
 * @file LoginPage.tsx
 * @description 登入頁面元件，實作雙階段帳密挑戰與 TOTP 動態碼驗證流程、錯誤處理與機密安全防護。
 */
import React, { useState } from 'react';
import { QRCodeSVG } from 'qrcode.react';
import './LoginPage.css';
import { sessionClient } from '../api/auth/session_client';
import {
  ApiHttpError,
  ApiNetworkError,
  ApiTimeoutError,
  ApiDecodeError,
  extractErrorMessage,
} from '../api/shared/typed_errors';

export interface LoginPageProps {
  onLoginSuccess?: (username: string) => void;
}

function getStage1ErrorMessage(err: unknown): string {
  if (err instanceof ApiHttpError) {
    if (err.status === 403 || err.code === 'mfa_enrollment_required') {
      return '此帳號需先完成 MFA 綁定；React 綁定流程尚未啟用。';
    }
    if (err.status === 401 || err.code === 'invalid_credentials_or_factor') {
      return '帳號或密碼錯誤';
    }
    if (err.status === 429 || err.code === 'login_rate_limited') {
      return '登入嘗試過於頻繁，請稍後再試';
    }
    if (
      err.status === 503 ||
      err.code === 'admin_auth_unavailable' ||
      err.code === 'admin_session_storage_unavailable'
    ) {
      return '系統驗證服務暫時無法使用，請稍後再試';
    }
    if (err.status === 422 || err.code === 'VALIDATION_ERROR') {
      return '輸入格式不符規定';
    }
    return err.message || '帳號或密碼錯誤';
  }
  if (err instanceof ApiNetworkError) {
    return '網路連線異常，請檢查網路後重試';
  }
  if (err instanceof ApiTimeoutError) {
    return '請求逾時，請稍後再試';
  }
  if (err instanceof ApiDecodeError) {
    return '伺服器回應結構異常';
  }
  const msg = extractErrorMessage(err);
  if (msg.includes('mfa_enrollment_required') || msg.includes('MFA')) {
    return '此帳號需先完成 MFA 綁定；React 綁定流程尚未啟用。';
  }
  if (
    msg.includes('401') ||
    msg.includes('帳號或密碼錯誤') ||
    msg.includes('admin_credentials_invalid') ||
    msg.includes('invalid_credentials_or_factor')
  ) {
    return '帳號或密碼錯誤';
  }
  if (msg.includes('429') || msg.includes('login_rate_limited')) {
    return '登入嘗試過於頻繁，請稍後再試';
  }
  if (msg.includes('503') || msg.includes('admin_auth_unavailable')) {
    return '系統驗證服務暫時無法使用，請稍後再試';
  }
  return msg;
}

function getStage2ErrorMessage(
  err: unknown,
  isClientExpired: boolean
): { message: string; expired: boolean } {
  if (isClientExpired) {
    return { message: '驗證階段已過期，請重新輸入帳號密碼', expired: true };
  }
  if (err instanceof ApiHttpError) {
    if (
      err.code === 'challenge_expired' ||
      err.message.includes('過期') ||
      err.message.includes('expired') ||
      err.message.includes('逾期')
    ) {
      return { message: '驗證階段已過期，請重新輸入帳號密碼', expired: true };
    }
    if (err.status === 429 || err.code === 'login_rate_limited') {
      return { message: '驗證嘗試過於頻繁，請稍後再試', expired: false };
    }
    if (err.status === 503 || err.code === 'admin_auth_unavailable') {
      return { message: '驗證服務暫時無法使用', expired: false };
    }
    if (err.status === 401 || err.code === 'invalid_credentials_or_factor') {
      return { message: '驗證碼錯誤或無效', expired: false };
    }
    return { message: err.message || '驗證碼錯誤或無效', expired: false };
  }
  if (err instanceof ApiNetworkError) {
    return { message: '網路連線異常，請檢查網路後重試', expired: false };
  }
  if (err instanceof ApiTimeoutError) {
    return { message: '請求逾時，請稍後再試', expired: false };
  }
  if (err instanceof ApiDecodeError) {
    return { message: '伺服器回應結構異常', expired: false };
  }
  const msg = extractErrorMessage(err);
  if (
    msg.includes('過期') ||
    msg.includes('expired') ||
    msg.includes('逾期') ||
    msg.includes('challenge_expired')
  ) {
    return { message: '驗證階段已過期，請重新輸入帳號密碼', expired: true };
  }
  if (msg.includes('429') || msg.includes('login_rate_limited')) {
    return { message: '驗證嘗試過於頻繁，請稍後再試', expired: false };
  }
  if (msg.includes('503') || msg.includes('admin_auth_unavailable')) {
    return { message: '驗證服務暫時無法使用', expired: false };
  }
  if (
    msg.includes('401') ||
    msg.includes('invalid_credentials_or_factor') ||
    msg.includes('驗證碼錯誤')
  ) {
    return { message: '驗證碼錯誤或無效', expired: false };
  }
  return { message: msg, expired: false };
}

const REMEMBER_COOKIE_NAME = 'remember_admin_username';
const normalizeTotpInput = (value: string) => value
  .replace(/[０-９]/g, digit => String.fromCharCode(digit.charCodeAt(0) - 0xfee0))
  .replace(/\s/g, '');

function getRememberedUsername(): string | null {
  try {
    if (typeof document === 'undefined') return null;
    const match = document.cookie.match(
      new RegExp('(?:^|; )' + REMEMBER_COOKIE_NAME.replace(/([.$?*|{}()[\]\\/+^])/g, '\\$1') + '=([^;]*)')
    );
    return match ? decodeURIComponent(match[1]) : null;
  } catch {
    return null;
  }
}

function setRememberedUsername(username: string): void {
  try {
    if (typeof document === 'undefined') return;
    const expires = new Date(Date.now() + 30 * 864e5).toUTCString();
    document.cookie = `${encodeURIComponent(REMEMBER_COOKIE_NAME)}=${encodeURIComponent(username)}; expires=${expires}; path=/; SameSite=Lax`;
  } catch {
    // Ignore in non-browser environments
  }
}

function clearRememberedUsername(): void {
  try {
    if (typeof document === 'undefined') return;
    document.cookie = `${encodeURIComponent(REMEMBER_COOKIE_NAME)}=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/; SameSite=Lax`;
  } catch {
    // Ignore in non-browser environments
  }
}

export const LoginPage: React.FC<LoginPageProps> = ({ onLoginSuccess }) => {
  // Stage 1: Account Login, Stage 2: TOTP 2FA Verification
  const [authStage, setAuthStage] = useState<'stage1' | 'stage2'>('stage1');

  const [rememberMe, setRememberMe] = useState<boolean>(() => {
    const saved = getRememberedUsername();
    return saved !== null && saved.length > 0;
  });
  const [username, setUsername] = useState<string>(() => {
    const saved = getRememberedUsername();
    return saved && saved.length > 0 ? saved : 'admin';
  });
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  // Stage 2 state
  const [challengeId, setChallengeId] = useState<string | null>(null);
  const [challengeToken, setChallengeToken] = useState<string | null>(null);
  const [challengeExpiresAt, setChallengeExpiresAt] = useState<string | null>(null);
  const [totpCode, setTotpCode] = useState('');
  const [provisioningUri, setProvisioningUri] = useState<string | null>(null);
  const [recoveryCodes, setRecoveryCodes] = useState<string[]>([]);

  const handleStage1Submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage(null);

    const trimmedUser = username.trim();
    const trimmedPass = password.trim();

    if (!trimmedUser) {
      setErrorMessage('請輸入帳號');
      return;
    }
    if (!trimmedPass) {
      setErrorMessage('請輸入密碼');
      return;
    }

    // Persist or clear remembered username in cookie
    if (rememberMe) {
      setRememberedUsername(trimmedUser);
    } else {
      clearRememberedUsername();
    }

    setIsLoading(true);
    try {
      const challenge = await sessionClient.issuePasswordChallenge(trimmedUser, password);
      setChallengeId(challenge.challenge_id);
      setChallengeToken(challenge.challenge_token);
      setChallengeExpiresAt(challenge.expires_at);
      setProvisioningUri(challenge.challenge_type === 'mfa_enrollment' ? challenge.provisioning_uri! : null);
      setRecoveryCodes([]);
      // Immediately wipe password from state
      setPassword('');
      setAuthStage('stage2');
      setErrorMessage(null);
    } catch (err) {
      // Clear password on error as well, preserving username
      setPassword('');
      setErrorMessage(getStage1ErrorMessage(err));
    } finally {
      setIsLoading(false);
    }
  };

  const handleTotpChange = (value: string) => {
    const normalized = normalizeTotpInput(value);
    if (/^\d*$/.test(normalized)) setTotpCode(normalized.slice(0, 6));
  };

  const handleStage2Submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage(null);

    const fullCode = normalizeTotpInput(totpCode);
    if (!/^\d{6}$/.test(fullCode)) {
      setErrorMessage('請完整輸入 6 位數 TOTP 動態安全碼');
      return;
    }

    // Check if challenge expired before sending
    const isExpired = challengeExpiresAt
      ? new Date(challengeExpiresAt).getTime() <= Date.now()
      : false;

    if (!challengeId || !challengeToken || isExpired) {
      setTotpCode('');
      setChallengeId(null);
      setChallengeToken(null);
      setChallengeExpiresAt(null);
      setAuthStage('stage1');
      setErrorMessage('驗證階段已過期，請重新輸入帳號密碼');
      return;
    }

    setIsLoading(true);
    try {
      if (provisioningUri) {
        const result = await sessionClient.verifyEnrollment(challengeId, challengeToken, fullCode);
        setRecoveryCodes(result.recovery_codes);
        setProvisioningUri(null);
        setChallengeId(null);
        setChallengeToken(null);
        setChallengeExpiresAt(null);
        setTotpCode('');
        return;
      }
      await sessionClient.verifyPasswordChallenge(
        challengeId,
        challengeToken,
        fullCode
      );

      // On success: wipe challenge secrets and TOTP digits
      setChallengeId(null);
      setChallengeToken(null);
      setChallengeExpiresAt(null);
      setTotpCode('');

      if (onLoginSuccess) {
        onLoginSuccess(username.trim());
      }
    } catch (err) {
      // On error: wipe TOTP digits
      setTotpCode('');
      const { message, expired } = getStage2ErrorMessage(err, false);

      if (expired) {
        setChallengeId(null);
        setChallengeToken(null);
        setChallengeExpiresAt(null);
        setAuthStage('stage1');
      }
      setErrorMessage(message);
    } finally {
      setIsLoading(false);
    }
  };

  const handleBackToStage1 = () => {
    setProvisioningUri(null);
    setRecoveryCodes([]);
    setErrorMessage(null);
    setChallengeId(null);
    setChallengeToken(null);
    setChallengeExpiresAt(null);
    setTotpCode('');
    setAuthStage('stage1');
  };

  return (
    <div className="login-viewport">
      <div className="login-top-brand">🤱 月子工會管理系統</div>

      <div className="login-card-container">
        {/* Stage 1: Username & Password */}
        {authStage === 'stage1' && (
          <>
            <div className="login-brand-badge">🤱</div>
            <h1 className="login-main-title">月子工會管理系統</h1>
            <p className="login-desc-subtitle">請輸入您的帳號密碼以登入後台</p>

            {errorMessage && (
              <div
                style={{
                  padding: '10px 14px',
                  borderRadius: '10px',
                  backgroundColor: '#ffe4e6',
                  color: '#9f1239',
                  fontSize: '0.85rem',
                  marginBottom: '16px',
                  fontWeight: 600,
                }}
              >
                ⚠️ {errorMessage}
              </div>
            )}

            <form onSubmit={handleStage1Submit}>
              <div className="login-input-group">
                <label className="login-field-label" htmlFor="login-username">
                  帳號 (Username)
                </label>
                <div className="login-input-wrapper">
                  <input
                    id="login-username"
                    className="login-text-input"
                    type="text"
                    placeholder="請輸入帳號"
                    value={username}
                    disabled={isLoading}
                    onChange={(e) => setUsername(e.target.value)}
                  />
                </div>
              </div>

              <div className="login-input-group">
                <label className="login-field-label" htmlFor="login-password">
                  密碼 (Password)
                </label>
                <div className="login-input-wrapper">
                  <input
                    id="login-password"
                    className="login-text-input"
                    type={showPassword ? 'text' : 'password'}
                    placeholder="請輸入密碼"
                    value={password}
                    disabled={isLoading}
                    onChange={(e) => setPassword(e.target.value)}
                  />
                  <button
                    type="button"
                    className="password-toggle-btn"
                    onClick={() => setShowPassword(!showPassword)}
                    title={showPassword ? '隱藏密碼' : '顯示密碼'}
                    disabled={isLoading}
                  >
                    {showPassword ? '👁️' : '🔒'}
                  </button>
                </div>
              </div>

              <div className="login-options-row">
                <label className="login-remember-me">
                  <input
                    type="checkbox"
                    checked={rememberMe}
                    disabled={isLoading}
                    onChange={(e) => setRememberMe(e.target.checked)}
                  />
                  <span>記住帳號 (Remember Me)</span>
                </label>
              </div>

              <button className="login-submit-btn" type="submit" disabled={isLoading}>
                {isLoading ? '處理中...' : '下一步：進行雙重驗證 ➔ (Next: 2FA)'}
              </button>
            </form>
          </>
        )}

        {/* Stage 2: TOTP 2FA Verification */}
        {authStage === 'stage2' && recoveryCodes.length > 0 && (
          <section aria-label="保存復原碼">
            <h1 className="login-main-title">驗證器綁定完成</h1>
            <p>請將以下一次性復原碼保存到安全位置，離開後不再顯示。不要分享給他人。</p>
            <ul>{recoveryCodes.map(code => <li key={code}><code>{code}</code></li>)}</ul>
            <button className="login-submit-btn" onClick={handleBackToStage1}>已保存復原碼，返回登入</button>
          </section>
        )}
        {authStage === 'stage2' && recoveryCodes.length === 0 && (
          <>
            <div
              className="login-brand-badge"
              style={{
                background: 'linear-gradient(135deg, #fed9b8 0%, #ffdbcf 100%)',
              }}
            >
              🛡️
            </div>
            <h1 className="login-main-title">{provisioningUri ? '綁定您的驗證器' : '雙重身分驗證 (2FA)'}</h1>
            {provisioningUri && <section aria-label="驗證器設定">
              <p>在手機驗證器選擇「新增帳戶／掃描 QR Code」，掃描下方圖片。</p>
              <div className="login-enrollment-qr">
                <QRCodeSVG value={provisioningUri} size={220} level="M" marginSize={4} title="驗證器綁定 QR Code" role="img" aria-label="驗證器綁定 QR Code" />
              </div>
              <p>帳戶名稱：{username}</p>
              <details>
              <summary>無法掃描？手動輸入設定金鑰</summary>
              <p>在驗證器選擇手動新增，類型選擇「以時間為基準」。</p>
              <label htmlFor="totp-setup-key">設定金鑰（請勿分享）</label>
              <input id="totp-setup-key" className="login-text-input" readOnly value={new URL(provisioningUri).searchParams.get('secret') || ''} />
              </details>
            </section>}
            <p className="login-desc-subtitle">請開啟 Authenticator 隨身驗證器，輸入 6 位動態碼</p>

            {errorMessage && (
              <div
                style={{
                  padding: '10px 14px',
                  borderRadius: '10px',
                  backgroundColor: '#ffe4e6',
                  color: '#9f1239',
                  fontSize: '0.85rem',
                  marginBottom: '16px',
                  fontWeight: 600,
                }}
              >
                ⚠️ {errorMessage}
              </div>
            )}

            <form onSubmit={handleStage2Submit}>
              <div className="totp-code-field">
                <label htmlFor="totp-code">六位數驗證碼</label>
                <input
                  id="totp-code"
                  className="login-text-input totp-code-input"
                  type="text"
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  maxLength={6}
                  value={totpCode}
                  disabled={isLoading}
                  onChange={event => {
                    if ((event.nativeEvent as InputEvent).isComposing) setTotpCode(event.target.value);
                    else handleTotpChange(event.target.value);
                  }}
                  onCompositionEnd={event => {
                    const normalized = normalizeTotpInput(event.currentTarget.value);
                    setTotpCode(/^\d*$/.test(normalized) ? normalized.slice(0, 6) : '');
                  }}
                  onPaste={event => {
                    const normalized = normalizeTotpInput(event.clipboardData.getData('text'));
                    if (/^\d+$/.test(normalized)) {
                      event.preventDefault();
                      setTotpCode(normalized.slice(0, 6));
                    }
                  }}
                />
              </div>

              <button className="login-submit-btn" type="submit" disabled={isLoading}>
                {isLoading ? '驗證中...' : provisioningUri ? '確認綁定驗證器' : '驗證並登入系統 (Verify & Login)'}
              </button>

              <button
                type="button"
                className="back-to-stage1-btn"
                disabled={isLoading}
                onClick={handleBackToStage1}
              >
                ← 返回重新輸入帳密
              </button>
            </form>
          </>
        )}
      </div>

      <div className="login-footer-copyright">
        月子工會 © 2026 Postpartum Care Labor Union. All rights reserved.
      </div>
    </div>
  );
};

export default LoginPage;
