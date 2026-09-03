/**
 * File: MasterLayout.tsx
 * Description: 系統主版面容器元件，以 typed 效能快照、會話主體與 canonical 導航呈現管理端狀態。
 */
import React, { useEffect, useState } from 'react';
import './MasterLayout.css';
import {
  fetchPerformanceSnapshot,
  type PerformanceSnapshot,
} from '../api/system/system_status_client';
import { sessionClient } from '../api/auth/session_client';

export type SectionType = 'operations' | 'line' | 'finance' | 'audit';
export type PageType = 
  | 'order-tracker'
  | 'orders'
  | 'scheduling'
  | 'staff'
  | 'data-import'
  | 'reports'
  | 'line-management'
  | 'line-ai-events'
  | 'line-llm-settings'
  | 'line-liff-studio'
  | 'line-security'
  | 'finance'
  | 'historical-service-accounting'
  | 'anomalies'
  | 'data-browser'
  | 'account-management'
  | 'system-status';

export const PAGE_SECTION_MAP: Record<PageType, SectionType> = {
  'order-tracker': 'operations',
  'orders': 'operations',
  'scheduling': 'operations',
  'staff': 'operations',
  'data-import': 'operations',
  'reports': 'operations',

  'line-management': 'line',
  'line-ai-events': 'line',
  'line-llm-settings': 'line',
  'line-liff-studio': 'line',
  'line-security': 'line',

  'finance': 'finance',
  'historical-service-accounting': 'finance',

  'anomalies': 'audit',
  'data-browser': 'operations',
  'account-management': 'audit',
  'system-status': 'audit',
};

export interface NavItem {
  id: PageType;
  icon: string;
  label: string;
  section: SectionType;
}

export const NAV_ITEMS: NavItem[] = [
  // Operations Section
  { id: 'order-tracker', icon: '📌', label: '待辦看板', section: 'operations' },
  { id: 'orders', icon: '📦', label: '訂單管理', section: 'operations' },
  { id: 'scheduling', icon: '📅', label: '排班日曆', section: 'operations' },
  { id: 'staff', icon: '👩‍🍼', label: '月嫂名冊', section: 'operations' },
  { id: 'data-import', icon: '🗄️', label: '資料中心', section: 'operations' },
  { id: 'reports', icon: '📊', label: '營運報表', section: 'operations' },

  // LINE Section
  { id: 'line-management', icon: '📋', label: '客服與選單', section: 'line' },
  { id: 'line-ai-events', icon: '🤖', label: 'AI 事件工作室', section: 'line' },
  { id: 'line-llm-settings', icon: '🔑', label: 'AI 模型設定', section: 'line' },
  { id: 'line-liff-studio', icon: '🪟', label: 'LIFF 卡片工作室', section: 'line' },
  { id: 'line-security', icon: '🔒', label: '群組與安全', section: 'line' },

  // Finance Section
  { id: 'finance', icon: '💰', label: '帳務中心', section: 'finance' },
  { id: 'historical-service-accounting', icon: '🧮', label: '歷史服務天數', section: 'finance' },

  // Audit & System Section
  { id: 'anomalies', icon: '⚠️', label: '異常審核', section: 'audit' },
  { id: 'account-management', icon: '👤', label: '帳號權限', section: 'audit' },
  { id: 'system-status', icon: '🩺', label: '系統狀態', section: 'audit' },
];

export interface MasterLayoutProps {
  currentSection: SectionType;
  currentPage: PageType;
  onSelectSection: (section: SectionType) => void;
  onSelectPage: (page: PageType) => void;
  onLogout: () => void;
  children?: React.ReactNode;
}

export const MasterLayout: React.FC<MasterLayoutProps> = ({
  currentSection,
  currentPage,
  onSelectSection,
  onSelectPage,
  onLogout,
  children,
}) => {
  const [systemOnline, setSystemOnline] = useState<boolean | null>(null);
  const [latencyText, setLatencyText] = useState<string>('查詢中');
  const [isDegraded, setIsDegraded] = useState<boolean>(false);
  const [showLogoutModal, setShowLogoutModal] = useState<boolean>(false);
  const shellOwnsSystemStatusQuery = currentPage !== 'system-status';

  useEffect(() => {
    if (!shellOwnsSystemStatusQuery) return undefined;

    let isMounted = true;

    async function loadSystemStatus() {
      try {
        const snapshot: PerformanceSnapshot = await fetchPerformanceSnapshot({ timeoutMs: 4000 });
        if (!isMounted) return;

        setSystemOnline(true);
        const p95 = snapshot.p95_response_time_upper_bound_ms;
        const avg = snapshot.average_response_time_ms;

        if (p95 !== null && p95 >= 2000) {
          setIsDegraded(true);
          setLatencyText(`${p95}ms (延遲偏高)`);
        } else if (avg !== null) {
          setIsDegraded(false);
          setLatencyText(`${avg}ms`);
        } else if (p95 !== null) {
          setIsDegraded(false);
          setLatencyText(`${p95}ms`);
        } else {
          setIsDegraded(false);
          setLatencyText('在線');
        }
      } catch {
        if (!isMounted) return;
        setSystemOnline(false);
        setIsDegraded(false);
        setLatencyText('離線');
      }
    }

    loadSystemStatus();

    return () => {
      isMounted = false;
    };
  }, [shellOwnsSystemStatusQuery]);

  const visibleNavItems = NAV_ITEMS.filter((item) => item.section === currentSection);
  const sidebarCurrentPage = currentPage === 'data-browser' ? 'data-import' : currentPage;
  const currentUser = sessionClient.getUser();

  const handleSectionClick = (section: SectionType) => {
    onSelectSection(section);
    const firstPage = NAV_ITEMS.find((item) => item.section === section);
    if (firstPage) {
      onSelectPage(firstPage.id);
    }
  };

  return (
    <div className="app-shell">
      {/* Top Primary Navbar */}
      <header className="top-navbar">
        <div className="brand-section" onClick={() => handleSectionClick('operations')}>
          <span className="brand-logo">🤱</span>
          <span>月子工會管理系統</span>
        </div>

        {/* Primary 4 Section Tabs */}
        <nav className="primary-section-tabs">
          <button
            className={`section-tab-btn ${currentSection === 'operations' ? 'active' : ''}`}
            onClick={() => handleSectionClick('operations')}
          >
            營運作業 (Operations)
          </button>
          <button
            className={`section-tab-btn ${currentSection === 'line' ? 'active' : ''}`}
            onClick={() => handleSectionClick('line')}
          >
            💬 LINE 專區 (LINE Hub)
          </button>
          <button
            className={`section-tab-btn ${currentSection === 'finance' ? 'active' : ''}`}
            onClick={() => handleSectionClick('finance')}
          >
            帳務作業 (Finance)
          </button>
          <button
            className={`section-tab-btn ${currentSection === 'audit' ? 'active' : ''}`}
            onClick={() => handleSectionClick('audit')}
          >
            稽核與系統 (Audit & System)
          </button>
        </nav>

        {/* Top Navbar Right Controls */}
        <div className="top-navbar-right">
          <div
            className="system-status-indicator"
            data-testid="system-status-indicator"
            title={systemOnline === null ? '正在查詢後端 API 狀態' : systemOnline ? `後端 API 運作正常 (${latencyText})` : '後端 API 離線或無法連線'}
          >
            <span
              className={`status-dot ${systemOnline ? (isDegraded ? 'degraded' : 'online') : 'offline'}`}
              style={{
                backgroundColor: systemOnline === null || !systemOnline
                  ? '#9ca3af'
                  : isDegraded
                  ? '#ea580c'
                  : '#16a34a',
              }}
            />
            <span>{systemOnline === null ? '系統狀態查詢中' : systemOnline ? `系統在線 (${latencyText})` : '系統離線'}</span>
          </div>

          <button
            className="notification-btn"
            title="查看待處理異常"
            onClick={() => {
              onSelectSection('audit');
              onSelectPage('anomalies');
            }}
          >
            🔔
          </button>

          <div className="user-profile-capsule">
            <span className="user-profile-name">
              👤 {currentUser?.display_name || currentUser?.username || '已登入使用者'}
            </span>
            <button
              type="button"
              className="logout-action-btn"
              onClick={() => setShowLogoutModal(true)}
              title="點擊登出系統"
            >
              🚪 登出
            </button>
          </div>
        </div>
      </header>

      {/* App Body: Slim Sidebar + Main Content */}
      <div className="app-body">
        <aside className="slim-sidebar">
          {visibleNavItems.map((item) => (
            <button
              key={item.id}
              className={`sidebar-nav-item ${sidebarCurrentPage === item.id ? 'active' : ''}`}
              onClick={() => onSelectPage(item.id)}
              title={item.label}
            >
              <span className="sidebar-nav-icon">{item.icon}</span>
              <span className="sidebar-nav-label">{item.label}</span>
            </button>
          ))}
        </aside>

        <main className="main-workspace">{children}</main>
      </div>

      {/* Stitch Nurture Core Logout Confirmation Modal */}
      {showLogoutModal && (
        <div
          className="logout-modal-backdrop"
          onClick={(e) => {
            if (e.target === e.currentTarget) setShowLogoutModal(false);
          }}
          role="dialog"
          aria-modal="true"
          aria-labelledby="logout-dialog-title"
        >
          <div className="logout-modal-card">
            <div className="logout-modal-icon">🚪</div>
            <h2 id="logout-dialog-title" className="logout-modal-title">確定要登出系統嗎？</h2>
            <p className="logout-modal-desc">
              登出後將清除當前工作會話，下次進入需重新進行雙重身分驗證。
            </p>
            <div className="logout-modal-actions">
              <button
                type="button"
                className="logout-btn-cancel"
                onClick={() => setShowLogoutModal(false)}
              >
                取消
              </button>
              <button
                type="button"
                className="logout-btn-confirm"
                onClick={() => {
                  setShowLogoutModal(false);
                  onLogout();
                }}
              >
                確認登出
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default MasterLayout;
