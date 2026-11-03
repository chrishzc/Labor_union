/** MySQL root designation gates the management application before session handling. */
import { useEffect, useState, type FormEvent, type ReactNode } from 'react';
import { setupClient } from '../api/auth/setup_client';
import { sessionClient } from '../api/auth/session_client';
import type { AdminPasswordChallengeResponse } from '../api/auth/two_step_auth_schemas';
import { LoginPage } from './LoginPage';
import { ApiHttpError } from '../api/shared/typed_errors';
import './LoginPage.css';
import './FirstRootSetup.css';

export function FirstRootSetupGate({ children }: { children: ReactNode }) {
  const [required, setRequired] = useState<boolean | null>(null);
  const [checking, setChecking] = useState(true);
  const [retry, setRetry] = useState(0);
  const [error, setError] = useState('');
  const [username, setUsername] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [password, setPassword] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const [saving, setSaving] = useState(false);
  const [enrollment, setEnrollment] = useState<AdminPasswordChallengeResponse | null>(null);

  useEffect(() => {
    let active = true;
    setupClient.status().then(status => {
      if (active) {
        setRequired(status.required);
      }
    }).catch(() => {
      if (active) setError('無法讀取帳號設定狀態，請確認資料庫連線與初始化已完成後重試。');
    }).finally(() => { if (active) setChecking(false); });
    return () => { active = false; };
  }, [retry]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError('');
    if (!username.trim() || !displayName.trim()) {
      setError('請填寫帳號與顯示名稱。');
      return;
    }
    if (password.length < 10 || password.length > 256) {
      setError('密碼長度須為 10–256 個字元。');
      return;
    }
    if (password !== confirmation) {
      setError('兩次輸入的密碼不一致。');
      return;
    }
    setSaving(true);
    try {
      const result = await setupClient.create({ username: username.trim(), display_name: displayName.trim(), password });
      sessionClient.clearSession();
      setEnrollment(result.enrollment);
    } catch (failure) {
      if (failure instanceof ApiHttpError && [409, 410].includes(failure.status)) {
        try {
          const status = await setupClient.status();
          if (!status.required) {
            sessionClient.clearSession();
            setRequired(false);
            return;
          }
        } catch { /* Keep setup closed to the application until status is known. */ }
      }
      setError(failure instanceof ApiHttpError
        ? failure.message : '無法完成帳號設定，請確認連線後重試。');
    } finally {
      setPassword('');
      setConfirmation('');
      setSaving(false);
    }
  }

  if (enrollment) return <LoginPage initialEnrollment={{ username: username.trim(), challenge: enrollment }}
    onEnrollmentFinished={() => {
      sessionClient.clearSession(); setEnrollment(null); setRequired(false);
    }} />;
  if (required === false) return children;

  return <main className="login-viewport first-root-setup">
    <div className="login-card-container">
      <h1 className="login-main-title">首次設定最高管理員</h1>
      {checking ? <p role="status">正在確認帳號設定狀態…</p>
        : <>
          {error && <p role="alert" className="first-root-error">{error}</p>}
          {required === null ? <button className="login-submit-btn" onClick={() => {
            setChecking(true); setError(''); setRetry(value => value + 1);
          }}>重新確認</button> : <>
            <p className="login-desc-subtitle">請設定帳號與密碼，接著立即綁定 TOTP 驗證器。完成綁定並保存復原碼後，再重新登入。</p>
            <form onSubmit={submit}>
              <fieldset disabled={saving}>
                <div className="login-input-group">
                  <label className="login-field-label" htmlFor="setup-username">帳號</label>
                  <input className="login-text-input" id="setup-username" autoComplete="username" required maxLength={100}
                    value={username} onChange={event => setUsername(event.target.value)} />
                </div>
                <div className="login-input-group">
                  <label className="login-field-label" htmlFor="setup-display-name">顯示名稱</label>
                  <input className="login-text-input" id="setup-display-name" autoComplete="name" required maxLength={100}
                    value={displayName} onChange={event => setDisplayName(event.target.value)} />
                </div>
                <div className="login-input-group">
                  <label className="login-field-label" htmlFor="setup-password">密碼（至少 10 個字元）</label>
                  <input className="login-text-input" id="setup-password" type="password" autoComplete="new-password"
                    required minLength={10} maxLength={256} value={password} onChange={event => setPassword(event.target.value)} />
                </div>
                <div className="login-input-group">
                  <label className="login-field-label" htmlFor="setup-confirmation">再次輸入密碼</label>
                  <input className="login-text-input" id="setup-confirmation" type="password" autoComplete="new-password"
                    required minLength={10} maxLength={256} value={confirmation} onChange={event => setConfirmation(event.target.value)} />
                </div>
                <button className="login-submit-btn" type="submit">{saving ? '建立中…' : '建立最高管理員'}</button>
              </fieldset>
            </form>
          </>}
        </>}
    </div>
  </main>;
}
