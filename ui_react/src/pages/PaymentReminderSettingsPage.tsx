/**
 * File: PaymentReminderSettingsPage.tsx
 * Description: 帳務通知設定專屬頁面，整合繳款提醒排程（通知條件）與帳務專用 LINE 訊息範本。
 */
import { ManagementPageHeader } from '../components/ManagementPageHeader';
import React, { useState } from 'react';
import { Bell, Clock, MessageSquareQuote } from 'lucide-react';
import { PaymentReminderSchedulePanel } from '../components/PaymentReminderSchedulePanel';
import { LineNotificationWorkbench } from '../components/LineNotificationWorkbench';
import { useUnsavedNavigation } from '../components/UnsavedChanges';
import './PaymentReminderSettingsPage.css';

type SettingView = 'reminder-schedule' | 'reminder-content';

function params(): URLSearchParams {
  const hash = window.location.hash;
  const queryString = hash.includes('?') ? hash.split('?')[1] : '';
  return new URLSearchParams(queryString);
}

export const PaymentReminderSettingsPage: React.FC = () => {
  const { requestLeave } = useUnsavedNavigation();
  const [view, setView] = useState<SettingView>(() => {
    const p = params();
    const v = p.get('view');
    return v === 'reminder-content' ? 'reminder-content' : 'reminder-schedule';
  });
  const [message, setMessage] = useState<string | null>(() => params().get('message') ?? 'deposit-reminder');
  const [search, setSearch] = useState('');

  function navigateView(next: SettingView) {
    requestLeave(() => {
      setView(next);
      const q = params();
      q.set('view', next);
      window.history.replaceState(null, '', '#payment-reminder-settings?' + q.toString());
    });
  }

  return (
    <div data-surface-id="finance.payment-reminder-settings.page">
      <ManagementPageHeader title="帳務通知設定" description="維護客戶各期繳款排程提醒條件、逾期補寄門檻與帳務 LINE 訊息範本。">
        <span className="reminder-badge"><Bell size={14} /> 帳務專區</span>
      </ManagementPageHeader>
      <div className="payment-reminder-page-container">
      <nav className="reminder-settings-nav" role="tablist" aria-label="帳務通知設定">
        <button
          type="button"
          role="tab"
          id="tab-reminder-schedule"
          aria-selected={view === 'reminder-schedule'}
          aria-controls="panel-reminder-schedule"
          className={`reminder-nav-btn ${view === 'reminder-schedule' ? 'active' : ''}`}
          onClick={() => navigateView('reminder-schedule')}
        >
          <Clock size={16} />
          <span>繳款提醒排程 (通知條件)</span>
        </button>
        <button
          type="button"
          role="tab"
          id="tab-reminder-content"
          aria-selected={view === 'reminder-content'}
          aria-controls="panel-reminder-content"
          className={`reminder-nav-btn ${view === 'reminder-content' ? 'active' : ''}`}
          onClick={() => navigateView('reminder-content')}
        >
          <MessageSquareQuote size={16} />
          <span>帳務 LINE 範本</span>
        </button>
      </nav>

      <main className="reminder-settings-content">
        {view === 'reminder-schedule' && (
          <div id="panel-reminder-schedule" role="tabpanel" aria-labelledby="tab-reminder-schedule">
            <PaymentReminderSchedulePanel />
          </div>
        )}

        {view === 'reminder-content' && (
          <div id="panel-reminder-content" role="tabpanel" aria-labelledby="tab-reminder-content">
            <LineNotificationWorkbench
              scope="payment-reminders"
              search={search}
              enabled="all"
              onSearchChange={setSearch}
              onEnabledChange={() => {}}
              selectedEntryId={message}
              onSelectedEntryChange={(id) => {
                setMessage(id);
                const q = params();
                if (id) q.set('message', id);
                else q.delete('message');
                window.history.replaceState(null, '', '#payment-reminder-settings?' + q.toString());
              }}
            />
          </div>
        )}
      </main>
      </div>
    </div>
  );
};

export default PaymentReminderSettingsPage;
