/**
 * File: line_identity_maintenance_actions.test.tsx
 * Description: 驗證 LINE 身分更正 Preview／Apply、解除 retry 與人工完成二次確認流程。
 */
import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { LineIdentityClient } from '../api/line_identity/line_identity_client';
import { LineIdentityClientError } from '../api/line_identity/line_identity_errors';
import { LineIdentityMaintenanceActions } from '../components/LineIdentityMaintenanceActions';
import {
  BOUND_IDENTITY_FIXTURE,
  FIXTURE_LINE_USER_ID,
  REVOCATION_REQUEST_FIXTURE,
} from './fixtures/line_identity/line_identity_contract_fixtures';

type MaintenanceClient = Pick<
  LineIdentityClient,
  | 'previewReplacement'
  | 'applyReplacement'
  | 'retryRevocation'
  | 'manualCompleteRevocation'
>;

afterEach(() => vi.restoreAllMocks());

function maintenanceClient(overrides: Partial<MaintenanceClient> = {}): MaintenanceClient {
  return {
    previewReplacement: vi.fn().mockResolvedValue({
      binding: BOUND_IDENTITY_FIXTURE,
      target_subject_reference: 'CLIENT-TARGET-002',
      target_subject_name: '更正客戶乙',
      blockers: [],
    }),
    applyReplacement: vi.fn().mockResolvedValue({
      ...BOUND_IDENTITY_FIXTURE,
      version: 8,
      subject_reference: 'CLIENT-TARGET-002',
      subject_name: '更正客戶乙',
    }),
    retryRevocation: vi.fn().mockResolvedValue({
      ...REVOCATION_REQUEST_FIXTURE,
      request_id: 91,
      status: 'menu_reset_failed',
    }),
    manualCompleteRevocation: vi.fn().mockResolvedValue({
      ...REVOCATION_REQUEST_FIXTURE,
      request_id: 91,
      status: 'manual_completed',
    }),
    ...overrides,
  };
}

describe('LINE 身分維護操作', () => {
  it('更正必須先 Preview、填寫原因並確認，Apply 使用唯一 caller identities', async () => {
    const client = maintenanceClient();
    const onBindingChanged = vi.fn();
    render(
      <LineIdentityMaintenanceActions
        lineUserId={FIXTURE_LINE_USER_ID}
        binding={BOUND_IDENTITY_FIXTURE}
        client={client}
        onBindingChanged={onBindingChanged}
      />
    );

    fireEvent.change(screen.getByRole('textbox', { name: '更正對象識別值' }), {
      target: { value: 'CLIENT-TARGET-002' },
    });
    fireEvent.click(screen.getByRole('button', { name: '預覽對象更正' }));
    await screen.findByText('更正客戶乙');
    const applyButton = screen.getByRole('button', { name: '提交對象更正' });
    expect(applyButton).toBeDisabled();

    fireEvent.change(screen.getByRole('textbox', { name: '更正原因' }), {
      target: { value: '先前綁定到錯誤客戶' },
    });
    fireEvent.click(screen.getByRole('checkbox', { name: '我已核對目前綁定與更正對象' }));
    fireEvent.click(applyButton);

    await screen.findByText(/綁定對象已更正為 更正客戶乙/);
    expect(client.previewReplacement).toHaveBeenCalledWith(
      FIXTURE_LINE_USER_ID,
      'CLIENT-TARGET-002',
      expect.any(Object)
    );
    expect(client.applyReplacement).toHaveBeenCalledWith(
      FIXTURE_LINE_USER_ID,
      expect.objectContaining({
        expected_version: 7,
        target_subject_reference: 'CLIENT-TARGET-002',
        reason: '先前綁定到錯誤客戶',
        idempotency_key: expect.stringMatching(/^line-identity-replacement-apply-/),
        correlation_id: expect.stringMatching(/^line-identity-replacement-/),
      }),
      expect.any(Object)
    );
    expect(onBindingChanged).toHaveBeenCalledTimes(1);
    expect(document.body.textContent).not.toContain(FIXTURE_LINE_USER_ID);
  });

  it('解除失敗可 retry，但人工完成必須原因加兩項明確確認', async () => {
    const client = maintenanceClient();
    const failedBinding = {
      ...BOUND_IDENTITY_FIXTURE,
      status: 'revocation_pending' as const,
      revocation_request_id: 91,
      revocation_status: 'menu_reset_failed' as const,
    };
    render(
      <LineIdentityMaintenanceActions
        lineUserId={FIXTURE_LINE_USER_ID}
        binding={failedBinding}
        client={client}
        canManualComplete
      />
    );

    const manualButton = screen.getByRole('button', { name: '人工完成解除' });
    expect(manualButton).toBeDisabled();
    fireEvent.change(screen.getByRole('textbox', { name: '維護原因' }), {
      target: { value: 'provider 回復已永久失敗' },
    });
    fireEvent.click(screen.getByRole('button', { name: '重新排入 Rich Menu 回復' }));
    await screen.findByText(/已重新排入 Rich Menu 回復流程/);
    expect(client.retryRevocation).toHaveBeenCalledWith(
      91,
      { reason: 'provider 回復已永久失敗' },
      expect.any(Object)
    );

    expect(manualButton).toBeDisabled();
    fireEvent.click(screen.getByRole('checkbox', { name: '我已確認 LINE 平台永久失敗或重試已耗盡' }));
    expect(manualButton).toBeDisabled();
    fireEvent.click(screen.getByRole('checkbox', { name: '我了解人工完成會直接完成解除並清除授權關聯' }));
    fireEvent.click(manualButton);

    await screen.findByText('人工解除完成');
    expect(client.manualCompleteRevocation).toHaveBeenCalledWith(
      91,
      { reason: 'provider 回復已永久失敗' },
      expect.any(Object)
    );
  });

  it('pending request 只顯示背景處理狀態，不提供後端不允許的維護按鈕', () => {
    const pendingBinding = {
      ...BOUND_IDENTITY_FIXTURE,
      status: 'revocation_pending' as const,
      revocation_request_id: 91,
      revocation_status: 'pending_menu_reset' as const,
    };
    render(
      <LineIdentityMaintenanceActions
        lineUserId={FIXTURE_LINE_USER_ID}
        binding={pendingBinding}
        client={maintenanceClient()}
      />
    );

    expect(screen.getByText(/背景服務正在回復 LINE 選單/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '重新排入 Rich Menu 回復' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '人工完成解除' })).not.toBeInTheDocument();
  });

  it('沒有 override capability 時不呈現人工完成控制', () => {
    const failedBinding = {
      ...BOUND_IDENTITY_FIXTURE,
      status: 'revocation_pending' as const,
      revocation_request_id: 91,
      revocation_status: 'menu_reset_failed' as const,
    };
    render(
      <LineIdentityMaintenanceActions
        lineUserId={FIXTURE_LINE_USER_ID}
        binding={failedBinding}
        client={maintenanceClient()}
        canManualComplete={false}
      />
    );

    expect(screen.getByText(/只提供具 LINE 身分人工處理權限/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '人工完成解除' })).not.toBeInTheDocument();
  });

  it('不將 typed error code 或後端訊息穿透到一般身分維護畫面', async () => {
    const client = maintenanceClient({
      previewReplacement: vi.fn().mockRejectedValue(new LineIdentityClientError(
        'BACKEND_REJECTED',
        'raw provider detail must stay closed',
      )),
    });
    render(
      <LineIdentityMaintenanceActions
        lineUserId={FIXTURE_LINE_USER_ID}
        binding={BOUND_IDENTITY_FIXTURE}
        client={client}
      />
    );

    fireEvent.change(screen.getByRole('textbox', { name: '更正對象識別值' }), {
      target: { value: 'CLIENT-TARGET-002' },
    });
    fireEvent.click(screen.getByRole('button', { name: '預覽對象更正' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('LINE 身分維護服務目前無法安全完成這項操作，請稍後再試。');
    expect(document.body.textContent).not.toContain('BACKEND_REJECTED');
    expect(document.body.textContent).not.toContain('raw provider detail');
  });
});
