/**
 * File: line_notification_rules_mutation_panel.test.tsx
 * Description: 驗證通知規則欄位編輯、Preview 確認 Save、刪除專用 Preview 與 receipt 顯示。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { LineNotificationRulesCatalog } from '../api/line_configuration/line_configuration_query_schemas';
import type { LineNotificationRulesMutationClient } from '../api/line_notification_rules/line_notification_rules_mutation_client';
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
        onCommitted={onCommitted}
      />
    );

    expect(screen.getByRole('button', { name: '預覽儲存變更' })).toBeDisabled();
    fireEvent.change(screen.getByRole('textbox', { name: '訊息模板 ID' }), {
      target: { value: 'deposit_template_v2' },
    });
    fireEvent.click(screen.getByRole('button', { name: '預覽儲存變更' }));

    await screen.findByText('儲存預覽已就緒');
    expect(screen.getByText('版本 3 → 4')).toBeInTheDocument();
    expect(screen.getByText('設定指紋摘要：01234567…cdef')).toBeInTheDocument();
    expect(screen.queryByText(FINGERPRINT)).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '確認儲存通知規則' })).toBeDisabled();

    fireEvent.change(screen.getByRole('textbox', { name: '操作原因' }), {
      target: { value: '核准訂金通知模板更新' },
    });
    fireEvent.click(screen.getByRole('checkbox', {
      name: '我已確認版本、規則數與指紋摘要',
    }));
    fireEvent.click(screen.getByRole('button', { name: '確認儲存通知規則' }));

    await screen.findByText(/通知規則已儲存；取消 1 個 intent、2 個 task/);
    expect(save).toHaveBeenCalledTimes(1);
    expect(save.mock.calls[0][0]).toMatchObject({
      expected_revision: 3,
      preview_fingerprint: FINGERPRINT,
      reason: '核准訂金通知模板更新',
      definition: { rules: [expect.objectContaining({ template_id: 'deposit_template_v2' })] },
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

    render(<LineNotificationRulesMutationPanel catalog={CATALOG} client={client} />);
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
      name: '我已確認版本、規則數與指紋摘要',
    }));
    fireEvent.click(screen.getByRole('button', { name: '確認刪除通知規則' }));

    await screen.findByText(/規則 deposit_notice 已刪除；取消 0 個 intent、1 個 task/);
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

  it('存在未儲存編輯時鎖定 Delete，避免用錯 fingerprint 合併未確認變更', () => {
    const client: LineNotificationRulesMutationClient = {
      preview: vi.fn(),
      save: vi.fn(),
      deleteRule: vi.fn(),
    };
    render(<LineNotificationRulesMutationPanel catalog={CATALOG} client={client} />);

    fireEvent.change(screen.getByRole('textbox', { name: '訊息模板 ID' }), {
      target: { value: 'unsaved_template' },
    });

    expect(screen.getByRole('button', { name: '預覽刪除規則' })).toBeDisabled();
    expect(screen.getByText(/有未儲存編輯時，刪除功能會鎖定/)).toBeInTheDocument();
  });
});
