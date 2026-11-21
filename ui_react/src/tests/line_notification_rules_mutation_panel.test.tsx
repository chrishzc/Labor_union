/**
 * File: line_notification_rules_mutation_panel.test.tsx
 * Description: 驗證一次點擊送出、選填原因、內部 Preview／Apply 一致性及唯讀訊息預覽。
 */
import { UnsavedChangesProvider } from '../components/UnsavedChanges';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { LineNotificationRulesCatalog } from '../api/line_configuration/line_configuration_query_schemas';
import type { LineNotificationRulesMutationClient } from '../api/line_notification_rules/line_notification_rules_mutation_client';
import type { LineNotificationTemplateClient } from '../api/line_notification_rules/line_notification_template_client';
import { LineNotificationRulesMutationError } from '../api/line_notification_rules/line_notification_rules_mutation_errors';
import { LineNotificationRulesMutationPanel } from '../components/LineNotificationRulesMutationPanel';
import { useState } from 'react';
import { LineNotificationWorkbench } from '../components/LineNotificationWorkbench';
import type { LineConfigurationQueryClient } from '../api/line_configuration/line_configuration_query_client';
import { ApiHttpError } from '../api/shared/typed_errors';
import type { LineMessagePreviewClient, PreviewNode } from '../api/line_notification_rules/line_message_preview_client';
import { lineMessagePreviewClient } from '../api/line_notification_rules/line_message_preview_client';
import { LineMessageFlow } from '../components/LineMessageFlow';
import { LineManagementPage } from '../pages/LineManagementPage';

const FINGERPRINT = '0123456789abcdef'.repeat(4);

async function findFlowMessage(name: string | RegExp) {
  const sidebar = screen.getByRole('region', { name: 'LINE 流程圖' });
  const message = await waitFor(() => {
    const row = Array.from(sidebar.querySelectorAll<HTMLButtonElement>('[data-notification-id]')).find(button => {
      const label = button.getAttribute('aria-label') ?? '';
      return typeof name === 'string' ? label === name : name.test(label);
    });
    if (!row) throw new Error(`找不到流程訊息 ${name}`);
    return row;
  });
  const journey = message.closest('.notification-sidebar-journey')?.querySelector<HTMLButtonElement>('.notification-sidebar-group');
  if (journey?.getAttribute('aria-expanded') === 'false') fireEvent.click(journey);
  const stage = message.closest('.notification-sidebar-step')?.querySelector<HTMLButtonElement>('.notification-sidebar-stage');
  if (stage?.getAttribute('aria-expanded') === 'false') fireEvent.click(stage);
  return within(sidebar).findByRole('button', { name });
}

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
    { id: 'current-start-rule', event_code: 'order.service_start_day', recipient_selector: 'case_group', template_id: 'LINE-ORDER-SERVICE-START-DAY-CARD-V1', enabled: false, schedule: { kind: 'immediate' }, frequency: { kind: 'once' }, predicates: [] },
    { id: 'service-start-result', event_code: 'order.service_start_result', recipient_selector: 'case_group', template_id: 'LINE-ORDER-SERVICE-START-RESULT-V1', enabled: false, schedule: { kind: 'immediate' }, frequency: { kind: 'once' }, predicates: [] },
  ] } } satisfies LineNotificationRulesCatalog;
  const clients = contentWorkbench(catalog);
  vi.mocked(clients.templates.get).mockImplementation(async id => ({ rule_id: id, template_id: id === 'current-start-rule' ? 'LINE-ORDER-SERVICE-START-DAY-CARD-V1' : 'LU96-M1-LEAVE-EXTENSION-CARD-V1', name: id === 'current-start-rule' ? '服務開始當天通知卡' : '目前正式請假卡', content: '目前正式文案 {case_no}', revision: 19, variables: ['case_no'], sample_preview: '目前正式文案 DEMO-CASE-001' }));
  const builtin = (id: string, name: string) => ({ id, name, template_id: null, format: 'flex' as const, requires_case: false, requires_staff: false, builtin: true, allows_draft: false });
  vi.mocked(clients.previews.catalog).mockResolvedValue([
    ...catalog.definition.rules.map(rule => ({ ...builtin(rule.id, rule.id === 'current-start-rule' ? '服務開始當天通知卡' : '服務排程'), template_id: rule.template_id, builtin: false })),
    builtin('service-start-inquiry', '服務開始－代班接案意願詢問'),
    builtin('staff-leave-completed', '月嫂請假完成正式排班通知'),
    builtin('card-candidate-information-package', '目前案件資訊整包'),
    builtin('card-candidate-information-1', '目前訂單資訊一'), builtin('card-candidate-information-2', '目前訂單資訊二'), builtin('card-candidate-information-3', '目前每週說明'),
    builtin('deposit-reminder', '目前訂金提醒卡'),
    builtin('customer-service-ticket-reply', '專員協助回覆'),
  ]);
  return { ...clients, catalog };
}

describe('LINE 精簡流程圖與正式訊息定位', () => {

  it('退役的管理員告警與完工 Push 規則不列編輯項目或查詢文案', async () => {
    const retiredRules = [
      { ...CATALOG.definition.rules[0], id: 'retired-runtime-alert', event_code: 'runtime.alert.review_required', template_id: 'LU96-M4-SAFE-ALERT-CARD-V1' },
      { ...CATALOG.definition.rules[0], id: 'retired-complaint-alert', event_code: 'complaint.ingress.hold_high_ticket', template_id: 'LU96-M4-COMPLAINT-HIGH-CARD-V1' },
      { ...CATALOG.definition.rules[0], id: 'retired-completion-custom', event_code: 'order.service_completed', template_id: 'custom-completion-push' },
    ];
    const { Harness, templates } = contentWorkbench({ ...CATALOG, definition: { rules: [...CATALOG.definition.rules, ...retiredRules] } });
    render(<Harness />);
    await findFlowMessage('編輯訂金確認通知內容');
    expect(vi.mocked(templates.get).mock.calls.map(([id]) => id)).toEqual(['deposit_notice']);
    fireEvent.change(screen.getByRole('searchbox', { name: '搜尋通知名稱或內容' }), { target: { value: '告警' } });
    expect(await screen.findByText('沒有符合條件的通知')).toBeInTheDocument();
  });


  it('保留開工問候，移除開工服務回報，服務進度仍可定位', async () => {
    const { configuration, previews, catalog } = flowWorkbench(); const onOpen = vi.fn();
    const current = await previews.catalog();
    const fixed = [
      ['service-start-normal-received', '服務當天－服務正常受理回覆'],
      ['service-start-help-received', '服務當天－協助需求受理回覆'],
      ['payment-first-greeting', '開工當天問候'],
      ['payment-first-reminder', '開工當天問候含第一期款'],
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
    expect(screen.getByText('群組小幫手選單（月嫂專屬控制台）')).toBeInTheDocument();
    expect(screen.getByText('確認開工日')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /開工當天群組問候.*2 種公版/ })).toBeInTheDocument();
    expect(screen.queryByText('開工當天服務回報')).not.toBeInTheDocument();
    expect(screen.getByText('雙方合意延期')).toBeInTheDocument();
    expect(screen.getByText('客戶常見疑問')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /服務排程/ }));
    expect(onOpen).toHaveBeenLastCalledWith('service-start-result', expect.objectContaining({ journeyId: 'matching' }));
    fireEvent.click(screen.getByRole('tab', { name: '自助服務與留言' }));
    fireEvent.click(screen.getByRole('button', { name: /1 開啟服務/ }));
    fireEvent.click(screen.getByRole('button', { name: '查詢服務進度 2 則訊息 查看訊息' }));
    fireEvent.click(screen.getByRole('button', { name: /服務進度查詢結果/ }));
    expect(onOpen).toHaveBeenLastCalledWith('service-progress', expect.objectContaining({ journeyId: 'support' }));
    fireEvent.click(screen.getByRole('button', { name: /2 工會處理/ }));
    expect(screen.getByText('查看系統狀態')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /管理員個人告警|current-safe-alert|current-complaint-alert/ })).not.toBeInTheDocument();
    expect(onOpen).toHaveBeenLastCalledWith('service-progress', expect.objectContaining({ journeyId: 'support' }));
    expect(previews.render).not.toHaveBeenCalled(); expect(previews.subjects).not.toHaveBeenCalled();
  });

  it('完整列出簽約、日期自助與各期人工提醒，查閱不發送或儲存', async () => {
    const { configuration, previews, templates } = flowWorkbench(); const onOpen=vi.fn();
    const current=await previews.catalog();
    const additions=[['contract-signing-client','簽署提醒－客戶'],['contract-signing-staff','簽署提醒－月嫂'],
      ['contract-document-client','客戶契約下載通知'],['contract-document-staff','月嫂契約下載通知'],
      ['payment-overdue-deposit','訂金逾期－人工提醒客戶'],['payment-overdue-first','第一期款逾期－人工提醒案件群組'],['payment-overdue-second','第二期款逾期－人工提醒案件群組']];
    vi.mocked(previews.catalog).mockResolvedValue([...current,...additions.map(([id,name])=>({id,name,template_id:null,format:'text' as const,requires_case:false,requires_staff:false,builtin:true,allows_draft:false}))]);
    render(<LineMessageFlow configuration={configuration} previews={previews} onOpenMessage={onOpen}/>);
    expect(screen.getByText(/簽約與訂金付款可先後交錯/)).toBeInTheDocument();
    fireEvent.click(await screen.findByRole('button',{name:/3 簽約/}));
    expect(screen.getByText(/LINE 官方帳號聊天後台手動選用範本/)).toBeVisible();
    expect(screen.queryByRole('button', { name: /簽署提醒/ })).not.toBeInTheDocument();
    expect(screen.getByText(/瀏覽器預覽、列印或另存契約 PDF/)).toBeVisible();
    expect(screen.getByText(/確認客戶與所有現行月嫂的簽署文件/)).toBeVisible();
    expect(screen.queryByText(/寄送客戶及月嫂契約文件|契約下載通知/)).not.toBeInTheDocument();
    expect(onOpen).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button',{name:/4 收款與建群/}));
    expect(screen.getByRole('button',{name:/訂金逾期－私訊補寄與人工提醒/})).toBeEnabled();
    fireEvent.click(screen.getByRole('button',{name:/5 開始服務/}));
    expect(screen.getByText('群組小幫手選單（月嫂專屬控制台）')).toBeInTheDocument();
    expect(screen.getByText('確認開工日')).toBeInTheDocument();
    expect(screen.getByText('雙方合意延期')).toBeInTheDocument();
    expect(screen.getByText('客戶常見疑問')).toBeInTheDocument();
    expect(screen.queryByText(/第一期款－自動客戶私訊|第一期款入帳收據|第一期款逾期－私訊補寄與人工提醒|服務開始當天通知卡|服務開始當天受理回覆/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button',{name:/6 持續服務與異動/}));
    expect(screen.getByRole('button',{name:/第二期款逾期－私訊補寄與人工提醒/})).toBeEnabled();
    expect(previews.render).not.toHaveBeenCalled(); expect(templates.update).not.toHaveBeenCalled();
  });

  it('缺少問卷公版時清楚標示設定缺漏，不提供假的可用訊息', async () => {
    const { configuration, previews } = flowWorkbench(); const onOpen = vi.fn();
    render(<LineMessageFlow configuration={configuration} previews={previews} onOpenMessage={onOpen} />);
    fireEvent.click(await screen.findByRole('button', { name: '7 完工與結案 缺少訊息設定' }));
    const completion = screen.getByRole('button', { name: /滿意度調查問卷 缺少訊息設定/ });
    expect(completion).toBeDisabled();
    expect(within(completion.parentElement!).getByText('此訊息的規則或模板尚未設定，請先同步通知設定。')).toBeInTheDocument();
    expect(onOpen).not.toHaveBeenCalled(); expect(previews.render).not.toHaveBeenCalled();
  });

  it('呈現登記推播和聊天室回覆，客服由工會在官方帳號處理', async () => {
    const { configuration, previews } = flowWorkbench();
    const onOpen = vi.fn();
    const missingCatalogIds = [
      'service-profile-update', 'service-order-update', 'order-update-menu', 'matching-willing-received',
      'matching-customer-response', 'service-registration-unavailable', 'identity-staff-link', 'identity-admin-link',
      'service-resolved',
      'registration-approved-citizen', 'registration-approved-non-citizen',
    ];
    vi.mocked(previews.catalog).mockResolvedValue([
      ...await previews.catalog(),
      ...missingCatalogIds.map(id => ({
        id, name: id, template_id: null, format: 'text' as const, requires_case: false,
        requires_staff: false, builtin: true, allows_draft: false,
      })),
    ]);
    render(<LineMessageFlow configuration={configuration} previews={previews} onOpenMessage={onOpen} />);
    fireEvent.click(await screen.findByRole('tab', { name: '登記與身分' }));
    fireEvent.click(screen.getByRole('button', { name: /2 登記需求/ }));
    const approval = screen.getByRole('button', { name: /需求申請核准通知/ });
    expect(within(approval.parentElement!).getByText('自動推播')).toBeInTheDocument();
    expect(within(screen.getByRole('button', { name: /開啟服務登記/ }).parentElement!).getByText('只在聊天室回覆')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('tab', { name: '自助服務與留言' }));
    expect(screen.queryByRole('button', { name: /案件完成/ })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /2 工會處理/ }));
    expect(screen.getByText('官方帳號留言')).toBeInTheDocument();
    expect(screen.getByText('工會人員回覆詢問與客訴，並確認客戶資料或訂單變更後於後台維護。')).toBeInTheDocument();
    expect(screen.queryByText('訂單異動申請')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /人工升級案件結案通知|service-resolved/ })).not.toBeInTheDocument();
    expect(onOpen).not.toHaveBeenCalled();
    expect(previews.render).not.toHaveBeenCalled();
  });

  it('持續服務與異動移除重複節點，請假完成公版仍可從通知與發送唯讀開啟', async () => {
    const { configuration, previews, templates } = flowWorkbench();
    vi.spyOn(lineMessagePreviewClient, 'catalog').mockImplementation(previews.catalog);
    vi.spyOn(lineMessagePreviewClient, 'render').mockImplementation(previews.render);
    const example = '您的請假申請已完成正式排班處理。';
    vi.mocked(previews.render).mockResolvedValue({
      status: 'ready', format: 'text', note: '公版預覽', text: example, bubbles: [], facts: [],
    });
    window.history.replaceState(null, '', '#line-interface?tab=message_flow');
    const flow = render(<UnsavedChangesProvider><LineManagementPage scope="notifications" lineConfiguration={configuration} notificationTemplateClient={templates} /></UnsavedChangesProvider>);
    fireEvent.click(await screen.findByRole('button', { name: '持續服務與異動' }));
    expect(screen.queryByRole('button', { name: /請假、順延、代班與換人/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /月嫂請假完成正式排班處理/ })).not.toBeInTheDocument();
    flow.unmount();
    window.history.replaceState(null, '', '#line-notifications?tab=push_queue&message=staff-leave-completed');
    const workbench = render(<UnsavedChangesProvider><LineManagementPage scope="notifications" lineConfiguration={configuration} notificationTemplateClient={templates} /></UnsavedChangesProvider>);
    expect(await screen.findByText(example)).toBeInTheDocument();
    expect(previews.render).toHaveBeenCalledWith({ id: 'staff-leave-completed', data_source: 'sample' }, expect.any(Object));
    expect(templates.get).not.toHaveBeenCalledWith('staff-leave-completed', expect.anything());
    expect(screen.queryByRole('button', { name: '發送設定' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '儲存內容' })).not.toBeInTheDocument();
    workbench.unmount();
    window.history.replaceState(null, '', '/');
  });

  it('客服說明統一由 AI 客服 LIFF 提供，通知流程不再提供重複編輯', async () => {
    const { configuration, previews } = flowWorkbench(); const onOpen = vi.fn();
    const current = await previews.catalog();
    vi.mocked(previews.catalog).mockResolvedValue([...current, ...['service-menu'].map(id => ({id,name:id,template_id:null,format:'text' as const,requires_case:false,requires_staff:false,builtin:true,allows_draft:false}))]);
    render(<LineMessageFlow configuration={configuration} previews={previews} onOpenMessage={onOpen} />);
    fireEvent.click(screen.getByRole('tab', { name: '自助服務與留言' }));
    await screen.findByText(/一般詢問、客訴及客戶資料或訂單變更由工會人員在 LINE 官方帳號處理/);
    fireEvent.click(await screen.findByRole('button', { name: '1 開啟服務 1 則訊息' }));
    expect(screen.getByText(/統一在 AI 客服 LIFF 查看常見問答或提問/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /修改訂單資訊導覽/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /服務流程與收費說明.*調整訊息/ })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /查看服務導覽.*調整訊息/ }));
    expect(onOpen).toHaveBeenCalledWith('service-menu', expect.objectContaining({ journeyId: 'support' }));
  });

  it('完工階段提供問卷 Reply 範本，取消結算保留在原工作台', async () => {
    const { configuration, previews } = flowWorkbench();
    const onOpen = vi.fn();
    const publicSamples = ['helper-satisfaction-survey', 'cancellation-notice-settlement'].map(id => ({
      id, name: id, template_id: null, format: 'text' as const, requires_case: false,
      requires_staff: false, builtin: true, allows_draft: false,
    }));
    vi.mocked(previews.catalog).mockResolvedValue([...await previews.catalog(), ...publicSamples]);
    render(<LineMessageFlow configuration={configuration} previews={previews} onOpenMessage={onOpen} />);
    fireEvent.click(await screen.findByRole('button', { name: /7 完工與結案/ }));
    const survey = screen.getByRole('button', { name: /滿意度調查問卷.*調整訊息/ });
    expect(within(survey.parentElement!).getByText('只在聊天室回覆')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /取消結算通知/ })).not.toBeInTheDocument();
    expect(screen.getByText('帳務結算與結案')).toBeInTheDocument();
    fireEvent.click(survey);
    expect(onOpen).toHaveBeenCalledWith('helper-satisfaction-survey', expect.objectContaining({ journeyId: 'matching' }));
    expect(document.querySelectorAll('.line-flow-step')).toHaveLength(7);
  });

  it('預設顯示完整七個步驟，寄送案件資訊只列一則整包公版', async () => {
    const { configuration, previews } = flowWorkbench(); const onOpen = vi.fn();
    render(<LineMessageFlow configuration={configuration} previews={previews} onOpenMessage={onOpen} />);
    const first = await screen.findByRole('button', { name: '1 初步候選聯絡 1 則訊息' });
    expect(screen.queryByRole('button', { name: /目前訂單資訊/ })).not.toBeInTheDocument();
    expect(document.querySelectorAll('.line-flow-step')).toHaveLength(7);
    fireEvent.click(first);
    fireEvent.click(screen.getByRole('button', { name: '寄送案件資訊 由流程控制 調整訊息' }));
    expect(screen.queryByRole('button', { name: /目前訂單資訊/ })).not.toBeInTheDocument();
    expect(onOpen).toHaveBeenCalledExactlyOnceWith('card-candidate-information-package', expect.objectContaining({ journeyId: 'matching' }));
    expect(previews.render).not.toHaveBeenCalled(); expect(previews.subjects).not.toHaveBeenCalled();
  });

  it('依正式規則呈現停用，shadow rule 關閉仍顯示流程控制，並用目前 rule ID 導覽', async () => {
    const { configuration, previews } = flowWorkbench(); const onOpen = vi.fn();
    render(<LineMessageFlow configuration={configuration} previews={previews} onOpenMessage={onOpen} />);
    fireEvent.click(await screen.findByRole('button', { name: /5 開始服務/ }));
    expect(screen.getByRole('button', { name: '服務排程 已停用 調整訊息' })).toBeEnabled();
    fireEvent.click(screen.getByRole('button', { name: '服務排程 已停用 調整訊息' }));
    expect(onOpen).toHaveBeenCalledWith('service-start-result', expect.objectContaining({ journeyId: 'matching' }));
    fireEvent.click(screen.getByRole('button', { name: /6 持續服務與異動/ }));
    expect(screen.queryByRole('button', { name: /日誌連續缺漏/ })).not.toBeInTheDocument();
    expect(screen.getByText('第二期款入帳收據')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /第二期款入帳收據.*調整訊息/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('switch')).not.toBeInTheDocument();
  });

  it('返回流程時重查啟用狀態並保留步驟', async () => {
    const { configuration, previews, catalog } = flowWorkbench(); const onOpen = vi.fn();
    const ui = (active: boolean) => <LineMessageFlow active={active} configuration={configuration} previews={previews} onOpenMessage={onOpen} />;
    const { rerender } = render(ui(true));
    fireEvent.click(await screen.findByRole('button', { name: /5 開始服務/ }));
    expect(screen.getByText('已停用')).toBeInTheDocument();
    rerender(ui(false));
    vi.mocked(configuration.getNotificationRules).mockResolvedValue({ ...catalog, definition: { rules: catalog.definition.rules.map(rule => ({ ...rule, enabled: true })) } });
    rerender(ui(true));
    await screen.findByText('已啟用');
    expect(screen.getByRole('button', { name: /5 開始服務/ })).toHaveAttribute('aria-expanded', 'true');
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
    await screen.findByRole('button', { name: '1 初步候選聯絡 1 則訊息' });
  });

  it('流程圖已完全移除日誌缺漏提醒與加入好友系統歡迎訊息節點，入帳改由官方帳號說明', async () => {
    const { configuration, previews } = flowWorkbench();
    render(<LineMessageFlow configuration={configuration} previews={previews} onOpenMessage={vi.fn()} />);
    fireEvent.click(await screen.findByRole('button', { name: /4 收款與建群/ }));
    expect(screen.getByText('訂金確認入帳')).toBeInTheDocument();
    expect(screen.getByText(/LINE 官方帳號聊天後台使用預設訊息手動發送/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /6 持續服務與異動/ }));
    expect(screen.queryByRole('button', { name: /日誌連續缺漏/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /服務日誌/ })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('tab', { name: '登記與身分' }));
    fireEvent.click(screen.getByRole('button', { name: /1 加入好友 內部作業/ }));
    expect(screen.getByText('加入 LINE 好友（官方帳號設定）')).toBeInTheDocument();
    expect(screen.getByText(/加入好友歡迎訊息改由 LINE 官方帳號後台設定/)).toBeInTheDocument();
  });

  it('舊流程網址開啟常駐側欄，切換訊息時保護未儲存文案', async () => {
    const clients = flowWorkbench(); const { configuration, previews, templates } = clients;
    vi.spyOn(lineMessagePreviewClient, 'catalog').mockImplementation(previews.catalog);
    vi.spyOn(lineMessagePreviewClient, 'render').mockImplementation(previews.render);
    window.history.replaceState(null, '', '#line-management?tab=message_flow&rule_state=enabled');
    const { unmount } = render(<UnsavedChangesProvider><LineManagementPage scope="notifications" lineConfiguration={configuration} notificationTemplateClient={templates} /></UnsavedChangesProvider>);
    const sidebar = screen.getByRole('region', { name: 'LINE 流程圖' });
    fireEvent.click(await within(sidebar).findByRole('button', { name: '收款與建群' }));
    const opener = within(sidebar).getByRole('button', { name: '查看目前訂金提醒卡內容' });
    fireEvent.click(opener);
    expect(await screen.findByRole('textbox', { name: '通知內容' })).toHaveValue('目前正式文案 {case_no}');
    expect(window.location.hash).toContain('#line-notifications?tab=push_queue'); expect(window.location.hash).toContain('message=deposit-reminder');
    expect(within(sidebar).getByRole('button', { name: '收款與建群' })).toHaveAttribute('aria-expanded', 'true');
    expect(within(sidebar).getByRole('button', { name: '編輯目前訂金提醒卡內容' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.queryByRole('button',{name:'發送設定'})).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '完整流程圖' })).not.toBeInTheDocument();
    fireEvent.change(screen.getByRole('textbox', { name: '通知內容' }), { target: { value: '尚未儲存的內容' } });
    fireEvent.click(within(sidebar).getByRole('button', { name: '開始服務' }));
    const nextMessage = within(sidebar).getByRole('button', { name: '編輯目前正式請假卡內容' });
    fireEvent.click(nextMessage);
    expect(await screen.findByRole('dialog')).toHaveTextContent('尚未儲存的內容');
    fireEvent.click(screen.getByRole('button', { name: '繼續編輯' }));
    expect(screen.getByRole('textbox', { name: '通知內容' })).toHaveValue('尚未儲存的內容');
    fireEvent.click(nextMessage);
    fireEvent.click(screen.getByRole('button', { name: '捨棄變更並離開' }));
    expect(within(sidebar).getByRole('button', { name: '開始服務' })).toHaveAttribute('aria-expanded', 'true');
    expect(nextMessage).toHaveAttribute('aria-pressed', 'true');
    await waitFor(() => expect(screen.getByRole('heading', { name: '目前正式請假卡' })).toHaveFocus());
    const params = new URLSearchParams(window.location.hash.split('?')[1]);
    expect(params.get('message')).toBe('service-start-result');
    expect(params.has('view')).toBe(false);
    expect(previews.catalog).toHaveBeenCalledTimes(1);
    expect(configuration.getNotificationRules).toHaveBeenCalledTimes(1);
    expect(templates.update).not.toHaveBeenCalled();
    unmount(); window.history.replaceState(null, '', '/');
  });

  it('重新載入 message 連結會等正式查詢完成並打開正確內容；失效 ID 不改選其他訊息', async () => {
    const clients = flowWorkbench(); const { configuration, previews, templates } = clients;
    let resolveCatalog!: (value: Awaited<ReturnType<LineMessagePreviewClient['catalog']>>) => void;
    const rows = await previews.catalog();
    vi.spyOn(lineMessagePreviewClient, 'catalog').mockImplementation(() => new Promise(resolve => { resolveCatalog = resolve; }));
    vi.spyOn(lineMessagePreviewClient, 'render').mockImplementation(previews.render);
    window.history.replaceState(null, '', '#line-management?tab=push_queue&view=flow&message=card-candidate-information-1');
    const { unmount } = render(<LineManagementPage scope="notifications" lineConfiguration={configuration} notificationTemplateClient={templates} />);
    expect(window.location.hash).toContain('tab=push_queue');
    expect(window.location.hash).toContain('message=card-candidate-information-1');
    expect(window.location.hash).not.toContain('view=flow');
    await waitFor(() => expect(templates.get).toHaveBeenCalledWith('service-start-result', expect.any(Object)));
    expect(screen.queryByText(/找不到指定訊息/)).not.toBeInTheDocument();
    await act(async () => resolveCatalog(rows));
    await screen.findByRole('heading', { name: '目前訂單資訊一' });
    await waitFor(() => expect(previews.render).toHaveBeenCalledWith({ id: 'card-candidate-information-1', content: '目前正式文案 {case_no}', data_source: 'sample' }, expect.any(Object)));
    unmount();
    vi.mocked(lineMessagePreviewClient.catalog).mockResolvedValue(rows);
    window.history.replaceState(null, '', '#line-management?tab=push_queue&message=removed-message');
    const view = render(<LineManagementPage scope="notifications" lineConfiguration={configuration} notificationTemplateClient={templates} />);
    expect(window.location.hash).toContain('tab=push_queue');
    await screen.findByText(/找不到指定訊息/);
    expect(screen.queryByRole('textbox', { name: '通知內容' })).not.toBeInTheDocument();
    view.unmount(); window.history.replaceState(null, '', '/');
  });

  it('步驟 5 小幫手選單、確認卡、延期與常見疑問可直接從流程圖進入文案編輯並提示指令設定', async () => {
    const clients = flowWorkbench(); const { configuration, previews, templates } = clients;
    const helperEntries = [
      ['helper-menu-card', '案件群組－月嫂小幫手選單卡', 'flex'],
      ['helper-menu-completed', '案件群組－服務完工後的小幫手選單', 'flex'],
      ['helper-confirm-start-card', '確認開工日－客戶確認卡', 'flex'],
      ['helper-confirm-start-completed', '確認開工日－自動排班完成回覆', 'text'],
      ['helper-schedule-unconfirmed', '服務排程－尚未確認開工日提示', 'text'],
      ['helper-postponement-card', '雙方合意延期－客戶確認卡', 'flex'],
      ['helper-postponement-completed', '雙方合意延期－排程更新完成回覆', 'text'],
      ['helper-staff-assistance-ack', '專員協助－群組待辦受理回覆', 'text'],
      ['helper-staff-assistance-closed', '專員協助－已處理結案群組回覆', 'text'],
      ['helper-guidelines-card', '客戶常見疑問－導覽卡', 'flex'],
      ['helper-faq-ingredients', '客戶常見疑問－食材採買與準備標準回答', 'text'],
      ['helper-faq-hours', '客戶常見疑問－每日服務時數與範圍標準回答', 'text'],
      ['helper-faq-subsidy', '客戶常見疑問－政府補助申請與撥款標準回答', 'text'],
    ] as const;
    const current = await previews.catalog();
    vi.mocked(previews.catalog).mockResolvedValue([
      ...current,
      ...helperEntries.map(([id, name, format]) => ({
        id, name, template_id: null, format, requires_case: false, requires_staff: false, builtin: true, allows_draft: false,
      })),
    ]);
    vi.mocked(templates.get).mockImplementation(async id => {
      if (id === 'helper-postponement-card') {
        return {
          rule_id: id, template_id: `LINE-COPY-${id}`, name: '雙方合意延期－客戶確認卡',
          content: JSON.stringify({ title: '雙方合意延期確認單', body: '請假日 {leave_start_date} 補班日 {leave_end_date}' }),
          revision: 19, variables: ['case_no', 'staff_name', 'leave_start_date', 'leave_end_date'],
          sample_preview: '雙方合意延期確認單',
          fields: [
            { id: 'title', label: '卡片標題', kind: 'title', content: '雙方合意延期確認單', max_length: 100 },
            { id: 'body', label: '說明內容', kind: 'body', content: '請假日 {leave_start_date} 補班日 {leave_end_date}', max_length: 5000 },
          ],
        };
      }
      if (id === 'helper-menu-card' || id === 'helper-confirm-start-card' || id === 'helper-guidelines-card') {
        return {
          rule_id: id, template_id: `LINE-COPY-${id}`, name: id,
          content: JSON.stringify({ title: '標題', body: '說明內容' }),
          revision: 19, variables: ['case_no', 'staff_name'], sample_preview: '標題',
          fields: [
            { id: 'title', label: '卡片標題', kind: 'title', content: '標題', max_length: 100 },
            { id: 'body', label: '說明內容', kind: 'body', content: '說明內容', max_length: 5000 },
          ],
        };
      }
      return {
        rule_id: id, template_id: `LINE-COPY-${id}`, name: id,
        content: `測試文案 ${id}`, revision: 19, variables: ['case_no'], sample_preview: `測試文案 ${id}`,
      };
    });

    const onOpen = vi.fn();
    const flow = render(<LineMessageFlow configuration={configuration} previews={previews} onOpenMessage={onOpen} />);
    fireEvent.click(await screen.findByRole('button', { name: /5 開始服務/ }));
    expect(screen.getByText(/正式完工後，本案月嫂重新叫出選單即可看到「滿意度調查問卷」/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /群組小幫手選單.*2 種公版/ }));
    fireEvent.click(screen.getByRole('button', { name: /案件群組－服務完工後的小幫手選單/ }));
    expect(onOpen).toHaveBeenCalledWith('helper-menu-completed', expect.objectContaining({ journeyId: 'matching' }));
    fireEvent.click(screen.getByRole('button', { name: /案件群組－月嫂小幫手選單卡/ }));
    expect(onOpen).toHaveBeenCalledWith('helper-menu-card', expect.objectContaining({ journeyId: 'matching' }));
    fireEvent.click(screen.getByRole('button', { name: /確認開工日.*查看訊息/ }));
    fireEvent.click(screen.getByRole('button', { name: /確認開工日－客戶確認卡/ }));
    expect(onOpen).toHaveBeenCalledWith('helper-confirm-start-card', expect.objectContaining({ journeyId: 'matching' }));
    fireEvent.click(screen.getByRole('button', { name: /客戶常見疑問.*查看訊息/ }));
    fireEvent.click(screen.getByRole('button', { name: /客戶常見疑問－食材採買與準備標準回答/ }));
    expect(onOpen).toHaveBeenCalledWith('helper-faq-ingredients', expect.objectContaining({ journeyId: 'matching' }));
    flow.unmount();

    vi.spyOn(lineMessagePreviewClient, 'catalog').mockImplementation(previews.catalog);
    vi.spyOn(lineMessagePreviewClient, 'render').mockImplementation(previews.render);
    window.history.replaceState(null, '', '#line-management?tab=push_queue&message=helper-staff-assistance-closed');
    const workbench = render(
      <UnsavedChangesProvider>
        <LineManagementPage scope="notifications" lineConfiguration={configuration} notificationTemplateClient={templates} />
      </UnsavedChangesProvider>,
    );
    await screen.findByRole('heading', { name: '專員協助－已處理結案群組回覆' });
    await screen.findByRole('textbox', { name: '通知內容' });
    expect(screen.getByRole('link', { name: /LINE 介面設定 → 引導動作/ })).toHaveAttribute('href', '#line-interface?tab=guidance');

    const searchBox = screen.getByRole('searchbox', { name: '搜尋通知名稱或內容' });
    fireEvent.change(searchBox, { target: { value: '月嫂小幫手選單卡' } });
    fireEvent.click(await findFlowMessage(/(查看|編輯)案件群組－月嫂小幫手選單卡內容/));
    await screen.findByRole('heading', { name: '案件群組－月嫂小幫手選單卡' });
    await screen.findByRole('textbox', { name: '卡片標題' });
    expect(screen.getByRole('link', { name: /LINE 介面設定 → 引導動作/ })).toHaveAttribute('href', '#line-interface?tab=guidance');

    fireEvent.click(screen.getByRole('button', { name: '查看完工後選單公版' }));
    await screen.findByRole('heading', { name: '案件群組－服務完工後的小幫手選單' });
    await waitFor(() => expect(previews.render).toHaveBeenCalledWith({ id: 'helper-menu-completed', data_source: 'sample' }, expect.any(Object)));
    expect(templates.get).not.toHaveBeenCalledWith('helper-menu-completed', expect.anything());
    expect(screen.queryByRole('button', { name: '儲存內容' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '返回小幫手選單文案' }));
    await screen.findByRole('textbox', { name: '卡片標題' });

    fireEvent.change(searchBox, { target: { value: '雙方合意延期' } });
    fireEvent.click(await findFlowMessage(/(查看|編輯)雙方合意延期－客戶確認卡內容/));
    await screen.findByRole('heading', { name: '雙方合意延期－客戶確認卡' });
    await waitFor(() => expect(screen.getByRole('button', { name: '＋ 請假日期' })).toBeInTheDocument());
    expect(screen.getByRole('button', { name: '＋ 補班日期' })).toBeInTheDocument();

    workbench.unmount();
    window.history.replaceState(null, '', '/');
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
  let message = '案件 {case_no} 已確認訂金。';
  const messageData = () => ({ rule_id: 'deposit_notice', template_id: 'deposit_template', name: '訂金確認通知', content: message, revision, variables: ['case_no'], sample_preview: message });
  const templates: LineNotificationTemplateClient = {
    get: vi.fn(async () => messageData()),
    update: vi.fn(async (_id, payload) => { expect(payload.expected_revision).toBe(revision); message = payload.content; revision++; return messageData(); }),
  };
  const configuration: LineConfigurationQueryClient = {
    getNotificationRules: vi.fn(async () => catalog), getRichMenuConfiguration: vi.fn(), listRichMenuPublications: vi.fn(), getRichMenuPublication: vi.fn(),
  };
  const previews: LineMessagePreviewClient = {
    catalog: vi.fn(async () => [
      ...('rules' in catalog.definition ? catalog.definition.rules : []).map(rule => ({ id: rule.id, template_id: rule.template_id, name: '通知', format: 'text' as const, requires_case: true, requires_staff: false, builtin: false, allows_draft: false })),
    ]),
    subjects: vi.fn(async () => ({ items: [{ id: 'CASE-1', label: 'CASE-1｜測試客戶' }], next_cursor: null })),
    render: vi.fn(async payload => ({ status: 'ready' as const, note: '公版範例', format: 'text' as const,
      text: (payload.content ?? '').replaceAll('{url}', '［專屬安全登記連結］').replaceAll('{case_no}', 'DEMO-CASE-001'), bubbles: [],
      facts: [{ id: '案件編號（case_no）', label: 'DEMO-CASE-001' }] })),
  };
  function Harness() {
    const [search, setSearch] = useState('');
    return <UnsavedChangesProvider><LineNotificationWorkbench configuration={configuration} templates={templates} previews={previews} search={search} onSearchChange={setSearch} /></UnsavedChangesProvider>;
  }
  return { templates, configuration, previews, Harness };
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
  ];
  const retiredReceiptDescriptors = [
    { id: 'deposit-settled', name: '訂金已確認入帳卡', template_id: null, format: 'flex' as const, requires_case: false, requires_staff: false, builtin: true, allows_draft: false },
    { id: 'payment-first-settled', name: '第一期款已確認入帳通知', template_id: null, format: 'text' as const, requires_case: false, requires_staff: false, builtin: true, allows_draft: false },
    { id: 'retired-second-receipt', name: '第二期款已入帳通知', template_id: 'LINE-SECOND-PAYMENT-SETTLED-TEXT-V1', format: 'text' as const, requires_case: false, requires_staff: false, builtin: false, allows_draft: false },
  ];
  const paymentDescriptors = paymentMessages.map(([id, name]) => ({ id, name, template_id: null, format: id==='deposit-reminder' ? 'flex' as const : 'text' as const, requires_case: false, requires_staff: false, builtin: true, allows_draft: false }));

  it.each(paymentMessages)('通知與發送內的帳務範本 %s 沿原版本化 writer 儲存', async (id) => {
    const clients = flowWorkbench();
    vi.mocked(clients.templates.update).mockResolvedValue({rule_id:id,template_id:'LINE-COPY-'+id,name:'逾期提醒',content:'請協助確認本期款項 {case_no}',revision:20,variables:['case_no'],sample_preview:'公版範例'});
    const descriptors = await clients.previews.catalog();
    vi.spyOn(lineMessagePreviewClient, 'catalog').mockResolvedValue([...descriptors.filter(row=>!paymentMessages.some(([key])=>key===row.id)), ...paymentDescriptors, ...retiredReceiptDescriptors]);
    vi.spyOn(lineMessagePreviewClient, 'render').mockImplementation(clients.previews.render);
    window.history.replaceState(null, '', '#line-notifications?tab=push_queue&category=accounting&message='+id);
    render(<UnsavedChangesProvider><LineManagementPage scope="notifications" lineConfiguration={clients.configuration} notificationTemplateClient={clients.templates} /></UnsavedChangesProvider>);
    const field = await screen.findByRole('textbox', {name:'通知內容'});
    const sidebar = screen.getByRole('region', { name: 'LINE 流程圖' });
    expect(within(sidebar).getByRole('button', { name: '媒合到服務' })).toHaveAttribute('aria-expanded', 'true');
    expect(within(sidebar).getByRole('button', { pressed: true })).toHaveAttribute('data-notification-id', id);
    expect(screen.getByRole('heading',{name:'通知與發送'})).toBeInTheDocument();
    expect(screen.queryByRole('button',{name:'發送設定'})).not.toBeInTheDocument();
    expect(clients.configuration.getNotificationRules).toHaveBeenCalledTimes(1);
    expect(clients.templates.get).toHaveBeenCalledWith(id, expect.any(Object));
    expect(clients.templates.get).not.toHaveBeenCalledWith('current-start-rule', expect.any(Object));
    for (const item of retiredReceiptDescriptors) {
      expect(screen.queryByRole('button', { name: new RegExp(item.name) })).not.toBeInTheDocument();
    }
    fireEvent.change(field, {target:{value:'請協助確認本期款項 {case_no}'}});
    fireEvent.click(screen.getByRole('button',{name:'儲存內容'}));
    await waitFor(()=>expect(clients.templates.update).toHaveBeenCalledExactlyOnceWith(id, {content:'請協助確認本期款項 {case_no}',expected_revision:19},expect.any(Object)));
    await screen.findByText('通知內容已儲存。');
    expect(clients.previews.subjects).not.toHaveBeenCalled();
  });

  it('依業務流程及步驟展開，隱藏已退役通知', async () => {
    const {Harness,previews}=contentWorkbench();
    vi.mocked(previews.catalog).mockResolvedValue([...(await previews.catalog()),...paymentDescriptors,...retiredReceiptDescriptors,
      {id:'identity-pending',name:'身分申請受理通知',template_id:null,format:'text',requires_case:false,requires_staff:false,builtin:true,allows_draft:false}]);
    render(<Harness/>);
    const sidebar = screen.getByRole('region', { name: 'LINE 流程圖' });
    const serviceStages = ['初步候選聯絡', '正式媒合與客戶確認', '簽約', '收款與建群', '開始服務', '持續服務與異動', '完工與結案'];
    await within(sidebar).findByRole('button', { name: '媒合到服務' });
    expect(serviceStages.map(name => within(sidebar).getByRole('button', { name }).parentElement)).toEqual(Array.from(sidebar.querySelectorAll('.notification-sidebar-step')).slice(0, serviceStages.length));
    fireEvent.click(within(sidebar).getByRole('button', { name: '開始服務' }));
    expect(within(sidebar).getByRole('button', { name: '查看第一期結清問候內容' })).toBeInTheDocument();
    fireEvent.click(within(sidebar).getByRole('button', { name: '登記與身分' }));
    fireEvent.click(within(sidebar).getByRole('button', { name: '身分確認' }));
    expect(within(sidebar).getByRole('button', { name: '查看身分申請受理通知內容' })).toBeInTheDocument();
    expect(screen.queryByRole('button',{name:'編輯新好友歡迎訊息內容'})).not.toBeInTheDocument();
    for(const item of retiredReceiptDescriptors)expect(screen.queryByRole('button',{name:new RegExp(item.name)})).not.toBeInTheDocument();
  });

  it('流程分類包括現行補充公版，取消結算節點與帳務指向同一則文案', async () => {
    const { Harness, previews, templates } = contentWorkbench();
    const message = (id: string, name: string) => ({
      id, name, template_id: null, format: 'text' as const, requires_case: false, requires_staff: false, builtin: true, allows_draft: false,
    });
    vi.mocked(previews.catalog).mockResolvedValue([
      ...(await previews.catalog()),
      message('cancellation-notice-settlement', '取消結算明細通知'),
      message('cancellation-notice-refund', '取消結算退款完成通知'),
      message('cancellation-notice-collection', '取消結算補收入帳通知'),
      message('card-candidate-information-3', '每週安排公版'),
      message('staff-leave-completed', '請假完成公版'),
      message('identity-pending', '身分申請受理通知'),
      message('service-registration', '服務登記入口'),
      message('payment-reminder-ack', '繳費回報受理'),
    ]);
    render(<Harness />);
    const sidebar = screen.getByRole('region', { name: 'LINE 流程圖' });
    await within(sidebar).findByRole('button', { name: '初步候選聯絡' });
    fireEvent.click(within(sidebar).getByRole('button', { name: '初步候選聯絡' }));
    expect(within(sidebar).getByRole('button', { name: '查看每週安排公版內容' })).toBeInTheDocument();
    fireEvent.click(within(sidebar).getByRole('button', { name: '開始服務' }));
    expect(within(sidebar).queryByRole('button', { name: /請假完成公版/ })).not.toBeInTheDocument();
    fireEvent.click(within(sidebar).getByRole('button', { name: '收款與建群' }));
    expect(within(sidebar).getByRole('button', { name: '查看繳費回報受理內容' })).toBeInTheDocument();
    expect(await findFlowMessage('編輯訂金確認通知內容')).toBeInTheDocument();
    fireEvent.click(within(sidebar).getByRole('button', { name: '取消與結算' }));
    fireEvent.click(within(sidebar).getByRole('button', { name: '退款或補收完成' }));
    fireEvent.click(within(sidebar).getByRole('button', { name: '查看取消結算退款完成通知內容' }));
    expect(await screen.findByRole('textbox', { name: '通知內容' })).toBeInTheDocument();
    expect(templates.get).toHaveBeenCalledWith('cancellation-notice-refund', expect.any(Object));
    expect(within(sidebar).getByRole('button', { name: '編輯取消結算退款完成通知內容' })).toHaveAttribute('aria-pressed', 'true');
    expect(templates.update).not.toHaveBeenCalled();
  });

  it('每週安排圖片自動帶入，沒有文案編輯或儲存操作', async () => {
    const { Harness, previews, templates } = contentWorkbench();
    vi.mocked(previews.catalog).mockResolvedValue([{ id: 'card-candidate-information-3', template_id: null, name: '初步候選聯絡－每週服務說明', format: 'flex', requires_case: true, requires_staff: true, builtin: true, allows_draft: false }]);
    const picture: PreviewNode = { kind: 'image', text: '每週服務安排', image_data: 'data:image/png;base64,iVBORw0KGgo=', bold: false, size: 'sm', layout: 'vertical', primary: false, action_description: '', children: [] };
    vi.mocked(previews.render).mockResolvedValue({ status: 'ready', note: '公版範例', format: 'flex', text: '', bubbles: [picture], facts: [] });
    render(<Harness />);
    const entry = await findFlowMessage('查看初步候選聯絡－每週服務說明內容');
    const reads = vi.mocked(templates.get).mock.calls.length;
    fireEvent.click(entry);
    expect(await screen.findByRole('img', { name: '每週服務安排' })).toBeInTheDocument();
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '儲存內容' })).not.toBeInTheDocument();
    expect(templates.get).toHaveBeenCalledTimes(reads);
    expect(templates.update).not.toHaveBeenCalled();
  });
  it('搜尋會展開符合的流程，清除後維持選定訊息和步驟', async () => {
    const { Harness, previews } = contentWorkbench();
    vi.mocked(previews.catalog).mockResolvedValue(Array.from({ length: 14 }, (_, index) => ({ id: `fixed-${index + 1}`, template_id: null, name: `固定公告${index + 1}`, format: 'text' as const, requires_case: false, requires_staff: false, builtin: true, allows_draft: false })));
    render(<Harness />);
    await screen.findByRole('button', { name: '其他通知' });
    expect(screen.queryByRole('button', { name: '查看固定公告14內容' })).not.toBeInTheDocument();
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
    vi.mocked(previews.render).mockResolvedValue({ status: 'ready', note: '公版範例', format: 'flex', text: '', bubbles: titles.map(title => ({
      ...node(''), kind: 'box' as const, appearance: { bubble_size: 'kilo', background_color: '#F9F1E8', padding_left: 16 },
      children: [node(title), { ...node('查看詳情'), kind: 'button' as const, appearance: { button_style: 'link', color: '#815239' }, action_description: '開啟案件資料' }],
    })), facts: [] });
    render(<Harness />);
    fireEvent.click(await findFlowMessage('查看正式媒合－客戶完整推薦確認包內容'));
    const picker = await screen.findByRole('combobox', { name: '選擇預覽卡片' });
    expect(picker.closest('.notification-phone')).not.toBeNull();
    expect(within(picker).getAllByRole('option')).toHaveLength(5);
    expect(screen.getByRole('button', { name: '下一張卡片' })).toBeDisabled();
    const card = () => document.querySelector('.notification-real-flex-bubble');
    expect(card()).toHaveTextContent(titles[4]);
    expect(card()).toHaveStyle({ width: '240px' });
    expect(card()?.firstElementChild).toHaveStyle({ backgroundColor: '#F9F1E8', paddingLeft: '16px' });
    const previewAction = within(screen.getByRole('complementary', { name: 'LINE 對話預覽' })).getByRole('button', { name: '查看詳情' });
    expect(previewAction).toHaveStyle({ color: '#815239' });
    fireEvent.click(previewAction);
    expect(screen.getByText('查看詳情：開啟案件資料')).toBeVisible();
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
    const { previews, templates, configuration } = contentWorkbench();
    const onSelectedEntryChange = vi.fn();
    vi.mocked(previews.catalog).mockResolvedValue([{ id: 'service-menu', template_id: null, name: '服務與問答導覽卡', format: 'flex', requires_case: false, requires_staff: false, builtin: true, allows_draft: false }]);
    render(<UnsavedChangesProvider><LineNotificationWorkbench configuration={configuration} templates={templates} previews={previews} search="" onSearchChange={vi.fn()} selectedEntryId="service-other" onSelectedEntryChange={onSelectedEntryChange} /></UnsavedChangesProvider>);
    expect(await screen.findByRole('heading', { name: '服務與問答導覽卡' })).toBeInTheDocument();
    expect(onSelectedEntryChange).toHaveBeenCalledWith('service-menu');
    await waitFor(() => expect(templates.get).toHaveBeenCalledWith('service-menu', expect.anything()));
    expect(vi.mocked(templates.get).mock.calls.some(([id]) => id === 'service-other')).toBe(false);
  });
  it('既有客戶綁定成功連結解析至客戶獨立文案', async () => {
    const { previews, templates, configuration } = contentWorkbench();
    const onSelectedEntryChange = vi.fn();
    vi.mocked(previews.catalog).mockResolvedValue([{ id: 'identity-bound-customer', template_id: null, name: '客戶綁定成功', format: 'text', requires_case: false, requires_staff: false, builtin: true, allows_draft: false }]);
    render(<UnsavedChangesProvider><LineNotificationWorkbench configuration={configuration} templates={templates} previews={previews} search="" onSearchChange={vi.fn()} selectedEntryId="template-bind_success_new_order" onSelectedEntryChange={onSelectedEntryChange} /></UnsavedChangesProvider>);
    await screen.findByRole('textbox', { name: '通知內容' });
    expect(screen.getByRole('heading', { name: '客戶綁定成功' })).toBeInTheDocument();
    expect(onSelectedEntryChange).toHaveBeenCalledWith('identity-bound-customer');
    expect(screen.queryByText(/找不到指定訊息/)).not.toBeInTheDocument();
  });
  it.each(['card-caregiver-information', 'card-caregiver-information-2', 'card-customer-profiles'])('原正式媒合單張卡片入口 %s 統一開啟完整推薦包', async previous => {
    const { previews, templates, configuration } = contentWorkbench();
    const onSelectedEntryChange = vi.fn();
    vi.mocked(previews.catalog).mockResolvedValue([{ id: 'card-customer-confirmation', template_id: null, name: '正式媒合－客戶完整推薦確認包', format: 'flex', requires_case: true, requires_staff: true, builtin: true, allows_draft: false }]);
    render(<UnsavedChangesProvider><LineNotificationWorkbench configuration={configuration} templates={templates} previews={previews} search="" onSearchChange={vi.fn()} selectedEntryId={previous} onSelectedEntryChange={onSelectedEntryChange} /></UnsavedChangesProvider>);
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
    fireEvent.click(await findFlowMessage('查看呼叫專員－需求受理內容'));
    expect(screen.getByText('正在載入訊息內容…')).toBeInTheDocument();
    expect(screen.queryByRole('textbox', { name: '通知內容' })).not.toBeInTheDocument();
    await act(async () => complete({ rule_id: 'service-contact', template_id: 'LINE-COPY-service-contact', name: '受理', content: '已儲存的受理文案', revision: 7, variables: [], sample_preview: '已儲存的受理文案' }));
    expect(await screen.findByRole('textbox', { name: '通知內容' })).toHaveValue('已儲存的受理文案');
  });
  it('固定流程回覆可從流程開啟且沒有獨立開關', async () => {
    const { Harness, previews, templates } = contentWorkbench();
    const current = await previews.catalog();
    vi.mocked(previews.catalog).mockResolvedValue([...current, {
      id: 'helper-schedule-unconfirmed', template_id: null, name: '服務排程－尚未確認開工日提示',
      format: 'text', requires_case: false, requires_staff: false, builtin: true, allows_draft: false,
    }]);
    render(<Harness />);
    const replyName = '查看服務排程－尚未確認開工日提示內容';
    fireEvent.click(await findFlowMessage(replyName));
    expect(screen.queryByRole('button', { name: '發送設定' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '修改發送設定' })).not.toBeInTheDocument();
    expect(await screen.findByRole('button', { name: '儲存內容' })).toBeDisabled();
    expect(templates.update).not.toHaveBeenCalled();
  });
  it('排班結果的結構化卡片可預覽，沒有文案編輯及發送設定入口', async () => {
    const id = 'LINE-ORDER-SERVICE-START-RESULT-V1';
    const { Harness, previews, templates } = contentWorkbench({ revision: 3, definition: { rules: [{
      id, event_code: 'order.service_start_result', enabled: true,
      schedule: { kind: 'immediate' }, frequency: { kind: 'once' }, predicates: [],
      recipient_selector: 'case_group', template_id: 'LINE-ORDER-SERVICE-START-RESULT-V1',
    }] } });
    vi.mocked(templates.get).mockRejectedValue(new ApiHttpError(409, 'HTTP_409', '此規則使用的訊息格式目前不支援文字編輯。'));
    vi.mocked(previews.catalog).mockResolvedValue([{ id, template_id: 'LINE-ORDER-SERVICE-START-RESULT-V1', name: '排班結果', format: 'flex', requires_case: true, requires_staff: false, builtin: false, allows_draft: false }]);
    render(<Harness />);
    fireEvent.click(await findFlowMessage('查看通知內容內容'));
    expect(await screen.findByText('此卡片使用結構化內容，請查看手機預覽。')).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '儲存內容' })).not.toBeInTheDocument();
    await waitFor(() => expect(previews.render).toHaveBeenCalledWith({ id, data_source: 'sample' }, expect.any(Object)));
    expect(screen.queryByRole('button', { name: '發送設定' })).not.toBeInTheDocument();
    expect(templates.update).not.toHaveBeenCalled();
  });

  it('整張卡片同時編輯標題、自由說明與按鈕，插入資料後一次儲存', async () => {
    const { Harness, previews, templates } = contentWorkbench();
    const originalGet = vi.mocked(templates.get).getMockImplementation()!;
    const originalRender = vi.mocked(previews.render).getMockImplementation()!;
    const fields = [
      { id: 'altText', label: '訊息摘要', content: '原始摘要', max_length: 400 },
      { id: 'contents/body/contents/0/text', label: '卡片標題', content: '工會詢問', max_length: 5000 },
      { id: 'contents/footer/contents/0/action/label', label: '按鈕名稱', content: '回答問題', max_length: 20 },
      { id: 'contents/body/contents/$description', label: '說明內容', content: '', max_length: 5000, kind: 'body' as const, optional: true },
      { id: 'contents/header/contents/2/text', label: '副標題說明', content: '請核對日期。同意後，系統會更新排班。', max_length: 5000, kind: 'label' as const },
    ];
    vi.mocked(templates.get).mockImplementation(async (id, options) => id === 'card-customer-confirmation'
      ? { rule_id: id, template_id: 'LINE-COPY-card-customer-confirmation', name: '正式媒合－客戶完整推薦確認包', revision: 7, variables: ['case_no'], sample_preview: '', fields, content: JSON.stringify(Object.fromEntries(fields.map(field => [field.id, field.content]))) }
      : originalGet(id, options));
    vi.mocked(previews.catalog).mockResolvedValue([
      { id: 'service-contact', template_id: null, name: '呼叫專員－需求受理', format: 'text', requires_case: false, requires_staff: false, builtin: true, allows_draft: false },
      { id: 'card-customer-confirmation', template_id: null, name: '正式媒合－客戶完整推薦確認包', format: 'flex', requires_case: true, requires_staff: false, builtin: true, allows_draft: true },
    ]);
    vi.mocked(previews.render).mockImplementation(async (request, options) => {
      if (request.id !== 'card-customer-confirmation') return originalRender(request, options);
      const text = request.content?.includes('填寫回覆') ? '填寫回覆' : '回答問題';
      const button: PreviewNode = { kind: 'button', text, bold: false, size: 'sm', layout: 'vertical', primary: true, action_description: '回覆本次詢問', children: [] };
      return { status: 'ready', format: 'flex', note: '', text: '', bubbles: [button], facts: [] };
    });
    render(<Harness />);
    fireEvent.click(await findFlowMessage('查看呼叫專員－需求受理內容'));
    const fixedText = await screen.findByRole('textbox', { name: '通知內容' });
    fireEvent.change(fixedText, { target: { value: '請留下需要協助的內容。' } });
    expect(screen.getByRole('button', { name: '儲存內容' })).toBeEnabled();
    fireEvent.click(screen.getByRole('button', { name: '還原內容' }));
    fireEvent.click(await findFlowMessage('查看正式媒合－客戶完整推薦確認包內容'));
    const title = await screen.findByRole('textbox', { name: '卡片標題' });
    const oldPreviewButton = await screen.findByRole('button', { name: '回答問題' });
    const jumps = within(screen.getByRole('navigation', { name: '跳到編輯欄位' }));
    fireEvent.click(jumps.getByRole('button', { name: '標題' }));
    expect(title).toHaveFocus();
    fireEvent.change(title, { target: { value: '請確認服務條件' } });
    const mainButton = screen.getByRole('textbox', { name: '主要按鈕' });
    fireEvent.click(jumps.getByRole('button', { name: '按鈕' }));
    expect(mainButton).toHaveFocus();
    fireEvent.change(mainButton, { target: { value: '填寫回覆' } });
    const introduction = screen.getByRole('textbox', { name: '卡片開頭說明' });
    fireEvent.click(jumps.getByRole('button', { name: '說明' }));
    expect(introduction).toHaveFocus();
    expect(introduction).toHaveValue(fields[4].content);
    fireEvent.change(introduction, { target: { value: '請先確認服務日期。' } });
    const body = screen.getByRole('textbox', { name: '補充說明' });
    fireEvent.click(jumps.getByRole('button', { name: '內文' }));
    expect(body).toHaveFocus();
    fireEvent.change(body, { target: { value: '第一段說明\n\n自行增加的第二段提醒。' } });
    fireEvent.click(screen.getByRole('button', { name: '＋ 新增段落' }));
    await waitFor(() => expect(body).toHaveFocus());
    fireEvent.click(screen.getByRole('button', { name: '＋ 案件編號' }));
    expect(body).toHaveValue('第一段說明\n\n自行增加的第二段提醒。\n\n{case_no}');
    fireEvent.click(oldPreviewButton);
    expect(screen.getByText('回答問題：回覆本次詢問')).toBeVisible();
    expect(screen.queryByRole('combobox', { name: '編輯欄位' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '下一個欄位' })).not.toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: '卡片標題' })).toHaveValue('請確認服務條件');
    await waitFor(() => expect(previews.render).toHaveBeenLastCalledWith({ id: 'card-customer-confirmation', content: expect.stringContaining('填寫回覆'), data_source: 'sample' }, expect.any(Object)));
    await screen.findByRole('button', { name: '填寫回覆' });
    expect(screen.queryByText('回答問題：回覆本次詢問')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '儲存內容' }));
    await waitFor(() => expect(templates.update).toHaveBeenCalledWith('card-customer-confirmation', { content: expect.stringContaining('請確認服務條件'), expected_revision: 7 }, expect.any(Object)));
    expect(JSON.parse(vi.mocked(templates.update).mock.calls[0][1].content)[fields[3].id]).toBe('第一段說明\n\n自行增加的第二段提醒。\n\n{case_no}');
    expect(JSON.parse(vi.mocked(templates.update).mock.calls[0][1].content)[fields[4].id]).toBe('請先確認服務日期。');
  });

  it('共用通知清單排除已退役歡迎訊息，直接搜尋與編輯且不提供獨立發送紀錄', async () => {
    const { Harness } = contentWorkbench(); render(<Harness />);
    await findFlowMessage('編輯訂金確認通知內容');
    expect(screen.queryByRole('button', { name: '編輯新好友歡迎訊息內容' })).not.toBeInTheDocument();
    expect(within(screen.getByRole('region', { name: 'LINE 流程圖' })).getAllByRole('button', { name: /^編輯/ })).toHaveLength(1);
    expect(screen.queryByRole('tab')).not.toBeInTheDocument();
    expect(screen.queryByText('發送紀錄')).not.toBeInTheDocument();
    fireEvent.change(screen.getByRole('searchbox'), { target: { value: '訂金' } });
    fireEvent.click(screen.getByRole('button', { name: '編輯訂金確認通知內容' }));
    expect(screen.getByRole('textbox', { name: '通知內容' })).toHaveValue('案件 {case_no} 已確認訂金。');
    expect(screen.getByRole('button', { name: '儲存內容' })).toBeDisabled();
  });

  it('編輯並儲存通知後重新查詢共享版本，下一筆沿用最新 revision', async () => {
    const { Harness, templates } = contentWorkbench(); render(<Harness />);
    fireEvent.click(await findFlowMessage('編輯訂金確認通知內容'));
    fireEvent.change(screen.getByRole('textbox', { name: '通知內容' }), { target: { value: '新訂金通知 {case_no}' } });
    await waitFor(() => expect(document.querySelector('.notification-bubble')).toHaveTextContent('新訂金通知 DEMO-CASE-001'));
    fireEvent.click(screen.getByRole('button', { name: '儲存內容' }));
    await waitFor(() => expect(templates.update).toHaveBeenCalledWith('deposit_notice', { content: '新訂金通知 {case_no}', expected_revision: 7 }, expect.any(Object)));
    await waitFor(() => expect(templates.get).toHaveBeenCalledTimes(2));
    fireEvent.click(await findFlowMessage('編輯訂金確認通知內容'));
    expect(screen.getByRole('textbox', { name: '通知內容' })).toHaveValue('新訂金通知 {case_no}');
    fireEvent.change(screen.getByRole('textbox', { name: '通知內容' }), { target: { value: '再次更新 {case_no}' } });
    fireEvent.click(screen.getByRole('button', { name: '儲存內容' }));
    await waitFor(() => expect(templates.update).toHaveBeenLastCalledWith('deposit_notice', { content: '再次更新 {case_no}', expected_revision: 8 }, expect.any(Object)));
  });

  it('卡片說明可編輯，原流程的對象與排程不可在此改寫', async () => {
    const { Harness, templates } = contentWorkbench({ revision: 3, definition: { rules: [{
      id: 'alert-review', event_code: 'runtime.alert.review_required', recipient_selector: 'admin.review_actor',
      template_id: 'alert-review-card', enabled: false, schedule: { kind: 'immediate' }, frequency: { kind: 'once' }, predicates: [],
    }] } });
    vi.mocked(templates.get).mockResolvedValue({ rule_id: 'alert-review', template_id: 'alert-review-card',
      name: '告警待審核通知', content: '請查看本次告警。', revision: 7, variables: [], sample_preview: '請查看本次告警。' });
    render(<Harness />);
    fireEvent.click(await findFlowMessage('編輯告警待審核通知內容'));
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
    fireEvent.click(await findFlowMessage('編輯訂金確認通知內容'));
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

  it('通知查詢失敗顯示錯誤且不保留已退役歡迎訊息，不當成零筆成功', async () => {
    const { Harness, configuration } = contentWorkbench();
    vi.mocked(configuration.getNotificationRules).mockRejectedValue(new Error('raw query error'));
    render(<Harness />);
    await screen.findByRole('alert');
    expect(screen.queryByRole('button', { name: '編輯新好友歡迎訊息內容' })).not.toBeInTheDocument();
    expect(document.body.textContent).not.toContain('raw query error');
  });

  it('預覽目錄失敗時，已載入的規則仍能從其他通知編輯', async () => {
    const { Harness, previews, templates } = contentWorkbench();
    vi.mocked(previews.catalog).mockRejectedValue(new Error('raw catalog error'));
    render(<Harness />);
    expect(await screen.findByRole('alert')).toHaveTextContent('既有通知內容仍可維護');
    fireEvent.click(await findFlowMessage('編輯訂金確認通知內容'));
    expect(screen.getByRole('textbox', { name: '通知內容' })).toHaveValue('案件 {case_no} 已確認訂金。');
    expect(templates.update).not.toHaveBeenCalled();
  });

  it('手機即時預覽省略公版預覽資料及發送設定，試改只呼叫預覽', async () => {
    const { Harness, previews, templates } = contentWorkbench(); render(<Harness />);
    fireEvent.click(await findFlowMessage('編輯訂金確認通知內容'));
    await waitFor(() => expect(document.querySelector('.notification-bubble')).toHaveTextContent('案件 DEMO-CASE-001 已確認訂金。'));
    expect(screen.queryByRole('combobox', { name: '選擇案件' })).not.toBeInTheDocument();
    expect(screen.queryByRole('region', { name: '公版預覽資料' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '發送設定' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '內容與測試' })).not.toBeInTheDocument();
    expect(previews.subjects).not.toHaveBeenCalled();
    fireEvent.change(screen.getByRole('textbox', { name: '通知內容' }), { target: { value: '試改案件 {case_no}' } });
    expect(screen.getByText('正在更新預覽…')).toBeVisible();
    expect(document.querySelector('.notification-bubble')).toHaveTextContent('案件 DEMO-CASE-001 已確認訂金。');
    await waitFor(() => expect(document.querySelector('.notification-bubble')).toHaveTextContent('試改案件 DEMO-CASE-001'));
    expect(screen.queryByText('正在更新預覽…')).not.toBeInTheDocument();
    expect(previews.render).toHaveBeenLastCalledWith({ id: 'deposit_notice', content: '試改案件 {case_no}', data_source: 'sample' }, expect.objectContaining({ signal: expect.any(AbortSignal) }));
    expect(templates.update).not.toHaveBeenCalled();
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
    fireEvent.click(await findFlowMessage('編輯訂金確認通知內容'));
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
    fireEvent.click(await findFlowMessage('編輯訂金確認通知內容'));
    await screen.findByText('預覽載入失敗，請重新查詢。');
    expect(screen.queryByRole('option', { name: 'CASE-1｜測試客戶' })).not.toBeInTheDocument();
    expect(document.body.textContent).not.toContain('private database detail');
    expect(document.querySelector('.notification-bubble')).toBeNull();
  });
});
