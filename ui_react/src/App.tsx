/**
 * File: App.tsx
 * Description: 應用程式根元件，實作 Hash 路由、認證守衛、頁面切換與低頻頁面動態載入。
 */
import React, { Suspense, lazy, useEffect, useRef, useState } from 'react';
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
import { ClientRegistryPage } from './pages/ClientRegistryPage';
import { FinancePage } from './pages/FinancePage';
import './pages/LineManagementPage.css';

const DataImportPage = lazy(() =>
  import('./pages/DataImportPage').then((m) => ({ default: m.DataImportPage }))
);
const ReportsPage = lazy(() =>
  import('./pages/ReportsPage').then((m) => ({ default: m.ReportsPage }))
);
const LineManagementPage = lazy(() =>
  import('./pages/LineManagementPage').then((m) => ({ default: m.LineManagementPage }))
);
const AiCustomerServiceStudioPage = lazy(() =>
  import('./pages/line_management/AiCustomerServiceStudioPage').then((m) => ({
    default: m.AiCustomerServiceStudioPage,
  }))
);
const AccountingParametersPage = lazy(() =>
  import('./pages/AccountingParametersPage').then((m) => ({
    default: m.AccountingParametersPage,
  }))
);
const PaymentReminderSettingsPage = lazy(() =>
  import('./pages/PaymentReminderSettingsPage').then((m) => ({
    default: m.PaymentReminderSettingsPage,
  }))
);
const AccountManagementPage = lazy(() =>
  import('./pages/AccountManagementPage').then((m) => ({ default: m.AccountManagementPage }))
);
const ContractTemplatesPage = lazy(() =>
  import('./pages/ContractTemplatesPage').then((m) => ({ default: m.ContractTemplatesPage }))
);
const DatabaseBackupPage = lazy(() =>
  import('./pages/DatabaseBackupPage').then((m) => ({ default: m.DatabaseBackupPage }))
);
const NotificationTasksPage = lazy(() =>
  import('./pages/NotificationTasksPreviewPage').then((m) => ({
    default: m.NotificationTasksPage,
  }))
);

export const HASH_ALIASES: Record<string, PageType> = {
  databrowser: 'clients',
  'data-browser': 'clients',
  'client-roster': 'clients',
  line: 'line-management',
  'line-management': 'line-management',
  'line-ai': 'line-ai-events',
  'line-ai-events': 'line-ai-events',
  'line-llm': 'line-ai-events',
  'line-llm-settings': 'line-ai-events',
  'line-notifications': 'line-notifications',
  'line-interface': 'line-interface',
  'line-studio': 'line-interface',
  'line-liff-studio': 'line-interface',
  'order-beta': 'order-workbench-v2',
  'historical-service-accounting': 'clients',
};

/** 舊版 #line-management?tab= 深連結依分頁責任導向新頁面。 */
const LINE_TAB_PAGES: Record<string, PageType> = {
  push_queue: 'line-notifications',
  delivery: 'line-notifications',
  richmenu: 'line-interface',
  message_flow: 'line-interface',
  liff: 'line-interface',
};

function getPageFromHash(): PageType {
  const [hashPath, hashQuery = ''] = window.location.hash.replace(/^#\/?/, '').split('?', 2);
  if (hashPath === 'line-management' || hashPath === 'line') {
    const tabPage = LINE_TAB_PAGES[new URLSearchParams(hashQuery).get('tab') ?? ''];
    if (tabPage) return tabPage;
  }
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
        <ErrorBoundary key={currentPage}>
        <StaffIdentityProvider key={currentPage} enabled={['order-workbench-v2', 'clients', 'finance', 'payment-reminder-settings', 'line-management', 'line-notifications', 'line-interface'].includes(currentPage)}>
        <Suspense fallback={<div className="app-route-loading" role="status" aria-live="polite">載入頁面中…</div>}>
        {/* Operations Section */}
        {currentPage === 'notifications' && <NotificationTasksPage />}
        {currentPage === 'order-workbench-v2' && <OrderWorkbenchV2Page homeNavigationRequest={workbenchHomeRequest} />}
        {currentPage === 'scheduling' && <SchedulingPage />}
        {currentPage === 'staff' && <StaffPage />}
        {currentPage === 'clients' && <ClientRegistryPage />}
        {currentPage === 'data-import' && <DataImportPage />}
        {currentPage === 'reports' && <ReportsPage />}

        {/* LINE Hub Section */}
        {currentPage === 'line-management' && <LineManagementPage scope="service" />}
        {currentPage === 'line-notifications' && <LineManagementPage scope="notifications" />}
        {currentPage === 'line-interface' && <LineManagementPage scope="interface" />}
        {currentPage === 'line-ai-events' && <AiCustomerServiceStudioPage />}

        {/* Finance Section */}
        {currentPage === 'finance' && <FinancePage />}
        {currentPage === 'accounting-parameters' && <AccountingParametersPage />}
        {currentPage === 'payment-reminder-settings' && <PaymentReminderSettingsPage />}

        {/* Audit & System Section */}
        {currentPage === 'account-management' && <AccountManagementPage />}
        {currentPage === 'contract-templates' && <ContractTemplatesPage />}
        {currentPage === 'database-backup' && <DatabaseBackupPage />}
        </Suspense>
        </StaffIdentityProvider>
        </ErrorBoundary>
      </MasterLayout>
    </ErrorBoundary>
  );
};

export const App: React.FC = () => <UnsavedChangesProvider><AppContent /></UnsavedChangesProvider>;

export default App;
