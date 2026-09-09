/**
 * File: line_rich_menu_query_flow.test.tsx
 * Description: 驗證 Rich Menu 設定與發布紀錄來自 query client，並依 publication state 掛載合法 controls。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { CustomerServiceClient } from '../api/customer_service/customer_service_client';
import type { LineConfigurationQueryClient } from '../api/line_configuration/line_configuration_query_client';
import type { LineIdentityClient } from '../api/line_identity/line_identity_client';
import type { LineRichMenuDraftClient } from '../api/line_rich_menu_draft/line_rich_menu_draft_client';
import type { LineRichMenuPublicationClient } from '../api/line_rich_menu_publication/line_rich_menu_publication_client';
import { sessionClient } from '../api/auth/session_client';
import { RichMenuDraftSchema } from '../api/line_rich_menu_draft/line_rich_menu_draft_schemas';
import { LineManagementPage, resolveRichMenuUri } from '../pages/LineManagementPage';
import { CUSTOMER_SERVICE_DETAIL_FIXTURE, CUSTOMER_SERVICE_PAGE_FIXTURE, CUSTOMER_SERVICE_SUMMARY_FIXTURE } from './fixtures/customer_service/customer_service_contract_fixtures';
import { BINDING_PAGE_FIXTURE, BOUND_IDENTITY_FIXTURE } from './fixtures/line_identity/line_identity_contract_fixtures';
import { LINE_NOTIFICATION_RULES_CATALOG_FIXTURE, LINE_RICH_MENU_CONFIGURATION_FIXTURE, LINE_RICH_MENU_DRAFT_FIXTURE, LINE_RICH_MENU_EDITABLE_DRAFT_FIXTURE, LINE_RICH_MENU_PUBLICATION_FIXTURE, LINE_RICH_MENU_PUBLICATION_PAGE_FIXTURE } from './fixtures/line_configuration_query_fixtures';

type CustomerServiceQueryClient = Pick<CustomerServiceClient, 'getSummary' | 'listTickets' | 'getTicketDetail'>;
type LineIdentityQueryClient = Pick<LineIdentityClient, 'listBindings' | 'getBinding'>;

function dependencies(): {
  customer: CustomerServiceQueryClient;
  identity: LineIdentityQueryClient;
  configuration: LineConfigurationQueryClient;
  richMenuDraft: LineRichMenuDraftClient;
} {
  return {
    customer: { getSummary: vi.fn().mockResolvedValue(CUSTOMER_SERVICE_SUMMARY_FIXTURE), listTickets: vi.fn().mockResolvedValue(CUSTOMER_SERVICE_PAGE_FIXTURE), getTicketDetail: vi.fn().mockResolvedValue(CUSTOMER_SERVICE_DETAIL_FIXTURE) },
    identity: { listBindings: vi.fn().mockResolvedValue(BINDING_PAGE_FIXTURE), getBinding: vi.fn().mockResolvedValue(BOUND_IDENTITY_FIXTURE) },
    configuration: { getNotificationRules: vi.fn().mockResolvedValue(LINE_NOTIFICATION_RULES_CATALOG_FIXTURE), getRichMenuConfiguration: vi.fn().mockResolvedValue(LINE_RICH_MENU_CONFIGURATION_FIXTURE), listRichMenuPublications: vi.fn().mockResolvedValue(LINE_RICH_MENU_PUBLICATION_PAGE_FIXTURE), getRichMenuPublication: vi.fn().mockResolvedValue(LINE_RICH_MENU_PUBLICATION_FIXTURE) },
    richMenuDraft: { query: vi.fn().mockResolvedValue(LINE_RICH_MENU_DRAFT_FIXTURE), preview: vi.fn(), apply: vi.fn() },
  };
}

afterEach(() => {
  sessionClient.clearSession();
  vi.restoreAllMocks();
});

describe('LINE Rich Menu query 接線', () => {
  it('將 LIFF 草稿參數解析成實際開啟路由', () => {
    expect(resolveRichMenuUri('?target=staff_schedule')).toBe('/line-staff-schedule');
    expect(resolveRichMenuUri('?target=staff_baby_log')).toBe('/line-staff-baby-log');
    expect(resolveRichMenuUri('?target=staff_payout')).toBe('/line-staff-payout');
    expect(resolveRichMenuUri('?target=unknown')).toBe('/line-identity?target=unknown');
  });

  it('顯示真實 menu label 與 publication，published 內容可建立下一版草稿', async () => {
    const fetchSpy = vi.fn().mockRejectedValue(new Error('unexpected network'));
    vi.stubGlobal('fetch', fetchSpy);
    const { customer, identity, configuration, richMenuDraft } = dependencies();
    render(<LineManagementPage customerService={customer} lineIdentity={identity} lineConfiguration={configuration} richMenuDraft={richMenuDraft} />);
    fireEvent.click(screen.getByRole('button', { name: 'Rich Menu' }));

    await waitFor(() => expect(screen.getAllByText('案件進度').length).toBeGreaterThan(0));
    expect(screen.queryByText('目前載入最多 100 筆。')).not.toBeInTheDocument();
    expect(screen.getAllByText('POSTBACK').length).toBeGreaterThan(0);
    expect(screen.getAllByText('case_progress').length).toBeGreaterThan(0);
    expect(screen.queryByText(/https?:\/\//)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '外觀編輯' }));
    expect(screen.getByLabelText('選單名稱')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '預覽草稿變更' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '按鈕動作' }));
    expect(screen.getByRole('button', { name: '預覽草稿變更' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '發布' }));
    expect(screen.queryByRole('button', { name: /準備發布至 LINE|確認排入異步發布/ })).not.toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '此版本已發布' })).toBeInTheDocument();
    expect(screen.getByText(/這不是月嫂或工會人員的權限限制/)).toBeInTheDocument();
    expect(richMenuDraft.query).toHaveBeenCalledTimes(1);
    expect(configuration.getRichMenuConfiguration).not.toHaveBeenCalled();
    expect(configuration.listRichMenuPublications).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole('button', { name: '發布歷程' }));
    expect(screen.getByText('已發布')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /查看紀錄/ }));
    await waitFor(() => expect(configuration.getRichMenuPublication).toHaveBeenCalledWith(
      19,
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    ));
    expect(screen.queryByRole('button', { name: '重新發布' })).not.toBeInTheDocument();
    expect(screen.queryByText(/發布工作 ID|設定版本|紀錄 ID|伺服器狀態/)).not.toBeInTheDocument();
    expect(richMenuDraft.preview).not.toHaveBeenCalled();
    expect(richMenuDraft.apply).not.toHaveBeenCalled();
  });

  it('processing exact lock 不掛載草稿或 provider mutation controls', async () => {
    const fetchSpy = vi.fn().mockRejectedValue(new Error('unexpected network'));
    vi.stubGlobal('fetch', fetchSpy);
    const dependenciesValue = dependencies();
    vi.mocked(dependenciesValue.richMenuDraft.query).mockResolvedValue(RichMenuDraftSchema.parse({
      ...LINE_RICH_MENU_DRAFT_FIXTURE,
      publication_locks: [{
        menu_definition_id: 'customer_menu',
        configuration_revision: 8,
        state: 'processing',
        readonly_reason: '此版本正在發布處理中，為避免變更已送出的內容，目前只能查看。',
      }],
    }));

    render(<LineManagementPage customerService={dependenciesValue.customer} lineIdentity={dependenciesValue.identity} lineConfiguration={dependenciesValue.configuration} richMenuDraft={dependenciesValue.richMenuDraft} />);
    fireEvent.click(screen.getByRole('button', { name: 'Rich Menu' }));

    fireEvent.click(screen.getByRole('button', { name: '外觀編輯' }));
    expect((await screen.findAllByText('此版本正在發布處理中，為避免變更已送出的內容，目前只能查看。')).length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole('button', { name: '按鈕動作' }));
    expect((await screen.findAllByText('此版本正在發布處理中，為避免變更已送出的內容，目前只能查看。')).length).toBeGreaterThan(0);
    expect(screen.queryByRole('button', { name: /檢查發布影響|預覽草稿變更|套用並回讀/ })).not.toBeInTheDocument();
    expect(dependenciesValue.richMenuDraft.preview).not.toHaveBeenCalled();
    expect(dependenciesValue.richMenuDraft.apply).not.toHaveBeenCalled();
    expect(fetchSpy).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: '發布' }));
    expect(screen.getByRole('heading', { name: '發布處理中' })).toBeInTheDocument();
    expect(screen.getByText('此版本正在發布處理中，為避免變更已送出的內容，目前只能查看。')).toBeInTheDocument();
  });

  it('排入後自動追蹤單筆工作，直到 terminal published 才停止', async () => {
    sessionClient.setSession('root-session', {
      id: 7,
      username: 'root-session-test',
      display_name: '根管理員測試',
      role: 'system_admin',
      capabilities: ['line.menu.publish'],
      is_root: true,
      access_control_version: 1,
    });
    const dependenciesValue = dependencies();
    vi.mocked(dependenciesValue.richMenuDraft.query)
      .mockResolvedValueOnce(RichMenuDraftSchema.parse(LINE_RICH_MENU_EDITABLE_DRAFT_FIXTURE))
      .mockResolvedValue(RichMenuDraftSchema.parse(LINE_RICH_MENU_DRAFT_FIXTURE));
    vi.mocked(dependenciesValue.configuration.getRichMenuPublication)
      .mockResolvedValueOnce({
        ...LINE_RICH_MENU_PUBLICATION_FIXTURE,
        status: 'publishing',
      })
      .mockResolvedValue(LINE_RICH_MENU_PUBLICATION_FIXTURE);
    const publication: LineRichMenuPublicationClient = {
      preview: vi.fn().mockResolvedValue({
        preview_id: 51,
        config_revision: '8',
        config_fingerprint: '0123456789abcdef'.repeat(4),
      }),
      publish: vi.fn().mockResolvedValue({
        id: 19,
        menu_definition_id: 'customer_menu',
        configuration_revision: 8,
        status: 'queued',
      }),
      retry: vi.fn(),
    };

    render(
      <LineManagementPage
        customerService={dependenciesValue.customer}
        lineIdentity={dependenciesValue.identity}
        lineConfiguration={dependenciesValue.configuration}
        richMenuDraft={dependenciesValue.richMenuDraft}
        richMenuPublication={publication}
        richMenuPublicationPollIntervalMs={50}
      />
    );
    fireEvent.click(screen.getByRole('button', { name: 'Rich Menu' }));
    fireEvent.click(await screen.findByRole('button', { name: '發布' }));
    fireEvent.click(await screen.findByRole('button', { name: /檢查發布影響/ }));
    await screen.findByText(/發布影響已確認/);
    fireEvent.change(screen.getByRole('textbox', { name: '發布原因' }), {
      target: { value: '發布客戶選單新版' },
    });
    fireEvent.click(screen.getByRole('checkbox', { name: /同意排入發布序列/ }));
    fireEvent.click(screen.getByRole('button', { name: /確認排入異步發布/ }));

    expect(await screen.findByRole('heading', { name: '發布處理中' })).toBeInTheDocument();
    expect(screen.getByText(/自動追蹤 LINE 發布結果/)).toBeInTheDocument();
    expect(await screen.findByRole('heading', { name: '此版本已發布' })).toBeInTheDocument();
    await waitFor(() => expect(dependenciesValue.configuration.getRichMenuPublication).toHaveBeenCalledTimes(2));
    expect(screen.queryByText(/自動追蹤 LINE 發布結果/)).not.toBeInTheDocument();
  });
});
