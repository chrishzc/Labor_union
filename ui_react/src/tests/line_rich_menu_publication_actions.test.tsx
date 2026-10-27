/**
 * File: line_rich_menu_publication_actions.test.tsx
 * Description: 驗證 Rich Menu 一次提交串接內部 Preview／queue、去敏摘要與失敗紀錄的條件式 retry。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { sessionClient } from '../api/auth/session_client';
import type { LineRichMenuPublicationClient } from '../api/line_rich_menu_publication/line_rich_menu_publication_client';
import { LineRichMenuPublicationError } from '../api/line_rich_menu_publication/line_rich_menu_publication_errors';
import { LineRichMenuPublicationActions } from '../components/LineRichMenuPublicationActions';

const FINGERPRINT = '0123456789abcdef'.repeat(4);

afterEach(() => {
  sessionClient.clearSession();
  vi.restoreAllMocks();
});

describe('Rich Menu publication actions', () => {
  it('一次點擊先取得內部預覽再排入發布，不受非同步畫面狀態阻擋', async () => {
    sessionClient.setSession('root-session', {
      id: 7, username: 'root-session-test', display_name: '根管理員測試',
      role: 'system_admin', capabilities: ['line.menu.publish'], is_root: true,
      access_control_version: 1,
    });
    const preview = vi.fn().mockResolvedValue({
      preview_id: 40, config_revision: '7', config_fingerprint: FINGERPRINT,
    });
    const publish = vi.fn().mockResolvedValue({ id: 18, menu_definition_id: 'union_staff_menu', configuration_revision: 7, status: 'queued' as const });
    render(<LineRichMenuPublicationActions
      selectedMenu={{ id: 'union_staff_menu', name: '工會人員專屬選單' }}
      client={{ preview, publish, retry: vi.fn() }}
    />);

    expect(publish).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: '發布至 LINE' }));
    await screen.findByText('選單發布：已排入');
    expect(preview).toHaveBeenCalledTimes(1);
    expect(publish).toHaveBeenCalledTimes(1);
    expect(preview.mock.invocationCallOrder[0]).toBeLessThan(publish.mock.invocationCallOrder[0]);
    expect(screen.queryByRole('button', { name: /確認發布至 LINE/ })).not.toBeInTheDocument();
  });

  it('發布保留選填原因與內部 Preview，僅建立 durable queue receipt', async () => {
    sessionClient.setSession('root-session', {
      id: 7,
      username: 'root-session-test',
      display_name: '根管理員測試',
      role: 'system_admin',
      capabilities: ['line.menu.publish'],
      is_root: true,
      access_control_version: 1,
    });
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


    expect(screen.queryByText('版本：7')).not.toBeInTheDocument();
    expect(screen.queryByText(/指紋摘要/)).not.toBeInTheDocument();
    expect(screen.queryByText(FINGERPRINT)).not.toBeInTheDocument();
    expect(publish).not.toHaveBeenCalled();

    fireEvent.change(screen.getByRole('textbox', { name: /發布原因/ }), {
      target: { value: '核准月嫂角色選單更新' },
    });
    expect(screen.queryByRole('checkbox', { name: '我已確認選單內容與影響範圍，同意排入發布序列' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '發布至 LINE' }));

    await screen.findByText('選單發布：已排入');
    expect(screen.getByText(/尚未代表 LINE 平台已完成發布/)).toBeInTheDocument();
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

  it('本機免驗證模式阻擋發布及其內部預覽，並說明需真實 Session', async () => {
    sessionClient.setSession('development-bypass', {
      id: null,
      username: 'development-bypass',
      display_name: '開發模式管理員',
      role: 'system_admin',
      capabilities: [],
      is_root: false,
      access_control_version: 1,
    });
    const preview = vi.fn().mockResolvedValue({
      preview_id: 42,
      config_revision: '8',
      config_fingerprint: FINGERPRINT,
    });
    const publish = vi.fn();
    const client: LineRichMenuPublicationClient = {
      preview,
      publish,
      retry: vi.fn(),
    };

    render(
      <LineRichMenuPublicationActions
        selectedMenu={{ id: 'staff-menu', name: '月嫂選單' }}
        client={client}
      />
    );

    expect(screen.getByRole('note')).toHaveTextContent(
      '本機免驗證模式不可發布；請改用真實已登入的管理員 Session。'
    );
    fireEvent.click(screen.getByRole('button', { name: '發布至 LINE' }));
    expect(preview).not.toHaveBeenCalled();
    fireEvent.change(screen.getByRole('textbox', { name: /發布原因/ }), {
      target: { value: '核准月嫂角色選單更新' },
    });
    expect(screen.queryByRole('checkbox', { name: '我已確認選單內容與影響範圍，同意排入發布序列' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '發布至 LINE' })).toBeDisabled();
    expect(publish).not.toHaveBeenCalled();
  });

  it('retry 只對 publish_retryable_failed 顯示，一次提交並保留選填原因', async () => {
    sessionClient.setSession('enabled-internal-session', {
      id: 9,
      username: 'enabled-internal-test',
      display_name: '啟用內部使用者測試',
      role: 'operator',
      capabilities: [],
      is_root: false,
      access_control_version: 1,
    });
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
    expect(screen.queryByRole('button', { name: '重新排入發布' })).not.toBeInTheDocument();

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
    expect(screen.getByText('此選單發布可重新排入')).toBeInTheDocument();
    expect(screen.getByText('目前狀態：發布可重試失敗')).toBeInTheDocument();
    expect(screen.queryByText(/發布紀錄 #23/)).not.toBeInTheDocument();
    expect(screen.queryByText(/customer-menu/)).not.toBeInTheDocument();
    expect(retry).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: '重新排入發布' })).toBeEnabled();
    fireEvent.change(screen.getByRole('textbox', { name: '重試原因（選填）' }), {
      target: { value: '確認 provider 暫時性失敗已排除' },
    });
    expect(screen.queryByRole('checkbox', { name: '我已確認此紀錄為發布可重試失敗' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '重新排入發布' }));

    await screen.findByText('選單發布：已排入');
    expect(retry).toHaveBeenCalledTimes(1);
    const payload = retry.mock.calls[0][1];
    expect(payload.idempotency_key).toMatch(/^line-rich-menu-retry-idem-/);
    expect(payload.correlation_id).toMatch(/^line-rich-menu-retry-corr-/);
    expect(payload.idempotency_key).not.toBe(payload.correlation_id);
  });
  it('stale publication requires a fresh explicit submit and never blindly republishes', async () => {
    sessionClient.setSession('enabled-test-session', { id: 9, username: 'enabled-test', display_name: '管理員', role: 'system_admin', capabilities: ['line.menu.publish'], is_root: false, access_control_version: 1 });
    const preview = vi.fn().mockResolvedValue({ preview_id: 42, config_revision: '8', config_fingerprint: FINGERPRINT });
    const publish = vi.fn().mockRejectedValue(new LineRichMenuPublicationError('conflict', 'rich_menu_preview_stale', 'stale', 409));
    render(<LineRichMenuPublicationActions selectedMenu={{ id: 'customer_menu', name: '客戶選單' }} client={{ preview, publish, retry: vi.fn() }} />);
    fireEvent.change(screen.getByLabelText('發布原因（選填）'), { target: { value: '更新選單' } });
    fireEvent.click(screen.getByRole('button', { name: '發布至 LINE' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('請重新查詢後再發布');
    expect(preview).toHaveBeenCalledTimes(1); expect(publish).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('button', { name: '確認發布至 LINE' })).not.toBeInTheDocument();
    expect(screen.queryByRole('checkbox', { name: /同意排入發布序列/ })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '發布至 LINE' }));
    await waitFor(() => expect(publish).toHaveBeenCalledTimes(2));
    expect(preview).toHaveBeenCalledTimes(2);
    expect(publish.mock.calls[1][1].idempotency_key).not.toBe(publish.mock.calls[0][1].idempotency_key);
  });

});
