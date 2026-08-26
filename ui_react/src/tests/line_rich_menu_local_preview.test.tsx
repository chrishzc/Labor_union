/**
 * File: line_rich_menu_local_preview.test.tsx
 * Description: 驗證 Rich Menu browser-memory edits、typed geometry 與安全 Diff blocker，且不觸發任何 mutation。
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { CustomerServiceClient } from '../api/customer_service/customer_service_client';
import type { LineConfigurationQueryClient } from '../api/line_configuration/line_configuration_query_client';
import type { LineIdentityClient } from '../api/line_identity/line_identity_client';
import type { LineRichMenuDraftClient } from '../api/line_rich_menu_draft/line_rich_menu_draft_client';
import { LineManagementPage } from '../pages/LineManagementPage';
import {
  CUSTOMER_SERVICE_DETAIL_FIXTURE,
  CUSTOMER_SERVICE_PAGE_FIXTURE,
  CUSTOMER_SERVICE_SUMMARY_FIXTURE,
} from './fixtures/customer_service/customer_service_contract_fixtures';
import {
  BINDING_PAGE_FIXTURE,
  BOUND_IDENTITY_FIXTURE,
} from './fixtures/line_identity/line_identity_contract_fixtures';
import {
  LINE_NOTIFICATION_RULES_CATALOG_FIXTURE,
  LINE_RICH_MENU_CONFIGURATION_FIXTURE,
  LINE_RICH_MENU_DRAFT_FIXTURE,
  LINE_RICH_MENU_PUBLICATION_FIXTURE,
  LINE_RICH_MENU_PUBLICATION_PAGE_FIXTURE,
} from './fixtures/line_configuration_query_fixtures';

type CustomerQuery = Pick<CustomerServiceClient, 'getSummary' | 'listTickets' | 'getTicketDetail'>;
type IdentityQuery = Pick<LineIdentityClient, 'listBindings' | 'getBinding'>;

afterEach(() => vi.unstubAllGlobals());

describe('Rich Menu 本機互動預覽', () => {
  it('即時投影外觀與 typed message，取消還原，且維持零 mutation', async () => {
    const fetchSpy = vi.fn().mockRejectedValue(new Error('unexpected network'));
    vi.stubGlobal('fetch', fetchSpy);
    const customer: CustomerQuery = {
      getSummary: vi.fn().mockResolvedValue(CUSTOMER_SERVICE_SUMMARY_FIXTURE),
      listTickets: vi.fn().mockResolvedValue(CUSTOMER_SERVICE_PAGE_FIXTURE),
      getTicketDetail: vi.fn().mockResolvedValue(CUSTOMER_SERVICE_DETAIL_FIXTURE),
    };
    const identity: IdentityQuery = {
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
      preview: vi.fn().mockRejectedValue(new Error('local preview must not call server Preview')),
      apply: vi.fn().mockRejectedValue(new Error('local preview must not Apply')),
    };

    const { container } = render(
      <LineManagementPage
        customerService={customer}
        lineIdentity={identity}
        lineConfiguration={configuration}
        richMenuDraft={richMenuDraft}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /2\. 多角色 Rich Menu/ }));
    await waitFor(() => expect(richMenuDraft.query).toHaveBeenCalledTimes(1));

    const appearance = container.querySelector('[data-control-id="line.richmenu.draft.appearance-editor"]');
    const action = container.querySelector('[data-control-id="line.richmenu.draft.action-editor"]');
    const phoneMenu = container.querySelector('[data-control-id="line.richmenu.local-preview"]');
    expect(appearance).not.toBeNull();
    expect(action).not.toBeNull();
    expect(phoneMenu).not.toBeNull();
    expect(screen.getByText(/下方 1 個按鈕測試互動反應/)).toBeInTheDocument();
    expect(within(phoneMenu as HTMLElement).getByRole('button', { name: /案件進度/ })).toHaveStyle({
      position: 'absolute',
      left: '0%',
      top: '0%',
      width: '100%',
      height: '100%',
    });
    expect(screen.queryByText('合規可發布')).not.toBeInTheDocument();
    expect(screen.queryByText(/熱區路由合格/)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /開啟版本變更比對/ }));
    expect(screen.getByRole('status')).toHaveTextContent('尚缺線上生效版本資料');
    expect(screen.queryByText(/服務登記 \(2500x843 半版\)/)).not.toBeInTheDocument();
    expect(screen.queryByText(/升級 4 宮格熱區/)).not.toBeInTheDocument();

    fireEvent.change(within(appearance as HTMLElement).getByLabelText('背景色彩'), { target: { value: '#123456' } });
    fireEvent.change(within(appearance as HTMLElement).getByLabelText('按鈕 1 名稱'), { target: { value: '本機案件按鈕' } });
    fireEvent.change(within(action as HTMLElement).getByLabelText('動作類型'), { target: { value: 'message' } });
    fireEvent.change(within(action as HTMLElement).getByLabelText('送出訊息'), { target: { value: '尚未保存的本機訊息' } });
    expect(phoneMenu).toHaveStyle({ backgroundColor: '#123456' });
    expect(within(phoneMenu as HTMLElement).getByText('本機案件按鈕')).toBeInTheDocument();
    fireEvent.click(within(phoneMenu as HTMLElement).getByRole('button', { name: /本機案件按鈕/ }));
    const phoneChat = container.querySelector('.richmenu-phone-chat');
    expect(phoneChat).not.toBeNull();
    expect(within(phoneChat as HTMLElement).getByText('尚未保存的本機訊息')).toBeInTheDocument();

    fireEvent.click(within(appearance as HTMLElement).getByRole('button', { name: '取消修改' }));
    expect(within(phoneMenu as HTMLElement).getByText('案件進度')).toBeInTheDocument();
    fireEvent.click(within(phoneMenu as HTMLElement).getByRole('button', { name: /案件進度/ }));
    expect(within(phoneChat as HTMLElement).getByText('尚未保存的本機訊息')).toBeInTheDocument();

    expect(richMenuDraft.preview).not.toHaveBeenCalled();
    expect(richMenuDraft.apply).not.toHaveBeenCalled();
    expect(fetchSpy).not.toHaveBeenCalled();
  });
});
