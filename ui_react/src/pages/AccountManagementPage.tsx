/**
 * @file AccountManagementPage.tsx
 * @description 帳號權限管理頁面，提供管理員帳號維護、2FA 強制狀態與資安審計日誌。
 */
import React, { useState } from 'react';
import './AccountManagementPage.css';
import { Drawer } from '../components/Drawer';

export interface AdminUserAccount {
  id: string;
  username: string;
  name: string;
  email: string;
  enabled: boolean;
  totpEnabled: boolean;
  activeSession: boolean;
  lastLoginAt: string;
  lastSeenIp: string;
  createdAt: string;
}

export interface SecurityAuditEntry {
  id: string;
  occurredAt: string;
  actor: string;
  action: 'AdminLogin' | 'RotateCredential' | 'DisableUser' | 'EnableUser' | 'RevokeSession' | 'TotpEnabled';
  targetResource: string;
  maskedIp: string;
  outcome: 'SUCCESS' | 'DENIED' | 'FAILED';
  reason: string;
}

export const AccountManagementPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'users' | 'totp' | 'audit' | 'jobs'>('users');

  // Admin Users State
  const [users, setUsers] = useState<AdminUserAccount[]>([
    {
      id: 'USR-001',
      username: 'lin_meiyun',
      name: '林美雲',
      email: 'meiyun.lin@postpartum-union.org.tw',
      enabled: true,
      totpEnabled: true,
      activeSession: true,
      lastLoginAt: '2026-08-15 08:30:12',
      lastSeenIp: '192.168.1.***',
      createdAt: '2026-01-01'
    },
    {
      id: 'USR-002',
      username: 'chen_shiyu',
      name: '陳世瑀',
      email: 'shiyu.chen@postpartum-union.org.tw',
      enabled: true,
      totpEnabled: true,
      activeSession: true,
      lastLoginAt: '2026-08-15 09:12:45',
      lastSeenIp: '192.168.1.***',
      createdAt: '2026-02-15'
    },
    {
      id: 'USR-003',
      username: 'wang_assistant',
      name: '王小芬',
      email: 'xiaofen.wang@postpartum-union.org.tw',
      enabled: true,
      totpEnabled: false,
      activeSession: false,
      lastLoginAt: '2026-08-14 17:45:00',
      lastSeenIp: '192.168.2.***',
      createdAt: '2026-06-01'
    },
    {
      id: 'USR-004',
      username: 'former_staff_lee',
      name: '李雅慧 (離職員工)',
      email: 'yahui.lee@postpartum-union.org.tw',
      enabled: false,
      totpEnabled: true,
      activeSession: false,
      lastLoginAt: '2026-05-30 18:00:00',
      lastSeenIp: '192.168.1.***',
      createdAt: '2025-10-01'
    }
  ]);

  // Security Audit Entries State
  const [auditLogs, setAuditLogs] = useState<SecurityAuditEntry[]>([
    {
      id: 'AUD-901',
      occurredAt: '2026-08-15 09:12:45',
      actor: 'chen_shiyu (陳世瑀)',
      action: 'AdminLogin',
      targetResource: 'SessionToken#8821a',
      maskedIp: '192.168.1.***',
      outcome: 'SUCCESS',
      reason: 'TOTP 2FA 驗證通過，核發 8 小時有效 Session'
    },
    {
      id: 'AUD-902',
      occurredAt: '2026-08-15 08:30:12',
      actor: 'lin_meiyun (林美雲)',
      action: 'AdminLogin',
      targetResource: 'SessionToken#7714b',
      maskedIp: '192.168.1.***',
      outcome: 'SUCCESS',
      reason: 'TOTP 2FA 驗證通過'
    },
    {
      id: 'AUD-903',
      occurredAt: '2026-08-10 14:20:00',
      actor: 'lin_meiyun (林美雲)',
      action: 'DisableUser',
      targetResource: 'USR-004 (李雅慧)',
      maskedIp: '192.168.1.***',
      outcome: 'SUCCESS',
      reason: '員工離職停權處理，撤銷所有在線 Session'
    },
    {
      id: 'AUD-904',
      occurredAt: '2026-08-01 10:00:00',
      actor: 'chen_shiyu (陳世瑀)',
      action: 'RotateCredential',
      targetResource: 'USR-001 (林美雲)',
      maskedIp: '192.168.1.***',
      outcome: 'SUCCESS',
      reason: '例行性 90 天密碼安全輪替'
    }
  ]);

  // Drawer States
  const [isAddUserOpen, setIsAddUserOpen] = useState<boolean>(false);
  const [newUsername, setNewUsername] = useState<string>('');
  const [newName, setNewName] = useState<string>('');
  const [newEmail, setNewEmail] = useState<string>('');

  const [totpSetupUser, setTotpSetupUser] = useState<AdminUserAccount | null>(null);
  const [totpVerifyCode, setTotpVerifyCode] = useState<string>('');

  const handleToggleUserStatus = (user: AdminUserAccount) => {
    const nextStatus = !user.enabled;
    const actionText = nextStatus ? '啟用' : '停權';
    if (window.confirm(`確定要將工作人員「${user.name}」設為【${actionText}】嗎？${!nextStatus ? '（停權將同步強制撤銷在線 Session）' : ''}`)) {
      setUsers(users.map(u => u.id === user.id ? { ...u, enabled: nextStatus, activeSession: nextStatus ? u.activeSession : false } : u));
      
      // Append Audit Log
      const newAudit: SecurityAuditEntry = {
        id: `AUD-${Date.now().toString().slice(-4)}`,
        occurredAt: new Date().toLocaleString(),
        actor: 'lin_meiyun (目前登入者)',
        action: nextStatus ? 'EnableUser' : 'DisableUser',
        targetResource: `${user.id} (${user.name})`,
        maskedIp: '192.168.1.***',
        outcome: 'SUCCESS',
        reason: `管理員手動${actionText}帳號`
      };
      setAuditLogs([newAudit, ...auditLogs]);
      alert(`✅ 已成功將「${user.name}」${actionText}！`);
    }
  };

  const handleRevokeSession = (user: AdminUserAccount) => {
    if (window.confirm(`確定要強制中斷「${user.name}」的線上連線 (Revoke Session) 嗎？`)) {
      setUsers(users.map(u => u.id === user.id ? { ...u, activeSession: false } : u));
      const newAudit: SecurityAuditEntry = {
        id: `AUD-${Date.now().toString().slice(-4)}`,
        occurredAt: new Date().toLocaleString(),
        actor: 'lin_meiyun (目前登入者)',
        action: 'RevokeSession',
        targetResource: `${user.id} (${user.name})`,
        maskedIp: '192.168.1.***',
        outcome: 'SUCCESS',
        reason: '管理員強制撤銷線上 Session'
      };
      setAuditLogs([newAudit, ...auditLogs]);
      alert(`✅ 已強制登出「${user.name}」！`);
    }
  };

  const handleCreateUser = () => {
    if (!newUsername.trim() || !newName.trim()) {
      alert('請填寫完整帳號與姓名！');
      return;
    }
    const newUser: AdminUserAccount = {
      id: `USR-00${users.length + 1}`,
      username: newUsername.trim(),
      name: newName.trim(),
      email: newEmail.trim() || `${newUsername.trim()}@postpartum-union.org.tw`,
      enabled: true,
      totpEnabled: false,
      activeSession: false,
      lastLoginAt: '從未登入',
      lastSeenIp: '－',
      createdAt: new Date().toISOString().split('T')[0]
    };
    setUsers([...users, newUser]);
    setIsAddUserOpen(false);
    setNewUsername('');
    setNewName('');
    setNewEmail('');
    alert(`✨ 成功建立工作人員「${newUser.name}」！請引導完成 TOTP 雙因子綁定。`);
  };

  const handleVerifyAndEnableTotp = () => {
    if (totpVerifyCode.trim().length !== 6) {
      alert('請輸入 6 位數 TOTP 動態驗證碼！');
      return;
    }
    if (totpSetupUser) {
      setUsers(users.map(u => u.id === totpSetupUser.id ? { ...u, totpEnabled: true } : u));
      const newAudit: SecurityAuditEntry = {
        id: `AUD-${Date.now().toString().slice(-4)}`,
        occurredAt: new Date().toLocaleString(),
        actor: `${totpSetupUser.username} (${totpSetupUser.name})`,
        action: 'TotpEnabled',
        targetResource: totpSetupUser.id,
        maskedIp: '192.168.1.***',
        outcome: 'SUCCESS',
        reason: '完成 Google Authenticator / TOTP 雙因子認證綁定'
      };
      setAuditLogs([newAudit, ...auditLogs]);
      alert(`🎉 恭喜！「${totpSetupUser.name}」已成功啟用 TOTP 雙因子認證防護！`);
      setTotpSetupUser(null);
      setTotpVerifyCode('');
    }
  };

  return (
    <div>
      <div className="page-header-banner" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h1 className="page-title">👤 系統帳號、權限與 TOTP 雙因子管理</h1>
          <p className="page-subtitle">落實 17_Access Control 規範：內部人員全功能存取、TOTP 2FA 強制驗證、8小時 Session 安全期限與審計日誌。</p>
        </div>

        <button 
          style={{
            padding: '10px 20px',
            backgroundColor: '#ff7f50',
            color: '#fff',
            border: 'none',
            borderRadius: '10px',
            fontWeight: 700,
            cursor: 'pointer',
            boxShadow: '0 2px 8px rgba(255,127,80,0.25)'
          }}
          onClick={() => setIsAddUserOpen(true)}
        >
          + 新增工作人員帳號
        </button>
      </div>

      {/* 3-Tab Bar */}
      <div className="account-tab-bar">
        <button
          className={`account-tab-btn ${activeTab === 'users' ? 'active' : ''}`}
          onClick={() => setActiveTab('users')}
        >
          👥 1. 內部人員帳號清冊 ({users.length})
        </button>
        <button
          className={`account-tab-btn ${activeTab === 'totp' ? 'active' : ''}`}
          onClick={() => setActiveTab('totp')}
        >
          📱 2. TOTP 雙因子認證 (2FA) 設定
        </button>
        <button
          className={`account-tab-btn ${activeTab === 'audit' ? 'active' : ''}`}
          onClick={() => setActiveTab('audit')}
        >
          🛡️ 3. 安全操作與 Session 審計軌跡 ({auditLogs.length})
        </button>
        <button
          className={`account-tab-btn ${activeTab === 'jobs' ? 'active' : ''}`}
          onClick={() => setActiveTab('jobs')}
        >
          ⚙️ 4. 背景排程與系統看板
        </button>
      </div>

      {/* TAB 1: Admin Users Grid */}
      {activeTab === 'users' && (
        <div>
          <div style={{ backgroundColor: '#fff8f6', border: '1px solid #fed9b8', borderRadius: '12px', padding: '14px 18px', marginBottom: '20px', fontSize: '0.85rem', color: '#57423b', lineHeight: '1.5' }}>
            💡 <strong>17_Access Control 內部存取模型：</strong>所有已啟用 (enabled) 之內部工作人員享有相同業務操作能力，由 <code>AdminPrincipal</code> 紀錄每筆業務指令之操作者身分，確保因果鏈審計責任可追溯。
          </div>

          <div className="account-grid">
            {users.map(user => (
              <div key={user.id} className="account-card">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span style={{ fontSize: '1.2rem', fontWeight: 700, color: '#1e1b19' }}>👤 {user.name}</span>
                    <span style={{ fontSize: '0.75rem', color: '#888' }}>({user.id})</span>
                  </div>
                  <span style={{
                    padding: '3px 10px',
                    borderRadius: '9999px',
                    fontSize: '0.75rem',
                    fontWeight: 700,
                    backgroundColor: user.enabled ? '#dcfce7' : '#fee2e2',
                    color: user.enabled ? '#166534' : '#991b1b'
                  }}>
                    {user.enabled ? '🟢 正常啟用' : '🔴 已停權鎖定'}
                  </span>
                </div>

                <div style={{ fontSize: '0.85rem', color: '#57423b', display: 'flex', flexDirection: 'column', gap: '4px' }}>
                  <div><strong>登入帳號：</strong><code>{user.username}</code></div>
                  <div><strong>電子郵件：</strong>{user.email}</div>
                  <div><strong>最後登入：</strong>{user.lastLoginAt} ({user.lastSeenIp})</div>
                  <div style={{ display: 'flex', gap: '8px', marginTop: '4px' }}>
                    <span>TOTP 2FA：
                      <strong style={{ color: user.totpEnabled ? '#16a34a' : '#ea580c' }}>
                        {user.totpEnabled ? ' 🟢 已啟用' : ' 🟡 未綁定'}
                      </strong>
                    </span>
                    <span>｜ 線上 Session：
                      <strong style={{ color: user.activeSession ? '#2563eb' : '#888' }}>
                        {user.activeSession ? ' 🔵 連線中' : ' ⚪ 離線'}
                      </strong>
                    </span>
                  </div>
                </div>

                <div style={{ display: 'flex', gap: '8px', marginTop: 'auto', paddingTop: '12px', borderTop: '1px solid #f2e2dc' }}>
                  <button
                    style={{
                      flex: 1,
                      padding: '8px',
                      backgroundColor: '#ffffff',
                      border: '1px solid #ff7f50',
                      color: '#ff7f50',
                      borderRadius: '8px',
                      fontWeight: 600,
                      fontSize: '0.82rem',
                      cursor: 'pointer'
                    }}
                    onClick={() => {
                      setTotpSetupUser(user);
                    }}
                  >
                    📱 綁定 TOTP
                  </button>

                  {user.activeSession && (
                    <button
                      style={{
                        padding: '8px 12px',
                        backgroundColor: '#fee2e2',
                        border: '1px solid #fca5a5',
                        color: '#991b1b',
                        borderRadius: '8px',
                        fontWeight: 600,
                        fontSize: '0.82rem',
                        cursor: 'pointer'
                      }}
                      onClick={() => handleRevokeSession(user)}
                    >
                      🚪 強制登出
                    </button>
                  )}

                  <button
                    style={{
                      padding: '8px 14px',
                      backgroundColor: user.enabled ? '#fff1f2' : '#f0fdf4',
                      border: user.enabled ? '1px solid #fecdd3' : '1px solid #bbf7d0',
                      color: user.enabled ? '#e11d48' : '#16a34a',
                      borderRadius: '8px',
                      fontWeight: 700,
                      fontSize: '0.82rem',
                      cursor: 'pointer'
                    }}
                    onClick={() => handleToggleUserStatus(user)}
                  >
                    {user.enabled ? '🔒 停權' : '🔓 啟用'}
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* TAB 2: TOTP 2FA Setup Guide */}
      {activeTab === 'totp' && (
        <div style={{ backgroundColor: '#ffffff', border: '1px solid #dec0b6', borderRadius: '18px', padding: '28px 32px', boxShadow: '0 4px 20px rgba(74,69,67,0.05)' }}>
          <h3 style={{ fontSize: '1.2rem', fontWeight: 700, color: '#1e1b19', marginBottom: '8px' }}>
            📱 TOTP (Time-based One-Time Password) 雙因子雙重安全認證說明
          </h3>
          <p style={{ fontSize: '0.88rem', color: '#74593f', lineHeight: '1.6', marginBottom: '24px' }}>
            為了保護工會產婦個資、排班日曆與財務金流帳目安全，所有登入人員登入時必須輸入密碼 ＋ 手機 Authenticator App 產生的 6 位數動態驗證碼。
          </p>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '20px', marginBottom: '24px' }}>
            <div style={{ border: '1px solid #dec0b6', borderRadius: '14px', padding: '20px', backgroundColor: '#fffdfc' }}>
              <div style={{ fontSize: '1.5rem', marginBottom: '8px' }}>📲 步驟 1</div>
              <h4 style={{ fontSize: '1rem', fontWeight: 700, marginBottom: '6px' }}>下載認證 App</h4>
              <p style={{ fontSize: '0.82rem', color: '#57423b' }}>
                在手機下載 <strong>Google Authenticator</strong> 或 <strong>Microsoft Authenticator</strong>。
              </p>
            </div>

            <div style={{ border: '1px solid #dec0b6', borderRadius: '14px', padding: '20px', backgroundColor: '#fffdfc' }}>
              <div style={{ fontSize: '1.5rem', marginBottom: '8px' }}>📷 步驟 2</div>
              <h4 style={{ fontSize: '1rem', fontWeight: 700, marginBottom: '6px' }}>掃描專屬 QR Code</h4>
              <p style={{ fontSize: '0.82rem', color: '#57423b' }}>
                在人員清冊點擊「📱 綁定 TOTP」，使用手機掃描金鑰 QR Code 建立月子工會帳戶。
              </p>
            </div>

            <div style={{ border: '1px solid #dec0b6', borderRadius: '14px', padding: '20px', backgroundColor: '#fffdfc' }}>
              <div style={{ fontSize: '1.5rem', marginBottom: '8px' }}>🔐 步驟 3</div>
              <h4 style={{ fontSize: '1rem', fontWeight: 700, marginBottom: '6px' }}>輸入 6 位數驗證啟用</h4>
              <p style={{ fontSize: '0.82rem', color: '#57423b' }}>
                輸入手機即時顯示的 6 位數動態碼完成校驗，往後登入均受 2FA 頂級資安防護！
              </p>
            </div>
          </div>
        </div>
      )}

      {/* TAB 3: Security Audit Log Table */}
      {activeTab === 'audit' && (
        <div className="account-table-container">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
            <div>
              <h3 style={{ fontSize: '1.15rem', fontWeight: 700, color: '#1e1b19' }}>
                🛡️ 安全決策與 Session 審計軌跡 (17_Access Control 4.5)
              </h3>
              <p style={{ fontSize: '0.85rem', color: '#74593f', marginTop: '2px' }}>
                所有登入已自動遮罩敏感資訊（IP、密碼雜湊與金鑰），紀錄保存兩年以供合規查核。
              </p>
            </div>
            <span style={{ fontSize: '0.85rem', backgroundColor: '#dcfce7', color: '#166534', padding: '4px 12px', borderRadius: '9999px', fontWeight: 700 }}>
              🟢 審計日誌保護中 (不可變)
            </span>
          </div>

          <table className="account-data-table">
            <thead>
              <tr>
                <th>審計編號</th>
                <th>事件時間</th>
                <th>操作人員</th>
                <th>安全動作 (Action)</th>
                <th>目標資源 (Target)</th>
                <th>來源 IP</th>
                <th>執行結果</th>
                <th>安全說明與備註</th>
              </tr>
            </thead>
            <tbody>
              {auditLogs.map(log => (
                <tr key={log.id}>
                  <td style={{ fontWeight: 700 }}>{log.id}</td>
                  <td style={{ fontSize: '0.82rem', color: '#888' }}>{log.occurredAt}</td>
                  <td style={{ fontWeight: 700 }}>👤 {log.actor}</td>
                  <td>
                    <span style={{
                      backgroundColor: '#fff8f6',
                      border: '1px solid #fed9b8',
                      padding: '2px 8px',
                      borderRadius: '6px',
                      fontWeight: 700,
                      fontSize: '0.82rem',
                      color: '#c2410c'
                    }}>
                      {log.action}
                    </span>
                  </td>
                  <td style={{ fontFamily: 'monospace', fontSize: '0.82rem' }}>{log.targetResource}</td>
                  <td style={{ fontFamily: 'monospace', fontSize: '0.82rem', color: '#888' }}>{log.maskedIp}</td>
                  <td>
                    <span style={{
                      padding: '2px 8px',
                      borderRadius: '4px',
                      fontSize: '0.78rem',
                      fontWeight: 700,
                      backgroundColor: log.outcome === 'SUCCESS' ? '#dcfce7' : '#fee2e2',
                      color: log.outcome === 'SUCCESS' ? '#166534' : '#991b1b'
                    }}>
                      {log.outcome}
                    </span>
                  </td>
                  <td style={{ fontSize: '0.85rem', color: '#57423b' }}>{log.reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Add User Drawer */}
      <Drawer
        isOpen={isAddUserOpen}
        onClose={() => setIsAddUserOpen(false)}
        title="➕ 新增內部工作人員帳號"
        footer={
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px', width: '100%' }}>
            <button
              style={{ padding: '8px 16px', border: '1px solid #dec0b6', borderRadius: '8px', background: '#fff', cursor: 'pointer' }}
              onClick={() => setIsAddUserOpen(false)}
            >
              取消
            </button>
            <button
              style={{ padding: '8px 20px', backgroundColor: '#ff7f50', color: '#fff', border: 'none', borderRadius: '8px', fontWeight: 700, cursor: 'pointer' }}
              onClick={handleCreateUser}
            >
              確認建立帳號
            </button>
          </div>
        }
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <div>
            <label style={{ display: 'block', fontWeight: 600, marginBottom: '6px', color: '#57423b' }}>登入帳號 (Username)：</label>
            <input
              type="text"
              value={newUsername}
              onChange={(e) => setNewUsername(e.target.value)}
              placeholder="例如: wang_assistant"
              style={{ width: '100%', padding: '10px 14px', borderRadius: '8px', border: '1px solid #dec0b6' }}
            />
          </div>

          <div>
            <label style={{ display: 'block', fontWeight: 600, marginBottom: '6px', color: '#57423b' }}>真實姓名：</label>
            <input
              type="text"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="例如: 王小芬"
              style={{ width: '100%', padding: '10px 14px', borderRadius: '8px', border: '1px solid #dec0b6' }}
            />
          </div>

          <div>
            <label style={{ display: 'block', fontWeight: 600, marginBottom: '6px', color: '#57423b' }}>電子郵件 (Email)：</label>
            <input
              type="email"
              value={newEmail}
              onChange={(e) => setNewEmail(e.target.value)}
              placeholder="例如: xiaofen.wang@postpartum-union.org.tw"
              style={{ width: '100%', padding: '10px 14px', borderRadius: '8px', border: '1px solid #dec0b6' }}
            />
          </div>
        </div>
      </Drawer>

      {/* TOTP Setup & Verification Drawer */}
      <Drawer
        isOpen={totpSetupUser !== null}
        onClose={() => setTotpSetupUser(null)}
        title={`📱 TOTP 雙因子綁定精靈 ── ${totpSetupUser?.name}`}
        footer={
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px', width: '100%' }}>
            <button
              style={{ padding: '8px 16px', border: '1px solid #dec0b6', borderRadius: '8px', background: '#fff', cursor: 'pointer' }}
              onClick={() => setTotpSetupUser(null)}
            >
              取消
            </button>
            <button
              style={{ padding: '8px 20px', backgroundColor: '#16a34a', color: '#fff', border: 'none', borderRadius: '8px', fontWeight: 700, cursor: 'pointer' }}
              onClick={handleVerifyAndEnableTotp}
            >
              驗證並啟用 2FA
            </button>
          </div>
        }
      >
        {totpSetupUser && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '20px', alignItems: 'center', textAlign: 'center' }}>
            <div style={{ fontSize: '0.9rem', color: '#57423b' }}>
              請開啟手機上的 <strong>Google Authenticator</strong> 或 <strong>Microsoft Authenticator</strong>，掃描下方 QR Code：
            </div>

            {/* Simulated Clean QR Code Box */}
            <div style={{
              width: '180px',
              height: '180px',
              backgroundColor: '#ffffff',
              border: '2px solid #1e1b19',
              borderRadius: '16px',
              display: 'flex',
              flexDirection: 'column',
              justifyContent: 'center',
              alignItems: 'center',
              boxShadow: '0 4px 12px rgba(0,0,0,0.1)'
            }}>
              <div style={{ fontSize: '3.5rem' }}>🏁</div>
              <div style={{ fontSize: '0.75rem', fontWeight: 700, marginTop: '4px' }}>TOTP QR CODE</div>
            </div>

            <div style={{ backgroundColor: '#fff8f6', border: '1px solid #fed9b8', borderRadius: '8px', padding: '8px 16px', fontSize: '0.8rem', fontFamily: 'monospace', color: '#c2410c' }}>
              密鑰字串: JBSWY3DPEHPK3PXP
            </div>

            <div style={{ width: '100%', textAlign: 'left', marginTop: '10px' }}>
              <label style={{ display: 'block', fontWeight: 700, marginBottom: '6px', color: '#1e1b19' }}>
                輸入 Authenticator 顯示的 6 位數驗證碼：
              </label>
              <input
                type="text"
                maxLength={6}
                value={totpVerifyCode}
                onChange={(e) => setTotpVerifyCode(e.target.value.replace(/\D/g, ''))}
                placeholder="例如: 123456"
                style={{ width: '100%', padding: '12px', borderRadius: '8px', border: '2px solid #ff7f50', fontSize: '1.2rem', textAlign: 'center', letterSpacing: '4px', fontWeight: 700 }}
              />
            </div>
          </div>
        )}
      </Drawer>

      {/* TAB 4: Background Jobs Monitor */}
      {activeTab === 'jobs' && (
        <div style={{ backgroundColor: '#fff', border: '1px solid #dec0b6', borderRadius: '12px', padding: '24px', boxShadow: '0 4px 12px rgba(0,0,0,0.02)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
            <div>
              <h3 style={{ fontSize: '1.2rem', fontWeight: 700, color: '#1e1b19', marginBottom: '4px' }}>⚙️ 背景排程與系統狀態看板 (jobs.py)</h3>
              <p style={{ fontSize: '0.85rem', color: '#57423b' }}>維運專用：監控系統背景排程、資料庫連線池與系統資源狀態。</p>
            </div>
            <button 
              style={{
                padding: '8px 16px',
                backgroundColor: '#f1f5f9',
                color: '#334155',
                border: '1px solid #cbd5e1',
                borderRadius: '8px',
                fontWeight: 700,
                cursor: 'pointer'
              }}
              onClick={() => alert('已刷新系統狀態')}
            >
              🔄 重新整理
            </button>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '16px', marginBottom: '24px' }}>
            <div style={{ backgroundColor: '#f8fafc', padding: '16px', borderRadius: '8px', border: '1px solid #e2e8f0' }}>
              <div style={{ fontSize: '0.85rem', color: '#64748b', fontWeight: 600 }}>LINE 推播排程佇列</div>
              <div style={{ fontSize: '1.5rem', fontWeight: 700, color: '#0f172a', marginTop: '8px' }}>0 筆</div>
              <div style={{ fontSize: '0.75rem', color: '#10b981', marginTop: '4px' }}>● 執行中 (Healthy)</div>
            </div>
            <div style={{ backgroundColor: '#f8fafc', padding: '16px', borderRadius: '8px', border: '1px solid #e2e8f0' }}>
              <div style={{ fontSize: '0.85rem', color: '#64748b', fontWeight: 600 }}>逾期未處理警報 (Anomalies)</div>
              <div style={{ fontSize: '1.5rem', fontWeight: 700, color: '#b91c1c', marginTop: '8px' }}>2 筆</div>
              <div style={{ fontSize: '0.75rem', color: '#ef4444', marginTop: '4px' }}>● 需人工介入</div>
            </div>
            <div style={{ backgroundColor: '#f8fafc', padding: '16px', borderRadius: '8px', border: '1px solid #e2e8f0' }}>
              <div style={{ fontSize: '0.85rem', color: '#64748b', fontWeight: 600 }}>資料庫連線狀態</div>
              <div style={{ fontSize: '1.5rem', fontWeight: 700, color: '#0f172a', marginTop: '8px' }}>12 / 100</div>
              <div style={{ fontSize: '0.75rem', color: '#10b981', marginTop: '4px' }}>● 連線正常 (12ms)</div>
            </div>
          </div>
        </div>
      )}

    </div>
  );
};

export default AccountManagementPage;
