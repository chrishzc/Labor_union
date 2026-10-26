/**
 * File: line_management_page_real_data.test.tsx
 * Description: 驗證 LINE 管理頁以 typed client 呈現既有 LINE 工作分頁與遮罩身分；客服提醒由 canonical reminder integration oracle 覆蓋，不把未知資料偽裝為零。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { CustomerServiceClient } from '../api/customer_service/customer_service_client';
import type { LineIdentityClient } from '../api/line_identity/line_identity_client';
import { lineRuntimeTargetClient } from '../api/line_runtime_targets/line_runtime_target_client';
import { sessionClient } from '../api/auth/session_client';
import { customerServiceEscalationClient } from '../api/customer_service_escalations/customer_service_escalation_client';
import { lineDeliveryQueryClient } from '../api/line_delivery/line_delivery_query_client';
import { lineOrderGroupQueryClient } from '../api/line_order_groups/line_order_group_query_client';
import type { LineConfigurationQueryClient } from '../api/line_configuration/line_configuration_query_client';
import type { LineRichMenuDraftClient } from '../api/line_rich_menu_draft/line_rich_menu_draft_client';
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
  it('切到身分頁才查詢清單，LINE ID 僅在明細以遮罩呈現', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('unexpected network')));
    const { customer, identity } = clients();
    render(<LineManagementPage customerService={customer} lineIdentity={identity} />);
    fireEvent.click(screen.getByRole('button', { name: '身分與授權' }));
    await screen.findByText(BOUND_IDENTITY_FIXTURE.subject_name);
    expect(screen.queryByText(BOUND_IDENTITY_FIXTURE.line_user_id)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '查看測試客戶甲的客戶身分' }));
    await screen.findByText('U123••••cdef');
    expect(screen.queryByText(REVOCATION_PREVIEW_FIXTURE.provider_menu_id ?? '')).not.toBeInTheDocument();
    expect(identity.listBindings).toHaveBeenCalledTimes(1);
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it('清單保留解除進度，移除以當頁假裝全域統計的角色 KPI', async () => {
    const { customer, identity } = clients();
    const revoked = { ...BOUND_IDENTITY_FIXTURE, line_user_id: 'U-history', subject_type: 'staff' as const, subject_name: '已解除月嫂', status: 'revoked' as const, revocation_status: 'manual_completed' as const };
    vi.mocked(identity.listBindings).mockResolvedValue({ items: [BOUND_IDENTITY_FIXTURE, revoked], total: 2, page: 1, page_size: 25 });
    render(<LineManagementPage customerService={customer} lineIdentity={identity} />);
    fireEvent.click(screen.getByRole('button', { name: '身分與授權' }));
    await screen.findByText('已解除月嫂');
    expect(document.querySelector('.line-kpi-grid')).toBeNull();
    expect(screen.getByText('訪客選單待修復')).toBeInTheDocument();
  });

  it('篩選後以正確的 LINE 與角色查詢明細，不因索引錯位開啟他人資料', async () => {
    const { customer, identity } = clients();
    const staffLineUserId = 'Ustaff567890abcdef1234567890abcdef';
    const staff = { ...BOUND_IDENTITY_FIXTURE, line_user_id: staffLineUserId, subject_type: 'staff' as const, subject_name: '測試月嫂乙', status: 'pending_review' as const };
    vi.mocked(identity.listBindings).mockImplementation(async query => ({ items: query?.subject_type === 'staff' ? [staff] : [BOUND_IDENTITY_FIXTURE, staff], total: query?.subject_type === 'staff' ? 1 : 2, page: 1, page_size: 25 }));
    vi.mocked(identity.getBinding).mockResolvedValue(staff);
    render(<LineManagementPage customerService={customer} lineIdentity={identity} />);
    fireEvent.click(screen.getByRole('button', { name: '身分與授權' }));
    await screen.findByText('測試月嫂乙');
    fireEvent.change(screen.getByRole('combobox', { name: '篩選身分角色' }), { target: { value: 'staff' } });
    await waitFor(() => expect(identity.listBindings).toHaveBeenLastCalledWith(expect.objectContaining({ subject_type: 'staff' }), expect.any(Object)));
    fireEvent.click(await screen.findByRole('button', { name: '查看測試月嫂乙的月嫂身分' }));
    await waitFor(() => expect(identity.getBinding).toHaveBeenCalledWith(staffLineUserId, expect.objectContaining({ subjectType: 'staff' })));
    expect(screen.queryByRole('button', { name: '解除此身分' })).not.toBeInTheDocument();
    expect(document.body.textContent).not.toContain(staffLineUserId);
  });

  it('人工升級預設只顯示業務欄位，技術校驗資料收在進階區', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('unexpected network')));
    const { customer, identity } = clients();
    const escalation = { ...customerServiceEscalationClient, previewCreate: vi.fn(), create: vi.fn() };
    render(<LineManagementPage customerService={customer} lineIdentity={identity} escalation={escalation} runtimeOnly />);

    const checksumLabel = screen.getByText('來源資料校驗碼');
    expect(checksumLabel).not.toBeVisible();
    expect(screen.getByLabelText('來源案件／事件參考')).toBeVisible();
    expect(document.body).not.toHaveTextContent(/Preview 指紋|SHA-256/);

    fireEvent.change(screen.getByLabelText('來源案件／事件參考'), {
      target: { value: 'ticket-referral-31' },
    });
    expect(screen.getByText('需先完成來源事件核對並補齊進階來源資料，才能建立。')).toBeVisible();
    const createButton = screen.getByRole('button', { name: '建立人工客服升級' });
    expect(createButton).toBeDisabled();
    fireEvent.click(createButton);
    expect(escalation.previewCreate).not.toHaveBeenCalled();

    fireEvent.click(screen.getByText('進階來源資料'));
    expect(checksumLabel).toBeVisible();
    expect(screen.getByLabelText('自動化暫停範圍')).toBeVisible();
    fireEvent.change(screen.getByLabelText('來源資料校驗碼'), { target: { value: 'b'.repeat(64) } });
    expect(createButton).toBeEnabled();
    fireEvent.change(screen.getByLabelText('自動化暫停範圍'), { target: { value: '   ' } });
    expect(createButton).toBeDisabled();
    expect(screen.getByText('需先完成來源事件核對並補齊進階來源資料，才能建立。')).toBeVisible();
    fireEvent.click(createButton);
    expect(escalation.previewCreate).not.toHaveBeenCalled();
    expect(escalation.create).not.toHaveBeenCalled();
  });

  it('沒有已連結 LINE 的管理員候選時顯示明確原因，不留下無說明的停用控制', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('unexpected network')));
    const { customer, identity } = clients();
    const runtimeTarget = {
      ...lineRuntimeTargetClient,
      listTargets: vi.fn(async () => []),
      listAdminCandidates: vi.fn(async () => []),
    } as typeof lineRuntimeTargetClient;

    render(
      <LineManagementPage
        customerService={customer}
        lineIdentity={identity}
        runtimeTarget={runtimeTarget}
        runtimeOnly
      />
    );

    await screen.findByText(/目前沒有已連結 LINE 且可加入的管理員/);
    expect(screen.queryByLabelText('新增管理員對象：')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '➕ 預覽新增通知對象' })).not.toBeInTheDocument();
  });

  it('案件群組依 server metadata 翻到第 2 頁並鎖定末頁', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('unexpected network')));
    const { customer, identity } = clients();
    vi.spyOn(lineOrderGroupQueryClient, 'workspaceList').mockImplementation(async (query) => ({
      items: [{
        case_no: query?.page === 2 ? 'CASE-26' : 'CASE-1',
        status: 'active',
        customer_name: '測試客戶',
        bound_at: null,
        last_invitation_at: null,
        members: [],
        latest_event: null,
      }],
      page: query?.page ?? 1,
      page_size: query?.pageSize ?? 25,
      total: 26,
      total_pages: 2,
    }));

    render(<LineManagementPage customerService={customer} lineIdentity={identity} />);
    fireEvent.click(screen.getByRole('button', { name: '案件群組' }));

    await screen.findByText('CASE-1');
    expect(lineOrderGroupQueryClient.workspaceList).toHaveBeenLastCalledWith(
      { page: 1, pageSize: 25, search: undefined, status: undefined },
      expect.any(Object),
    );
    fireEvent.click(screen.getByRole('button', { name: '下一頁案件群組' }));
    await screen.findByText('CASE-26');
    expect(lineOrderGroupQueryClient.workspaceList).toHaveBeenLastCalledWith(
      { page: 2, pageSize: 25, search: undefined, status: undefined },
      expect.any(Object),
    );
    expect(screen.getByRole('button', { name: '下一頁案件群組' })).toBeDisabled();
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
        target_kind: 'admin_user' as const,
        display_label: '跨分頁測試管理員',
        state: 'active' as const,
        minimum_status: 'critical' as const,
        current_version: 'version-8',
        updated_at: '2026-08-25T01:02:03+08:00',
      }, {
        target_id: 9, target_kind: 'group' as const, display_label: '已退役群組',
        state: 'active' as const, minimum_status: 'critical' as const,
        current_version: 'version-9', updated_at: '2026-08-25T01:02:03+08:00',
      }]),
      listAdminCandidates: vi.fn(async () => []),
      getPreferences: vi.fn(async () => ({
        customer_service: true,
        dispatch_matching: true,
        staff_leave_urgent: true,
        system_health: false,
        contract_signing: true,
      })),
      updatePreferences: vi.fn(async (_targetId, preferences) => preferences),
      previewSetEnabled: vi.fn(() => previewPromise),
      previewAddAdminTarget: vi.fn(),
      previewResetGroup: vi.fn(),
      addAdminTarget: vi.fn(),
      resetGroup: vi.fn(),
      setEnabled: vi.fn(),
    } as typeof lineRuntimeTargetClient;

    const { unmount } = render(
      <LineManagementPage
        customerService={customer}
        lineIdentity={identity}
        runtimeTarget={runtimeTarget}
        runtimeOnly
      />
    );
    await screen.findByText('跨分頁測試管理員');
    expect(screen.queryByText('已退役群組')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '重設群組' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '停用' }));

    const requestOptions = vi.mocked(runtimeTarget.previewSetEnabled).mock.calls[0][2];
    expect(requestOptions?.signal?.aborted).toBe(false);
    unmount();
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
    render(<LineManagementPage customerService={customer} lineIdentity={identity} runtimeTarget={runtimeTarget} runtimeOnly />);
    await screen.findByText('跨分頁測試管理員');
    expect(screen.queryByText(/尚未建立.*停用/)).not.toBeInTheDocument();
    expect(screen.queryByRole('checkbox', { name: /我已確認此通知對象異動/ })).not.toBeInTheDocument();
    expect(runtimeTarget.setEnabled).not.toHaveBeenCalled();
    expect(runtimeTarget.previewResetGroup).not.toHaveBeenCalled();
    expect(runtimeTarget.resetGroup).not.toHaveBeenCalled();
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

    const { unmount } = render(
      <LineManagementPage
        customerService={customer}
        lineIdentity={identity}
        escalation={escalation}
        runtimeOnly
      />
    );
    fireEvent.change(screen.getByLabelText('來源案件／事件參考'), {
      target: { value: 'ticket-referral-31' },
    });
    fireEvent.click(screen.getByText('進階來源資料'));
    fireEvent.change(screen.getByLabelText('來源資料校驗碼'), {
      target: { value: 'b'.repeat(64) },
    });
    fireEvent.click(screen.getByRole('button', { name: '建立人工客服升級' }));

    const requestOptions = vi.mocked(escalation.previewCreate).mock.calls[0][1];
    expect(requestOptions?.signal?.aborted).toBe(false);
    unmount();
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
    render(<LineManagementPage customerService={customer} lineIdentity={identity} escalation={escalation} runtimeOnly />);
    expect(screen.queryByRole('checkbox', { name: /我已確認人工升級影響/ })).not.toBeInTheDocument();
    expect(escalation.create).not.toHaveBeenCalled();
  });

  it('通知頁統一歡迎與內容設定，舊發送連結不再查詢獨立發送紀錄', async () => {
    window.history.replaceState(null, '', '#line-management?tab=push_queue&notice=delivery');
    const { customer, identity } = clients();
    const delivery = { ...lineDeliveryQueryClient, summary: vi.fn(), list: vi.fn(), detail: vi.fn() };
    const lineConfiguration = {
      getNotificationRules: vi.fn(async () => LINE_NOTIFICATION_RULES_CATALOG_FIXTURE),
      getRichMenuConfiguration: vi.fn(), listRichMenuPublications: vi.fn(), getRichMenuPublication: vi.fn(),
    };
    const onboardingClient = {
      get: vi.fn(async () => ({ template_id: 'customer_onboarding_welcome', content: '歡迎加入 {url}', revision: 1, sample_preview: '歡迎加入', variables: ['url'] })),
      update: vi.fn(), preview: vi.fn(),
    };
    const notificationTemplateClient = {
      get: vi.fn(async (ruleId: string) => ({ rule_id: ruleId, template_id: 'deposit_template', name: '訂金通知', content: '正式通知內容', revision: 1, variables: [], sample_preview: '正式通知內容' })),
      update: vi.fn(),
    };
    render(<LineManagementPage customerService={customer} lineIdentity={identity} lineConfiguration={lineConfiguration} delivery={delivery} onboardingClient={onboardingClient} notificationTemplateClient={notificationTemplateClient} />);
    await screen.findByRole('button', { name: '編輯新好友歡迎訊息內容' });
    expect(screen.queryByRole('button', { name: '發送佇列與歷程' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Onboarding 訊息' })).not.toBeInTheDocument();
    expect(delivery.summary).not.toHaveBeenCalled(); expect(delivery.list).not.toHaveBeenCalled(); expect(delivery.detail).not.toHaveBeenCalled();
    expect(window.location.hash).not.toContain('notice=');
    window.history.replaceState(null, '', '/');
  });

  it('離開通知頁會取消內容查詢，晚到結果不開啟編輯頁', async () => {
    const { customer, identity } = clients();
    const lineConfiguration = {
      getNotificationRules: vi.fn(async () => LINE_NOTIFICATION_RULES_CATALOG_FIXTURE),
      getRichMenuConfiguration: vi.fn(), listRichMenuPublications: vi.fn(), getRichMenuPublication: vi.fn(),
    };
    const onboardingClient = { get: vi.fn(() => new Promise<never>(() => {})), update: vi.fn(), preview: vi.fn() };
    render(<LineManagementPage customerService={customer} lineIdentity={identity} lineConfiguration={lineConfiguration} onboardingClient={onboardingClient} />);
    fireEvent.click(screen.getByRole('button', { name: '通知與發送' }));
    await waitFor(() => expect(onboardingClient.get).toHaveBeenCalled());
    const options = vi.mocked(onboardingClient.get).mock.calls[0] as unknown as [{ signal: AbortSignal }];
    fireEvent.click(screen.getByRole('button', { name: '身分與授權' }));
    expect(options[0].signal.aborted).toBe(true);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('圖文選單直接進入編輯，移除發布紀錄入口並停止清單查詢', async () => {
    vi.spyOn(sessionClient, 'getUser').mockReturnValue(null);
    const { customer, identity } = clients();
    const listRichMenuPublications = vi.fn();
    const lineConfiguration: LineConfigurationQueryClient = {
      getNotificationRules: vi.fn(async () => LINE_NOTIFICATION_RULES_CATALOG_FIXTURE),
      getRichMenuConfiguration: vi.fn(async () => LINE_RICH_MENU_CONFIGURATION_FIXTURE),
      listRichMenuPublications,
      getRichMenuPublication: vi.fn(async () => LINE_RICH_MENU_PUBLICATION_FIXTURE),
    };
    const richMenuDraft: LineRichMenuDraftClient = {
      query: vi.fn(async () => ({
        kind: 'rich_menus' as const,
        revision: 1,
        definition: LINE_RICH_MENU_CONFIGURATION_FIXTURE.definition as any,
        publication_locks: LINE_RICH_MENU_CONFIGURATION_FIXTURE.definition.menus.map((menu) => ({
          menu_definition_id: menu.id,
          configuration_revision: 1,
          state: 'editable' as const,
          readonly_reason: null,
        })),
      })),
      preview: vi.fn(),
      apply: vi.fn(),
    };

    render(
      <LineManagementPage
        customerService={customer}
        lineIdentity={identity}
        lineConfiguration={lineConfiguration}
        richMenuDraft={richMenuDraft}
      />
    );
    fireEvent.click(screen.getByRole('button', { name: '圖文選單' }));
    await screen.findByRole('button', { name: '外觀與名稱' });
    expect(screen.queryByRole('button', { name: '發布紀錄' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '編輯選單' })).not.toBeInTheDocument();
    expect(screen.queryByRole('navigation', { name: '圖文選單工作頁' })).not.toBeInTheDocument();
    expect(listRichMenuPublications).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: '發布至 LINE' })).toBeDisabled();
    expect(screen.getByText(/請先登入/)).toBeInTheDocument();
  });
});
