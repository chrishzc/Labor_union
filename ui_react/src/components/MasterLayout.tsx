/**
 * File: MasterLayout.tsx
 * Description: 系統主版面容器元件，以 typed 效能快照、會話主體與 canonical 導航呈現管理端狀態。
 */
import React, { useEffect, useRef, useState } from 'react';
import {
  Bell,
  Bot,
  CalendarDays,
  CircleDollarSign,
  ClipboardList,
  Database,
  FileBarChart,
  HardDrive,
  HeartHandshake,
  History,
  KeyRound,
  LayoutDashboard,
  LogOut,
  Menu,
  MessageCircle,
  PanelTop,
  ShieldAlert,
  ShieldCheck,
  UserRound,
  UsersRound,
  X,
  type LucideIcon,
} from 'lucide-react';
import './MasterLayout.css';
import {
  fetchPerformanceSnapshot,
  type PerformanceSnapshot,
} from '../api/system/system_status_client';
import { sessionClient } from '../api/auth/session_client';

export type SectionType = 'operations' | 'line' | 'finance' | 'audit';
export type PageType = 
  | 'order-workbench-v2'
  | 'scheduling'
  | 'staff'
  | 'clients'
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
  | 'account-management'
  | 'storage-management';

export const PAGE_SECTION_MAP: Record<PageType, SectionType> = {
  'order-workbench-v2': 'operations',
  'scheduling': 'operations',
  'staff': 'operations',
  'clients': 'operations',
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
  'account-management': 'audit',
  'storage-management': 'audit',
};

export interface NavItem {
  id: PageType;
  icon: LucideIcon;
  label: string;
  section: SectionType;
}

export const NAV_ITEMS: NavItem[] = [
  // Operations Section
  { id: 'order-workbench-v2', icon: LayoutDashboard, label: '待辦看板', section: 'operations' },
  { id: 'scheduling', icon: CalendarDays, label: '排班日曆', section: 'operations' },
  { id: 'staff', icon: UsersRound, label: '月嫂名冊', section: 'operations' },
  { id: 'clients', icon: HeartHandshake, label: '客戶名冊', section: 'operations' },
  { id: 'data-import', icon: Database, label: '資料中心', section: 'operations' },
  { id: 'reports', icon: FileBarChart, label: '營運報表', section: 'operations' },

  // LINE Section
  { id: 'line-management', icon: ClipboardList, label: '客服與營運', section: 'line' },
  { id: 'line-ai-events', icon: Bot, label: 'AI 客服工作室', section: 'line' },
  { id: 'line-llm-settings', icon: KeyRound, label: 'AI 模型設定', section: 'line' },
  { id: 'line-liff-studio', icon: PanelTop, label: 'LIFF 資產工作室', section: 'line' },
  { id: 'line-security', icon: ShieldCheck, label: '群組與安全', section: 'line' },

  // Finance Section
  { id: 'finance', icon: CircleDollarSign, label: '帳務中心', section: 'finance' },
  { id: 'historical-service-accounting', icon: History, label: '歷史服務天數', section: 'finance' },

  // Audit & System Section
  { id: 'anomalies', icon: ShieldAlert, label: '異常審核', section: 'audit' },
  { id: 'account-management', icon: UserRound, label: '帳號權限', section: 'audit' },
  { id: 'storage-management', icon: HardDrive, label: '儲存空間管理', section: 'audit' },
];

const SECTION_LABELS: Record<SectionType, string> = {
  operations: '營運作業',
  line: 'LINE 專區',
  finance: '帳務作業',
  audit: '稽核與系統',
};

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
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const logoutCancelRef = useRef<HTMLButtonElement | null>(null);
  const logoutTriggerRef = useRef<HTMLButtonElement | null>(null);

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

  useEffect(() => {
    if (!showLogoutModal) return undefined;
    logoutCancelRef.current?.focus();
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return;
      setShowLogoutModal(false);
      logoutTriggerRef.current?.focus();
    };
    document.body.classList.add('modal-open');
    window.addEventListener('keydown', handleEscape);
    return () => {
      document.body.classList.remove('modal-open');
      window.removeEventListener('keydown', handleEscape);
    };
  }, [showLogoutModal]);

  const visibleNavItems = NAV_ITEMS.filter((item) => item.section === currentSection);
  const sidebarCurrentPage = currentPage;
  const currentUser = sessionClient.getUser();

  const handleSectionClick = (section: SectionType) => {
    setIsSidebarOpen(false);
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
        <button
          type="button"
          className="mobile-menu-toggle"
          aria-label={isSidebarOpen ? '關閉功能選單' : '開啟功能選單'}
          aria-controls="application-sidebar"
          aria-expanded={isSidebarOpen}
          onClick={() => setIsSidebarOpen((value) => !value)}
        >
          {isSidebarOpen ? <X aria-hidden="true" /> : <Menu aria-hidden="true" />}
        </button>
        <button type="button" className="brand-section" onClick={() => handleSectionClick('operations')}>
          <HeartHandshake className="brand-logo" aria-hidden="true" />
          <span>月子工會管理系統</span>
        </button>

        {/* Primary 4 Section Tabs */}
        <nav className="primary-section-tabs" aria-label="主要工作區">
          <button
            className={`section-tab-btn ${currentSection === 'operations' ? 'active' : ''}`}
            onClick={() => handleSectionClick('operations')}
          >
            營運作業
          </button>
          <button
            className={`section-tab-btn ${currentSection === 'line' ? 'active' : ''}`}
            onClick={() => handleSectionClick('line')}
          >
            <MessageCircle size={17} aria-hidden="true" /> LINE 專區
          </button>
          <button
            className={`section-tab-btn ${currentSection === 'finance' ? 'active' : ''}`}
            onClick={() => handleSectionClick('finance')}
          >
            帳務作業
          </button>
          <button
            className={`section-tab-btn ${currentSection === 'audit' ? 'active' : ''}`}
            onClick={() => handleSectionClick('audit')}
          >
            稽核與系統
          </button>
        </nav>

        <label className="mobile-section-picker">
          <span className="sr-only">選擇主要工作區</span>
          <select
            value={currentSection}
            onChange={(event) => handleSectionClick(event.target.value as SectionType)}
          >
            {(Object.keys(SECTION_LABELS) as SectionType[]).map((section) => (
              <option key={section} value={section}>{SECTION_LABELS[section]}</option>
            ))}
          </select>
        </label>

        {/* Top Navbar Right Controls */}
        <div className="top-navbar-right">
          <div
            className="system-status-indicator"
            data-testid="system-status-indicator"
            title={systemOnline === null ? '正在查詢後端 API 狀態' : systemOnline ? `後端 API 運作正常 (${latencyText})` : '後端 API 離線或無法連線'}
          >
            <span
              className={`status-dot ${systemOnline === null ? 'pending' : systemOnline ? (isDegraded ? 'degraded' : 'online') : 'offline'}`}
            />
            <span className="system-status-label">{systemOnline === null ? '查詢中' : systemOnline ? '系統在線' : '系統離線'}</span>
            <span className="sr-only">{systemOnline ? `，目前延遲 ${latencyText}` : ''}</span>
          </div>

          <button
            className="notification-btn"
            aria-label="查看待處理異常"
            onClick={() => {
              onSelectSection('audit');
              onSelectPage('anomalies');
            }}
          >
            <Bell aria-hidden="true" />
          </button>

          <details className="user-profile-menu">
            <summary className="user-profile-capsule">
              <UserRound size={17} aria-hidden="true" />
              <span className="user-profile-name">
                {currentUser?.display_name || currentUser?.username || '已登入使用者'}
              </span>
            </summary>
            <div className="user-profile-popover">
            <button
              ref={logoutTriggerRef}
              type="button"
              className="logout-action-btn"
              onClick={() => setShowLogoutModal(true)}
            >
              <LogOut size={17} aria-hidden="true" /> 登出
            </button>
            </div>
          </details>
        </div>
      </header>

      {/* App Body: Slim Sidebar + Main Content */}
      <div className="app-body">
        <aside
          id="application-sidebar"
          className={`slim-sidebar ${isSidebarOpen ? 'open' : ''}`}
          aria-label={`${SECTION_LABELS[currentSection]}功能`}
        >
          {visibleNavItems.map((item) => (
            (() => {
              const Icon = item.icon;
              return (
            <button
              key={item.id}
              className={`sidebar-nav-item ${sidebarCurrentPage === item.id ? 'active' : ''}`}
              onClick={() => {
                setIsSidebarOpen(false);
                onSelectPage(item.id);
              }}
              aria-current={sidebarCurrentPage === item.id ? 'page' : undefined}
              title={item.label}
            >
              <Icon className="sidebar-nav-icon" aria-hidden="true" />
              <span className="sidebar-nav-label">{item.label}</span>
            </button>
              );
            })()
          ))}
        </aside>

        {isSidebarOpen && (
          <button
            type="button"
            className="sidebar-backdrop"
            aria-label="關閉功能選單"
            onClick={() => setIsSidebarOpen(false)}
          />
        )}

        <main className="main-workspace">{children}</main>
      </div>

      {/* Stitch Nurture Core Logout Confirmation Modal */}
      {showLogoutModal && (
        <div
          className="logout-modal-backdrop"
          onClick={(e) => {
            if (e.target === e.currentTarget) setShowLogoutModal(false);
          }}
        >
          <div
            className="logout-modal-card"
            role="dialog"
            aria-modal="true"
            aria-labelledby="logout-dialog-title"
          >
            <div className="logout-modal-icon"><LogOut aria-hidden="true" /></div>
            <h2 id="logout-dialog-title" className="logout-modal-title">確定要登出系統嗎？</h2>
            <p className="logout-modal-desc">
              登出後將清除當前工作會話，下次進入需重新進行雙重身分驗證。
            </p>
            <div className="logout-modal-actions">
              <button
                ref={logoutCancelRef}
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
