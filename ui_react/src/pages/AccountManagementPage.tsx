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

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : '查詢失敗，請稍後重試。';
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
      setUsersState({ status: 'error', data: null, error: errorMessage(error) });
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
      setCommandState({ status: 'error', data: null, error: errorMessage(error) });
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
      setAuditState((current) => ({ ...current, status: 'error', error: errorMessage(error) }));
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
      setAuditDetailState({ status: 'error', data: null, error: errorMessage(error) });
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
      setJobState({ status: 'error', data: null, error: errorMessage(error) });
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
          <h1 className="page-title">👤 系統帳號、權限與 TOTP 雙因子管理</h1>
          <p className="page-subtitle">帳號清冊、遮罩稽核與背景工作觀察均以後端 typed GET 顯示；帳號與 MFA 變更仍由原核准流程管理。</p>
        </div>
        <button
          type="button"
          className="account-primary-btn"
          data-control-id="account.user.create"
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
          📱 2. TOTP 雙因子認證（說明）
        </button>
        <button
          type="button"
          role="tab"
          data-surface-id="account.tab.audit"
          aria-selected={activeTab === 'audit'}
          className={`account-tab-btn ${activeTab === 'audit' ? 'active' : ''}`}
          onClick={() => setActiveTab('audit')}
        >
          🛡️ 3. 安全操作與 Session 審計軌跡 {auditPageView ? `(${auditPageView.total})` : ''}
        </button>
        <button
          type="button"
          role="tab"
          data-surface-id="account.tab.jobs"
          aria-selected={activeTab === 'jobs'}
          className={`account-tab-btn ${activeTab === 'jobs' ? 'active' : ''}`}
          onClick={() => setActiveTab('jobs')}
        >
          ⚙️ 4. 背景排程與系統看板
        </button>
      </div>

      {activeTab === 'users' && (
        <section aria-label="帳號清冊" data-surface-id="account.users.list">
          <div className="account-query-panel">
            <span>💡 帳號清冊只顯示後端核准的識別、啟用狀態與存取版本；Email、IP、Session、TOTP 與能力不在本次 typed contract。</span>
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
          </div>

          {commandState.status === 'error' && (
            <div className="account-query-state account-query-error" role="alert">
              <span>{commandState.error}</span>
            </div>
          )}
          {commandState.status === 'ready' && commandState.data && (
            <div className="account-query-panel" data-surface-id="account.command.receipt">
              命令已受理：{commandState.data.operation}／版本 {commandState.data.resulting_access_control_version}／{commandState.data.replayed ? '重播' : '首次執行'}
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
              後端目前沒有可顯示的帳號清冊。
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
                    <div><strong>帳號識別：</strong><code>{user.id}</code></div>
                    <div><strong>Root：</strong>{user.isRoot ? '是' : '否'}</div>
                    <div><strong>Access Control Version：</strong>{user.accessControlVersion}</div>
                    <div><strong>Email / IP / 最後登入：</strong><Unavailable /></div>
                    <div><strong>Session / TOTP：</strong><Unavailable /></div>
                  </div>
                  <div className="account-card-actions">
                    <button
                      type="button"
                      data-control-id="account.user.password-reset"
                      onClick={() => void mutateAccount(user, 'password')}
                      disabled={commandState.status === 'loading' || !commandReason.trim() || commandPassword.length < 12}
                    >
                      重設密碼
                    </button>
                    <button
                      type="button"
                      data-control-id="account.mfa.reset"
                      onClick={() => void mutateAccount(user, 'mfa')}
                      disabled={commandState.status === 'loading' || !commandReason.trim()}
                    >
                      重設 MFA
                    </button>
                    <button
                      type="button"
                      data-control-id="account.user.session-revoke"
                      onClick={() => void mutateAccount(user, 'sessions')}
                      disabled={commandState.status === 'loading' || !commandReason.trim()}
                    >
                      🚪 強制登出
                    </button>
                    <button
                      type="button"
                      data-control-id={user.enabled ? 'account.user.disable' : 'account.user.enable'}
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
          <h3>📱 TOTP（Time-based One-Time Password）雙因子認證說明</h3>
          <p>登入流程為帳號密碼 Challenge 通過後，再輸入手機 Authenticator App 產生的 6 位數動態碼。此頁只保留流程說明，不顯示任何 provisioning URI、secret、QR Code、recovery code 或帳號 enrollment 狀態。</p>
          <div className="account-step-grid">
            <div><strong>步驟 1</strong><span>輸入帳號與密碼，取得短效登入挑戰。</span></div>
            <div><strong>步驟 2</strong><span>輸入六位數 TOTP，通過後建立 Bearer Session。</span></div>
            <div><strong>步驟 3</strong><span>帳號中心的綁定、重設與驗證 mutation 尚未開放。</span></div>
          </div>
          <div className="account-query-panel"><Unavailable>後端尚未提供 typed MFA enrollment / reset contract</Unavailable></div>
          <button type="button" data-control-id="account.mfa.enroll" disabled>啟用或重設 TOTP（未開放）</button>
        </section>
      )}

      {activeTab === 'audit' && (
        <section className="account-table-container" aria-label="遮罩稽核清單" data-surface-id="account.audit.table">
          <div className="account-table-toolbar">
            <div>
              <h3>🛡️ 安全操作與 Session 審計軌跡</h3>
              <p>伺服器只回傳遮罩 actor、target、IP、結果、安全動作分類與 allowlisted detail；request path、raw payload 與 PII 不進入 React。</p>
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
              後端目前沒有符合條件的遮罩稽核紀錄。
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
                    <th>安全代碼</th>
                    <th>Detail</th>
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
                      <td><span className={`account-outcome-pill ${entry.outcome}`}>{entry.outcome}</span></td>
                      <td>{entry.reasonCode ?? '—'}</td>
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
                <span>沒有可顯示的 allowlisted detail。</span>
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
              <h3>⚙️ 背景排程與系統看板</h3>
              <p>此頁只查詢指定 job ID 的執行狀態，不顯示 receipt、error、result reference、LINE queue 或 Domain 成功結果。</p>
            </div>
          </div>
          <div className="account-filter-row">
            <label htmlFor="account-job-id">Job ID</label>
            <input
              id="account-job-id"
              data-control-id="account.jobs.lookup"
              value={jobIdInput}
              onChange={(event) => setJobIdInput(event.target.value)}
              maxLength={191}
              placeholder="輸入後端已提供的 job ID"
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
              <Unavailable>輸入有效 Job ID 後才會發出一次 observation GET</Unavailable>
            </div>
          )}
          {jobState.status === 'loading' && <div className="account-query-state">載入背景工作狀態中…</div>}
          {jobState.status === 'error' && (
            <QueryError message={jobState.error ?? '背景工作觀察查詢失敗。'} onRetry={() => void loadJob()} />
          )}
          {jobState.status === 'ready' && jobState.data && (
            <div className="account-job-observation">
              <div><strong>Job ID</strong><code>{jobState.data.jobId}</code></div>
              <div><strong>Command type</strong><span>{jobState.data.commandType}</span></div>
              <div><strong>Execution status</strong><span>{jobState.data.status}</span></div>
              <div><strong>Attempt</strong><span>{jobState.data.attemptCount} / {jobState.data.maxAttempts}</span></div>
              <div><strong>Domain receipt / error / result</strong><Unavailable /></div>
            </div>
          )}
          <div className="account-card-actions">
            <button type="button" data-control-id="account.jobs.cancel" disabled>取消背景工作（未開放）</button>
            <button type="button" data-control-id="account.jobs.retry" disabled>重試背景工作（未開放）</button>
            <button type="button" data-control-id="account.jobs.run" disabled>立即執行（未開放）</button>
          </div>
        </section>
      )}
    </div>
  );
};

export default AccountManagementPage;

