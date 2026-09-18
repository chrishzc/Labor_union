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
    const ruleSelector = screen.getByRole('combobox', { name: /要編輯的通知規則/ });
    expect(within(ruleSelector).getByRole('option', { name: '訂金確認' })).toBeInTheDocument();
    expect(screen.queryByRole('textbox', { name: '規則 ID' })).not.toBeInTheDocument();
    expect(screen.queryByRole('textbox', { name: '訊息模板 ID' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '預覽儲存變更' })).toBeDisabled();
    fireEvent.change(screen.getByRole('combobox', { name: '事件' }), {
      target: { value: 'order_lifecycle_transition' },
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
        event_code: 'order_lifecycle_transition',
        id: 'deposit_notice',
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

    fireEvent.change(screen.getByRole('combobox', { name: '事件' }), {
      target: { value: 'order_lifecycle_transition' },
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
});
