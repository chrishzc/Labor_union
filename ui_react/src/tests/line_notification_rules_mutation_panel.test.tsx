import { UnsavedChangesProvider } from '../components/UnsavedChanges';
/**
 * File: line_notification_rules_mutation_panel.test.tsx
 * Description: 驗證一次點擊送出、選填原因、內部 Preview／Apply 一致性及唯讀訊息預覽。
 */
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { LineNotificationRulesCatalog } from '../api/line_configuration/line_configuration_query_schemas';
import type { LineNotificationRulesMutationClient } from '../api/line_notification_rules/line_notification_rules_mutation_client';
import type { LineNotificationTemplateClient } from '../api/line_notification_rules/line_notification_template_client';
import { LineNotificationRulesMutationError } from '../api/line_notification_rules/line_notification_rules_mutation_errors';
import { LineNotificationRulesMutationPanel } from '../components/LineNotificationRulesMutationPanel';
import { useState } from 'react';
import { LineNotificationWorkbench } from '../components/LineNotificationWorkbench';
import type { LineOnboardingClient } from '../api/line_onboarding/line_onboarding_client';
import type { LineConfigurationQueryClient } from '../api/line_configuration/line_configuration_query_client';
import { ApiHttpError } from '../api/shared/typed_errors';
import type { LineMessagePreviewClient, PreviewNode } from '../api/line_notification_rules/line_message_preview_client';
import { lineMessagePreviewClient } from '../api/line_notification_rules/line_message_preview_client';
import { LineMessageFlow } from '../components/LineMessageFlow';
import { LineManagementPage } from '../pages/LineManagementPage';
import { FinanceWarningWorkspace } from '../components/FinanceWarningWorkspace';
import { lineConfigurationQueryClient } from '../api/line_configuration/line_configuration_query_client';
import { lineOnboardingClient } from '../api/line_onboarding/line_onboarding_client';
import { lineNotificationTemplateClient } from '../api/line_notification_rules/line_notification_template_client';

const FINGERPRINT = '0123456789abcdef'.repeat(4);
const CATALOG: LineNotificationRulesCatalog = {
  revision: 3,
  definition: {
    rules: [{
      id: 'deposit_notice',
      event_code: 'deposit_confirmed',
      recipient_selector: 'client',
      template_id: 'deposit_template',
      enabled: true,
      schedule: { kind: 'immediate' },
      frequency: { kind: 'once' },
      predicates: [],
    }],
  },
};

const CARD_CATALOG: LineNotificationRulesCatalog = {
  revision: 3,
  definition: {
    rules: [{
      id: 'leave_confirmation',
      event_code: 'scheduling.leave.extension_requested',
      recipient_selector: 'client.bound_case',
      template_id: 'leave_confirmation_card',
      enabled: false,
      schedule: { kind: 'immediate' },
      frequency: { kind: 'once' },
      predicates: [],
    }],
  },
};

function templateClient(overrides: Partial<LineNotificationTemplateClient> = {}): LineNotificationTemplateClient {
  return {
    get: vi.fn().mockResolvedValue({
      rule_id: 'deposit_notice',
      template_id: 'deposit_template',
      name: '訂金確認通知',
      content: '案件 {case_no} 已確認訂金。',
      revision: 7,
      variables: ['case_no'],
      sample_preview: '案件〔case_no〕已確認訂金。',
    }),
    update: vi.fn(),
    ...overrides,
  };
}

afterEach(() => vi.restoreAllMocks());

function flowWorkbench() {
  const catalog = { revision: 11, definition: { rules: [
    { id: 'current-payment-rule', event_code: 'client.second_payment_settled', recipient_selector: 'case_group', template_id: 'LINE-SECOND-PAYMENT-SETTLED-TEXT-V1', enabled: false, schedule: { kind: 'immediate' }, frequency: { kind: 'once' }, predicates: [] },
  ] } } satisfies LineNotificationRulesCatalog;
  const clients = contentWorkbench(catalog);
  vi.mocked(clients.templates.get).mockImplementation(async id => ({ rule_id: id, template_id: id === 'current-payment-rule' ? 'LINE-SECOND-PAYMENT-SETTLED-TEXT-V1' : 'LU96-M1-LEAVE-EXTENSION-CARD-V1', name: id === 'current-payment-rule' ? '目前正式第二期款入帳通知' : '目前正式請假卡', content: '目前正式文案 {case_no}', revision: 19, variables: ['case_no'], sample_preview: '目前正式文案 DEMO-CASE-001' }));
  const builtin = (id: string, name: string) => ({ id, name, template_id: null, format: 'flex' as const, requires_case: false, requires_staff: false, builtin: true, allows_draft: false });
  vi.mocked(clients.previews.catalog).mockResolvedValue([
    { ...builtin('welcome', '新好友歡迎訊息'), template_id: 'customer_onboarding_welcome', builtin: false, format: 'text' },
    ...catalog.definition.rules.map(rule => ({ ...builtin(rule.id, rule.id === 'current-payment-rule' ? '目前正式第二期款提醒' : '目前正式請假卡'), template_id: rule.template_id, builtin: false })),
    { ...builtin('service-day-log-reminder', '服務日誌－工會發送案件群組提醒'), format: 'text' },
    builtin('service-start-inquiry', '服務開始－代班接案意願詢問'),
    builtin('card-candidate-information-1', '目前訂單資訊一'), builtin('card-candidate-information-2', '目前訂單資訊二'), builtin('card-candidate-information-3', '目前每週說明'),
    builtin('deposit-reminder', '目前訂金提醒卡'), builtin('deposit-settled', '目前訂金入帳卡'),
  ]);
  return { ...clients, catalog };
}

function financeContentClients(clients:ReturnType<typeof flowWorkbench>){
  vi.spyOn(lineConfigurationQueryClient,'getNotificationRules').mockImplementation(clients.configuration.getNotificationRules);
  vi.spyOn(lineOnboardingClient,'get').mockImplementation(clients.onboarding.get);
  vi.spyOn(lineOnboardingClient,'update').mockImplementation(clients.onboarding.update);
  vi.spyOn(lineNotificationTemplateClient,'get').mockImplementation(clients.templates.get);
  vi.spyOn(lineNotificationTemplateClient,'update').mockImplementation(clients.templates.update);
}

describe('LINE 精簡流程圖與正式訊息定位', () => {

  it('管理員告警規則保留於設定快照，但不列編輯項目或查詢文案', async () => {
    const alertRules = [
      { ...CATALOG.definition.rules[0], id: 'retired-runtime-alert', event_code: 'runtime.alert.review_required', template_id: 'LU96-M4-SAFE-ALERT-CARD-V1' },
      { ...CATALOG.definition.rules[0], id: 'retired-complaint-alert', event_code: 'complaint.ingress.hold_high_ticket', template_id: 'LU96-M4-COMPLAINT-HIGH-CARD-V1' },
    ];
    const { Harness, templates } = contentWorkbench({ ...CATALOG, definition: { rules: [...CATALOG.definition.rules, ...alertRules] } });
    render(<Harness />);
    await screen.findByRole('button', { name: '編輯訂金確認通知內容' });
    expect(vi.mocked(templates.get).mock.calls.map(([id]) => id)).toEqual(['deposit_notice']);
    fireEvent.change(screen.getByRole('searchbox', { name: '搜尋通知名稱或內容' }), { target: { value: '告警' } });
    expect(await screen.findByText('沒有符合條件的通知')).toBeInTheDocument();
  });


  it('服務當天受理與進度仍可定位，管理員告警改為內部主動查詢', async () => {
    const { configuration, previews, catalog } = flowWorkbench(); const onOpen = vi.fn();
    const current = await previews.catalog();
    const fixed = [
      ['service-start-normal-received', '服務當天－服務正常受理回覆'],
      ['service-start-help-received', '服務當天－協助需求受理回覆'],
      ['service-progress', '服務進度查詢結果'],
      ['service-progress-unbound', '服務進度－未綁定提示'],
      ['runtime-system-health', '系統健康異常－管理員通知'],
    ].map(([id, name]) => ({ id, name, template_id: null, format: 'text' as const, requires_case: false, requires_staff: false, builtin: true, allows_draft: false }));
    const alerts = [
      { ...catalog.definition.rules[0], id: 'current-safe-alert', event_code: 'runtime.alert.review_required', template_id: 'LU96-M4-SAFE-ALERT-CARD-V1', recipient_selector: 'admin.review_actor' },
      { ...catalog.definition.rules[0], id: 'current-complaint-alert', event_code: 'complaint.ingress.hold_high_ticket', template_id: 'LU96-M4-COMPLAINT-HIGH-CARD-V1', recipient_selector: 'customer_service.claim_owner' },
    ];
    vi.mocked(configuration.getNotificationRules).mockResolvedValue({ ...catalog, definition: { rules: [...catalog.definition.rules, ...alerts] } });
    vi.mocked(previews.catalog).mockResolvedValue([...current, ...fixed, ...alerts.map(rule => ({ ...fixed[0], id: rule.id, name: rule.id, template_id: rule.template_id, builtin: false }))]);
    render(<LineMessageFlow configuration={configuration} previews={previews} onOpenMessage={onOpen} />);
    fireEvent.click(await screen.findByRole('button', { name: /5 開始服務/ }));
    fireEvent.click(screen.getByRole('button', { name: '服務開始當天 2 則訊息 查看訊息' }));
    fireEvent.click(screen.getByRole('button', { name: /服務當天－協助需求受理回覆/ }));
    expect(onOpen).toHaveBeenLastCalledWith('service-start-help-received');
    fireEvent.click(screen.getByRole('tab', { name: '客服與支援' }));
    fireEvent.click(screen.getByRole('button', { name: /1 開啟服務/ }));
    fireEvent.click(screen.getByRole('button', { name: '查詢服務進度 2 則訊息 查看訊息' }));
    fireEvent.click(screen.getByRole('button', { name: /服務進度查詢結果/ }));
    expect(onOpen).toHaveBeenLastCalledWith('service-progress');
    fireEvent.click(screen.getByRole('button', { name: /3 人工處理/ }));
    expect(screen.getByText('查看系統狀態與客服待辦')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /管理員個人告警|current-safe-alert|current-complaint-alert/ })).not.toBeInTheDocument();
    expect(onOpen).toHaveBeenLastCalledWith('service-progress');
    expect(previews.render).not.toHaveBeenCalled(); expect(previews.subjects).not.toHaveBeenCalled();
  });

  it('完整列出簽約、日期自助、各期人工提醒與共用換人流程，查閱不發送或儲存', async () => {
    const { configuration, previews, templates } = flowWorkbench(); const onOpen=vi.fn();
    const current=await previews.catalog();
    const additions=[['contract-signing-client','簽署提醒－客戶'],['contract-signing-staff','簽署提醒－月嫂'],
      ['payment-overdue-deposit','訂金逾期－人工提醒客戶'],['payment-overdue-first','第一期款逾期－人工提醒案件群組'],['payment-overdue-second','第二期款逾期－人工提醒案件群組']];
    vi.mocked(previews.catalog).mockResolvedValue([...current,...additions.map(([id,name])=>({id,name,template_id:null,format:'text' as const,requires_case:false,requires_staff:false,builtin:true,allows_draft:false}))]);
    render(<LineMessageFlow configuration={configuration} previews={previews} onOpenMessage={onOpen}/>);
    expect(screen.getByText(/簽約與訂金付款可先後交錯/)).toBeInTheDocument();
    fireEvent.click(await screen.findByRole('button',{name:/3 簽約/}));
    fireEvent.click(screen.getByRole('button',{name:/人工發送簽署提醒/}));
    fireEvent.click(screen.getByRole('button',{name:/簽署提醒－客戶/}));
    expect(onOpen).toHaveBeenCalledWith('contract-signing-client');
    fireEvent.click(screen.getByRole('button',{name:/4 收款與建群/}));
    expect(screen.getByRole('button',{name:/訂金逾期－私訊補寄與人工提醒/})).toBeEnabled();
    fireEvent.click(screen.getByRole('button',{name:/5 開始服務/}));
    expect(screen.getByText('月嫂提交已協調的開始日')).toBeInTheDocument();
    expect(screen.getByText('自助／內部操作')).toBeInTheDocument();
    expect(screen.getByText(/無衝突即更新正式日期/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button',{name:/第一期款逾期－私訊補寄與人工提醒/}));
    expect(onOpen).toHaveBeenCalledWith('payment-overdue-first');
    fireEvent.click(screen.getByRole('button',{name:/6 持續服務與異動/}));
    expect(screen.getByRole('button',{name:/第二期款逾期－私訊補寄與人工提醒/})).toBeEnabled();
    expect(screen.getByRole('button',{name:/請假、順延、代班與換人（共用流程）/})).toBeEnabled();
    expect(previews.render).not.toHaveBeenCalled(); expect(templates.update).not.toHaveBeenCalled();
  });

  it('缺少完工規則或模板時清楚標示設定缺漏，不提供假的可用訊息', async () => {
    const { configuration, previews } = flowWorkbench(); const onOpen = vi.fn();
    render(<LineMessageFlow configuration={configuration} previews={previews} onOpenMessage={onOpen} />);
    fireEvent.click(await screen.findByRole('button', { name: '7 完工與結案 缺少訊息設定' }));
    expect(screen.getByRole('button', { name: /服務完工與滿意度問卷邀請 缺少訊息設定/ })).toBeDisabled();
    expect(screen.getByText('此訊息的規則或模板尚未設定，請先同步通知設定。')).toBeInTheDocument();
    expect(onOpen).not.toHaveBeenCalled(); expect(previews.render).not.toHaveBeenCalled();
  });

  it('客服說明統一由 AI 客服 LIFF 提供，通知流程不再提供重複編輯', async () => {
    const { configuration, previews } = flowWorkbench(); const onOpen = vi.fn();
    const current = await previews.catalog();
    vi.mocked(previews.catalog).mockResolvedValue([...current, ...['service-menu'].map(id => ({id,name:id,template_id:null,format:'text' as const,requires_case:false,requires_staff:false,builtin:true,allows_draft:false}))]);
    render(<LineMessageFlow configuration={configuration} previews={previews} onOpenMessage={onOpen} />);
    fireEvent.click(screen.getByRole('tab', { name: '客服與支援' }));
    await screen.findByText(/一般留言不啟動聊天室 AI/);
    fireEvent.click(await screen.findByRole('button', { name: '1 開啟服務 1 則訊息' }));
    expect(screen.getByText(/統一在 AI 客服 LIFF 查看常見問答或提問/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /收費與補助說明.*調整訊息/ })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /查看服務導覽.*調整訊息/ }));
    expect(onOpen).toHaveBeenCalledWith('service-menu');
  });

  it('服務完工通知沿既有流程導向可編輯問卷邀請，網址可後續加入', async () => {
    const { configuration, previews, catalog } = flowWorkbench();
    const onOpen = vi.fn();
    const descriptor = { id: 'LINE-SERVICE-COMPLETION-V1', template_id: 'LINE-SERVICE-COMPLETION-TEXT-V1',
      name: '服務完工－滿意度問卷邀請', format: 'text' as const, requires_case: false, requires_staff: false, builtin: false, allows_draft: false };
    const descriptors = await previews.catalog();
    vi.mocked(previews.catalog).mockResolvedValue([...descriptors, descriptor]);
    vi.mocked(configuration.getNotificationRules).mockResolvedValue({ ...catalog, definition: { rules: [...catalog.definition.rules,
      { id: descriptor.id, event_code: 'order.service_completed', recipient_selector: 'case_group', template_id: descriptor.template_id,
        enabled: true, schedule: { kind: 'immediate' }, frequency: { kind: 'once' }, predicates: [] }] } });
    render(<LineMessageFlow configuration={configuration} previews={previews} onOpenMessage={onOpen} />);
    fireEvent.click(await screen.findByRole('button', { name: '7 完工與結案 1 則訊息' }));
    fireEvent.click(screen.getByRole('button', { name: '服務完工與滿意度問卷邀請 已啟用 調整訊息' }));
    expect(onOpen).toHaveBeenCalledExactlyOnceWith(descriptor.id);
    expect(previews.render).not.toHaveBeenCalled();
    expect(document.querySelectorAll('.line-flow-step')).toHaveLength(7);
  });

  it('預設顯示完整七個步驟；展開後使用目前目錄名稱，選定多則中的正確訊息', async () => {
    const { configuration, previews } = flowWorkbench(); const onOpen = vi.fn();
    render(<LineMessageFlow configuration={configuration} previews={previews} onOpenMessage={onOpen} />);
    const first = await screen.findByRole('button', { name: '1 初步候選聯絡 3 則訊息' });
    expect(screen.queryByRole('button', { name: /目前訂單資訊/ })).not.toBeInTheDocument();
    expect(document.querySelectorAll('.line-flow-step')).toHaveLength(7);
    fireEvent.click(first);
    fireEvent.click(screen.getByRole('button', { name: '寄送案件資訊 3 則訊息 查看訊息' }));
    fireEvent.click(screen.getByRole('button', { name: /目前訂單資訊二/ }));
    expect(onOpen).toHaveBeenCalledExactlyOnceWith('card-candidate-information-2');
    expect(previews.render).not.toHaveBeenCalled(); expect(previews.subjects).not.toHaveBeenCalled();
  });

  it('依正式規則呈現停用，shadow rule 關閉仍顯示流程控制，並用目前 rule ID 導覽', async () => {
    const { configuration, previews } = flowWorkbench(); const onOpen = vi.fn();
    render(<LineMessageFlow configuration={configuration} previews={previews} onOpenMessage={onOpen} />);
    fireEvent.click(await screen.findByRole('button', { name: '6 持續服務與異動 3 則訊息' }));
    expect(screen.getByRole('button', { name: '日誌連續缺漏－工會決定提醒 由流程控制 調整訊息' })).toBeEnabled();
    expect(screen.getByRole('button', { name: '第二期款到期與入帳 已停用 調整訊息' })).toBeEnabled();
    expect(screen.getByRole('button', { name: '請假、順延、代班與換人（共用流程） 由流程控制 調整訊息' })).toBeEnabled();
    fireEvent.click(screen.getByRole('button', { name: '第二期款到期與入帳 已停用 調整訊息' }));
    expect(onOpen).toHaveBeenCalledExactlyOnceWith('current-payment-rule');
    expect(screen.queryByRole('switch')).not.toBeInTheDocument();
  });

  it('返回流程時重查啟用狀態並保留步驟', async () => {
    const { configuration, previews, catalog } = flowWorkbench(); const onOpen = vi.fn();
    const ui = (active: boolean) => <LineMessageFlow active={active} configuration={configuration} previews={previews} onOpenMessage={onOpen} />;
    const { rerender } = render(ui(true));
    fireEvent.click(await screen.findByRole('button', { name: '6 持續服務與異動 3 則訊息' }));
    expect(screen.getByText('已停用')).toBeInTheDocument();
    rerender(ui(false));
    vi.mocked(configuration.getNotificationRules).mockResolvedValue({ ...catalog, definition: { rules: catalog.definition.rules.map(rule => ({ ...rule, enabled: true })) } });
    rerender(ui(true));
    await screen.findByText('已啟用');
    expect(screen.getByRole('button', { name: '6 持續服務與異動 3 則訊息' })).toHaveAttribute('aria-expanded', 'true');
    expect(configuration.getNotificationRules).toHaveBeenCalledTimes(2);
  });

  it('查詢失敗不顯示假件數或舊狀態，重試成功後才可操作', async () => {
    const { configuration, previews } = flowWorkbench();
    vi.mocked(configuration.getNotificationRules).mockRejectedValueOnce(new Error('raw mysql private detail'));
    render(<LineMessageFlow configuration={configuration} previews={previews} onOpenMessage={vi.fn()} />);
    expect(await screen.findByRole('alert')).toHaveTextContent('流程訊息暫時無法載入');
    expect(document.body).not.toHaveTextContent('raw mysql');
    expect(document.querySelector('.line-flow-step')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: '重新載入流程訊息' }));
    await screen.findByRole('button', { name: '1 初步候選聯絡 3 則訊息' });
  });

  it('人工日誌提醒跳到共用公版，顯示工會決定及流程控制，不提供儲存或啟用開關', async () => {
    const clients = flowWorkbench(); const { configuration, previews, templates, onboarding } = clients;
    vi.mocked(previews.render).mockResolvedValue({ status: 'ready', note: '公版範例', format: 'text',
      text: '請 範例月嫂 補上尚未填寫的服務日誌，謝謝。', bubbles: [], facts: [{ id: '月嫂姓名（staff_name）', label: '範例月嫂' }] });
    vi.spyOn(lineMessagePreviewClient, 'catalog').mockImplementation(previews.catalog);
    vi.spyOn(lineMessagePreviewClient, 'render').mockImplementation(previews.render);
    window.history.replaceState(null, '', '#line-management?tab=message_flow');
    const { unmount } = render(<UnsavedChangesProvider><LineManagementPage lineConfiguration={configuration} notificationTemplateClient={templates} onboardingClient={onboarding} /></UnsavedChangesProvider>);
    fireEvent.click(await screen.findByRole('button', { name: '6 持續服務與異動 3 則訊息' }));
    fireEvent.click(screen.getByRole('button', { name: '日誌連續缺漏－工會決定提醒 由流程控制 調整訊息' }));
    expect(window.location.hash).toContain('message=service-day-log-reminder');
    await waitFor(()=>expect(window.location.hash).toContain('tab=push_queue'));
    await screen.findByText('請 範例月嫂 補上尚未填寫的服務日誌，謝謝。');
    fireEvent.click(screen.getByText('公版預覽資料', { selector: 'summary' }));
    expect(screen.getByRole('region', { name: '帶入欄位與值' })).toHaveTextContent('月嫂姓名（staff_name）範例月嫂');
    expect(screen.getByRole('button', { name: '儲存內容' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: '發送設定' }));
    expect(screen.getByText('案件群組', { selector: 'dd' })).toBeInTheDocument();
    expect(screen.getByText('由流程控制', { selector: 'dd' })).toBeInTheDocument();
    expect(screen.getByText('由工會逐次決定，點「發送提醒」後建立寄送工作')).toBeInTheDocument();
    expect(screen.queryByRole('checkbox', { name: '啟用此規則' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '修改發送設定' })).not.toBeInTheDocument();
    fireEvent.change(screen.getByRole('combobox', { name: '啟用狀態' }), { target: { value: 'enabled' } });
    expect(screen.queryByRole('button', { name: '查看服務日誌－工會發送案件群組提醒內容' })).not.toBeInTheDocument();
    expect(templates.update).not.toHaveBeenCalled();
    expect(onboarding.update).not.toHaveBeenCalled();
    expect(previews.subjects).not.toHaveBeenCalled();
    unmount(); window.history.replaceState(null, '', '/');
  });

  it('從頁面流程跳到正式文案與停用設定，網址保留精確 ID，返回沿未儲存保護且不寫入', async () => {
    const clients = flowWorkbench(); const { configuration, previews, templates, onboarding } = clients;
    vi.spyOn(lineMessagePreviewClient, 'catalog').mockImplementation(previews.catalog);
    vi.spyOn(lineMessagePreviewClient, 'render').mockImplementation(previews.render);
    window.history.replaceState(null, '', '#line-management?tab=message_flow&rule_q=遮蔽條件&rule_state=enabled');
    const { unmount,rerender } = render(<UnsavedChangesProvider><LineManagementPage lineConfiguration={configuration} notificationTemplateClient={templates} onboardingClient={onboarding} /></UnsavedChangesProvider>);
    fireEvent.click(await screen.findByRole('button', { name: '6 持續服務與異動 3 則訊息' }));
    fireEvent.click(screen.getByRole('button', { name: '第二期款到期與入帳 已停用 調整訊息' }));
    financeContentClients(clients);
    await waitFor(()=>expect(window.location.hash).toContain('view=reminder-content'));
    rerender(<UnsavedChangesProvider><FinanceWarningWorkspace onCase={()=>{}}/></UnsavedChangesProvider>);
    expect(await screen.findByRole('textbox', { name: '通知內容' })).toHaveValue('目前正式文案 {case_no}');
    expect(window.location.hash).toContain('tab=accounting-warnings'); expect(window.location.hash).toContain('message=current-payment-rule');
    expect(screen.queryByRole('button',{name:'發送設定'})).not.toBeInTheDocument();
    fireEvent.change(screen.getByRole('textbox', { name: '通知內容' }), { target: { value: '尚未儲存的內容' } });
    fireEvent.click(screen.getByRole('tab', { name: '提醒排程' }));
    expect(await screen.findByRole('dialog')).toHaveTextContent('尚未儲存的內容');
    fireEvent.click(screen.getByRole('button', { name: '繼續編輯' }));
    expect(screen.getByRole('textbox', { name: '通知內容' })).toHaveValue('尚未儲存的內容');
    expect(templates.update).not.toHaveBeenCalled(); expect(onboarding.update).not.toHaveBeenCalled();
    unmount(); window.history.replaceState(null, '', '/');
  });

  it('重新載入 message 連結會等正式查詢完成並打開正確內容；失效 ID 不改選其他訊息', async () => {
    const clients = flowWorkbench(); const { configuration, previews, templates, onboarding } = clients;
    let resolveCatalog!: (value: Awaited<ReturnType<LineMessagePreviewClient['catalog']>>) => void;
    const rows = await previews.catalog();
    vi.spyOn(lineMessagePreviewClient, 'catalog').mockImplementation(() => new Promise(resolve => { resolveCatalog = resolve; }));
    vi.spyOn(lineMessagePreviewClient, 'render').mockImplementation(previews.render);
    window.history.replaceState(null, '', '#line-management?tab=push_queue&message=card-candidate-information-1');
    const { unmount } = render(<LineManagementPage lineConfiguration={configuration} notificationTemplateClient={templates} onboardingClient={onboarding} />);
    expect(window.location.hash).toContain('tab=push_queue');
    await screen.findByRole('button', { name: '編輯新好友歡迎訊息內容' });
    expect(screen.queryByText(/找不到指定訊息/)).not.toBeInTheDocument();
    await act(async () => resolveCatalog(rows));
    await screen.findByRole('heading', { name: '目前訂單資訊一' });
    await waitFor(() => expect(previews.render).toHaveBeenCalledWith({ id: 'card-candidate-information-1', content: '目前正式文案 {case_no}', data_source: 'sample' }, expect.any(Object)));
    unmount();
    vi.mocked(lineMessagePreviewClient.catalog).mockResolvedValue(rows);
    window.history.replaceState(null, '', '#line-management?tab=push_queue&message=removed-message');
    const view = render(<LineManagementPage lineConfiguration={configuration} notificationTemplateClient={templates} onboardingClient={onboarding} />);
    expect(window.location.hash).toContain('tab=push_queue');
    await screen.findByText(/找不到指定訊息/);
    expect(screen.queryByRole('textbox', { name: '通知內容' })).not.toBeInTheDocument();
    view.unmount(); window.history.replaceState(null, '', '/');
  });
});

describe('LINE notification rules mutation panel', () => {
  it.each(['', '核准訂金通知事件更新'])('一次點擊儲存，內部檢查後套用同一候選；原因可選填：%s', async reason => {
    const preview = vi.fn().mockImplementation(async request => ({
      before_revision: request.expected_revision, resulting_revision: request.expected_revision + 1,
      definition: request.definition, fingerprint: FINGERPRINT,
    }));
    const save = vi.fn().mockResolvedValue({ revision: 4, preview_fingerprint: FINGERPRINT, cancelled_intent_count: 1, cancelled_task_count: 2 });
    const client: LineNotificationRulesMutationClient = { preview, save, deleteRule: vi.fn() };
    const onCommitted = vi.fn();
    render(<LineNotificationRulesMutationPanel catalog={CATALOG} client={client} templateClient={templateClient()} onCommitted={onCommitted} />);
    await screen.findByRole('textbox', { name: '訊息內容編輯' });
    expect(screen.getByRole('button', { name: '儲存變更' })).toBeDisabled();
    expect(screen.queryByRole('textbox', { name: '規則 ID' })).not.toBeInTheDocument();
    expect(screen.queryByRole('textbox', { name: '訊息模板 ID' })).not.toBeInTheDocument();
    expect(screen.queryByRole('combobox', { name: '事件' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '新增規則' })).not.toBeInTheDocument();
    fireEvent.change(screen.getByRole('combobox', { name: '收件者' }), { target: { value: 'assigned_caregiver' } });
    if (reason) fireEvent.change(screen.getByRole('textbox', { name: '操作原因（選填）' }), { target: { value: reason } });
    fireEvent.click(screen.getByRole('button', { name: '儲存變更' }));
    await screen.findByText(/通知規則已儲存；已取消 1 筆待發通知與 2 筆發送工作/);
    expect(preview).toHaveBeenCalledTimes(1);
    expect(preview).toHaveBeenCalledWith({ expected_revision: 3, definition: expect.objectContaining({ rules: [expect.objectContaining({ recipient_selector: 'assigned_caregiver' })] }) }, expect.objectContaining({ signal: expect.any(AbortSignal) }));
    expect(save).toHaveBeenCalledTimes(1);
    expect(preview.mock.invocationCallOrder[0]).toBeLessThan(save.mock.invocationCallOrder[0]);
    expect(save.mock.calls[0][0]).toMatchObject({
      expected_revision: 3, preview_fingerprint: FINGERPRINT, reason,
      definition: { rules: [expect.objectContaining({ event_code: 'deposit_confirmed', id: 'deposit_notice', recipient_selector: 'assigned_caregiver', template_id: 'deposit_template' })] },
      idempotency_key: expect.stringMatching(/^line-notification-save-idem-/), correlation_id: expect.stringMatching(/^line-notification-save-corr-/),
    });
    expect(save.mock.calls[0][0].idempotency_key).not.toBe(save.mock.calls[0][0].correlation_id);
    expect(document.body.textContent).not.toContain(FINGERPRINT);
    expect(screen.queryByRole('button', { name: '預覽儲存變更' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '確認儲存通知規則' })).not.toBeInTheDocument();
    expect(screen.queryByRole('checkbox', { name: '我已確認通知規則與影響範圍' })).not.toBeInTheDocument();
    await waitFor(() => expect(onCommitted).toHaveBeenCalledTimes(1));
  });

  it('一次點擊刪除，以目前版本取得刪除候選後呼叫 DELETE，空白原因可接受', async () => {
    const preview = vi.fn().mockResolvedValue({ before_revision: 3, resulting_revision: 4, definition: { rules: [] }, fingerprint: FINGERPRINT });
    const deleteRule = vi.fn().mockResolvedValue({ rule_id: 'deposit_notice', revision: 4, preview_fingerprint: FINGERPRINT, cancelled_intent_count: 0, cancelled_task_count: 1 });
    const client: LineNotificationRulesMutationClient = { preview, save: vi.fn(), deleteRule };
    render(<LineNotificationRulesMutationPanel catalog={CATALOG} client={client} templateClient={templateClient()} />);
    await screen.findByRole('textbox', { name: '訊息內容編輯' });
    fireEvent.click(screen.getByRole('button', { name: '刪除規則' }));
    await screen.findByText(/規則 deposit_notice 已刪除；已取消 0 筆待發通知與 1 筆發送工作/);
    expect(preview).toHaveBeenCalledWith({ expected_revision: 3, definition: { rules: [] } }, expect.objectContaining({ signal: expect.any(AbortSignal) }));
    expect(deleteRule).toHaveBeenCalledTimes(1);
    expect(preview.mock.invocationCallOrder[0]).toBeLessThan(deleteRule.mock.invocationCallOrder[0]);
    expect(deleteRule.mock.calls[0]).toEqual(['deposit_notice', expect.objectContaining({ expected_revision: 3, preview_fingerprint: FINGERPRINT, reason: '', idempotency_key: expect.stringMatching(/^line-notification-delete-idem-/), correlation_id: expect.stringMatching(/^line-notification-delete-corr-/) }), expect.objectContaining({ signal: expect.any(AbortSignal) })]);
    expect(screen.queryByRole('button', { name: '確認刪除通知規則' })).not.toBeInTheDocument();
  });

  it('存在未儲存編輯時鎖定刪除，不呼叫內部檢查或刪除命令', async () => {
    const client: LineNotificationRulesMutationClient = { preview: vi.fn(), save: vi.fn(), deleteRule: vi.fn() };
    render(<LineNotificationRulesMutationPanel catalog={CATALOG} client={client} templateClient={templateClient()} />);
    await screen.findByRole('textbox', { name: '訊息內容編輯' });
    fireEvent.change(screen.getByRole('combobox', { name: '收件者' }), { target: { value: 'assigned_caregiver' } });
    const remove = screen.getByRole('button', { name: '刪除規則' });
    expect(remove).toBeDisabled();
    fireEvent.click(remove);
    expect(client.preview).not.toHaveBeenCalled();
    expect(client.deleteRule).not.toHaveBeenCalled();
    expect(screen.getByText(/有未儲存編輯時，刪除功能會鎖定/)).toBeInTheDocument();
  });

  it('內部檢查失敗時不儲存，不將錯誤代碼與後端原文顯示於通知規則畫面', async () => {
    const client: LineNotificationRulesMutationClient = {
      preview: vi.fn().mockRejectedValue(new LineNotificationRulesMutationError('raw_rule_failure', 'raw provider detail must stay closed')),
      save: vi.fn(), deleteRule: vi.fn(),
    };
    render(<LineNotificationRulesMutationPanel catalog={CATALOG} client={client} templateClient={templateClient()} />);
    await screen.findByRole('textbox', { name: '訊息內容編輯' });
    fireEvent.change(screen.getByRole('combobox', { name: '收件者' }), { target: { value: 'assigned_caregiver' } });
    fireEvent.click(screen.getByRole('button', { name: '儲存變更' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('LINE 通知規則操作未完成，請重新載入最新規則後再試。');
    expect(client.save).not.toHaveBeenCalled();
    expect(document.body.textContent).not.toContain('raw_rule_failure');
    expect(document.body.textContent).not.toContain('raw provider detail');
  });

  it('載入規則實際引用的訊息內容，提供即時預覽並以模板 revision 儲存', async () => {
    const update = vi.fn().mockResolvedValue({
      rule_id: 'deposit_notice',
      template_id: 'deposit_template',
      name: '訂金確認通知',
      content: '案件 {case_no} 的訂金已完成確認。',
      revision: 8,
      variables: ['case_no'],
      sample_preview: '案件〔case_no〕的訂金已完成確認。',
    });
    const messageClient = templateClient({ update });
    const ruleClient: LineNotificationRulesMutationClient = {
      preview: vi.fn(),
      save: vi.fn(),
      deleteRule: vi.fn(),
    };

    render(
      <LineNotificationRulesMutationPanel
        catalog={CATALOG}
        client={ruleClient}
        templateClient={messageClient}
      />
    );

    const editor = await screen.findByRole('textbox', { name: '訊息內容編輯' });
    expect(editor).toHaveValue('案件 {case_no} 已確認訂金。');
    const preview = document.querySelector('.notification-template-preview .notification-message-preview');
    expect(preview).toHaveTextContent('案件 〔case_no〕 已確認訂金。');

    fireEvent.change(editor, { target: { value: '案件 {case_no} 的訂金已完成確認。' } });
    expect(preview).toHaveTextContent('案件 〔case_no〕 的訂金已完成確認。');
    fireEvent.click(screen.getByRole('button', { name: '儲存訊息內容' }));

    await screen.findByText('通知訊息內容已成功儲存！');
    expect(update).toHaveBeenCalledWith(
      'deposit_notice',
      {
        content: '案件 {case_no} 的訂金已完成確認。',
        expected_revision: 7,
      },
    );
    expect(screen.getByText('版本 Rev.8')).toBeInTheDocument();
  });

  it('互動卡片顯示真實卡片預覽與觸發狀態，不誤載文字模板編輯器', () => {
    const messageClient = templateClient();
    const ruleClient: LineNotificationRulesMutationClient = {
      preview: vi.fn(),
      save: vi.fn(),
      deleteRule: vi.fn(),
    };

    render(
      <LineNotificationRulesMutationPanel
        catalog={CARD_CATALOG}
        client={ruleClient}
        templateClient={messageClient}
      />
    );

    expect(screen.getByRole('region', { name: '通知內容與觸發狀態' })).toHaveTextContent(
      '互動卡片｜已由月嫂請假流程觸發',
    );
    expect(screen.getByText('🌸 服務調休與順延確認通知')).toBeInTheDocument();
    expect(screen.getByText('🟢 我同意順延一日')).toBeInTheDocument();
    expect(screen.getByText('🔴 不同意順延')).toBeInTheDocument();
    expect(screen.queryByRole('textbox', { name: '訊息內容編輯' })).not.toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: '收件者' })).toBeDisabled();
    expect(screen.queryByRole('button', { name: '預覽刪除規則' })).not.toBeInTheDocument();
    expect(messageClient.get).not.toHaveBeenCalled();
  });
});


function contentWorkbench(catalog: LineNotificationRulesCatalog = CATALOG) {
  let revision = 7;
  let welcome = '歡迎加入工會，請開啟 {url} 登記。';
  let message = '案件 {case_no} 已確認訂金。';
  const messageData = () => ({ rule_id: 'deposit_notice', template_id: 'deposit_template', name: '訂金確認通知', content: message, revision, variables: ['case_no'], sample_preview: message });
  const welcomeData = () => ({ template_id: 'customer_onboarding_welcome', content: welcome, revision, variables: ['url'], sample_preview: welcome });
  const templates: LineNotificationTemplateClient = {
    get: vi.fn(async () => messageData()),
    update: vi.fn(async (_id, payload) => { expect(payload.expected_revision).toBe(revision); message = payload.content; revision++; return messageData(); }),
  };
  const onboarding: LineOnboardingClient = {
    get: vi.fn(async () => welcomeData()), preview: vi.fn(),
    update: vi.fn(async payload => { expect(payload.expected_revision).toBe(revision); welcome = payload.content; revision++; return welcomeData(); }),
  };
  const configuration: LineConfigurationQueryClient = {
    getNotificationRules: vi.fn(async () => catalog), getRichMenuConfiguration: vi.fn(), listRichMenuPublications: vi.fn(), getRichMenuPublication: vi.fn(),
  };
  const previews: LineMessagePreviewClient = {
    catalog: vi.fn(async () => [
      { id: 'welcome', template_id: 'customer_onboarding_welcome', name: '歡迎', format: 'text' as const, requires_case: false, requires_staff: false, builtin: false, allows_draft: false },
      ...('rules' in catalog.definition ? catalog.definition.rules : []).map(rule => ({ id: rule.id, template_id: rule.template_id, name: '通知', format: 'text' as const, requires_case: true, requires_staff: false, builtin: false, allows_draft: false })),
    ]),
    subjects: vi.fn(async () => ({ items: [{ id: 'CASE-1', label: 'CASE-1｜測試客戶' }], next_cursor: null })),
    render: vi.fn(async payload => ({ status: 'ready' as const, note: '公版範例', format: 'text' as const,
      text: (payload.content ?? '').replaceAll('{url}', '［專屬安全登記連結］').replaceAll('{case_no}', 'DEMO-CASE-001'), bubbles: [],
      facts: payload.id === 'welcome' ? [] : [{ id: '案件編號（case_no）', label: 'DEMO-CASE-001' }] })),
  };
  function Harness() {
    const [search, setSearch] = useState('');
    const [enabled, setEnabled] = useState<'all' | 'enabled' | 'disabled'>('all');
    return <UnsavedChangesProvider><LineNotificationWorkbench configuration={configuration} onboarding={onboarding} templates={templates} previews={previews} search={search} enabled={enabled} onSearchChange={setSearch} onEnabledChange={setEnabled} /></UnsavedChangesProvider>;
  }
  return { templates, onboarding, configuration, previews, Harness };
}

describe('通知內容統一工作區', () => {
  const paymentMessages = [
    ['deposit-reminder', '訂金繳費提醒卡'],
    ['payment-first-reminder', '第一期繳款提醒'],
    ['payment-first-greeting', '第一期結清問候'],
    ['payment-second-reminder', '第二期到期提醒'],
    ['payment-overdue-deposit', '訂金逾期提醒'],
    ['payment-overdue-first', '第一期款逾期提醒'],
    ['payment-overdue-second', '第二期款逾期提醒'],
    ['deposit-settled','訂金已確認入帳卡'],
    ['current-payment-rule','第二期款已入帳通知'],
  ];
  const paymentDescriptors = paymentMessages.map(([id, name]) => ({ id, name, template_id: id==='current-payment-rule'?'LINE-SECOND-PAYMENT-SETTLED-TEXT-V1':null, format: id==='deposit-reminder' ? 'flex' as const : 'text' as const, requires_case: false, requires_staff: false, builtin: id!=='current-payment-rule', allows_draft: false }));

  it.each(paymentMessages)('帳務包含提醒及入帳的九則內容，%s 沿原版本化 writer 儲存', async (id) => {
    const clients = flowWorkbench();
    vi.mocked(clients.templates.update).mockResolvedValue({rule_id:id,template_id:'LINE-COPY-'+id,name:'逾期提醒',content:'請協助確認本期款項 {case_no}',revision:20,variables:['case_no'],sample_preview:'公版範例'});
    financeContentClients(clients);
    const descriptors = await clients.previews.catalog();
    vi.spyOn(lineMessagePreviewClient, 'catalog').mockResolvedValue([...descriptors.filter(row=>!paymentMessages.some(([key])=>key===row.id)), ...paymentDescriptors]);
    vi.spyOn(lineMessagePreviewClient, 'render').mockImplementation(clients.previews.render);
    window.history.replaceState(null, '', '#finance?tab=accounting-warnings&view=reminder-content&message='+id);
    render(<UnsavedChangesProvider><FinanceWarningWorkspace onCase={()=>{}}/></UnsavedChangesProvider>);
    const field = await screen.findByRole('textbox', {name:'通知內容'});
    expect(document.querySelectorAll('.notification-message-item')).toHaveLength(9);
    expect(screen.getByRole('heading',{name:'提醒內容'})).toBeInTheDocument();
    expect(screen.queryByRole('heading',{name:'通知與發送'})).not.toBeInTheDocument();
    expect(screen.queryByRole('button',{name:'發送設定'})).not.toBeInTheDocument();
    expect(clients.onboarding.get).not.toHaveBeenCalled();
    expect(clients.configuration.getNotificationRules).toHaveBeenCalledTimes(1);
    expect(clients.templates.get).toHaveBeenCalledWith(id, expect.any(Object));
    expect(vi.mocked(clients.templates.get).mock.calls.every(([key])=>key===id||key==='current-payment-rule')).toBe(true);
    fireEvent.change(field, {target:{value:'請協助確認本期款項 {case_no}'}});
    fireEvent.click(screen.getByRole('button',{name:'儲存內容'}));
    await waitFor(()=>expect(clients.templates.update).toHaveBeenCalledExactlyOnceWith(id, {content:'請協助確認本期款項 {case_no}',expected_revision:19},expect.any(Object)));
    await screen.findByText('通知內容已儲存。');
    expect(clients.onboarding.update).not.toHaveBeenCalled();
    expect(clients.previews.subjects).not.toHaveBeenCalled();
  });

  it('LINE 其他通知與卡片維持原位，繳款提醒不再混入清單',async()=>{
    const {Harness,previews}=contentWorkbench();
    vi.mocked(previews.catalog).mockResolvedValue([...(await previews.catalog()),...paymentDescriptors,
      {id:'service-start-inquiry',name:'服務開始詢問卡',template_id:null,format:'flex',requires_case:false,requires_staff:false,builtin:true,allows_draft:false}]);
    render(<Harness/>);
    await screen.findByRole('button',{name:'查看服務開始詢問卡內容'});
    expect(screen.getByRole('heading',{name:'通知與發送'})).toBeInTheDocument();
    expect(screen.getByRole('button',{name:'編輯新好友歡迎訊息內容'})).toBeInTheDocument();
    for(const [,name] of paymentMessages)expect(screen.queryByRole('button',{name:'查看'+name+'內容'})).not.toBeInTheDocument();
  });

  it('每週安排圖片自動帶入，沒有文案編輯或儲存操作', async () => {
    const { Harness, previews, templates } = contentWorkbench();
    vi.mocked(previews.catalog).mockResolvedValue([{ id: 'card-candidate-information-3', template_id: null, name: '初步候選聯絡－每週服務說明', format: 'flex', requires_case: true, requires_staff: true, builtin: true, allows_draft: false }]);
    const picture: PreviewNode = { kind: 'image', text: '每週服務安排', image_data: 'data:image/png;base64,iVBORw0KGgo=', bold: false, size: 'sm', layout: 'vertical', primary: false, action_description: '', children: [] };
    vi.mocked(previews.render).mockResolvedValue({ status: 'ready', note: '公版範例', format: 'flex', text: '', bubbles: [picture], facts: [] });
    render(<Harness />);
    const entry = await screen.findByRole('button', { name: '查看初步候選聯絡－每週服務說明內容' });
    const reads = vi.mocked(templates.get).mock.calls.length;
    fireEvent.click(entry);
    expect(await screen.findByRole('img', { name: '每週服務安排' })).toBeInTheDocument();
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '儲存內容' })).not.toBeInTheDocument();
    expect(templates.get).toHaveBeenCalledTimes(reads);
    expect(templates.update).not.toHaveBeenCalled();
  });
  it('訊息清單每頁六則，搜尋後顯示符合項目並維持目前訊息定位', async () => {
    const { Harness, previews } = contentWorkbench();
    vi.mocked(previews.catalog).mockResolvedValue(Array.from({ length: 14 }, (_, index) => ({ id: `fixed-${index + 1}`, template_id: null, name: `固定公告${index + 1}`, format: 'text' as const, requires_case: false, requires_staff: false, builtin: true, allows_draft: false })));
    const { container } = render(<Harness />);
    await screen.findByRole('navigation', { name: '訊息清單分頁' });
    expect(container.querySelectorAll('.notification-message-items > button')).toHaveLength(6);
    fireEvent.click(screen.getByRole('button', { name: '下一頁訊息' }));
    expect(container.querySelectorAll('.notification-message-items > button')).toHaveLength(6);
    fireEvent.change(screen.getByRole('searchbox', { name: '搜尋通知名稱或內容' }), { target: { value: '固定公告14' } });
    fireEvent.click(await screen.findByRole('button', { name: '查看固定公告14內容' }));
    await screen.findByRole('textbox', { name: '通知內容' });
    fireEvent.change(screen.getByRole('searchbox', { name: '搜尋通知名稱或內容' }), { target: { value: '' } });
    expect(await screen.findByRole('button', { name: '編輯固定公告14內容' })).toHaveAttribute('aria-pressed', 'true');
  });

  it('完整推薦包在手機內依名稱選擇五張卡片，切換不重建訊息或發送', async () => {
    const { Harness, previews, templates } = contentWorkbench();
    const node = (text: string): PreviewNode => ({ kind: 'text', text, bold: false, size: 'sm', layout: 'vertical', primary: false, action_description: '', children: [] });
    const titles = ['陳月嫂（範例）', '訂單資訊－1', '訂單資訊－2', '每周服務中說明', '確認本次推薦'];
    vi.mocked(previews.catalog).mockResolvedValue([{ id: 'card-customer-confirmation', template_id: null, name: '正式媒合－客戶完整推薦確認包', format: 'flex', requires_case: true, requires_staff: true, builtin: true, allows_draft: false }]);
    vi.mocked(previews.render).mockResolvedValue({ status: 'ready', note: '公版範例', format: 'flex', text: '', bubbles: titles.map(title => ({ ...node(''), kind: 'box' as const, children: [node(title)] })), facts: [] });
    render(<Harness />);
    fireEvent.click(await screen.findByRole('button', { name: '查看正式媒合－客戶完整推薦確認包內容' }));
    const picker = await screen.findByRole('combobox', { name: '選擇預覽卡片' });
    expect(picker.closest('.notification-phone')).not.toBeNull();
    expect(within(picker).getAllByRole('option')).toHaveLength(5);
    expect(screen.getByRole('button', { name: '下一張卡片' })).toBeDisabled();
    const card = () => document.querySelector('.notification-real-flex-bubble');
    expect(card()).toHaveTextContent(titles[4]);
    const requests = vi.mocked(previews.render).mock.calls.length;
    fireEvent.click(screen.getByRole('button', { name: '上一張卡片' }));
    expect(card()).toHaveTextContent(titles[3]);
    for (let index = 0; index < titles.length; index++) {
      fireEvent.change(picker, { target: { value: String(index) } });
      expect(card()).toHaveTextContent(titles[index]);
      expect(screen.getByText(`第 ${index + 1} / 5 張`)).toBeInTheDocument();
    }
    expect(screen.getByRole('button', { name: '下一張卡片' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: '上一張卡片' }));
    expect(card()).toHaveTextContent(titles[3]);
    expect(previews.render).toHaveBeenCalledTimes(requests);
    expect(templates.update).not.toHaveBeenCalled();
  });
  it('舊其他問題導覽深連結開啟共用服務導覽，不建立第二個編輯入口', async () => {
    const { previews, templates, configuration, onboarding } = contentWorkbench();
    const onSelectedEntryChange = vi.fn();
    vi.mocked(previews.catalog).mockResolvedValue([{ id: 'service-menu', template_id: null, name: '服務與問答導覽卡', format: 'flex', requires_case: false, requires_staff: false, builtin: true, allows_draft: false }]);
    render(<UnsavedChangesProvider><LineNotificationWorkbench configuration={configuration} onboarding={onboarding} templates={templates} previews={previews} search="" enabled="all" onSearchChange={vi.fn()} onEnabledChange={vi.fn()} selectedEntryId="service-other" onSelectedEntryChange={onSelectedEntryChange} /></UnsavedChangesProvider>);
    expect(await screen.findByRole('heading', { name: '服務與問答導覽卡' })).toBeInTheDocument();
    expect(onSelectedEntryChange).toHaveBeenCalledWith('service-menu');
    await waitFor(() => expect(templates.get).toHaveBeenCalledWith('service-menu', expect.anything()));
    expect(vi.mocked(templates.get).mock.calls.some(([id]) => id === 'service-other')).toBe(false);
  });
  it('既有客戶綁定成功連結解析至客戶獨立文案', async () => {
    const { previews, templates, configuration, onboarding } = contentWorkbench();
    const onSelectedEntryChange = vi.fn();
    vi.mocked(previews.catalog).mockResolvedValue([{ id: 'identity-bound-customer', template_id: null, name: '客戶綁定成功', format: 'text', requires_case: false, requires_staff: false, builtin: true, allows_draft: false }]);
    render(<UnsavedChangesProvider><LineNotificationWorkbench configuration={configuration} onboarding={onboarding} templates={templates} previews={previews} search="" enabled="all" onSearchChange={vi.fn()} onEnabledChange={vi.fn()} selectedEntryId="template-bind_success_new_order" onSelectedEntryChange={onSelectedEntryChange} /></UnsavedChangesProvider>);
    await screen.findByRole('textbox', { name: '通知內容' });
    expect(screen.getByRole('heading', { name: '客戶綁定成功' })).toBeInTheDocument();
    expect(onSelectedEntryChange).toHaveBeenCalledWith('identity-bound-customer');
    expect(screen.queryByText(/找不到指定訊息/)).not.toBeInTheDocument();
  });
  it.each(['card-caregiver-information', 'card-caregiver-information-2', 'card-customer-profiles'])('原正式媒合單張卡片入口 %s 統一開啟完整推薦包', async previous => {
    const { previews, templates, configuration, onboarding } = contentWorkbench();
    const onSelectedEntryChange = vi.fn();
    vi.mocked(previews.catalog).mockResolvedValue([{ id: 'card-customer-confirmation', template_id: null, name: '正式媒合－客戶完整推薦確認包', format: 'flex', requires_case: true, requires_staff: true, builtin: true, allows_draft: false }]);
    render(<UnsavedChangesProvider><LineNotificationWorkbench configuration={configuration} onboarding={onboarding} templates={templates} previews={previews} search="" enabled="all" onSearchChange={vi.fn()} onEnabledChange={vi.fn()} selectedEntryId={previous} onSelectedEntryChange={onSelectedEntryChange} /></UnsavedChangesProvider>);
    await screen.findByRole('textbox', { name: '通知內容' });
    expect(screen.getByRole('heading', { name: '正式媒合－客戶完整推薦確認包' })).toBeInTheDocument();
    expect(onSelectedEntryChange).toHaveBeenCalledWith('card-customer-confirmation');
    expect(templates.get).toHaveBeenCalledWith('card-customer-confirmation', expect.any(Object));
    expect(vi.mocked(templates.get).mock.calls.some(([id]) => id === previous)).toBe(false);
    expect(screen.queryByText(/找不到指定訊息/)).not.toBeInTheDocument();
    expect(templates.update).not.toHaveBeenCalled();
  });
  it('內建文案讀取完成前不提供會被晚到設定覆寫的編輯欄位', async () => {
    const { Harness, previews, templates } = contentWorkbench();
    let complete!: (value: Awaited<ReturnType<LineNotificationTemplateClient['get']>>) => void;
    const originalGet = vi.mocked(templates.get).getMockImplementation()!;
    vi.mocked(templates.get).mockImplementation((id, options) => id === 'service-contact' ? new Promise(resolve => { complete = resolve; }) : originalGet(id, options));
    vi.mocked(previews.catalog).mockResolvedValue([{ id: 'service-contact', template_id: null, name: '呼叫專員－需求受理', format: 'text', requires_case: false, requires_staff: false, builtin: true, allows_draft: false }]);
    render(<Harness />);
    fireEvent.click(await screen.findByRole('button', { name: '查看呼叫專員－需求受理內容' }));
    expect(screen.getByText('正在載入訊息內容…')).toBeInTheDocument();
    expect(screen.queryByRole('textbox', { name: '通知內容' })).not.toBeInTheDocument();
    await act(async () => complete({ rule_id: 'service-contact', template_id: 'LINE-COPY-service-contact', name: '受理', content: '已儲存的受理文案', revision: 7, variables: [], sample_preview: '已儲存的受理文案' }));
    expect(await screen.findByRole('textbox', { name: '通知內容' })).toHaveValue('已儲存的受理文案');
  });
  it('固定流程回覆和歡迎訊息不混入啟停篩選，與流程圖共用狀態且沒有獨立開關', async () => {
    const { Harness, previews, templates, onboarding } = contentWorkbench();
    const current = await previews.catalog();
    vi.mocked(previews.catalog).mockResolvedValue([...current, {
      id: 'service-start-normal-received', template_id: null, name: '服務當天－服務正常受理回覆',
      format: 'text', requires_case: false, requires_staff: false, builtin: true, allows_draft: false,
    }]);
    render(<Harness />);
    const replyName = '查看服務當天－服務正常受理回覆內容';
    await screen.findByRole('button', { name: replyName });
    const stateFilter = screen.getByRole('combobox', { name: '啟用狀態' });
    fireEvent.change(stateFilter, { target: { value: 'enabled' } });
    expect(screen.queryByRole('button', { name: replyName })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '編輯新好友歡迎訊息內容' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '編輯訂金確認通知內容' })).toBeInTheDocument();
    fireEvent.change(stateFilter, { target: { value: 'disabled' } });
    expect(screen.getByText('沒有符合條件的通知')).toBeInTheDocument();
    fireEvent.change(stateFilter, { target: { value: 'all' } });
    fireEvent.click(screen.getByRole('button', { name: replyName }));
    fireEvent.click(screen.getByRole('button', { name: '發送設定' }));
    expect(screen.getByText('由流程控制', { selector: 'dd' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '修改發送設定' })).not.toBeInTheDocument();
    expect(await screen.findByRole('button', { name: '儲存內容' })).toBeDisabled();
    expect(templates.update).not.toHaveBeenCalled(); expect(onboarding.update).not.toHaveBeenCalled();
  });
  it('服務當天結構化卡片不把不支援文字編輯誤報為版本衝突，保留正式預覽與啟用設定', async () => {
    const id = 'LINE-ORDER-SERVICE-START-DAY-V1';
    const { Harness, previews, templates, onboarding } = contentWorkbench({ revision: 3, definition: { rules: [{
      id, event_code: 'order.service_start_day', enabled: true,
      schedule: { kind: 'immediate' }, frequency: { kind: 'once' }, predicates: [],
      recipient_selector: 'case_group', template_id: 'LINE-ORDER-SERVICE-START-DAY-CARD-V1',
    }] } });
    vi.mocked(templates.get).mockRejectedValue(new ApiHttpError(409, 'HTTP_409', '此規則使用的訊息格式目前不支援文字編輯。'));
    vi.mocked(previews.catalog).mockResolvedValue([{ id, template_id: 'LINE-ORDER-SERVICE-START-DAY-CARD-V1', name: '服務當天', format: 'flex', requires_case: true, requires_staff: false, builtin: false, allows_draft: false }]);
    render(<Harness />);
    fireEvent.click(await screen.findByRole('button', { name: /查看服務當天/ }));
    expect(await screen.findByText('此卡片使用結構化內容，請查看右側預覽；可在「發送設定」調整啟用狀態。')).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '儲存內容' })).not.toBeInTheDocument();
    await waitFor(() => expect(previews.render).toHaveBeenCalledWith({ id, data_source: 'sample' }, expect.any(Object)));
    fireEvent.click(screen.getByRole('button', { name: '發送設定' }));
    expect(screen.getByText('已啟用', { selector: 'dd' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '修改發送設定' }));
    expect(screen.getByRole('checkbox', { name: '啟用此規則' })).toBeChecked();
    expect(templates.update).not.toHaveBeenCalled();
    expect(onboarding.update).not.toHaveBeenCalled();
  });

  it('整張卡片同時編輯標題、自由說明與按鈕，插入資料後一次儲存', async () => {
    const { Harness, previews, templates, onboarding } = contentWorkbench();
    const originalGet = vi.mocked(templates.get).getMockImplementation()!;
    const fields = [
      { id: 'altText', label: '訊息摘要', content: '原始摘要', max_length: 400 },
      { id: 'contents/body/contents/0/text', label: '卡片標題', content: '工會詢問', max_length: 5000 },
      { id: 'contents/footer/contents/0/action/label', label: '按鈕名稱', content: '回答問題', max_length: 20 },
      { id: 'contents/body/contents/$description', label: '說明內容', content: '', max_length: 5000, kind: 'body' as const, optional: true },
    ];
    vi.mocked(templates.get).mockImplementation(async (id, options) => id === 'card-union-question'
      ? { rule_id: id, template_id: 'LINE-COPY-card-union-question', name: '初步候選聯絡－工會詢問客戶卡', revision: 7, variables: ['case_no'], sample_preview: '', fields, content: JSON.stringify(Object.fromEntries(fields.map(field => [field.id, field.content]))) }
      : originalGet(id, options));
    vi.mocked(previews.catalog).mockResolvedValue([
      { id: 'service-contact', template_id: null, name: '呼叫專員－需求受理', format: 'text', requires_case: false, requires_staff: false, builtin: true, allows_draft: false },
      { id: 'card-union-question', template_id: null, name: '初步候選聯絡－工會詢問客戶卡', format: 'flex', requires_case: true, requires_staff: false, builtin: true, allows_draft: true },
    ]);
    render(<Harness />);
    fireEvent.click(await screen.findByRole('button', { name: '查看呼叫專員－需求受理內容' }));
    const fixedText = await screen.findByRole('textbox', { name: '通知內容' });
    fireEvent.change(fixedText, { target: { value: '請留下需要協助的內容。' } });
    expect(screen.getByRole('button', { name: '儲存內容' })).toBeEnabled();
    fireEvent.click(screen.getByRole('button', { name: '還原內容' }));
    fireEvent.click(screen.getByRole('button', { name: '查看初步候選聯絡－工會詢問客戶卡內容' }));
    fireEvent.change(await screen.findByRole('textbox', { name: '卡片標題' }), { target: { value: '請確認服務條件' } });
    fireEvent.change(screen.getByRole('textbox', { name: '主要按鈕' }), { target: { value: '填寫回覆' } });
    const body = screen.getByRole('textbox', { name: '說明內容' });
    fireEvent.change(body, { target: { value: '第一段說明\n\n自行增加的第二段提醒。' } });
    fireEvent.click(screen.getByRole('button', { name: '＋ 新增段落' }));
    await waitFor(() => expect(body).toHaveFocus());
    fireEvent.click(screen.getByRole('button', { name: '＋ 案件編號' }));
    expect(body).toHaveValue('第一段說明\n\n自行增加的第二段提醒。\n\n{case_no}');
    expect(screen.queryByRole('combobox', { name: '編輯欄位' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '下一個欄位' })).not.toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: '卡片標題' })).toHaveValue('請確認服務條件');
    await waitFor(() => expect(previews.render).toHaveBeenLastCalledWith({ id: 'card-union-question', content: expect.stringContaining('填寫回覆'), data_source: 'sample' }, expect.any(Object)));
    fireEvent.click(screen.getByRole('button', { name: '儲存內容' }));
    await waitFor(() => expect(templates.update).toHaveBeenCalledWith('card-union-question', { content: expect.stringContaining('請確認服務條件'), expected_revision: 7 }, expect.any(Object)));
    expect(JSON.parse(vi.mocked(templates.update).mock.calls[0][1].content)[fields[3].id]).toBe('第一段說明\n\n自行增加的第二段提醒。\n\n{case_no}');
    expect(onboarding.update).not.toHaveBeenCalled();
  });

  it('歡迎訊息與通知共用清單，搜尋內容且直接開啟編輯，不提供獨立發送紀錄', async () => {
    const { Harness } = contentWorkbench(); render(<Harness />);
    await screen.findByRole('button', { name: '編輯新好友歡迎訊息內容' });
    expect(within(screen.getByRole('region', { name: '訊息清單' })).getAllByRole('button', { name: /^編輯/ })).toHaveLength(2);
    expect(screen.queryByRole('tab')).not.toBeInTheDocument();
    expect(screen.queryByText('發送紀錄')).not.toBeInTheDocument();
    fireEvent.change(screen.getByRole('searchbox'), { target: { value: '登記' } });
    expect(screen.queryByRole('button', { name: '編輯訂金確認通知內容' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '編輯新好友歡迎訊息內容' }));
    expect(screen.getByRole('textbox', { name: '通知內容' })).toHaveValue('歡迎加入工會，請開啟 {url} 登記。');
    expect(screen.getByRole('button', { name: '儲存內容' })).toBeDisabled();
    expect(screen.queryByRole('button', { name: '修改發送設定' })).not.toBeInTheDocument();
  });

  it('歡迎與一般文字分別儲存，重新查詢共享版本，下一筆不沿用舊版本', async () => {
    const { Harness, onboarding, templates } = contentWorkbench(); render(<Harness />);
    fireEvent.click(await screen.findByRole('button', { name: '編輯新好友歡迎訊息內容' }));
    fireEvent.change(screen.getByRole('textbox', { name: '通知內容' }), { target: { value: '新歡迎文字 {url}' } });
    await waitFor(() => expect(document.querySelector('.notification-bubble')).toHaveTextContent('新歡迎文字 ［專屬安全登記連結］'));
    fireEvent.click(screen.getByRole('button', { name: '儲存內容' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(onboarding.update).toHaveBeenCalledWith({ content: '新歡迎文字 {url}', expected_revision: 7 }, expect.objectContaining({ signal: expect.any(AbortSignal) }));
    fireEvent.click(await screen.findByRole('button', { name: '編輯訂金確認通知內容' }));
    fireEvent.change(screen.getByRole('textbox', { name: '通知內容' }), { target: { value: '新訂金通知 {case_no}' } });
    fireEvent.click(screen.getByRole('button', { name: '儲存內容' }));
    await waitFor(() => expect(templates.update).toHaveBeenCalledWith('deposit_notice', { content: '新訂金通知 {case_no}', expected_revision: 8 }, expect.any(Object)));
    await waitFor(() => expect(templates.get).toHaveBeenCalledTimes(3));
    fireEvent.click(await screen.findByRole('button', { name: '編輯訂金確認通知內容' }));
    expect(screen.getByRole('textbox', { name: '通知內容' })).toHaveValue('新訂金通知 {case_no}');
  });

  it('卡片說明可編輯，原流程的對象與排程不可在此改寫', async () => {
    const { Harness, templates } = contentWorkbench({ revision: 3, definition: { rules: [{
      id: 'alert-review', event_code: 'runtime.alert.review_required', recipient_selector: 'admin.review_actor',
      template_id: 'alert-review-card', enabled: false, schedule: { kind: 'immediate' }, frequency: { kind: 'once' }, predicates: [],
    }] } });
    vi.mocked(templates.get).mockResolvedValue({ rule_id: 'alert-review', template_id: 'alert-review-card',
      name: '告警待審核通知', content: '請查看本次告警。', revision: 7, variables: [], sample_preview: '請查看本次告警。' });
    render(<Harness />);
    fireEvent.click(await screen.findByRole('button', { name: '編輯告警待審核通知內容' }));
    const editor = screen.getByRole('textbox', { name: '通知說明文字' });
    expect(editor).toBeEnabled();
    expect(screen.queryByRole('button', { name: '修改發送設定' })).not.toBeInTheDocument();
    fireEvent.change(editor, { target: { value: '請查看本次告警並處理。' } });
    fireEvent.click(screen.getByRole('button', { name: '儲存內容' }));
    await waitFor(() => expect(templates.update).toHaveBeenCalledWith('alert-review', expect.objectContaining({ content: '請查看本次告警並處理。' }), expect.any(Object)));
  });

  it('儲存失敗保留修改，不輸出後端 raw detail，也不假裝成功', async () => {
    const { Harness, templates } = contentWorkbench();
    vi.mocked(templates.update).mockRejectedValue(new ApiHttpError(409, 'raw_code', 'provider secret detail', false));
    render(<Harness />);
    fireEvent.click(await screen.findByRole('button', { name: '編輯訂金確認通知內容' }));
    fireEvent.change(screen.getByRole('textbox', { name: '通知內容' }), { target: { value: '尚未儲存的文字' } });
    fireEvent.click(screen.getByRole('button', { name: '儲存內容' }));
    await screen.findByRole('alert');
    expect(screen.getByRole('textbox', { name: '通知內容' })).toHaveValue('尚未儲存的文字');
    expect(document.body.textContent).not.toContain('provider secret detail');
    expect(screen.queryByText('通知內容已儲存。')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '取消' }));
    fireEvent.click(screen.getByRole('button', { name: '繼續編輯' }));
    expect(screen.getByRole('textbox', { name: '通知內容' })).toHaveValue('尚未儲存的文字');
  });

  it('通知查詢失敗仍保留歡迎訊息並顯示錯誤，不當成零筆成功', async () => {
    const { Harness, configuration } = contentWorkbench();
    vi.mocked(configuration.getNotificationRules).mockRejectedValue(new Error('raw query error'));
    render(<Harness />);
    await screen.findByRole('alert');
    expect(screen.getByRole('button', { name: '編輯新好友歡迎訊息內容' })).toBeInTheDocument();
    expect(screen.queryByText('沒有符合條件的通知')).not.toBeInTheDocument();
    expect(document.body.textContent).not.toContain('raw query error');
  });

  it('確認放棄之前不卸載發送設定草稿，繼續編輯時保留選擇', async () => {
    const { Harness } = contentWorkbench(); render(<Harness />);
    fireEvent.click(await screen.findByRole('button', { name: '編輯訂金確認通知內容' }));
    fireEvent.click(screen.getByRole('button', { name: '發送設定' }));
    fireEvent.click(screen.getByRole('button', { name: '修改發送設定' }));
    fireEvent.click(screen.getByRole('checkbox', { name: '啟用此規則' }));
    fireEvent.click(screen.getByRole('button', { name: '返回內容' }));
    fireEvent.click(screen.getByRole('button', { name: '繼續編輯' }));
    expect(screen.getByRole('checkbox', { name: '啟用此規則' })).not.toBeChecked();
  });

  it('公版直接預覽且列出欄位與值，不查真實案件，試改只呼叫預覽', async () => {
    const { Harness, previews, templates, onboarding } = contentWorkbench(); render(<Harness />);
    fireEvent.click(await screen.findByRole('button', { name: '編輯訂金確認通知內容' }));
    await waitFor(() => expect(document.querySelector('.notification-bubble')).toHaveTextContent('案件 DEMO-CASE-001 已確認訂金。'));
    expect(screen.queryByRole('combobox', { name: '選擇案件' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByText('公版預覽資料', { selector: 'summary' }));
    expect(screen.getByRole('region', { name: '公版預覽資料' })).toHaveTextContent('案件編號（case_no）');
    expect(screen.getByRole('table', { name: '本次帶入欄位與值' })).toHaveTextContent('DEMO-CASE-001');
    expect(previews.subjects).not.toHaveBeenCalled();
    fireEvent.change(screen.getByRole('textbox', { name: '通知內容' }), { target: { value: '試改案件 {case_no}' } });
    await waitFor(() => expect(document.querySelector('.notification-bubble')).toHaveTextContent('試改案件 DEMO-CASE-001'));
    expect(previews.render).toHaveBeenLastCalledWith({ id: 'deposit_notice', content: '試改案件 {case_no}', data_source: 'sample' }, expect.objectContaining({ signal: expect.any(AbortSignal) }));
    expect(templates.update).not.toHaveBeenCalled(); expect(onboarding.update).not.toHaveBeenCalled();
    expect(screen.queryByRole('button', { name: '一般內容' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '長文字' })).not.toBeInTheDocument();
  });

  it('舊文案的晚到預覽不能覆蓋最新內容', async () => {
    const { Harness, previews } = contentWorkbench();
    let resolveOld: ((value: Awaited<ReturnType<LineMessagePreviewClient['render']>>) => void) | undefined;
    vi.mocked(previews.render).mockImplementation(payload => payload.content === '舊文案'
      ? new Promise(resolve => { resolveOld = resolve; })
      : Promise.resolve({ status: 'ready', note: '', format: 'text', text: payload.content ?? '', bubbles: [], facts: [] }));
    render(<Harness />);
    fireEvent.click(await screen.findByRole('button', { name: '編輯新好友歡迎訊息內容' }));
    fireEvent.change(screen.getByRole('textbox', { name: '通知內容' }), { target: { value: '舊文案' } });
    await waitFor(() => expect(resolveOld).toBeTypeOf('function'));
    fireEvent.change(screen.getByRole('textbox', { name: '通知內容' }), { target: { value: '最新文案' } });
    await waitFor(() => expect(document.querySelector('.notification-bubble')).toHaveTextContent('最新文案'));
    await act(async () => { resolveOld!({ status: 'ready', note: '', format: 'text', text: '舊文案', bubbles: [], facts: [] }); });
    await waitFor(() => expect(document.querySelector('.notification-bubble')).toHaveTextContent('最新文案'));
    expect(document.querySelector('.notification-bubble')).not.toHaveTextContent('舊文案');
  });

  it('公版預覽失敗顯示錯誤，不殘留舊值或洩漏資料庫訊息', async () => {
    const { Harness, previews } = contentWorkbench();
    vi.mocked(previews.render).mockRejectedValue(new Error('private database detail'));
    render(<Harness />);
    fireEvent.click(await screen.findByRole('button', { name: '編輯訂金確認通知內容' }));
    await screen.findByText('預覽載入失敗，請重新查詢。');
    expect(screen.queryByRole('option', { name: 'CASE-1｜測試客戶' })).not.toBeInTheDocument();
    expect(document.body.textContent).not.toContain('private database detail');
    expect(document.querySelector('.notification-bubble')).toBeNull();
  });
});
