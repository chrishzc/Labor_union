/**
 * File: line_management_page_real_data.test.tsx
 * Description: 驗證 LINE 管理頁以 typed client 呈現六個 canonical 頁籤、客服 KPI 與遮罩身分。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { CustomerServiceClient } from '../api/customer_service/customer_service_client';
import type { LineIdentityClient } from '../api/line_identity/line_identity_client';
import { lineRuntimeTargetClient } from '../api/line_runtime_targets/line_runtime_target_client';
import { customerServiceEscalationClient } from '../api/customer_service_escalations/customer_service_escalation_client';
import { lineDeliveryQueryClient } from '../api/line_delivery/line_delivery_query_client';
import { LineManagementPage } from '../pages/LineManagementPage';
import {
  CUSTOMER_SERVICE_DETAIL_FIXTURE,
  CUSTOMER_SERVICE_PAGE_FIXTURE,
  CUSTOMER_SERVICE_RESOLVE_PREVIEW_FIXTURE,
  CUSTOMER_SERVICE_SUMMARY_FIXTURE,
} from './fixtures/customer_service/customer_service_contract_fixtures';
import {
  BINDING_PAGE_FIXTURE,
  BOUND_IDENTITY_FIXTURE,
  REVOCATION_PREVIEW_FIXTURE,
  REVOCATION_REQUEST_FIXTURE,
} from './fixtures/line_identity/line_identity_contract_fixtures';
import {
  LINE_NOTIFICATION_RULES_CATALOG_FIXTURE,
  LINE_RICH_MENU_CONFIGURATION_FIXTURE,
  LINE_RICH_MENU_PUBLICATION_FIXTURE,
  LINE_RICH_MENU_PUBLICATION_PAGE_FIXTURE,
} from './fixtures/line_configuration_query_fixtures';

function clients(): { customer: CustomerServiceClient; identity: Pick<LineIdentityClient, 'listBindings' | 'getBinding' | 'previewRevocation' | 'applyRevocation'> } {
  return {
    customer: {
      getSummary: vi.fn().mockResolvedValue(CUSTOMER_SERVICE_SUMMARY_FIXTURE),
      listTickets: vi.fn().mockResolvedValue({
        ...CUSTOMER_SERVICE_PAGE_FIXTURE,
        items: CUSTOMER_SERVICE_PAGE_FIXTURE.items.map((item) => ({
          ...item,
          status: 'waiting' as const,
        })),
      }),
      getTicketDetail: vi.fn().mockResolvedValue(CUSTOMER_SERVICE_DETAIL_FIXTURE),
      previewResolve: vi.fn().mockResolvedValue(CUSTOMER_SERVICE_RESOLVE_PREVIEW_FIXTURE),
      applyResolve: vi.fn().mockResolvedValue(CUSTOMER_SERVICE_DETAIL_FIXTURE),
    },
    identity: {
      listBindings: vi.fn().mockResolvedValue(BINDING_PAGE_FIXTURE),
      getBinding: vi.fn().mockResolvedValue(BOUND_IDENTITY_FIXTURE),
      previewRevocation: vi.fn().mockResolvedValue(REVOCATION_PREVIEW_FIXTURE),
      applyRevocation: vi.fn().mockResolvedValue(REVOCATION_REQUEST_FIXTURE),
    },
  };
}

afterEach(() => vi.restoreAllMocks());

describe('LINE 管理頁真實資料呈現', () => {
  it('呈現六頁籤與客服 typed KPI／列表，不顯示 prototype 工單', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('unexpected network')));
    const { customer, identity } = clients();
    render(<LineManagementPage customerService={customer} lineIdentity={identity} />);

    await waitFor(() => expect(screen.getByText('#31')).toBeInTheDocument());
    expect(screen.getByText('2')).toBeInTheDocument();
    expect(screen.getByText('請開啟明細查看訊息')).toBeInTheDocument();
    expect(screen.queryByText('TKT-2026-001')).not.toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: /[1-6]\./ })).toHaveLength(6);
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it('typed backend 回傳空工單時顯示真實空狀態，不切換 runtime 模擬資料', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('unexpected network')));
    const { customer, identity } = clients();
    vi.mocked(customer.listTickets).mockResolvedValue({
      ...CUSTOMER_SERVICE_PAGE_FIXTURE,
      items: [],
      total: 0,
    });
    render(<LineManagementPage customerService={customer} lineIdentity={identity} />);

    await screen.findByRole('heading', { name: '目前沒有符合篩選條件的客服工單' });
    expect(screen.queryByRole('button', { name: /模擬預覽中|真實連線/ })).not.toBeInTheDocument();
    expect(screen.queryByText('ORD-2026-0815')).not.toBeInTheDocument();
    expect(document.body.textContent).not.toContain('U9a8');
  });

  it('切到身分頁才查詢清單，只呈現遮罩 LINE ID', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('unexpected network')));
    const { customer, identity } = clients();
    render(<LineManagementPage customerService={customer} lineIdentity={identity} />);
    fireEvent.click(screen.getByRole('button', { name: /3\. LINE 身分綁定/ }));

    await waitFor(() => expect(screen.getByText('U123••••cdef')).toBeInTheDocument());
    expect(screen.queryByText(BOUND_IDENTITY_FIXTURE.line_user_id)).not.toBeInTheDocument();
    expect(screen.queryByText(REVOCATION_PREVIEW_FIXTURE.provider_menu_id ?? '')).not.toBeInTheDocument();
    expect(identity.listBindings).toHaveBeenCalledTimes(1);
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it('篩選身分後仍以同一列的原始 identity 查詢明細，不得因索引錯位開啟他人資料', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('unexpected network')));
    const { customer, identity } = clients();
    const staffLineUserId = 'Ustaff567890abcdef1234567890abcdef';
    const staffBinding = {
      ...BOUND_IDENTITY_FIXTURE,
      line_user_id: staffLineUserId,
      status: 'pending_review' as const,
      subject_type: 'staff' as const,
      subject_reference: 'STAFF-FIXTURE-002',
      subject_name: '測試月嫂乙',
    };
    vi.mocked(identity.listBindings).mockImplementation(async (query) => ({
      items: query?.subject_type === 'staff'
        ? [staffBinding]
        : [BOUND_IDENTITY_FIXTURE, staffBinding],
      total: query?.subject_type === 'staff' ? 1 : 2,
      page: 1,
      page_size: 25,
    }));
    vi.mocked(identity.getBinding).mockResolvedValue(staffBinding);

    render(<LineManagementPage customerService={customer} lineIdentity={identity} />);
    fireEvent.click(screen.getByRole('button', { name: /3\. LINE 身分綁定/ }));
    await screen.findByText(/測試月嫂乙/);
    fireEvent.change(screen.getByDisplayValue('全部身分角色'), { target: { value: 'staff' } });
    await waitFor(() => expect(identity.listBindings).toHaveBeenLastCalledWith(
      expect.objectContaining({ subject_type: 'staff' }),
      expect.any(Object),
    ));
    await waitFor(() => expect(screen.getAllByRole('button', { name: /查看明細/ })).toHaveLength(1));
    fireEvent.click(screen.getByRole('button', { name: /查看明細/ }));

    await screen.findByText('月嫂');
    expect(identity.getBinding).toHaveBeenCalledWith(staffLineUserId, expect.any(Object));
    expect(screen.getByText(/尚未構成有效授權/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '預覽解除' })).not.toBeInTheDocument();
    expect(document.body.textContent).not.toContain(staffLineUserId);
  });

  it('人工升級預設只顯示業務欄位，技術校驗資料收在進階區', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('unexpected network')));
    const { customer, identity } = clients();
    render(<LineManagementPage customerService={customer} lineIdentity={identity} />);
    fireEvent.click(screen.getByRole('button', { name: /6\. 安全設定與人工升級/ }));

    const checksumLabel = screen.getByText('來源資料校驗碼');
    expect(checksumLabel).not.toBeVisible();
    expect(screen.getByLabelText('來源案件／事件參考')).toBeVisible();
    expect(document.body).not.toHaveTextContent(/Preview 指紋|SHA-256/);

    fireEvent.click(screen.getByText('進階來源資料'));
    expect(checksumLabel).toBeVisible();
    expect(screen.getByLabelText('自動化暫停範圍')).toBeVisible();
  });

  it('切離安全分頁會取消未完成 Preview，晚到結果不得重新掛回', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('unexpected network')));
    const { customer, identity } = clients();
    let resolvePreview!: (value: {
      operation: 'disable'; target_id: number; previous_state: 'active';
      resulting_state: 'disabled'; current_version: string;
      preview_fingerprint: string; apply_ready: true;
    }) => void;
    const previewPromise = new Promise<Parameters<typeof resolvePreview>[0]>((resolve) => {
      resolvePreview = resolve;
    });
    const runtimeTarget = {
      listTargets: vi.fn(async () => [{
        target_id: 8,
        target_kind: 'group' as const,
        display_label: '跨分頁測試群組',
        state: 'active' as const,
        minimum_status: 'critical' as const,
        current_version: 'version-8',
        updated_at: '2026-08-25T01:02:03+08:00',
      }]),
      listAdminCandidates: vi.fn(async () => []),
      previewSetEnabled: vi.fn(() => previewPromise),
      previewAddAdminTarget: vi.fn(),
      previewResetGroup: vi.fn(),
      addAdminTarget: vi.fn(),
      resetGroup: vi.fn(),
      setEnabled: vi.fn(),
    } as typeof lineRuntimeTargetClient;

    render(
      <LineManagementPage
        customerService={customer}
        lineIdentity={identity}
        runtimeTarget={runtimeTarget}
      />
    );
    fireEvent.click(screen.getByRole('button', { name: /6\. 安全設定與人工升級/ }));
    await screen.findByText('跨分頁測試群組');
    fireEvent.click(screen.getByRole('button', { name: '預覽停用' }));

    const requestOptions = vi.mocked(runtimeTarget.previewSetEnabled).mock.calls[0][2];
    expect(requestOptions?.signal?.aborted).toBe(false);
    fireEvent.click(screen.getByRole('button', { name: /1\. 客服工單與案件追蹤/ }));
    expect(requestOptions?.signal?.aborted).toBe(true);

    resolvePreview({
      operation: 'disable',
      target_id: 8,
      previous_state: 'active',
      resulting_state: 'disabled',
      current_version: 'version-8',
      preview_fingerprint: 'a'.repeat(64),
      apply_ready: true,
    });
    await Promise.resolve();
    fireEvent.click(screen.getByRole('button', { name: /6\. 安全設定與人工升級/ }));
    await screen.findByText('跨分頁測試群組');
    expect(screen.queryByText(/尚未建立.*停用/)).not.toBeInTheDocument();
    expect(screen.queryByRole('checkbox', { name: /我已確認此通知對象異動/ })).not.toBeInTheDocument();
    expect(runtimeTarget.setEnabled).not.toHaveBeenCalled();
  });

  it('人工升級 Preview 離頁後的晚到結果不會形成可套用狀態', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('unexpected network')));
    const { customer, identity } = clients();
    let resolvePreview!: (value: {
      operation: 'create'; escalation_id: null; before_workflow_status: 'absent';
      resulting_workflow_status: 'open'; before_hold_state: 'absent';
      resulting_hold_state: 'active'; current_escalation_version: null;
      current_ticket_version: null; preview_fingerprint: string; apply_ready: true;
    }) => void;
    const previewPromise = new Promise<Parameters<typeof resolvePreview>[0]>((resolve) => {
      resolvePreview = resolve;
    });
    const escalation = {
      ...customerServiceEscalationClient,
      previewCreate: vi.fn(() => previewPromise),
      create: vi.fn(),
    } as typeof customerServiceEscalationClient;

    render(
      <LineManagementPage
        customerService={customer}
        lineIdentity={identity}
        escalation={escalation}
      />
    );
    fireEvent.click(screen.getByRole('button', { name: /6\. 安全設定與人工升級/ }));
    fireEvent.change(screen.getByLabelText('來源案件／事件參考'), {
      target: { value: 'ticket-referral-31' },
    });
    fireEvent.click(screen.getByText('進階來源資料'));
    fireEvent.change(screen.getByLabelText('來源資料校驗碼'), {
      target: { value: 'b'.repeat(64) },
    });
    fireEvent.click(screen.getByRole('button', { name: /預覽建立人工客服升級/ }));

    const requestOptions = vi.mocked(escalation.previewCreate).mock.calls[0][1];
    expect(requestOptions?.signal?.aborted).toBe(false);
    fireEvent.click(screen.getByRole('button', { name: /1\. 客服工單與案件追蹤/ }));
    expect(requestOptions?.signal?.aborted).toBe(true);

    resolvePreview({
      operation: 'create',
      escalation_id: null,
      before_workflow_status: 'absent',
      resulting_workflow_status: 'open',
      before_hold_state: 'absent',
      resulting_hold_state: 'active',
      current_escalation_version: null,
      current_ticket_version: null,
      preview_fingerprint: 'c'.repeat(64),
      apply_ready: true,
    });
    await Promise.resolve();
    fireEvent.click(screen.getByRole('button', { name: /6\. 安全設定與人工升級/ }));
    expect(screen.queryByRole('checkbox', { name: /我已確認人工升級影響/ })).not.toBeInTheDocument();
    expect(escalation.create).not.toHaveBeenCalled();
  });

  it('發送任務使用 server page metadata 翻頁，末頁不再提供下一頁', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('unexpected network')));
    const { customer, identity } = clients();
    const baseTask = {
      id: 17,
      task_id: 17,
      task_type: 'follow_up',
      source_type: 'customer_service' as const,
      status: 'sent' as const,
      scheduled_at: '2026-08-23T10:00:00+08:00',
      completed_attempts: 1,
      max_attempts: 3,
      next_retry_at: null,
      sent_at: '2026-08-23T10:01:00+08:00',
      failed_at: null,
      created_at: '2026-08-23T09:00:00+08:00',
      updated_at: '2026-08-23T10:01:00+08:00',
    };
    const delivery = {
      ...lineDeliveryQueryClient,
      summary: vi.fn(async () => ({
        total: 26, pending: 0, processing: 0, sent: 26,
        retryable_failed: 0, failed: 0, cancelled: 0, overdue: 0,
        sent_today: 1, next_run_at: null, worker_running: true,
        worker_status: 'healthy' as const,
      })),
      list: vi.fn(async (query: { page?: number; pageSize?: number }) => query.page === 2
        ? {
            items: [{ ...baseTask, id: 26, task_id: 26, source_type: 'contract' as const }],
            page: 2, page_size: 25, total: 26, total_pages: 2,
          }
        : {
            items: [baseTask], page: 1, page_size: 25, total: 26, total_pages: 2,
          }),
    } as typeof lineDeliveryQueryClient;
    const lineConfiguration = {
      getNotificationRules: vi.fn(async () => LINE_NOTIFICATION_RULES_CATALOG_FIXTURE),
      getRichMenuConfiguration: vi.fn(async () => LINE_RICH_MENU_CONFIGURATION_FIXTURE),
      listRichMenuPublications: vi.fn(async () => ({
        ...LINE_RICH_MENU_PUBLICATION_PAGE_FIXTURE,
        items: [...LINE_RICH_MENU_PUBLICATION_PAGE_FIXTURE.items],
      })),
      getRichMenuPublication: vi.fn(async () => LINE_RICH_MENU_PUBLICATION_FIXTURE),
    };

    render(
      <LineManagementPage
        customerService={customer}
        lineIdentity={identity}
        lineConfiguration={lineConfiguration}
        delivery={delivery}
      />
    );
    fireEvent.click(screen.getByRole('button', { name: /4\. 通知規則目錄/ }));
    expect(await screen.findByText(/第 1／2 頁/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '上一頁' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: '下一頁' }));

    expect(await screen.findByText(/第 2／2 頁/)).toBeInTheDocument();
    expect(delivery.list).toHaveBeenLastCalledWith(
      { page: 2, pageSize: 25 },
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
    expect(screen.getByRole('button', { name: '下一頁' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '上一頁' })).toBeEnabled();
    expect(screen.getByText(/本頁 1 筆，共 26 筆/)).toBeInTheDocument();
  });
});
