/**
 * @file MasterLayout.tsx
 * @description 系統主版面容器元件，整合導航標籤、側邊欄、實時效能狀態指示器與登出機制。
 */
import React, { useEffect, useState } from 'react';
import './MasterLayout.css';
import {
  fetchPerformanceSnapshot,
  type PerformanceSnapshot,
} from '../api/system/system_status_client';

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
  | 'line-liff-studio'
  | 'line-security'
  | 'finance'
  | 'anomalies'
  | 'data-browser'
  | 'account-management';

export const PAGE_SECTION_MAP: Record<PageType, SectionType> = {
  'order-tracker': 'operations',
  'orders': 'operations',
  'scheduling': 'operations',
  'staff': 'operations',
  'data-import': 'operations',
  'reports': 'operations',

  'line-management': 'line',
  'line-ai-events': 'line',
  'line-liff-studio': 'line',
  'line-security': 'line',

  'finance': 'finance',

  'anomalies': 'audit',
  'data-browser': 'audit',
  'account-management': 'audit',
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
  { id: 'data-import', icon: '📥', label: '資料匯入', section: 'operations' },
  { id: 'reports', icon: '📊', label: '營運報表', section: 'operations' },

  // LINE Section
  { id: 'line-management', icon: '📋', label: '客服與選單', section: 'line' },
  { id: 'line-ai-events', icon: '🤖', label: 'AI事件管理', section: 'line' },
  { id: 'line-liff-studio', icon: '🪟', label: 'LIFF與卡片', section: 'line' },
  { id: 'line-security', icon: '🔒', label: '群組與安全', section: 'line' },

  // Finance Section
  { id: 'finance', icon: '💰', label: '帳務中心', section: 'finance' },

  // Audit & System Section
  { id: 'anomalies', icon: '⚠️', label: '異常審核', section: 'audit' },
  { id: 'data-browser', icon: '🔍', label: '數據瀏覽', section: 'audit' },
  { id: 'account-management', icon: '👤', label: '帳號權限', section: 'audit' },
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
  const [systemOnline, setSystemOnline] = useState<boolean>(true);
  const [latencyText, setLatencyText] = useState<string>('在線');
  const [isDegraded, setIsDegraded] = useState<boolean>(false);

  useEffect(() => {
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
  }, []);

  const visibleNavItems = NAV_ITEMS.filter((item) => item.section === currentSection);

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
            title={systemOnline ? `後端 API 運作正常 (${latencyText})` : '後端 API 離線或無法連線'}
          >
            <span
              className={`status-dot ${systemOnline ? (isDegraded ? 'degraded' : 'online') : 'offline'}`}
              style={{
                backgroundColor: !systemOnline
                  ? '#9ca3af'
                  : isDegraded
                  ? '#ea580c'
                  : '#16a34a',
              }}
            />
            <span>{systemOnline ? `系統在線 (${latencyText})` : '系統離線'}</span>
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
            <span className="notification-badge">3</span>
          </button>

          <button className="user-profile-btn" onClick={onLogout} title="點擊登出系統">
            <span>👤 管理員</span>
            <span style={{ fontSize: '0.75rem', color: '#999' }}>🚪 登出</span>
          </button>
        </div>
      </header>

      {/* App Body: Slim Sidebar + Main Content */}
      <div className="app-body">
        <aside className="slim-sidebar">
          {visibleNavItems.map((item) => (
            <button
              key={item.id}
              className={`sidebar-nav-item ${currentPage === item.id ? 'active' : ''}`}
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
    </div>
  );
};

export default MasterLayout;
