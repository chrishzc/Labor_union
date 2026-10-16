/**
 * File: line_notification_rules_mutation_panel.test.tsx
 * Description: 驗證通知規則欄位編輯、Preview 確認 Save、刪除專用 Preview 與 receipt 顯示。
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
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
  it('欄位變更後先顯示去敏 Preview，經原因與人工確認才儲存', async () => {
    const preview = vi.fn().mockImplementation(async (request) => ({
      before_revision: request.expected_revision,
      resulting_revision: request.expected_revision + 1,
      definition: request.definition,
      fingerprint: FINGERPRINT,
    }));
    const save = vi.fn().mockResolvedValue({
      revision: 4,
      preview_fingerprint: FINGERPRINT,
      cancelled_intent_count: 1,
      cancelled_task_count: 2,
    });
    const client: LineNotificationRulesMutationClient = {
      preview,
      save,
      deleteRule: vi.fn(),
    };
    const onCommitted = vi.fn();

    render(
      <LineNotificationRulesMutationPanel
        catalog={CATALOG}
        client={client}
        templateClient={templateClient()}
        onCommitted={onCommitted}
      />
    );

    await screen.findByRole('textbox', { name: '訊息內容編輯' });
    const ruleSelector = screen.getByRole('combobox', { name: '通知規則：' });
    expect(within(ruleSelector).getByRole('option', { name: '訂金確認' })).toBeInTheDocument();
    expect(screen.queryByRole('textbox', { name: '規則 ID' })).not.toBeInTheDocument();
    expect(screen.queryByRole('textbox', { name: '訊息模板 ID' })).not.toBeInTheDocument();
    expect(screen.queryByRole('combobox', { name: '事件' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '新增規則' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '預覽儲存變更' })).toBeDisabled();
    fireEvent.change(screen.getByRole('combobox', { name: '收件者' }), {
      target: { value: 'assigned_caregiver' },
    });
    fireEvent.click(screen.getByRole('button', { name: '預覽儲存變更' }));

    await screen.findByText('儲存預覽已就緒');
    expect(screen.queryByText('版本 3 → 4')).not.toBeInTheDocument();
    expect(screen.queryByText(/指紋摘要/)).not.toBeInTheDocument();
    expect(screen.queryByText(FINGERPRINT)).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '確認儲存通知規則' })).toBeDisabled();

    fireEvent.change(screen.getByRole('textbox', { name: '操作原因' }), {
      target: { value: '核准訂金通知事件更新' },
    });
    fireEvent.click(screen.getByRole('checkbox', {
      name: '我已確認通知規則與影響範圍',
    }));
    fireEvent.click(screen.getByRole('button', { name: '確認儲存通知規則' }));

    await screen.findByText(/通知規則已儲存；已取消 1 筆待發通知與 2 筆發送工作/);
    expect(save).toHaveBeenCalledTimes(1);
    expect(save.mock.calls[0][0]).toMatchObject({
      expected_revision: 3,
      preview_fingerprint: FINGERPRINT,
      reason: '核准訂金通知事件更新',
      definition: { rules: [expect.objectContaining({
        event_code: 'deposit_confirmed',
        id: 'deposit_notice',
        recipient_selector: 'assigned_caregiver',
        template_id: 'deposit_template',
      })] },
      idempotency_key: expect.stringMatching(/^line-notification-save-idem-/),
      correlation_id: expect.stringMatching(/^line-notification-save-corr-/),
    });
    expect(save.mock.calls[0][0].idempotency_key).not.toBe(
      save.mock.calls[0][0].correlation_id
    );
    await waitFor(() => expect(onCommitted).toHaveBeenCalledTimes(1));
  });

  it('刪除使用目前 revision 移除單一規則的專用 Preview，再呼叫 DELETE', async () => {
    const preview = vi.fn().mockResolvedValue({
      before_revision: 3,
      resulting_revision: 4,
      definition: { rules: [] },
      fingerprint: FINGERPRINT,
    });
    const deleteRule = vi.fn().mockResolvedValue({
      rule_id: 'deposit_notice',
      revision: 4,
      preview_fingerprint: FINGERPRINT,
      cancelled_intent_count: 0,
      cancelled_task_count: 1,
    });
    const client: LineNotificationRulesMutationClient = {
      preview,
      save: vi.fn(),
      deleteRule,
    };

    render(<LineNotificationRulesMutationPanel catalog={CATALOG} client={client} templateClient={templateClient()} />);
    fireEvent.click(screen.getByRole('button', { name: '預覽刪除規則' }));

    await screen.findByText('刪除預覽已就緒');
    expect(preview).toHaveBeenCalledWith(
      { expected_revision: 3, definition: { rules: [] } },
      expect.objectContaining({ signal: expect.any(AbortSignal) })
    );
    fireEvent.change(screen.getByRole('textbox', { name: '操作原因' }), {
      target: { value: '停用已退役通知流程' },
    });
    fireEvent.click(screen.getByRole('checkbox', {
      name: '我已確認通知規則與影響範圍',
    }));
    fireEvent.click(screen.getByRole('button', { name: '確認刪除通知規則' }));

    await screen.findByText(/規則 deposit_notice 已刪除；已取消 0 筆待發通知與 1 筆發送工作/);
    expect(deleteRule).toHaveBeenCalledTimes(1);
    expect(deleteRule.mock.calls[0][0]).toBe('deposit_notice');
    expect(deleteRule.mock.calls[0][1]).toMatchObject({
      expected_revision: 3,
      preview_fingerprint: FINGERPRINT,
      reason: '停用已退役通知流程',
      idempotency_key: expect.stringMatching(/^line-notification-delete-idem-/),
      correlation_id: expect.stringMatching(/^line-notification-delete-corr-/),
    });
  });

  it('存在未儲存編輯時鎖定 Delete，避免用錯 fingerprint 合併未確認變更', async () => {
    const client: LineNotificationRulesMutationClient = {
      preview: vi.fn(),
      save: vi.fn(),
      deleteRule: vi.fn(),
    };
    render(<LineNotificationRulesMutationPanel catalog={CATALOG} client={client} templateClient={templateClient()} />);
    await screen.findByRole('textbox', { name: '訊息內容編輯' });

    fireEvent.change(screen.getByRole('combobox', { name: '收件者' }), {
      target: { value: 'assigned_caregiver' },
    });

    expect(screen.getByRole('button', { name: '預覽刪除規則' })).toBeDisabled();
    expect(screen.getByText(/有未儲存編輯時，刪除功能會鎖定/)).toBeInTheDocument();
  });

  it('不將 typed error code 或後端訊息穿透到一般通知規則畫面', async () => {
    const client: LineNotificationRulesMutationClient = {
      preview: vi.fn().mockRejectedValue(new LineNotificationRulesMutationError(
        'raw_rule_failure',
        'raw provider detail must stay closed',
      )),
      save: vi.fn(),
      deleteRule: vi.fn(),
    };
    render(<LineNotificationRulesMutationPanel catalog={CATALOG} client={client} templateClient={templateClient()} />);
    await screen.findByRole('textbox', { name: '訊息內容編輯' });

    fireEvent.change(screen.getByRole('combobox', { name: '收件者' }), {
      target: { value: 'assigned_caregiver' },
    });
    fireEvent.click(screen.getByRole('button', { name: '預覽儲存變更' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('LINE 通知規則操作未完成，請重新載入最新規則後再試。');
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
  function Harness() {
    const [search, setSearch] = useState('');
    const [enabled, setEnabled] = useState<'all' | 'enabled' | 'disabled'>('all');
    return <LineNotificationWorkbench configuration={configuration} onboarding={onboarding} templates={templates} search={search} enabled={enabled} onSearchChange={setSearch} onEnabledChange={setEnabled} />;
  }
  return { templates, onboarding, configuration, Harness };
}

describe('通知內容統一工作區', () => {
  it('歡迎訊息與通知共用清單，搜尋內容且直接開啟編輯，不提供獨立發送紀錄', async () => {
    const { Harness } = contentWorkbench(); render(<Harness />);
    await screen.findByRole('button', { name: '編輯新好友歡迎訊息內容' });
    expect(screen.getAllByRole('row')).toHaveLength(3);
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
    expect(document.querySelector('.notification-bubble')).toHaveTextContent('新歡迎文字 ［專屬安全登記連結］');
    fireEvent.click(screen.getByRole('button', { name: '儲存內容' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(onboarding.update).toHaveBeenCalledWith({ content: '新歡迎文字 {url}', expected_revision: 7 }, expect.objectContaining({ signal: expect.any(AbortSignal) }));
    fireEvent.click(await screen.findByRole('button', { name: '編輯訂金確認通知內容' }));
    fireEvent.change(screen.getByRole('textbox', { name: '通知內容' }), { target: { value: '新訂金通知 {case_no}' } });
    fireEvent.click(screen.getByRole('button', { name: '儲存內容' }));
    await waitFor(() => expect(templates.update).toHaveBeenCalledWith('deposit_notice', { content: '新訂金通知 {case_no}', expected_revision: 8 }, expect.any(Object)));
    await screen.findByText('新訂金通知 {case_no}');
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
    fireEvent.click(screen.getByText('發送設定', { selector: 'summary' }));
    fireEvent.click(screen.getByRole('button', { name: '修改發送設定' }));
    fireEvent.click(screen.getByRole('checkbox', { name: '啟用此規則' }));
    fireEvent.click(screen.getByRole('button', { name: '返回內容' }));
    fireEvent.click(screen.getByRole('button', { name: '繼續編輯' }));
    expect(screen.getByRole('checkbox', { name: '啟用此規則' })).not.toBeChecked();
  });
});
