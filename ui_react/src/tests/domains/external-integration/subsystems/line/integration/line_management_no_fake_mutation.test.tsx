import { CUSTOMER_SERVICE_REMINDER_PAGE_FIXTURE } from './fixtures/customer_service_reminder_fixtures';
/**
 * File: line_management_no_fake_mutation.test.tsx
 * Description: 驗證 LINE successor 不暴露未授權控制項，且未觸發 Preview／Apply 或 provider 請求。
 */
import { readFileSync } from 'node:fs';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { CustomerServiceClient, CustomerServiceReminderClient } from '../../../../../../api/customer_service/customer_service_client';
import { CustomerServiceClientError } from '../../../../../../api/customer_service/customer_service_errors';
import type { LineIdentityClient } from '../../../../../../api/line_identity/line_identity_client';
import type { LineConfigurationQueryClient } from '../../../../../../api/line_configuration/line_configuration_query_client';
import type { LineRichMenuDraftClient } from '../../../../../../api/line_rich_menu_draft/line_rich_menu_draft_client';
import type { LineOnboardingClient } from '../../../../../../api/line_onboarding/line_onboarding_client';
import { lineMessagePreviewClient } from '../../../../../../api/line_notification_rules/line_message_preview_client';
import { LineManagementPage } from '../../../../../../pages/LineManagementPage';
import { CUSTOMER_SERVICE_DETAIL_FIXTURE, CUSTOMER_SERVICE_PAGE_FIXTURE, CUSTOMER_SERVICE_SUMMARY_FIXTURE } from '../../../../../fixtures/customer_service/customer_service_contract_fixtures';
import { BINDING_PAGE_FIXTURE, BOUND_IDENTITY_FIXTURE } from '../../../../../fixtures/line_identity/line_identity_contract_fixtures';
import { LINE_NOTIFICATION_RULES_CATALOG_FIXTURE, LINE_RICH_MENU_CONFIGURATION_FIXTURE, LINE_RICH_MENU_DRAFT_FIXTURE, LINE_RICH_MENU_PUBLICATION_FIXTURE, LINE_RICH_MENU_PUBLICATION_PAGE_FIXTURE } from '../../../../../fixtures/line_configuration_query_fixtures';

type CustomerServiceQueryClient = Pick<CustomerServiceClient, 'getSummary' | 'listTickets' | 'getTicketDetail'> & Partial<CustomerServiceReminderClient>;
type LineIdentityQueryClient = Pick<LineIdentityClient, 'listBindings' | 'getBinding'>;

afterEach(() => vi.restoreAllMocks());

describe('LINE 管理頁禁止假 mutation', () => {
  it('查詢失敗先顯示可讀訊息，技術錯誤碼預設收合', async () => {
    const unavailable = new CustomerServiceClientError('unavailable', 'HTTP_503', 'Service Unavailable', 503, true);
    const customer: CustomerServiceQueryClient = {
      listReminders: vi.fn().mockRejectedValue(unavailable),
      getSummary: vi.fn().mockRejectedValue(unavailable),
      listTickets: vi.fn().mockRejectedValue(unavailable),
      getTicketDetail: vi.fn().mockRejectedValue(new Error('not used')),
    };

    render(<LineManagementPage customerService={customer} />);

    const alerts = await screen.findAllByRole('alert');
    expect(alerts).toHaveLength(1);
    expect(alerts[0]).toHaveTextContent('客服案件暫時無法載入');
    expect(alerts[0]).not.toHaveTextContent('HTTP_503');
    expect(alerts[0]).not.toHaveTextContent('Service Unavailable');
  });

  it('未授權控制項不進入畫面，合法流程在未操作前維持零 mutation', async () => {
    const catalogQuery = vi.spyOn(lineMessagePreviewClient, 'catalog').mockResolvedValue([]);
    const fetchSpy = vi.fn().mockRejectedValue(new Error('unexpected network'));
    vi.stubGlobal('fetch', fetchSpy);

    const previewResolve = vi.fn();
    const applyResolve = vi.fn();
    const customerCandidate = {
      listReminders: vi.fn().mockResolvedValue(CUSTOMER_SERVICE_REMINDER_PAGE_FIXTURE),
      getSummary: vi.fn().mockResolvedValue(CUSTOMER_SERVICE_SUMMARY_FIXTURE),
      listTickets: vi.fn().mockResolvedValue({
        ...CUSTOMER_SERVICE_PAGE_FIXTURE,
        items: CUSTOMER_SERVICE_PAGE_FIXTURE.items.map((item) => ({
          ...item,
          status: 'waiting' as const,
        })),
      }),
      getTicketDetail: vi.fn().mockResolvedValue(CUSTOMER_SERVICE_DETAIL_FIXTURE),
      previewResolve,
      applyResolve,
    };
    const customer: CustomerServiceQueryClient = customerCandidate;

    const previewRevocation = vi.fn();
    const applyRevocation = vi.fn();
    const identityCandidate = {
      listBindings: vi.fn().mockResolvedValue(BINDING_PAGE_FIXTURE),
      getBinding: vi.fn().mockResolvedValue(BOUND_IDENTITY_FIXTURE),
      previewRevocation,
      applyRevocation,
    };
    const identity: LineIdentityQueryClient = identityCandidate;

    const configuration: LineConfigurationQueryClient = {
      getNotificationRules: vi.fn().mockResolvedValue(LINE_NOTIFICATION_RULES_CATALOG_FIXTURE),
      getRichMenuConfiguration: vi.fn().mockResolvedValue(LINE_RICH_MENU_CONFIGURATION_FIXTURE),
      listRichMenuPublications: vi.fn().mockResolvedValue(LINE_RICH_MENU_PUBLICATION_PAGE_FIXTURE),
      getRichMenuPublication: vi.fn().mockResolvedValue(LINE_RICH_MENU_PUBLICATION_FIXTURE),
    };
    const richMenuDraft: LineRichMenuDraftClient = {
      query: vi.fn().mockResolvedValue(LINE_RICH_MENU_DRAFT_FIXTURE),
      preview: vi.fn().mockRejectedValue(new Error('not used')),
      apply: vi.fn().mockRejectedValue(new Error('not used')),
    };

    const onboardingClient: LineOnboardingClient = {
      get: vi.fn().mockResolvedValue({
        template_id: 'customer_onboarding_welcome',
        content: '歡迎加入工會！請至 {url} 登記。',
        revision: 1,
        sample_preview: '歡迎加入工會！請至 https://liff.line.me/123/gateway 登記。',
        variables: ['url'],
      }),
      preview: vi.fn().mockResolvedValue({
        sample_preview: '預覽',
        variables: ['url'],
      }),
      update: vi.fn().mockResolvedValue({
        template_id: 'customer_onboarding_welcome',
        content: '更新',
        revision: 2,
        sample_preview: '更新',
        variables: ['url'],
      }),
    };

    render(
      <LineManagementPage
        customerService={customer}
        lineIdentity={identity}
        lineConfiguration={configuration}
        richMenuDraft={richMenuDraft}
        onboardingClient={onboardingClient}
        notificationTemplateClient={{ get: vi.fn(async (ruleId: string) => ({ rule_id: ruleId, template_id: 'deposit_template', name: '訂金確認通知', content: '正式訂金通知內容', revision: 1, variables: [], sample_preview: '正式訂金通知內容' })), update: vi.fn() }}
      />
    );
    await waitFor(() => expect(screen.getByText('ORD-TEST-0031')).toBeInTheDocument());
    expect(screen.queryByRole('button', { name: '開啟 LINE' })).not.toBeInTheDocument();

    expect(screen.queryByRole('button', { name: '檢查結案影響' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '查看明細' })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '圖文選單' }));
    expect((await screen.findAllByText('案件進度')).length).toBeGreaterThan(0);
    expect(screen.queryByRole('button', { name: /發布至 LINE|上傳圖片|刪除選單/ })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '身分與授權' }));
    await screen.findByText('測試客戶甲');
    expect(screen.queryByRole('button', { name: /產生綁定邀請/ })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '查看測試客戶甲的客戶身分' }));
    await screen.findByRole('button', { name: '解除此身分' });
    expect(screen.queryByRole('button', { name: /觀察解除|改綁其他身分|重試 Rich Menu 回復|人工完成/ })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '關閉身分明細' }));

    fireEvent.click(screen.getByRole('button', { name: '通知與發送' }));
    const ruleWorkspace = (await screen.findByRole('heading', { name: '通知與發送' })).closest('section');
    expect(ruleWorkspace).not.toBeNull();
    await within(ruleWorkspace as HTMLElement).findByRole('button', { name: '編輯新好友歡迎訊息內容' });
    expect(within(ruleWorkspace as HTMLElement).queryByRole('button', { name: 'Onboarding 訊息' })).not.toBeInTheDocument();
    expect(within(ruleWorkspace as HTMLElement).queryByText(/多日排程關懷設定/)).not.toBeInTheDocument();
    fireEvent.click(await within(ruleWorkspace as HTMLElement).findByRole('button', { name: '編輯訂金確認通知內容' }));
    expect(screen.queryByRole('button', { name: /儲存並發布|手動重播/ })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '取消' }));

    expect(screen.queryByRole('button', { name: /智慧客服 FAQ/ })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '案件群組' }));
    expect(screen.queryByRole('button', { name: /建立案件群組/ })).not.toBeInTheDocument();

    expect(previewResolve).not.toHaveBeenCalled();
    expect(applyResolve).not.toHaveBeenCalled();
    expect(previewRevocation).not.toHaveBeenCalled();
    expect(applyRevocation).not.toHaveBeenCalled();
    expect(catalogQuery).toHaveBeenCalledTimes(1);
    expect(richMenuDraft.preview).not.toHaveBeenCalled();
    expect(richMenuDraft.apply).not.toHaveBeenCalled();
    expect(onboardingClient.update).not.toHaveBeenCalled();
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it('Rich Menu 手機模擬器只呈現 typed action，不保留假案件、假統計或假回覆', async () => {
    const source = readFileSync('src/pages/LineManagementPage.tsx', 'utf8');
    for (const forbidden of [
      'CASE-202608-019',
      '工會即時營運數據看板',
      '本月市府補助申請',
      '98.6% 家長給予 5 星好評',
      '工會系統已為您記錄並處理中',
    ]) {
      expect(source).not.toContain(forbidden);
    }
    expect(source).toContain("text: act.text ?? ''");
    expect(source).toContain('系統不會依按鈕名稱猜測 action。');
    expect(source).toContain('不會送出 LINE 訊息。');

    const fetchSpy = vi.fn().mockRejectedValue(new Error('unexpected network'));
    vi.stubGlobal('fetch', fetchSpy);
    const customer: CustomerServiceQueryClient = {
      listReminders: vi.fn().mockResolvedValue(CUSTOMER_SERVICE_REMINDER_PAGE_FIXTURE),
      getSummary: vi.fn().mockResolvedValue(CUSTOMER_SERVICE_SUMMARY_FIXTURE),
      listTickets: vi.fn().mockResolvedValue(CUSTOMER_SERVICE_PAGE_FIXTURE),
      getTicketDetail: vi.fn().mockResolvedValue(CUSTOMER_SERVICE_DETAIL_FIXTURE),
    };
    const identity: LineIdentityQueryClient = {
      listBindings: vi.fn().mockResolvedValue(BINDING_PAGE_FIXTURE),
      getBinding: vi.fn().mockResolvedValue(BOUND_IDENTITY_FIXTURE),
    };
    const configuration: LineConfigurationQueryClient = {
      getNotificationRules: vi.fn().mockResolvedValue(LINE_NOTIFICATION_RULES_CATALOG_FIXTURE),
      getRichMenuConfiguration: vi.fn().mockResolvedValue(LINE_RICH_MENU_CONFIGURATION_FIXTURE),
      listRichMenuPublications: vi.fn().mockResolvedValue(LINE_RICH_MENU_PUBLICATION_PAGE_FIXTURE),
      getRichMenuPublication: vi.fn().mockResolvedValue(LINE_RICH_MENU_PUBLICATION_FIXTURE),
    };
    const richMenuDraft: LineRichMenuDraftClient = {
      query: vi.fn().mockResolvedValue(LINE_RICH_MENU_DRAFT_FIXTURE),
      preview: vi.fn().mockRejectedValue(new Error('not used')),
      apply: vi.fn().mockRejectedValue(new Error('not used')),
    };

    render(
      <LineManagementPage
        customerService={customer}
        lineIdentity={identity}
        lineConfiguration={configuration}
        richMenuDraft={richMenuDraft}
      />
    );
    fireEvent.click(screen.getByRole('button', { name: '圖文選單' }));
    const caseProgressLabel = await screen.findByText('案件進度', { selector: 'span.richmenu-btn-text' });
    fireEvent.click(caseProgressLabel.closest('button') as HTMLButtonElement);

    expect(await screen.findByText('Postback 動作本機預覽')).toBeInTheDocument();
    expect(document.body.textContent).not.toContain('CASE-202608-019');
    expect(document.body.textContent).not.toContain('工會系統已為您記錄並處理中');
    expect(fetchSpy).not.toHaveBeenCalled();
  });
});
