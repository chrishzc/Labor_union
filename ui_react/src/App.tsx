/**
 * File: App.tsx
 * Description: 應用程式根元件，實作 URL Hash 路由同步、認證守衛與 ErrorBoundary 容錯防護。
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
import { AiEventStudio } from './pages/line_management/AiEventStudio';
import { LiffCardStudio } from './pages/line_management/LiffCardStudio';
import { AlertGroupSecurity } from './pages/line_management/AlertGroupSecurity';
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
  'line-ai': 'line-ai-events',
  'line-ai-events': 'line-ai-events',
  'line-studio': 'line-liff-studio',
  'line-liff-studio': 'line-liff-studio',
  'line-security': 'line-security',
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
        {currentPage === 'line-ai-events' && (
          <div className="line-page-wrapper">
            <div className="page-header-banner line-page-header">
              <div>
                <h1 className="page-title">🤖 LINE AI 客服事件與意圖規則管理</h1>
                <p className="page-subtitle">可視化管理 Tag 語意錨點標籤、官方核定回覆範本與 Live 實時對話模擬器。</p>
              </div>
            </div>
            <AiEventStudio />
          </div>
        )}
        {currentPage === 'line-liff-studio' && (
          <div className="line-page-wrapper">
            <div className="page-header-banner line-page-header">
              <div>
                <h1 className="page-title">🪟 LIFF 8大表單與 Flex 卡片 Live 預覽中心</h1>
                <p className="page-subtitle">8 大受保護 LIFF 表單 ＋ 4 大 Flex 卡片高擬真手機模擬器與實機測試。</p>
              </div>
            </div>
            <LiffCardStudio />
          </div>
        )}
        {currentPage === 'line-security' && (
          <div className="line-page-wrapper">
            <div className="page-header-banner line-page-header">
              <div>
                <h1 className="page-title">🔒 幹部通知群組與系統安全配置</h1>
                <p className="page-subtitle">全系統唯一幹部異常通報群組狀態監控與最高權限管理員一鍵清空重設。</p>
              </div>
            </div>
            <AlertGroupSecurity />
          </div>
        )}

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
