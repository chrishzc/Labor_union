/**
 * File: line_management_no_fake_mutation.test.tsx
 * Description: 驗證 LINE query-only slice 的未開放控制項原生鎖定、零 Preview／Apply 與零直接網路請求。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { CustomerServiceClient } from '../api/customer_service/customer_service_client';
import type { LineIdentityClient } from '../api/line_identity/line_identity_client';
import type { LineConfigurationQueryClient } from '../api/line_configuration/line_configuration_query_client';
import { LineManagementPage } from '../pages/LineManagementPage';
import { CUSTOMER_SERVICE_DETAIL_FIXTURE, CUSTOMER_SERVICE_PAGE_FIXTURE, CUSTOMER_SERVICE_SUMMARY_FIXTURE } from './fixtures/customer_service/customer_service_contract_fixtures';
import { BINDING_PAGE_FIXTURE, BOUND_IDENTITY_FIXTURE } from './fixtures/line_identity/line_identity_contract_fixtures';
import { LINE_NOTIFICATION_RULES_CATALOG_FIXTURE, LINE_RICH_MENU_CONFIGURATION_FIXTURE, LINE_RICH_MENU_PUBLICATION_FIXTURE, LINE_RICH_MENU_PUBLICATION_PAGE_FIXTURE } from './fixtures/line_configuration_query_fixtures';

type CustomerServiceQueryClient = Pick<CustomerServiceClient, 'getSummary' | 'listTickets' | 'getTicketDetail'>;
type LineIdentityQueryClient = Pick<LineIdentityClient, 'listBindings' | 'getBinding'>;

afterEach(() => vi.restoreAllMocks());

describe('LINE 管理頁禁止假 mutation', () => {
  it('所有未核准控制項均為 native disabled 且零 mutation', async () => {
    const fetchSpy = vi.fn().mockRejectedValue(new Error('unexpected network'));
    vi.stubGlobal('fetch', fetchSpy);

    const previewResolve = vi.fn();
    const applyResolve = vi.fn();
    const customerCandidate = {
      getSummary: vi.fn().mockResolvedValue(CUSTOMER_SERVICE_SUMMARY_FIXTURE),
      listTickets: vi.fn().mockResolvedValue(CUSTOMER_SERVICE_PAGE_FIXTURE),
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

    render(<LineManagementPage customerService={customer} lineIdentity={identity} lineConfiguration={configuration} />);
    await waitFor(() => expect(screen.getByText('#31')).toBeInTheDocument());
    expect(screen.getByRole('button', { name: '開啟 LINE' })).toBeDisabled();

    fireEvent.click(screen.getByRole('button', { name: '查看明細' }));
    await screen.findByText('客服結案 mutation 未開放');
    expect(screen.getByRole('button', { name: '預覽結案（未開放）' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '確認結案（未開放）' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '重試結案（未開放）' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: '關閉' }));

    fireEvent.click(screen.getByRole('button', { name: /2\. 多角色 Rich Menu/ }));
    await screen.findByText('案件進度');
    expect(screen.getByRole('button', { name: /發布至 LINE/ })).toBeDisabled();
    expect(screen.getByRole('button', { name: '上傳圖片' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '刪除選單' })).toBeDisabled();

    fireEvent.click(screen.getByRole('button', { name: /3\. LINE 身分綁定/ }));
    await screen.findByText('U123••••cdef');
    expect(screen.getByRole('button', { name: /產生綁定邀請/ })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: '查看明細' }));
    await screen.findByText('身分解除 mutation 未開放');
    expect(screen.getByRole('button', { name: '預覽解除（未開放）' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '提交解除（未開放）' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '觀察解除（未開放）' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '改綁其他身分' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '重試 Rich Menu 回復' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '人工完成' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: '關閉' }));

    fireEvent.click(screen.getByRole('button', { name: /4\. 通知規則/ }));
    await screen.findByText('deposit_notice');
    expect(screen.getByRole('button', { name: /建立新通知規則/ })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: /deposit_notice/ }));
    expect(screen.getByRole('button', { name: /儲存並發布/ })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: '關閉' }));

    fireEvent.click(screen.getByRole('button', { name: /5\. 智慧客服 FAQ/ }));
    expect(screen.getByRole('button', { name: /新增 FAQ/ })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: /6\. 三方服務群組/ }));
    expect(screen.getByRole('button', { name: /建立三方群組/ })).toBeDisabled();

    expect(previewResolve).not.toHaveBeenCalled();
    expect(applyResolve).not.toHaveBeenCalled();
    expect(previewRevocation).not.toHaveBeenCalled();
    expect(applyRevocation).not.toHaveBeenCalled();
    expect(fetchSpy).not.toHaveBeenCalled();
  });
});
