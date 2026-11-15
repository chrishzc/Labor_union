/** 帳務繳款提醒排程與通知條件。 */
import { useEffect } from 'react';
import { Bell } from 'lucide-react';
import { notificationMessageHref } from '../adapters/line_configuration/line_message_flow_adapter';
import { ManagementPageHeader } from '../components/ManagementPageHeader';
import { PaymentReminderSchedulePanel } from '../components/PaymentReminderSchedulePanel';
import './PaymentReminderSettingsPage.css';

export function PaymentReminderSettingsPage() {
  useEffect(() => {
    const query = new URLSearchParams(window.location.hash.split('?')[1]);
    if (query.get('view') === 'reminder-content') window.location.replace(notificationMessageHref(query.get('message'), 'accounting'));
  }, []);

  return (
    <div data-surface-id="finance.payment-reminder-settings.page">
      <ManagementPageHeader title="帳務通知設定" description="設定繳款提醒與逾期補寄時段。">
        <span className="reminder-badge"><Bell size={14} /> 帳務專區</span>
      </ManagementPageHeader>
      <main className="payment-reminder-page-container">
        <PaymentReminderSchedulePanel />
      </main>
    </div>
  );
}

export default PaymentReminderSettingsPage;
