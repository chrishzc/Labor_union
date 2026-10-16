import type { CustomerServiceReminderPage } from '../../../../../../../api/customer_service/customer_service_schemas';

export const CUSTOMER_SERVICE_REMINDER_PAGE_FIXTURE: CustomerServiceReminderPage = {
  items: [{
    ticket_id: 31, client_name: '測試客戶', case_no: 'ORD-TEST-0031', status: 'waiting',
    assigned_admin_name: null, source: 'feedback', sources: ['feedback'],
    reason: 'unresolved_feedback', is_priority: false, updated_at: '2026-10-15T02:00:00Z',
  }],
  total: 1, page: 1, page_size: 25, summary: { waiting: 2, handling: 1 },
};
