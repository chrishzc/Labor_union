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
import type { LineMessagePreviewClient } from '../api/line_notification_rules/line_message_preview_client';

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
  it('補列正式訊息與卡片，詢問文案只能預覽，不提供儲存或正式動作', async () => {
    const { Harness, previews, templates, onboarding } = contentWorkbench();
    vi.mocked(previews.catalog).mockResolvedValue([
      { id: 'service-contact', template_id: null, name: '呼叫專員－需求受理', format: 'text', requires_case: false, requires_staff: false, builtin: true, allows_draft: false },
      { id: 'card-union-question', template_id: null, name: '工會詢問客戶卡', format: 'flex', requires_case: true, requires_staff: false, builtin: true, allows_draft: true },
    ]);
    render(<Harness />);
    fireEvent.click(await screen.findByRole('button', { name: '查看呼叫專員－需求受理內容' }));
    expect(screen.queryByRole('button', { name: '儲存內容' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '查看工會詢問客戶卡內容' }));
    fireEvent.change(screen.getByRole('textbox', { name: '預覽文案' }), { target: { value: '請協助確認服務條件。' } });
    await waitFor(() => expect(previews.render).toHaveBeenLastCalledWith({ id: 'card-union-question', content: '請協助確認服務條件。', data_source: 'sample' }, expect.any(Object)));
    expect(screen.queryByRole('button', { name: '儲存內容' })).not.toBeInTheDocument();
    expect(templates.update).not.toHaveBeenCalled(); expect(onboarding.update).not.toHaveBeenCalled();
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
    const { Harness, templates } = contentWorkbench(CARD_CATALOG); render(<Harness />);
    fireEvent.click(await screen.findByRole('button', { name: '編輯訂金確認通知內容' }));
    const editor = screen.getByRole('textbox', { name: '通知說明文字' });
    expect(editor).toBeEnabled();
    expect(screen.queryByRole('button', { name: '修改發送設定' })).not.toBeInTheDocument();
    fireEvent.change(editor, { target: { value: '請確認本次請假安排。' } });
    fireEvent.click(screen.getByRole('button', { name: '儲存內容' }));
    await waitFor(() => expect(templates.update).toHaveBeenCalledWith('leave_confirmation', expect.objectContaining({ content: '請確認本次請假安排。' }), expect.any(Object)));
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
