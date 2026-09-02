/**
 * File: App.tsx
 * Description: 應用程式根元件，實作含 bounded query 的 Hash 路由、認證守衛與頁面切換。
 */
import React, { useEffect, useState } from 'react';
import './styles/design-tokens.css';
import {
  MasterLayout,
  PAGE_SECTION_MAP,
  NAV_ITEMS,
  type SectionType,
  type PageType,
} from './components/MasterLayout';
import { ErrorBoundary } from './components/ErrorBoundary';
import { LoginPage } from './pages/LoginPage';
import { sessionClient } from './api/auth/session_client';
import { ADMIN_SESSION_UNAUTHORIZED_EVENT } from './api/shared/transport';
import { OrderTrackerPage } from './pages/OrderTrackerPage';
import { OrdersPage } from './pages/OrdersPage';
import { SchedulingPage } from './pages/SchedulingPage';
import { StaffPage } from './pages/StaffPage';
import { DataImportPage } from './pages/DataImportPage';
import { LineManagementPage } from './pages/LineManagementPage';
import { AiEventStudio } from './pages/line_management/AiEventStudio';
import { LlmConfigurationPage } from './pages/line_management/LlmConfigurationPage';
import { LiffCardStudio } from './pages/line_management/LiffCardStudio';
import { AlertGroupSecurity } from './pages/line_management/AlertGroupSecurity';
import { ReportsPage } from './pages/ReportsPage';
import { FinancePage } from './pages/FinancePage';
import { CurrentAnomaliesPage } from './pages/CurrentAnomaliesPage';
import { AccountManagementPage } from './pages/AccountManagementPage';
import { SystemStatusPage } from './pages/SystemStatusPage';
import './pages/LineManagementPage.css';

export const HASH_ALIASES: Record<string, PageType> = {
  databrowser: 'data-browser',
  line: 'line-management',
  'line-management': 'line-management',
  'line-ai': 'line-ai-events',
  'line-ai-events': 'line-ai-events',
  'line-llm': 'line-llm-settings',
  'line-llm-settings': 'line-llm-settings',
  'line-studio': 'line-liff-studio',
  'line-liff-studio': 'line-liff-studio',
  'line-security': 'line-security',
};

function getPageFromHash(): PageType {
  const hashPath = window.location.hash.replace(/^#\/?/, '').split('?', 1)[0];
  if (hashPath in HASH_ALIASES) {
    return HASH_ALIASES[hashPath];
  }
  if (hashPath in PAGE_SECTION_MAP) {
    return hashPath as PageType;
  }
  return 'order-tracker';
}

export function getMobileAdminReturnPathFromHash(hash: string): string | null {
  const query = hash.includes('?') ? hash.slice(hash.indexOf('?') + 1) : '';
  const returnTarget = new URLSearchParams(query).get('return_target');
  return returnTarget === 'scheduling_review'
    ? '/line-mobile-admin?target=scheduling_review'
    : null;
}

export const App: React.FC = () => {
  const [isLoggedIn, setIsLoggedIn] = useState<boolean>(() => sessionClient.isAuthenticated());
  const [currentPage, setCurrentPage] = useState<PageType>(() => getPageFromHash());

  // 永遠自當前頁面確定性派生所屬分區，杜絕 HMR 快取或非同步狀態脫鉤
  const currentSection: SectionType = PAGE_SECTION_MAP[currentPage] || 'operations';

  useEffect(() => {
    const handleHashChange = () => {
      const page = getPageFromHash();
      setCurrentPage(page);
    };

    window.addEventListener('hashchange', handleHashChange);
    return () => {
      window.removeEventListener('hashchange', handleHashChange);
    };
  }, []);

  useEffect(() => {
    const handleSessionUnauthorized = (event: Event) => {
      const rejectedToken = event instanceof CustomEvent
        ? (event.detail as { rejectedToken?: unknown } | null)?.rejectedToken
        : null;
      if (typeof rejectedToken !== 'string' || rejectedToken !== sessionClient.getToken()) return;
      sessionClient.clearSession();
      setIsLoggedIn(false);
      window.location.hash = '#login';
    };

    window.addEventListener(ADMIN_SESSION_UNAUTHORIZED_EVENT, handleSessionUnauthorized);
    return () => window.removeEventListener(ADMIN_SESSION_UNAUTHORIZED_EVENT, handleSessionUnauthorized);
  }, []);

  const handleSelectPage = (page: PageType) => {
    setCurrentPage(page);
    window.location.hash = `#${page}`;
  };

  const handleSelectSection = (section: SectionType) => {
    // 切換頂部大分區時，自動跳轉至該分區的第一個子頁面
    const firstPage = NAV_ITEMS.find((item) => item.section === section);
    if (firstPage) {
      handleSelectPage(firstPage.id);
    }
  };

  const handleLoginSuccess = (_username: string) => {
    setIsLoggedIn(true);
    const mobileAdminReturnPath = getMobileAdminReturnPathFromHash(window.location.hash);
    if (mobileAdminReturnPath) {
      window.location.replace(mobileAdminReturnPath);
      return;
    }
    const targetPage = getPageFromHash();
    window.location.hash = `#${targetPage}`;
  };

  const handleLogout = async () => {
    await sessionClient.logout();
    setIsLoggedIn(false);
    window.location.hash = '#login';
  };

  if (!isLoggedIn) {
    return (
      <ErrorBoundary>
        <LoginPage onLoginSuccess={handleLoginSuccess} />
      </ErrorBoundary>
    );
  }

  return (
    <ErrorBoundary>
      <MasterLayout
        currentSection={currentSection}
        currentPage={currentPage}
        onSelectSection={handleSelectSection}
        onSelectPage={handleSelectPage}
        onLogout={handleLogout}
      >
        {/* Operations Section */}
        {currentPage === 'order-tracker' && <OrderTrackerPage />}
        {currentPage === 'orders' && <OrdersPage />}
        {currentPage === 'scheduling' && <SchedulingPage />}
        {currentPage === 'staff' && <StaffPage />}
        {currentPage === 'data-import' && <DataImportPage initialTab="workbook-import" />}
        {currentPage === 'reports' && <ReportsPage />}

        {/* LINE Hub Section */}
        {currentPage === 'line-management' && <LineManagementPage />}
        {currentPage === 'line-ai-events' && <AiEventStudio />}
        {currentPage === 'line-llm-settings' && <LlmConfigurationPage />}
        {currentPage === 'line-liff-studio' && <LiffCardStudio />}
        {currentPage === 'line-security' && <AlertGroupSecurity />}

        {/* Finance Section */}
        {currentPage === 'finance' && <FinancePage />}

        {/* Audit & System Section */}
        {currentPage === 'anomalies' && <CurrentAnomaliesPage />}
        {currentPage === 'data-browser' && <DataImportPage initialTab="data-browser" />}
        {currentPage === 'account-management' && <AccountManagementPage />}
        {currentPage === 'system-status' && <SystemStatusPage />}
      </MasterLayout>
    </ErrorBoundary>
  );
};

export default App;
