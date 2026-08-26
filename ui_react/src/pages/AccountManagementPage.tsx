/**
 * File: AccountManagementPage.tsx
 * Description: 帳號中心三個唯讀查詢區塊與明確停用的安全操作槽位。
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import './AccountManagementPage.css';
import { accountDirectoryClient } from '../api/access/account_directory_client';
import { accountCenterClient } from '../api/access/account_center_client';
import type { AccountMutationReceipt } from '../api/access/account_center_schemas';
import { auditQueryClient, type AuditQueryParams } from '../api/access/audit_query_client';
import { jobObservationClient } from '../api/jobs/job_observation_client';
import {
  adaptAccountDirectory,
  adaptJobObservation,
  ACCOUNT_UNAVAILABLE,
  type AccountDirectoryRow,
  type JobObservationView,
} from '../adapters/access/account_query_adapter';
import {
  adaptAuditDetail,
  adaptAuditPage,
  type AuditDetailView,
  type AuditPageView,
} from '../adapters/access/audit_query_adapter';

type Tab = 'users' | 'totp' | 'audit' | 'jobs';
type LoadStatus = 'idle' | 'loading' | 'ready' | 'empty' | 'error';

interface QueryState<T> {
  status: LoadStatus;
  data: T | null;
  error: string | null;
}

const initialUsersState: QueryState<AccountDirectoryRow[]> = { status: 'idle', data: null, error: null };
const initialAuditState: QueryState<AuditPageView> = { status: 'idle', data: null, error: null };
const initialAuditDetailState: QueryState<AuditDetailView> = { status: 'idle', data: null, error: null };
const initialJobState: QueryState<JobObservationView> = { status: 'idle', data: null, error: null };
const initialCommandState: QueryState<AccountMutationReceipt> = { status: 'idle', data: null, error: null };

function errorMessage(error: unknown, fallback: string): string {
  const code = String((error as { code?: unknown })?.code ?? (error instanceof Error ? error.message : '')).toUpperCase();
  if (code.includes('UNAUTHENTICATED')) return '請先完成管理員登入後再操作。';
  if (code.includes('FORBIDDEN')) return '帳號中心僅限唯一啟用的 root 帳號；請以 root 身分重新登入。';
  if (code.includes('STALE') || code.includes('CONFLICT')) return '資料已更新，請重新整理後再操作。';
  if (code.includes('UNAVAILABLE') || code.includes('NETWORK') || code.includes('TIMEOUT')) return '服務目前暫時無法使用，請稍後重試。';
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

function Unavailable({ children = ACCOUNT_UNAVAILABLE }: { children?: React.ReactNode }) {
  return <span className="account-unavailable">{children}</span>;
}

export const AccountManagementPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState<Tab>('users');
  const [usersState, setUsersState] = useState(initialUsersState);
  const [auditState, setAuditState] = useState(initialAuditState);
  const [auditDetailState, setAuditDetailState] = useState(initialAuditDetailState);
  const [jobState, setJobState] = useState(initialJobState);
  const [commandState, setCommandState] = useState(initialCommandState);
  const [commandReason, setCommandReason] = useState('');
  const [commandPassword, setCommandPassword] = useState('');
  const [createUsername, setCreateUsername] = useState('');
  const [createDisplayName, setCreateDisplayName] = useState('');
  const [createPassword, setCreatePassword] = useState('');
  const [auditLoaded, setAuditLoaded] = useState(false);
  const [auditPage, setAuditPage] = useState(1);
  const [auditFilterInput, setAuditFilterInput] = useState('');
  const [jobIdInput, setJobIdInput] = useState('');

  const usersGeneration = useRef(0);
  const auditGeneration = useRef(0);
  const auditDetailGeneration = useRef(0);
  const jobGeneration = useRef(0);
  const usersController = useRef<AbortController | null>(null);
  const auditController = useRef<AbortController | null>(null);
  const auditDetailController = useRef<AbortController | null>(null);
  const jobController = useRef<AbortController | null>(null);
  const auditActionPrefixRef = useRef('');
  const commandKeys = useRef(new Map<string, string>());

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
      setUsersState({ status: 'error', data: null, error: errorMessage(error, '帳號清冊暫時無法取得，請稍後重試。') });
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
      setCommandState({ status: 'ready', data: receipt, error: null });
      setCommandPassword('');
      setCreatePassword('');
      await loadUsers();
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

  const mutateAccount = useCallback((user: AccountDirectoryRow, action: 'enabled' | 'password' | 'mfa' | 'sessions') => {
    const reason = commandReason.trim();
    const identity = `${action}:${user.id}:${user.accessControlVersion}:${reason}:${action === 'password' ? commandPassword : ''}`;
    return runAccountCommand(identity, (idempotencyKey) => {
      const common = { reason, expected_version: user.accessControlVersion, idempotency_key: idempotencyKey };
      if (action === 'enabled') return accountCenterClient.setEnabled(user.id, { ...common, enabled: !user.enabled });
      if (action === 'password') return accountCenterClient.resetPassword(user.id, { ...common, password: commandPassword });
      if (action === 'mfa') return accountCenterClient.resetMfa(user.id, common);
      return accountCenterClient.revokeSessions(user.id, common);
    });
  }, [commandPassword, commandReason, runAccountCommand]);

  const loadAudit = useCallback(async (page: number, actionPrefix = auditActionPrefixRef.current) => {
    const generation = ++auditGeneration.current;
    auditController.current?.abort();
    auditDetailController.current?.abort();
    auditDetailGeneration.current += 1;
    setAuditDetailState(initialAuditDetailState);
    const controller = new AbortController();
    auditController.current = controller;
    setAuditState((current) => ({ ...current, status: 'loading', error: null }));
    const params: AuditQueryParams = { page, pageSize: 25, actionPrefix: actionPrefix.trim() || undefined };
    try {
      const result = await auditQueryClient.query(params, { signal: controller.signal });
      if (generation !== auditGeneration.current) return;
      const pageView = adaptAuditPage(result);
      setAuditPage(pageView.page);
      setAuditLoaded(true);
      setAuditState({ status: pageView.items.length > 0 ? 'ready' : 'empty', data: pageView, error: null });
    } catch (error) {
      if (generation !== auditGeneration.current || isAbortError(error)) return;
      setAuditState((current) => ({ ...current, status: 'error', error: errorMessage(error, '安全稽核紀錄暫時無法取得，請稍後重試。') }));
    }
  }, []);

  const loadAuditDetail = useCallback(async (auditId: number) => {
    const generation = ++auditDetailGeneration.current;
    auditDetailController.current?.abort();
    const controller = new AbortController();
    auditDetailController.current = controller;
    setAuditDetailState({ status: 'loading', data: null, error: null });
    try {
      const result = await auditQueryClient.detail(auditId, { signal: controller.signal });
      if (generation !== auditDetailGeneration.current) return;
      setAuditDetailState({ status: 'ready', data: adaptAuditDetail(result), error: null });
    } catch (error) {
      if (generation !== auditDetailGeneration.current || isAbortError(error)) return;
      setAuditDetailState({ status: 'error', data: null, error: errorMessage(error, '安全稽核詳情暫時無法取得，請稍後重試。') });
    }
  }, []);

  const loadJob = useCallback(async () => {
    const jobId = jobIdInput.trim();
    if (!jobId) return;
    const generation = ++jobGeneration.current;
    jobController.current?.abort();
    const controller = new AbortController();
    jobController.current = controller;
    setJobState({ status: 'loading', data: null, error: null });
    try {
      const result = await jobObservationClient.query(jobId, { signal: controller.signal });
      if (generation !== jobGeneration.current) return;
      setJobState({ status: 'ready', data: adaptJobObservation(result), error: null });
    } catch (error) {
      if (generation !== jobGeneration.current || isAbortError(error)) return;
      setJobState({ status: 'error', data: null, error: errorMessage(error, '背景工作狀態暫時無法取得，請稍後重試。') });
    }
  }, [jobIdInput]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void loadUsers();
    }, 0);
    return () => {
      window.clearTimeout(timer);
      usersController.current?.abort();
    };
  }, [loadUsers]);

  useEffect(() => {
    if (activeTab === 'audit' && !auditLoaded) void loadAudit(1);
    return () => {
      auditController.current?.abort();
      auditDetailController.current?.abort();
      jobController.current?.abort();
    };
  }, [activeTab, auditLoaded, loadAudit]);

  const userRows = usersState.data ?? [];
  const auditPageView = auditState.data;

  return (
    <div className="account-page-container" data-surface-id="account.page">
      <div className="page-header-banner account-page-header">
        <div className="account-page-header-text">
          <h1 className="page-title">👤 系統帳號與安全管理</h1>
          <p className="page-subtitle">管理工作人員帳號、登入驗證、安全稽核與背景工作狀態。</p>
        </div>
        <button
          type="button"
          className="account-primary-btn"
          data-control-id="account.user.create"
          aria-describedby="account-command-disabled-reason"
          onClick={() => void createAccount()}
          disabled={commandState.status === 'loading' || !commandReason.trim() || !createUsername.trim() || !createDisplayName.trim() || createPassword.length < 12}
        >
          + 建立工作人員帳號
        </button>
      </div>

      <div className="account-tab-bar" role="tablist" aria-label="帳號中心查詢分頁">
        <button
          type="button"
          role="tab"
          data-surface-id="account.tab.users"
          aria-selected={activeTab === 'users'}
          className={`account-tab-btn ${activeTab === 'users' ? 'active' : ''}`}
          onClick={() => setActiveTab('users')}
        >
          👥 1. 內部人員帳號清冊 {usersState.data ? `(${userRows.length})` : ''}
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
        <button
          type="button"
          role="tab"
          data-surface-id="account.tab.audit"
          aria-selected={activeTab === 'audit'}
          className={`account-tab-btn ${activeTab === 'audit' ? 'active' : ''}`}
          onClick={() => setActiveTab('audit')}
        >
          🛡️ 3. 安全操作與登入稽核 {auditPageView ? `(${auditPageView.total})` : ''}
        </button>
        <button
          type="button"
          role="tab"
          data-surface-id="account.tab.jobs"
          aria-selected={activeTab === 'jobs'}
          className={`account-tab-btn ${activeTab === 'jobs' ? 'active' : ''}`}
          onClick={() => setActiveTab('jobs')}
        >
          ⚙️ 4. 背景工作狀態
        </button>
      </div>

      {activeTab === 'users' && (
        <section aria-label="帳號清冊" data-surface-id="account.users.list">
          <div className="account-query-panel">
            <span>💡 帳號清冊顯示工作人員帳號、啟用狀態與管理權限；安全操作皆須填寫原因。</span>
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

          <div className="account-form-panel" aria-label="帳號中心命令輸入">
            <div className="account-form-panel-header">
              <h3 className="account-form-panel-title">📝 帳號建立與操作安全參數</h3>
              <span style={{ fontSize: '0.8rem', color: '#8b7169' }}>
                填寫後可點擊上方「+ 建立工作人員帳號」或卡片上的操作按鈕
              </span>
            </div>
            <div className="account-form-grid">
              <div className="account-field-item">
                <label htmlFor="account-create-username">新帳號</label>
                <input
                  id="account-create-username"
                  value={createUsername}
                  onChange={(event) => setCreateUsername(event.target.value)}
                  maxLength={100}
                  placeholder="例如 supervisor_chen"
                />
              </div>
              <div className="account-field-item">
                <label htmlFor="account-create-display">顯示名稱</label>
                <input
                  id="account-create-display"
                  value={createDisplayName}
                  onChange={(event) => setCreateDisplayName(event.target.value)}
                  maxLength={100}
                  placeholder="例如 陳督導"
                />
              </div>
              <div className="account-field-item">
                <label htmlFor="account-create-password">新密碼</label>
                <input
                  id="account-create-password"
                  type="password"
                  value={createPassword}
                  onChange={(event) => setCreatePassword(event.target.value)}
                  maxLength={256}
                  autoComplete="new-password"
                  placeholder="建立帳號密碼 (至少 12 位)"
                />
              </div>
              <div className="account-field-item">
                <label htmlFor="account-command-password">重設密碼</label>
                <input
                  id="account-command-password"
                  type="password"
                  value={commandPassword}
                  onChange={(event) => setCommandPassword(event.target.value)}
                  maxLength={256}
                  autoComplete="new-password"
                  placeholder="重設密碼使用 (至少 12 位)"
                />
              </div>
              <div className="account-field-item account-field-item-full">
                <label htmlFor="account-command-reason">操作原因</label>
                <input
                  id="account-command-reason"
                  value={commandReason}
                  onChange={(event) => setCommandReason(event.target.value)}
                  maxLength={500}
                  placeholder="請輸入本次操作原因（例如：2026/08 督導人員職務建立與啟用）"
                />
              </div>
            </div>
            <p id="account-command-disabled-reason" className="account-query-state">
              若操作按鈕無法使用，請先填寫操作原因；建立帳號須填齊帳號、顯示名稱與至少 12 位密碼，重設密碼也須輸入至少 12 位新密碼。操作進行中會暫時鎖定其他帳號操作。
            </p>
          </div>

          {commandState.status === 'error' && (
            <div className="account-query-state account-query-error" role="alert">
              <span>{commandState.error}</span>
            </div>
          )}
          {commandState.status === 'ready' && commandState.data && (
            <div className="account-query-panel" data-surface-id="account.command.receipt">
              帳號操作已完成，清冊已重新整理。
            </div>
          )}
          {usersState.status === 'loading' && (
            <div className="account-query-state" data-surface-id="account.users.loading">
              載入帳號清冊中…
            </div>
          )}
          {usersState.status === 'error' && (
            <div data-surface-id="account.users.error">
              <QueryError message={usersState.error ?? '帳號清冊查詢失敗。'} onRetry={() => void loadUsers()} />
            </div>
          )}
          {usersState.status === 'empty' && (
            <div className="account-query-state" data-surface-id="account.users.empty">
              目前沒有可顯示的帳號清冊。
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
                  <div className="account-card-actions">
                    <button
                      type="button"
                      data-control-id="account.user.password-reset"
                      aria-describedby="account-command-disabled-reason"
                      onClick={() => void mutateAccount(user, 'password')}
                      disabled={commandState.status === 'loading' || !commandReason.trim() || commandPassword.length < 12}
                    >
                      重設密碼
                    </button>
                    <button
                      type="button"
                      data-control-id="account.mfa.reset"
                      aria-describedby="account-command-disabled-reason"
                      onClick={() => void mutateAccount(user, 'mfa')}
                      disabled={commandState.status === 'loading' || !commandReason.trim()}
                    >
                      重設 MFA
                    </button>
                    <button
                      type="button"
                      data-control-id="account.user.session-revoke"
                      aria-describedby="account-command-disabled-reason"
                      onClick={() => void mutateAccount(user, 'sessions')}
                      disabled={commandState.status === 'loading' || !commandReason.trim()}
                    >
                      🚪 強制登出
                    </button>
                    <button
                      type="button"
                      data-control-id={user.enabled ? 'account.user.disable' : 'account.user.enable'}
                      aria-describedby="account-command-disabled-reason"
                      onClick={() => void mutateAccount(user, 'enabled')}
                      disabled={commandState.status === 'loading' || !commandReason.trim()}
                    >
                      {user.enabled ? '🔒 停權' : '🔓 啟用'}
                    </button>
                  </div>
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
            <div><strong>管理方式</strong><span>首次登入時依畫面完成設定；需要重設時，請回帳號清冊使用「重設 MFA」。</span></div>
          </div>
        </section>
      )}

      {activeTab === 'audit' && (
        <section className="account-table-container" aria-label="遮罩稽核清單" data-surface-id="account.audit.table">
          <div className="account-table-toolbar">
            <div>
              <h3>🛡️ 安全操作與登入稽核</h3>
              <p>查看已去敏的操作人員、影響對象、來源位置、執行結果與安全操作詳情。</p>
            </div>
            <button
              type="button"
              className="account-secondary-btn"
              data-control-id="account.audit.refresh"
              onClick={() => void loadAudit(auditPage)}
              disabled={auditState.status === 'loading'}
            >
              重新整理
            </button>
          </div>
          <div className="account-filter-row">
            <label htmlFor="account-audit-filter">動作前綴</label>
            <input
              id="account-audit-filter"
              data-control-id="account.audit.filter"
              value={auditFilterInput}
              onChange={(event) => setAuditFilterInput(event.target.value)}
              maxLength={100}
              placeholder="例如 admin.login"
            />
            <button
              type="button"
              className="account-secondary-btn"
              onClick={() => { auditActionPrefixRef.current = auditFilterInput.trim(); void loadAudit(1, auditFilterInput); }}
              disabled={auditState.status === 'loading'}
            >
              套用篩選
            </button>
          </div>
          {auditState.status === 'loading' && <div className="account-query-state">載入遮罩稽核清單中…</div>}
          {auditState.status === 'error' && (
            <div data-surface-id="account.audit.error">
              <QueryError message={auditState.error ?? '遮罩稽核查詢失敗。'} onRetry={() => void loadAudit(auditPage)} />
            </div>
          )}
          {auditState.status === 'empty' && (
            <div className="account-query-state" data-surface-id="account.audit.empty">
              目前沒有符合條件的安全稽核紀錄。
            </div>
          )}
          {auditState.status === 'ready' && auditPageView && (
            <>
              <table className="account-data-table">
                <thead>
                  <tr>
                    <th>審計編號</th>
                    <th>事件時間</th>
                    <th>操作分類</th>
                    <th>操作人員</th>
                    <th>目標</th>
                    <th>來源 IP</th>
                    <th>執行結果</th>
                    <th>操作詳情</th>
                  </tr>
                </thead>
                <tbody>
                  {auditPageView.items.map((entry) => (
                    <tr key={entry.auditId} data-surface-id="account.audit.row">
                      <td><code>{entry.auditId}</code></td>
                      <td>{entry.occurredAt}</td>
                      <td><span className="account-action-pill">{entry.actionFamily}</span></td>
                      <td>{entry.actorLabelMasked ?? '—'}</td>
                      <td>{entry.targetLabelMasked ?? '—'}</td>
                      <td><code>{entry.ipAddressMasked ?? '—'}</code></td>
                      <td><span className="account-outcome-pill">{entry.outcome}</span></td>
                      <td>
                        <button
                          type="button"
                          className="account-secondary-btn"
                          data-control-id="account.audit.detail"
                          onClick={() => void loadAuditDetail(entry.auditId)}
                          disabled={auditDetailState.status === 'loading'}
                        >
                          查看
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <div className="account-pagination" data-surface-id="account.audit.pagination">
                <button
                  type="button"
                  onClick={() => void loadAudit(auditPageView.page - 1)}
                  disabled={auditPageView.page <= 1}
                >
                  上一頁
                </button>
                <span>第 {auditPageView.page} / {auditPageView.totalPages} 頁（共 {auditPageView.total} 筆）</span>
                <button
                  type="button"
                  onClick={() => void loadAudit(auditPageView.page + 1)}
                  disabled={auditPageView.page >= auditPageView.totalPages}
                >
                  下一頁
                </button>
              </div>
            </>
          )}
          {auditDetailState.status === 'loading' && (
            <div className="account-query-state" data-surface-id="account.audit.unavailable">
              載入遮罩明細中…
            </div>
          )}
          {auditDetailState.status === 'error' && (
            <div data-surface-id="account.audit.unavailable" role="alert">
              {auditDetailState.error ?? '遮罩明細查詢失敗。'}
            </div>
          )}
          {auditDetailState.status === 'ready' && auditDetailState.data && (
            <aside className="account-query-panel" aria-label="遮罩稽核明細">
              <strong>稽核 #{auditDetailState.data.auditId}</strong>
              {auditDetailState.data.details.length === 0 ? (
                <span>這筆紀錄沒有其他可顯示的安全詳情。</span>
              ) : (
                <dl>
                  {auditDetailState.data.details.map((field) => (
                    <React.Fragment key={field.key}>
                      <dt>{field.key}</dt>
                      <dd>{field.valueMasked}</dd>
                    </React.Fragment>
                  ))}
                </dl>
              )}
            </aside>
          )}
        </section>
      )}

      {activeTab === 'jobs' && (
        <section className="account-table-container" aria-label="背景工作觀察">
          <div className="account-table-toolbar">
            <div>
              <h3>⚙️ 背景工作狀態</h3>
              <p>輸入作業頁面提供的查詢碼，可確認背景工作是否仍在處理或已完成。</p>
            </div>
          </div>
          <div className="account-filter-row">
            <label htmlFor="account-job-id">背景工作查詢碼</label>
            <input
              id="account-job-id"
              data-control-id="account.jobs.lookup"
              value={jobIdInput}
              onChange={(event) => setJobIdInput(event.target.value)}
              maxLength={191}
              placeholder="輸入作業頁面提供的查詢碼"
            />
            <button
              type="button"
              className="account-secondary-btn"
              onClick={() => void loadJob()}
              disabled={!jobIdInput.trim() || jobState.status === 'loading'}
            >
              查詢狀態
            </button>
            <button
              type="button"
              className="account-secondary-btn"
              data-control-id="account.jobs.refresh"
              onClick={() => void loadJob()}
              disabled={!jobIdInput.trim() || jobState.status === 'loading'}
            >
              重新整理
            </button>
          </div>
          {jobState.status === 'idle' && (
            <div className="account-query-state">
              <Unavailable>請輸入作業頁面提供的查詢碼。</Unavailable>
            </div>
          )}
          {jobState.status === 'loading' && <div className="account-query-state">載入背景工作狀態中…</div>}
          {jobState.status === 'error' && (
            <QueryError message={jobState.error ?? '背景工作觀察查詢失敗。'} onRetry={() => void loadJob()} />
          )}
          {jobState.status === 'ready' && jobState.data && (
            <div className="account-job-observation">
              <div><strong>工作類型</strong><span>{jobState.data.commandType}</span></div>
              <div><strong>處理狀態</strong><span>{jobState.data.status}</span></div>
              <div><strong>已嘗試次數</strong><span>{jobState.data.attemptCount} / {jobState.data.maxAttempts}</span></div>
            </div>
          )}
          <div className="account-query-panel">需要重新執行或修正時，請回原作業頁面依可用流程處理。</div>
        </section>
      )}
    </div>
  );
};

export default AccountManagementPage;
