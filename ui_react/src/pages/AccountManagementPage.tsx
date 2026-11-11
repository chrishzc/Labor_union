import { ManagementPageHeader } from '../components/ManagementPageHeader';
import { useUnsavedDraft } from '../components/UnsavedChanges';
import { useSaveValidation } from '../components/useSaveValidation';
/**
 * File: AccountManagementPage.tsx
 * Description: 帳號清冊、安全操作與驗證器動態碼說明。
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import './AccountManagementPage.css';
import { Drawer } from '../components/Drawer';
import { accountDirectoryClient } from '../api/access/account_directory_client';
import { accountCenterClient } from '../api/access/account_center_client';
import type { AccountMutationReceipt } from '../api/access/account_center_schemas';
import {
  adaptAccountDirectory,
  type AccountDirectoryRow,
} from '../adapters/access/account_query_adapter';
type Tab = 'users' | 'totp';
type AccountAction = 'enabled' | 'password' | 'mfa' | 'sessions';
type LoadStatus = 'idle' | 'loading' | 'ready' | 'empty' | 'error';

interface QueryState<T> {
  status: LoadStatus;
  data: T | null;
  error: string | null;
}

const initialUsersState: QueryState<AccountDirectoryRow[]> = { status: 'idle', data: null, error: null };
const initialCommandState: QueryState<AccountMutationReceipt> = { status: 'idle', data: null, error: null };

function errorMessage(error: unknown, fallback: string): string {
  const code = String((error as { code?: unknown })?.code ?? (error instanceof Error ? error.message : '')).toUpperCase();
  if (code.includes('UNAUTHENTICATED')) return '請先完成管理員登入後再操作。';
  if (code.includes('FORBIDDEN')) return '僅限最高權限管理員使用。請以具此權限的帳號登入。';
  if (code.includes('STALE') || code.includes('CONFLICT')) return '資料已更新，請重新整理後再操作。';
  if (code.includes('UNAVAILABLE') || code.includes('NETWORK') || code.includes('TIMEOUT')) return '服務暫時無法使用，請稍後再試。';
  return fallback;
}

function isAbortError(error: unknown): boolean {
  return typeof error === 'object' && error !== null && 'code' in error
    && String(error.code).endsWith('_ABORTED');
}

function QueryError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="account-query-state account-query-error" role="alert">
      <span>{message}</span>
      <button type="button" className="account-secondary-btn" onClick={onRetry}>重新整理</button>
    </div>
  );
}

export const AccountManagementPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState<Tab>('users');
  const [usersState, setUsersState] = useState(initialUsersState);
  const [commandState, setCommandState] = useState(initialCommandState);
  const [commandTarget, setCommandTarget] = useState<'create' | { user: AccountDirectoryRow; action: AccountAction } | null>(null);
  const [commandReason, setCommandReason] = useState('');
  const saveValidation = useSaveValidation();
  const usernameRef = useRef<HTMLInputElement>(null);
  const displayNameRef = useRef<HTMLInputElement>(null);
  const createPasswordRef = useRef<HTMLInputElement>(null);
  const commandPasswordRef = useRef<HTMLInputElement>(null);
  const commandReasonRef = useRef<HTMLInputElement>(null);
  const [commandPassword, setCommandPassword] = useState('');
  const [createUsername, setCreateUsername] = useState('');
  const [createDisplayName, setCreateDisplayName] = useState('');
  const [createPassword, setCreatePassword] = useState('');

  const usersGeneration = useRef(0);
  const usersController = useRef<AbortController | null>(null);
  const commandKeys = useRef(new Map<string, string>());
  const openCommand = (target: NonNullable<typeof commandTarget>) => {
    setCommandReason('');
    setCommandPassword('');
    setCreatePassword('');
    setCommandState(initialCommandState);
    setActiveTab('users');
    setCommandTarget(target);
  };

  const commandKey = (identity: string): string => {
    const existing = commandKeys.current.get(identity);
    if (existing) return existing;
    const key = `account-${globalThis.crypto.randomUUID()}`;
    commandKeys.current.set(identity, key);
    return key;
  };

  const loadUsers = useCallback(async () => {
    const generation = ++usersGeneration.current;
    usersController.current?.abort();
    const controller = new AbortController();
    usersController.current = controller;
    setUsersState({ status: 'loading', data: null, error: null });
    try {
      const items = await accountDirectoryClient.query({ signal: controller.signal });
      if (generation !== usersGeneration.current) return;
      const rows = adaptAccountDirectory(items);
      setUsersState({ status: rows.length > 0 ? 'ready' : 'empty', data: rows, error: null });
    } catch (error) {
      if (generation !== usersGeneration.current || isAbortError(error)) return;
      setUsersState({ status: 'error', data: null, error: errorMessage(error, '帳號列表暫時無法取得，請稍後重試。') });
    }
  }, []);

  const runAccountCommand = useCallback(async (
    identity: string,
    operation: (idempotencyKey: string) => Promise<AccountMutationReceipt>,
  ) => {
    setCommandState({ status: 'loading', data: null, error: null });
    try {
      const receipt = await operation(commandKey(identity));
      commandKeys.current.delete(identity);
      setCommandPassword('');
      setCreatePassword('');
      await loadUsers();
      setCommandState({ status: 'ready', data: receipt, error: null });
      setCommandTarget(null);
    } catch (error) {
      setCommandState({ status: 'error', data: null, error: errorMessage(error, '帳號操作未完成，請確認資料後再試。') });
    }
  }, [loadUsers]);

  const createAccount = useCallback(() => {
    const reason = commandReason.trim();
    const identity = `create:${createUsername}:${createDisplayName}:${reason}`;
    return runAccountCommand(identity, (idempotencyKey) => accountCenterClient.create({
      username: createUsername.trim(),
      display_name: createDisplayName.trim(),
      password: createPassword,
      linked_line_user_id: null,
      reason,
      idempotency_key: idempotencyKey,
    }));
  }, [commandReason, createDisplayName, createPassword, createUsername, runAccountCommand]);

  const mutateAccount = useCallback((user: AccountDirectoryRow, action: 'enabled' | 'password' | 'mfa' | 'sessions', note = commandReason) => {
    const reason = note.trim();
    const identity = `${action}:${user.id}:${user.accessControlVersion}:${reason}:${action === 'password' ? commandPassword : ''}`;
    return runAccountCommand(identity, (idempotencyKey) => {
      const common = { reason, expected_version: user.accessControlVersion, idempotency_key: idempotencyKey };
      if (action === 'enabled') return accountCenterClient.setEnabled(user.id, { ...common, enabled: !user.enabled });
      if (action === 'password') return accountCenterClient.resetPassword(user.id, { ...common, password: commandPassword });
      if (action === 'mfa') return accountCenterClient.resetMfa(user.id, common);
      return accountCenterClient.revokeSessions(user.id, common);
    });
  }, [commandPassword, commandReason, runAccountCommand]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void loadUsers();
    }, 0);
    return () => {
      window.clearTimeout(timer);
      usersController.current?.abort();
    };
  }, [loadUsers]);

  const userRows = usersState.data ?? [];
  useUnsavedDraft('帳號權限', { '帳號': createUsername, '顯示名稱': createDisplayName, '原因': commandReason, '新密碼已輸入（不顯示內容）': !!createPassword || !!commandPassword }, { enabled: !!commandTarget, busy: commandState.status === 'loading', resetKey: commandTarget });


  return (
    <div className="account-page-container" data-surface-id="account.page">
      <ManagementPageHeader className="account-page-header" title="👤 系統帳號與安全管理" description="管理工作人員帳號與登入驗證。">
        <button
          type="button"
          className="account-primary-btn"
          data-control-id="account.user.create"
          aria-describedby="account-command-disabled-reason"
          onClick={() => openCommand('create')}
          disabled={commandState.status === 'loading' || !['ready', 'empty'].includes(usersState.status)}
        >
          + 建立工作人員帳號
        </button>
      </ManagementPageHeader>

      <div className="account-tab-bar" role="tablist" aria-label="帳號中心查詢分頁">
        <button
          type="button"
          role="tab"
          data-surface-id="account.tab.users"
          aria-selected={activeTab === 'users'}
          className={`account-tab-btn ${activeTab === 'users' ? 'active' : ''}`}
          onClick={() => setActiveTab('users')}
        >
          👥 1. 內部人員帳號列表 {usersState.data ? `(${userRows.length})` : ''}
        </button>
        <button
          type="button"
          role="tab"
          data-surface-id="account.tab.totp"
          aria-selected={activeTab === 'totp'}
          className={`account-tab-btn ${activeTab === 'totp' ? 'active' : ''}`}
          onClick={() => setActiveTab('totp')}
        >
          📱 2. 驗證器動態碼（說明）
        </button>
      </div>

      {activeTab === 'users' && (
        <section aria-label="帳號列表" data-surface-id="account.users.list">
          <div className="account-query-panel">
            <span>💡 帳號列表顯示工作人員帳號、啟用狀態與管理權限；安全操作皆須填寫原因。</span>
            <button
              type="button"
              className="account-secondary-btn"
              data-control-id="account.users.refresh"
              onClick={() => void loadUsers()}
              disabled={usersState.status === 'loading'}
            >
              重新整理清冊
            </button>
          </div>

          <Drawer isOpen={commandTarget !== null} onClose={() => { setCommandTarget(null); setCommandPassword(''); setCreatePassword(''); }} closeDisabled={commandState.status === 'loading'} closeLabel="關閉帳號操作" title={commandTarget === 'create' ? '建立工作人員帳號' : '帳號安全操作'}>
            <div className="account-form-panel-header">
              <h3 className="account-form-panel-title">{commandTarget === 'create' ? '新帳號資料' : commandTarget ? `${commandTarget.user.displayName}（${commandTarget.user.username}）` : ''}</h3>
              {commandTarget && commandTarget !== 'create' && <p>本次操作：{({ password: '重設密碼', mfa: '重設驗證器', sessions: '強制登出', enabled: commandTarget.user.enabled ? '停權' : '啟用' })[commandTarget.action]}</p>}
            </div>
            <fieldset className="account-form-grid" disabled={commandState.status === 'loading'}>
              {commandTarget === 'create' && <>
              <div className="account-field-item">
                <label htmlFor="account-create-username">新帳號</label>
                <input
                  id="account-create-username" ref={usernameRef} aria-required="true"
                  value={createUsername}
                  onChange={(event) => setCreateUsername(event.target.value)}
                  maxLength={100}
                  placeholder="例如 supervisor_chen"
                />
              </div>
              <div className="account-field-item">
                <label htmlFor="account-create-display">顯示名稱</label>
                <input
                  id="account-create-display" ref={displayNameRef} aria-required="true"
                  value={createDisplayName}
                  onChange={(event) => setCreateDisplayName(event.target.value)}
                  maxLength={100}
                  placeholder="例如 陳督導"
                />
              </div>
              <div className="account-field-item">
                <label htmlFor="account-create-password">新密碼</label>
                <input
                  id="account-create-password" ref={createPasswordRef} aria-required="true"
                  type="password"
                  value={createPassword}
                  onChange={(event) => setCreatePassword(event.target.value)}
                  maxLength={256}
                  autoComplete="new-password"
                  placeholder="建立帳號密碼 (至少 10 個字元)"
                />
              </div>
              </>}
              {commandTarget && commandTarget !== 'create' && commandTarget.action === 'password' && <div className="account-field-item">
                <label htmlFor="account-command-password">重設密碼</label>
                <input
                  id="account-command-password" ref={commandPasswordRef} aria-required="true"
                  type="password"
                  value={commandPassword}
                  onChange={(event) => setCommandPassword(event.target.value)}
                  maxLength={256}
                  autoComplete="new-password"
                  placeholder="重設密碼使用 (至少 10 個字元)"
                />
              </div>}
              <div className="account-field-item account-field-item-full">
                <label htmlFor="account-command-reason">備註（選填）</label>
                <input
                  id="account-command-reason" ref={commandReasonRef}
                  value={commandReason}
                  onChange={(event) => setCommandReason(event.target.value)}
                  maxLength={500}
                  placeholder="有需要補充的內容再填寫"
                />
              </div>
            </fieldset>
            <p id="account-command-disabled-reason" className="account-query-state" style={{ color: 'var(--md-sys-color-error)' }}>
              備註可留白；建立或重設密碼至少需要 10 個字元。
            </p>
            {saveValidation.feedback}
            {commandState.status === 'error' && <div role="alert">{commandState.error}</div>}
            <button type="button" className="account-primary-btn" disabled={commandState.status === 'loading'} onClick={() => {
              if (!saveValidation.validate([
                ...(commandTarget === 'create' ? [
                  { value: createUsername, label: '新帳號', ref: usernameRef },
                  { value: createDisplayName, label: '顯示名稱', ref: displayNameRef },
                  { value: createPassword, label: '新密碼', ref: createPasswordRef, valid: createPassword.length >= 10, message: '請填寫至少 10 個字元的新密碼。' },
                ] : commandTarget?.action === 'password' ? [{ value: commandPassword, label: '重設密碼', ref: commandPasswordRef, valid: commandPassword.length >= 10, message: '請填寫至少 10 個字元的重設密碼。' }] : []),
              ])) return;
              if (commandTarget === 'create') void createAccount(); else if (commandTarget) void mutateAccount(commandTarget.user, commandTarget.action);
            }}>確認執行</button>
          </Drawer>

          {commandState.status === 'error' && commandTarget === null && (
            <div className="account-query-state account-query-error" role="alert">
              <span>{commandState.error}</span>
            </div>
          )}
          {commandState.status === 'ready' && commandState.data && (
            <div className="account-query-panel" data-surface-id="account.command.receipt">
              帳號已更新。
            </div>
          )}
          {usersState.status === 'loading' && (
            <div className="account-query-state" data-surface-id="account.users.loading">
              載入帳號列表中…
            </div>
          )}
          {usersState.status === 'error' && (
            <div data-surface-id="account.users.error">
              <QueryError message={usersState.error ?? '帳號列表查詢失敗。'} onRetry={() => void loadUsers()} />
            </div>
          )}
          {usersState.status === 'empty' && (
            <div className="account-query-state" data-surface-id="account.users.empty">
              目前沒有可顯示的帳號列表。
            </div>
          )}
          {usersState.status === 'ready' && (
            <div className="account-grid" data-surface-id="account.users.ready">
              {userRows.map((user) => (
                <div key={user.id} className="account-card">
                  <div className="account-card-heading">
                    <span className="account-card-name">👤 {user.displayName}</span>
                    <span className={`account-status-pill ${user.enabled ? 'enabled' : 'disabled'}`}>
                      {user.enabled ? '🟢 正常啟用' : '🔴 已停權鎖定'}
                    </span>
                  </div>
                  <div className="account-card-facts">
                    <div><strong>帳號：</strong><code>{user.username}</code></div>
                    <div><strong>Root：</strong>{user.isRoot ? '是' : '否'}</div>
                  </div>
                  {user.isRoot ? <p>Root 帳號受保護；重設帳密、驗證器或撤銷登入須透過離線維運，不可在此停權。</p> : <div className="account-card-actions">
                    <button
                      type="button"
                      data-control-id="account.user.password-reset"
                      aria-describedby="account-command-disabled-reason"
                      onClick={() => openCommand({ user, action: 'password' })}
                      disabled={commandState.status === 'loading'}
                    >
                      重設密碼
                    </button>
                    <button
                      type="button"
                      data-control-id="account.mfa.reset"
                      aria-describedby="account-command-disabled-reason"
                      onClick={() => void mutateAccount(user, 'mfa', '')}
                      disabled={commandState.status === 'loading'}
                    >
                      重設 MFA
                    </button>
                    <button
                      type="button"
                      data-control-id="account.user.session-revoke"
                      aria-describedby="account-command-disabled-reason"
                      onClick={() => void mutateAccount(user, 'sessions', '')}
                      disabled={commandState.status === 'loading'}
                    >
                      🚪 強制登出
                    </button>
                    <button
                      type="button"
                      data-control-id={user.enabled ? 'account.user.disable' : 'account.user.enable'}
                      aria-describedby="account-command-disabled-reason"
                      onClick={() => void mutateAccount(user, 'enabled', '')}
                      disabled={commandState.status === 'loading'}
                    >
                      {user.enabled ? '🔒 停權' : '🔓 啟用'}
                    </button>
                  </div>}
                </div>
              ))}
            </div>
          )}
        </section>
      )}

      {activeTab === 'totp' && (
        <section className="account-explanation" aria-label="TOTP 說明">
          <h3>📱 驗證器動態碼登入說明</h3>
          <p>登入時先輸入帳號密碼，再輸入手機驗證器產生的 6 位數動態碼。</p>
          <div className="account-step-grid">
            <div><strong>步驟 1</strong><span>輸入帳號與密碼。</span></div>
            <div><strong>步驟 2</strong><span>輸入手機驗證器產生的六位數動態碼。</span></div>
            <div><strong>管理方式</strong><span>首次登入時依畫面完成設定；需要重設時，請回帳號列表使用「重設 MFA」。</span></div>
          </div>
        </section>
      )}

    </div>
  );
};

export default AccountManagementPage;
