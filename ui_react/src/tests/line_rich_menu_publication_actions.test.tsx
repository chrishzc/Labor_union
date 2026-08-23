/**
 * File: line_rich_menu_publication_actions.test.tsx
 * Description: 驗證 Rich Menu 發布 Preview 確認 queue、去敏摘要與失敗紀錄的條件式 retry。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { LineRichMenuPublicationClient } from '../api/line_rich_menu_publication/line_rich_menu_publication_client';
import { LineRichMenuPublicationActions } from '../components/LineRichMenuPublicationActions';

const FINGERPRINT = '0123456789abcdef'.repeat(4);

afterEach(() => vi.restoreAllMocks());

describe('Rich Menu publication actions', () => {
  it('先顯示去敏 Preview，經原因與人工確認後只建立 durable queue receipt', async () => {
    const preview = vi.fn().mockResolvedValue({
      preview_id: 41,
      config_revision: '7',
      config_fingerprint: FINGERPRINT,
    });
    const publish = vi.fn().mockResolvedValue({
      id: 19,
      menu_definition_id: 'staff-menu',
      configuration_revision: 7,
      status: 'queued' as const,
    });
    const client: LineRichMenuPublicationClient = {
      preview,
      publish,
      retry: vi.fn(),
    };
    const onQueued = vi.fn();

    render(
      <LineRichMenuPublicationActions
        selectedMenu={{ id: 'staff-menu', name: '月嫂選單' }}
        client={client}
        onQueued={onQueued}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: '預覽發布' }));
    await screen.findByText('預覽已就緒');
    expect(screen.getByText('設定版本：7')).toBeInTheDocument();
    expect(screen.getByText('設定指紋摘要：01234567…cdef')).toBeInTheDocument();
    expect(screen.queryByText(FINGERPRINT)).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '確認排入發布' })).toBeDisabled();

    fireEvent.change(screen.getByRole('textbox', { name: '發布原因' }), {
      target: { value: '核准月嫂角色選單更新' },
    });
    fireEvent.click(screen.getByRole('checkbox', { name: '我已確認選單、設定版本與指紋摘要' }));
    fireEvent.click(screen.getByRole('button', { name: '確認排入發布' }));

    await screen.findByText('發布工作 #19：已排入');
    expect(screen.getByText(/durable 發布工作已建立/)).toBeInTheDocument();
    expect(publish).toHaveBeenCalledTimes(1);
    const payload = publish.mock.calls[0][1];
    expect(payload).toMatchObject({
      preview_id: 41,
      reason: '核准月嫂角色選單更新',
      idempotency_key: expect.stringMatching(/^line-rich-menu-publish-idem-/),
      correlation_id: expect.stringMatching(/^line-rich-menu-publish-corr-/),
    });
    expect(payload.idempotency_key).not.toBe(payload.correlation_id);
    await waitFor(() => expect(onQueued).toHaveBeenCalledTimes(1));
  });

  it('retry 只對 publish_retryable_failed 顯示，且需要原因與確認', async () => {
    const retry = vi.fn().mockResolvedValue({
      id: 23,
      menu_definition_id: 'customer-menu',
      configuration_revision: 9,
      status: 'queued' as const,
    });
    const client: LineRichMenuPublicationClient = {
      preview: vi.fn(),
      publish: vi.fn(),
      retry,
    };
    const { rerender } = render(
      <LineRichMenuPublicationActions
        selectedMenu={null}
        selectedPublication={{
          id: 23,
          menuDefinitionId: 'customer-menu',
          status: 'failed',
          statusLabel: '失敗',
        }}
        client={client}
      />
    );
    expect(screen.queryByRole('button', { name: '確認重新排入' })).not.toBeInTheDocument();

    rerender(
      <LineRichMenuPublicationActions
        selectedMenu={null}
        selectedPublication={{
          id: 23,
          menuDefinitionId: 'customer-menu',
          status: 'publish_retryable_failed',
          statusLabel: '發布可重試失敗',
        }}
        client={client}
      />
    );
    expect(screen.getByRole('button', { name: '確認重新排入' })).toBeDisabled();
    fireEvent.change(screen.getByRole('textbox', { name: '重試原因' }), {
      target: { value: '確認 provider 暫時性失敗已排除' },
    });
    fireEvent.click(screen.getByRole('checkbox', { name: '我已確認此紀錄為發布可重試失敗' }));
    fireEvent.click(screen.getByRole('button', { name: '確認重新排入' }));

    await screen.findByText('發布工作 #23：已排入');
    expect(retry).toHaveBeenCalledTimes(1);
    const payload = retry.mock.calls[0][1];
    expect(payload.idempotency_key).toMatch(/^line-rich-menu-retry-idem-/);
    expect(payload.correlation_id).toMatch(/^line-rich-menu-retry-corr-/);
    expect(payload.idempotency_key).not.toBe(payload.correlation_id);
  });
});
