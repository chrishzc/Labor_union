/**
 * File: App.tsx
 * Description: 應用程式根元件，實作含 bounded query 的 Hash 路由、認證守衛與頁面切換。
 */
import React, { useEffect, useRef, useState } from 'react';
import { UnsavedChangesProvider, useUnsavedNavigation } from './components/UnsavedChanges';
import './styles/design-tokens.css';
import {
  MasterLayout,
  PAGE_SECTION_MAP,
  NAV_ITEMS,
  type SectionType,
  type PageType,
} from './components/MasterLayout';
import { ErrorBoundary } from './components/ErrorBoundary';
import { StaffIdentityProvider } from './components/StaffIdentityProvider';
import { LoginPage } from './pages/LoginPage';
import { sessionClient } from './api/auth/session_client';
import { ADMIN_SESSION_UNAUTHORIZED_EVENT } from './api/shared/transport';
import { OrderWorkbenchV2Page } from './pages/OrderWorkbenchV2Page';
import { SchedulingPage } from './pages/SchedulingPage';
import { StaffPage } from './pages/StaffPage';
import { DataImportPage } from './pages/DataImportPage';
import { ClientRegistryPage } from './pages/ClientRegistryPage';
import { LineManagementPage } from './pages/LineManagementPage';
import { AiCustomerServiceStudioPage } from './pages/line_management/AiCustomerServiceStudioPage';
import { LlmConfigurationPage } from './pages/line_management/LlmConfigurationPage';
import { LiffCardStudio } from './pages/line_management/LiffCardStudio';
import { AlertGroupSecurity } from './pages/line_management/AlertGroupSecurity';
import { ReportsPage } from './pages/ReportsPage';
import { FinancePage } from './pages/FinancePage';
import { HistoricalServiceAccountingPage } from './pages/HistoricalServiceAccountingPage';
import { AccountManagementPage } from './pages/AccountManagementPage';
import { StorageManagementPage } from './pages/StorageManagementPage';
import { FileSettingsPage } from './pages/FileSettingsPage';
import './pages/LineManagementPage.css';

export const HASH_ALIASES: Record<string, PageType> = {
  databrowser: 'clients',
  'data-browser': 'clients',
  'client-roster': 'clients',
  line: 'line-management',
  'line-management': 'line-management',
  'line-ai': 'line-ai-events',
  'line-ai-events': 'line-ai-events',
  'line-llm': 'line-llm-settings',
  'line-llm-settings': 'line-llm-settings',
  'line-studio': 'line-liff-studio',
  'line-liff-studio': 'line-liff-studio',
  'line-security': 'line-security',
  'order-beta': 'order-workbench-v2',
};

function getPageFromHash(): PageType {
  const hashPath = window.location.hash.replace(/^#\/?/, '').split('?', 1)[0];
  if (hashPath in HASH_ALIASES) {
    return HASH_ALIASES[hashPath];
  }
  if (hashPath in PAGE_SECTION_MAP) {
    return hashPath as PageType;
  }
  return 'order-workbench-v2';
}

const AppContent: React.FC = () => {
  const { requestLeave } = useUnsavedNavigation();
  const committedHash = useRef(window.location.hash);
  const [isLoggedIn, setIsLoggedIn] = useState<boolean>(() => sessionClient.isAuthenticated());
  const [currentPage, setCurrentPage] = useState<PageType>(() => getPageFromHash());
  const [workbenchHomeRequest, setWorkbenchHomeRequest] = useState(0);

  // 永遠自當前頁面確定性派生所屬分區，杜絕 HMR 快取或非同步狀態脫鉤
  const currentSection: SectionType = PAGE_SECTION_MAP[currentPage] || 'operations';

  useEffect(() => {
    const handleHashChange = (event: HashChangeEvent) => {
      const nextHash = window.location.hash;
      if (nextHash === committedHash.current) return;
      const previousHash = event.oldURL ? new URL(event.oldURL).hash : committedHash.current;
      const page = getPageFromHash();
      window.history.replaceState(null, '', previousHash || '#order-workbench-v2');
      requestLeave(() => {
        committedHash.current = nextHash;
        window.history.replaceState(null, '', nextHash);
        setCurrentPage(page);
        window.dispatchEvent(new HashChangeEvent('hashchange'));
      });
    };

    window.addEventListener('hashchange', handleHashChange, true);
    return () => {
      window.removeEventListener('hashchange', handleHashChange, true);
    };
  }, [requestLeave]);

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
    if (page === 'order-workbench-v2' && currentPage === page) {
      setWorkbenchHomeRequest(value => value + 1);
      return;
    }
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
    committedHash.current = `#${targetPage}`;
    setCurrentPage(targetPage);
    window.location.hash = `#${targetPage}`;
  };

  const handleLogout = () => {
    requestLeave(() => {
      void sessionClient.logout().finally(() => {
        setIsLoggedIn(false);
        committedHash.current = '#login';
        window.location.hash = '#login';
      });
    });
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
        <StaffIdentityProvider key={currentPage} enabled={['order-workbench-v2', 'clients', 'finance', 'historical-service-accounting', 'line-management'].includes(currentPage)}>
        {/* Operations Section */}
        {currentPage === 'order-workbench-v2' && <OrderWorkbenchV2Page homeNavigationRequest={workbenchHomeRequest} />}
        {currentPage === 'scheduling' && <SchedulingPage />}
        {currentPage === 'staff' && <StaffPage />}
        {currentPage === 'clients' && <ClientRegistryPage />}
        {currentPage === 'data-import' && <DataImportPage />}
        {currentPage === 'reports' && <ReportsPage />}

        {/* LINE Hub Section */}
        {currentPage === 'line-management' && <LineManagementPage />}
        {currentPage === 'line-ai-events' && <AiCustomerServiceStudioPage />}
        {currentPage === 'line-llm-settings' && <LlmConfigurationPage />}
        {currentPage === 'line-liff-studio' && <LiffCardStudio />}
        {currentPage === 'line-security' && <AlertGroupSecurity />}

        {/* Finance Section */}
        {currentPage === 'finance' && <FinancePage />}
        {currentPage === 'historical-service-accounting' && <HistoricalServiceAccountingPage />}

        {/* Audit & System Section */}
        {currentPage === 'account-management' && <AccountManagementPage />}
        {currentPage === 'storage-management' && <StorageManagementPage />}
        {currentPage === 'file-settings' && <FileSettingsPage />}
        </StaffIdentityProvider>
      </MasterLayout>
    </ErrorBoundary>
  );
};

export const App: React.FC = () => <UnsavedChangesProvider><AppContent /></UnsavedChangesProvider>;

export default App;
