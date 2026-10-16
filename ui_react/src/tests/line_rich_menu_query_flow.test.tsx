/**
 * File: line_rich_menu_query_flow.test.tsx
 * Description: 驗證 Rich Menu 草稿與發布工作來自 query client，並依 publication state 掛載合法 controls。
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
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('LINE Rich Menu query 接線', () => {
  it('將 LIFF 草稿參數解析成實際開啟路由', () => {
    expect(resolveRichMenuUri('?target=staff_schedule')).toBe('/line-staff-schedule');
    expect(resolveRichMenuUri('?target=staff_baby_log')).toBe('/line-staff-baby-log');
    expect(resolveRichMenuUri('?target=staff_payout')).toBe('/line-staff-payout');
    expect(resolveRichMenuUri('?target=staff_verification')).toBe('/line-identity?target=staff_verification');
    expect(resolveRichMenuUri('?target=order_update')).toBe('/line-order-update');
    expect(resolveRichMenuUri('?target=order_tracking')).toBe('/line-mobile-admin?target=order_tracking');
    expect(resolveRichMenuUri('?target=dashboard')).toBe('/line-mobile-admin?target=dashboard');
    expect(resolveRichMenuUri('?target=faq')).toBe('/line-service-help?tab=faq');
    expect(resolveRichMenuUri('?target=ai_assistant')).toBe('/line-service-help?tab=ai');
    expect(resolveRichMenuUri('?target=unknown')).toBe('/line-identity?target=unknown');
  });

  it('發布緊鄰儲存且保留確認，移除歷程入口；published 內容可建立下一版草稿', async () => {
    const fetchSpy = vi.fn().mockRejectedValue(new Error('unexpected network'));
    vi.stubGlobal('fetch', fetchSpy);
    const { customer, identity, configuration, richMenuDraft } = dependencies();
    render(<LineManagementPage customerService={customer} lineIdentity={identity} lineConfiguration={configuration} richMenuDraft={richMenuDraft} />);
    fireEvent.click(screen.getByRole('button', { name: '圖文選單' }));

    await waitFor(() => expect(screen.getAllByText('案件進度').length).toBeGreaterThan(0));
    expect(screen.queryByText('目前載入最多 100 筆。')).not.toBeInTheDocument();
    // Typed action data is revealed only by the phone preview or its editor.
    expect(screen.queryByText(/https?:\/\//)).not.toBeInTheDocument();

    fireEvent.click(await screen.findByRole('button', { name: '外觀與名稱' }));
    expect(screen.getByLabelText('選單名稱')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '檢查並儲存草稿' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '按鈕設定' }));
    expect(screen.getByRole('button', { name: '檢查並儲存草稿' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '發布' }));
    expect(screen.queryByRole('button', { name: /準備發布至 LINE|確認發布至 LINE/ })).not.toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '此版本已發布' })).toBeInTheDocument();
    expect(screen.getByText(/這不是月嫂或工會人員的權限限制/)).toBeInTheDocument();
    expect(richMenuDraft.query).toHaveBeenCalledTimes(1);
    expect(configuration.getRichMenuConfiguration).not.toHaveBeenCalled();
    expect(configuration.listRichMenuPublications).not.toHaveBeenCalled();
    expect(screen.queryByRole('button', { name: '發布紀錄' })).not.toBeInTheDocument();
    expect(screen.queryByRole('navigation', { name: '圖文選單工作頁' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '關閉發布確認' }));
    expect(screen.getByRole('button', { name: '發布' }).parentElement).toBe(screen.getByRole('button', { name: '檢查並儲存草稿' }).parentElement);
    expect(configuration.getRichMenuPublication).not.toHaveBeenCalled();
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
    fireEvent.click(screen.getByRole('button', { name: '圖文選單' }));

    fireEvent.click(await screen.findByRole('button', { name: '外觀與名稱' }));
    expect((await screen.findAllByText('此版本正在發布處理中，為避免變更已送出的內容，目前只能查看。')).length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole('button', { name: '按鈕設定' }));
    expect((await screen.findAllByText('此版本正在發布處理中，為避免變更已送出的內容，目前只能查看。')).length).toBeGreaterThan(0);
    expect(screen.queryByRole('button', { name: /檢查發布影響|預覽草稿變更|套用並回讀/ })).not.toBeInTheDocument();
    expect(dependenciesValue.richMenuDraft.preview).not.toHaveBeenCalled();
    expect(dependenciesValue.richMenuDraft.apply).not.toHaveBeenCalled();
    expect(fetchSpy).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: '查看發布狀態' }));
    expect(screen.getByRole('heading', { name: '發布處理中' })).toBeInTheDocument();
    expect(screen.getAllByText('此版本正在發布處理中，為避免變更已送出的內容，目前只能查看。').length).toBeGreaterThan(0);
  });

  it.each(['published', 'publish_retryable_failed'] as const)('排入後追蹤至 %s；可重試失敗留在確認視窗處理', async (terminalStatus) => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('unexpected network')));
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
      .mockResolvedValue({ ...LINE_RICH_MENU_PUBLICATION_FIXTURE, status: terminalStatus });
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
      retry: vi.fn().mockResolvedValue({ id: 19, menu_definition_id: 'customer_menu', configuration_revision: 8, status: 'queued' }),
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
    fireEvent.click(screen.getByRole('button', { name: '圖文選單' }));
    fireEvent.click(await screen.findByRole('button', { name: '發布' }));
    fireEvent.click(await screen.findByRole('button', { name: /檢查發布影響/ }));
    await screen.findByText(/發布影響已確認/);
    fireEvent.change(screen.getByRole('textbox', { name: '發布原因' }), {
      target: { value: '發布客戶選單新版' },
    });
    fireEvent.click(screen.getByRole('checkbox', { name: /同意排入發布序列/ }));
    fireEvent.click(screen.getByRole('button', { name: /確認發布至 LINE/ }));

    await waitFor(() => expect(dependenciesValue.configuration.getRichMenuPublication).toHaveBeenCalledTimes(2));
    expect(await screen.findByRole('heading', { name: terminalStatus === 'published' ? '此版本已發布' : '發布未完成' }, { timeout: 4000 })).toBeInTheDocument();
    if (terminalStatus === 'publish_retryable_failed') {
      fireEvent.change(screen.getByRole('textbox', { name: '重試原因' }), { target: { value: '確認後重新排入' } });
      fireEvent.click(screen.getByRole('checkbox', { name: /我已確認此紀錄為發布可重試失敗/ }));
      fireEvent.click(screen.getByRole('button', { name: '確認重新排入發布' }));
      await waitFor(() => expect(publication.retry).toHaveBeenCalledWith(19, expect.objectContaining({ reason: '確認後重新排入' }), expect.objectContaining({ signal: expect.any(AbortSignal) })));
      await screen.findByRole('heading', { name: '發布未完成' });
    }
    expect(screen.queryByText(/自動追蹤 LINE 發布結果/)).not.toBeInTheDocument();
  });
});


describe('Rich Menu shared draft persistence', () => {
  it('keeps appearance and button edits across work pages, saves once, then reloads the persisted background after remount', async () => {
    window.location.hash = '#line-management?tab=richmenu';
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('unexpected network')));
    const deps = dependencies();
    let persisted = RichMenuDraftSchema.parse(structuredClone(LINE_RICH_MENU_EDITABLE_DRAFT_FIXTURE));
    persisted = RichMenuDraftSchema.parse({ ...persisted, definition: { ...persisted.definition, menus: [
      ...persisted.definition.menus,
      { ...persisted.definition.menus[0], id: 'staff_menu', name: '月嫂選單', audience_role: 'staff', set_as_default: false },
    ] }, publication_locks: [...persisted.publication_locks, { menu_definition_id: 'staff_menu', configuration_revision: persisted.revision, state: 'editable', readonly_reason: null }] });
    const publication: LineRichMenuPublicationClient = { preview: vi.fn(), publish: vi.fn(), retry: vi.fn() };
    vi.mocked(deps.richMenuDraft.query).mockImplementation(async () => structuredClone(persisted));
    vi.mocked(deps.richMenuDraft.preview).mockImplementation(async request => ({ before_revision: persisted.revision, resulting_revision: persisted.revision + 1, normalized_definition: request.definition, preview_fingerprint: 'a'.repeat(64) }));
    vi.mocked(deps.richMenuDraft.apply).mockImplementation(async request => {
      persisted = { ...persisted, revision: persisted.revision + 1, definition: request.definition, publication_locks: persisted.publication_locks.map(lock => ({ ...lock, configuration_revision: persisted.revision + 1, state: 'editable', readonly_reason: null })) };
      return { receipt: { outcome: 'created', committed_revision: persisted.revision, receipt_reference: 'shared-draft-save' }, readback: structuredClone(persisted) };
    });
    const page = () => <LineManagementPage customerService={deps.customer} lineIdentity={deps.identity} lineConfiguration={deps.configuration} richMenuDraft={deps.richMenuDraft} richMenuPublication={publication} />;
    const mounted = render(page());
    const color = await screen.findByLabelText('自訂選單底色');
    expect(screen.queryByLabelText('按鈕顯示名稱')).not.toBeInTheDocument();
    fireEvent.change(color, { target: { value: '#123456' } });
    fireEvent.click(screen.getByRole('button', { name: '月嫂' }));
    fireEvent.click(screen.getByRole('button', { name: '客戶' }));
    expect(screen.getByLabelText('自訂選單底色')).toHaveValue('#123456');
    fireEvent.click(screen.getByRole('button', { name: '按鈕設定' }));
    fireEvent.change(screen.getByLabelText('按鈕顯示名稱'), { target: { value: '查詢服務進度' } });
    expect(screen.getByRole('button', { name: '發布' })).toBeDisabled();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '檢查發布影響' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '外觀與名稱' }));
    expect(screen.getByLabelText('自訂選單底色')).toHaveValue('#123456');
    fireEvent.click(screen.getByRole('button', { name: '檢查並儲存草稿' }));
    await screen.findByRole('dialog');
    fireEvent.change(screen.getByLabelText('變更原因'), { target: { value: '確認背景色及按鈕名稱' } });
    fireEvent.click(screen.getByRole('checkbox', { name: /我確認儲存此草稿/ }));
    fireEvent.click(screen.getByRole('button', { name: '確認儲存草稿' }));
    await screen.findByText('草稿已儲存並重新載入；尚未發布至 LINE。');
    expect(deps.richMenuDraft.apply).toHaveBeenCalledTimes(1);
    expect(deps.richMenuDraft.query).toHaveBeenCalledTimes(2);
    expect(persisted.definition.menus[0].appearance?.background_color).toBe('#123456');
    expect(persisted.definition.menus[0].buttons[0].label).toBe('查詢服務進度');
    expect(persisted.definition.menus[0].buttons[0].action).toEqual(LINE_RICH_MENU_EDITABLE_DRAFT_FIXTURE.definition.menus[0].buttons[0].action);
    expect(publication.publish).not.toHaveBeenCalled();
    mounted.unmount(); render(page());
    expect(await screen.findByLabelText('自訂選單底色')).toHaveValue('#123456');
    fireEvent.click(screen.getByRole('button', { name: '按鈕設定' }));
    expect(screen.getByLabelText('按鈕顯示名稱')).toHaveValue('查詢服務進度');
  });
  it('a failed fresh readback keeps publication blocked even after local edits are discarded, until a fresh Query succeeds', async () => {
    window.location.hash = '#line-management?tab=richmenu';
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('unexpected network')));
    const deps = dependencies();
    const initial = RichMenuDraftSchema.parse(structuredClone(LINE_RICH_MENU_EDITABLE_DRAFT_FIXTURE));
    vi.mocked(deps.richMenuDraft.query).mockResolvedValue(initial);
    vi.mocked(deps.richMenuDraft.preview).mockImplementation(async request => ({ before_revision: 8, resulting_revision: 9, normalized_definition: request.definition, preview_fingerprint: 'a'.repeat(64) }));
    vi.mocked(deps.richMenuDraft.apply).mockResolvedValue({ receipt: { outcome: 'created', committed_revision: 9, receipt_reference: 'readback-mismatch' }, readback: { ...initial, revision: 9 } });
    render(<LineManagementPage customerService={deps.customer} lineIdentity={deps.identity} lineConfiguration={deps.configuration} richMenuDraft={deps.richMenuDraft} />);
    fireEvent.change(await screen.findByLabelText('自訂選單底色'), { target: { value: '#123456' } });
    fireEvent.click(screen.getByRole('button', { name: '檢查並儲存草稿' })); await screen.findByRole('dialog');
    fireEvent.change(screen.getByLabelText('變更原因'), { target: { value: '驗證讀回衝突' } });
    fireEvent.click(screen.getByRole('checkbox', { name: /我確認儲存此草稿/ }));
    fireEvent.click(screen.getByRole('button', { name: '確認儲存草稿' }));
    await screen.findAllByText(/重新載入的內容與確認結果不同/);
    fireEvent.click(screen.getByRole('button', { name: '繼續編輯' }));
    fireEvent.click(screen.getByRole('button', { name: '取消修改' })); fireEvent.click(screen.getByRole('button', { name: '確認取消修改' }));
    expect(screen.getByRole('button', { name: '發布' })).toBeDisabled();
    expect(screen.queryByRole('button', { name: '檢查發布影響' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '重新整理' }));
    await screen.findByLabelText('自訂選單底色'); fireEvent.click(screen.getByRole('button', { name: '發布' }));
    expect(screen.getByRole('button', { name: '檢查發布影響' })).toBeInTheDocument();
  });

});
