/**
 * File: App.tsx
 * Description: 應用程式根元件，實作 URL Hash 路由、認證守衛與單一 LINE canonical 工作區。
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
import { OrderTrackerPage } from './pages/OrderTrackerPage';
import { OrdersPage } from './pages/OrdersPage';
import { SchedulingPage } from './pages/SchedulingPage';
import { StaffPage } from './pages/StaffPage';
import { DataImportPage } from './pages/DataImportPage';
import { LineManagementPage } from './pages/LineManagementPage';
import { ReportsPage } from './pages/ReportsPage';
import { FinancePage } from './pages/FinancePage';
import { AnomaliesPage } from './pages/AnomaliesPage';
import { DataBrowserPage } from './pages/DataBrowserPage';
import { AccountManagementPage } from './pages/AccountManagementPage';
import { SystemStatusPage } from './pages/SystemStatusPage';
import './pages/LineManagementPage.css';

const HASH_ALIASES: Record<string, PageType> = {
  line: 'line-management',
  'line-management': 'line-management',
  'line-ai': 'line-management',
  'line-ai-events': 'line-management',
  'line-studio': 'line-management',
  'line-liff-studio': 'line-management',
  'line-security': 'line-management',
};

function getPageFromHash(): PageType {
  const hash = window.location.hash.replace(/^#\/?/, '');
  if (hash in HASH_ALIASES) {
    return HASH_ALIASES[hash];
  }
  if (hash in PAGE_SECTION_MAP) {
    return hash as PageType;
  }
  return 'order-tracker';
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
        {currentPage === 'data-import' && <DataImportPage />}
        {currentPage === 'reports' && <ReportsPage />}

        {/* LINE Hub Section */}
        {currentPage === 'line-management' && <LineManagementPage />}

        {/* Finance Section */}
        {currentPage === 'finance' && <FinancePage />}

        {/* Audit & System Section */}
        {currentPage === 'anomalies' && <AnomaliesPage />}
        {currentPage === 'data-browser' && <DataBrowserPage />}
        {currentPage === 'account-management' && <AccountManagementPage />}
        {currentPage === 'system-status' && <SystemStatusPage />}
      </MasterLayout>
    </ErrorBoundary>
  );
};

export default App;
