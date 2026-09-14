/**
 * File: line_onboarding_editor.test.tsx
 * Description: 測試 LINE Onboarding 訊息編輯器之載入、即時預覽、編輯、還原預設與儲存流程。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { LineOnboardingClient, LineOnboardingData } from '../api/line_onboarding/line_onboarding_client';
import { LineOnboardingEditor, OFFICIAL_DEFAULT_ONBOARDING_MESSAGE } from '../components/LineOnboardingEditor';

const MOCK_DATA: LineOnboardingData = {
  template_id: 'customer_onboarding_welcome',
  content: '您好！歡迎加入工會。\n請點選連結：{url} 完成登記。',
  revision: 3,
  sample_preview: '您好！歡迎加入工會。\n請點選連結：https://liff.line.me/sample/gateway 完成登記。',
  variables: ['url'],
};

describe('LineOnboardingEditor', () => {
  it('成功載入並展示現有文案與版本號', async () => {
    const mockClient: LineOnboardingClient = {
      get: vi.fn().mockResolvedValue(MOCK_DATA),
      preview: vi.fn(),
      update: vi.fn(),
    };

    render(<LineOnboardingEditor client={mockClient} />);

    expect(screen.getByText(/正在載入 Onboarding 歡迎訊息設定/)).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText('版本 Rev.3')).toBeInTheDocument();
    });

    const textarea = screen.getByTestId('onboarding-textarea') as HTMLTextAreaElement;
    expect(textarea.value).toBe(MOCK_DATA.content);

    const preview = screen.getByTestId('onboarding-preview-box');
    expect(preview.textContent).toContain('您好！歡迎加入工會。');
    expect(preview.textContent).toContain('https://liff.line.me/{LIFF_ID}/gateway');
  });

  it('支援手動編輯文字並即時反應在預覽區', async () => {
    const mockClient: LineOnboardingClient = {
      get: vi.fn().mockResolvedValue(MOCK_DATA),
      preview: vi.fn(),
      update: vi.fn(),
    };

    render(<LineOnboardingEditor client={mockClient} />);
    await waitFor(() => expect(screen.getByTestId('onboarding-textarea')).toBeInTheDocument());

    const textarea = screen.getByTestId('onboarding-textarea') as HTMLTextAreaElement;
    fireEvent.change(textarea, { target: { value: '全新自訂歡迎文字！登記入線：{url}' } });

    const preview = screen.getByTestId('onboarding-preview-box');
    expect(preview.textContent).toContain('全新自訂歡迎文字！登記入線：https://liff.line.me/{LIFF_ID}/gateway');

    // 儲存按鈕啟用
    const saveBtn = screen.getByTestId('onboarding-save-btn');
    expect(saveBtn).not.toBeDisabled();
  });

  it('支援還原官方預設值，且預設值不含已過時的 AI 客服文字', async () => {
    const mockClient: LineOnboardingClient = {
      get: vi.fn().mockResolvedValue(MOCK_DATA),
      preview: vi.fn(),
      update: vi.fn(),
    };

    render(<LineOnboardingEditor client={mockClient} />);
    await waitFor(() => expect(screen.getByTestId('onboarding-textarea')).toBeInTheDocument());

    const resetBtn = screen.getByRole('button', { name: /還原官方預設/ });
    fireEvent.click(resetBtn);

    const textarea = screen.getByTestId('onboarding-textarea') as HTMLTextAreaElement;
    expect(textarea.value).toBe(OFFICIAL_DEFAULT_ONBOARDING_MESSAGE);
    expect(textarea.value).not.toContain('AI 小幫手 24 小時為您即時解答');
    expect(textarea.value).toContain('服務說明與專人諮詢');
    expect(textarea.value).toContain('轉真人客服');
  });

  it('成功送出儲存並呈現成功通知', async () => {
    const mockUpdate = vi.fn().mockResolvedValue({
      ...MOCK_DATA,
      content: '修改後的新訊息：{url}',
      revision: 4,
    });
    const mockClient: LineOnboardingClient = {
      get: vi.fn().mockResolvedValue(MOCK_DATA),
      preview: vi.fn(),
      update: mockUpdate,
    };
    const onSaved = vi.fn();

    render(<LineOnboardingEditor client={mockClient} onSaved={onSaved} />);
    await waitFor(() => expect(screen.getByTestId('onboarding-textarea')).toBeInTheDocument());

    const textarea = screen.getByTestId('onboarding-textarea');
    fireEvent.change(textarea, { target: { value: '修改後的新訊息：{url}' } });

    const saveBtn = screen.getByTestId('onboarding-save-btn');
    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent('Onboarding 歡迎訊息已成功儲存！');
    });

    expect(mockUpdate).toHaveBeenCalledWith({
      content: '修改後的新訊息：{url}',
      expected_revision: 3,
    });
    expect(onSaved).toHaveBeenCalled();
    expect(screen.getByText('版本 Rev.4')).toBeInTheDocument();
  });

  it('儲存失敗時顯示錯誤回饋', async () => {
    const mockClient: LineOnboardingClient = {
      get: vi.fn().mockResolvedValue(MOCK_DATA),
      preview: vi.fn(),
      update: vi.fn().mockRejectedValue(new Error('版本衝突，請重新載入')),
    };

    render(<LineOnboardingEditor client={mockClient} />);
    await waitFor(() => expect(screen.getByTestId('onboarding-textarea')).toBeInTheDocument());

    const textarea = screen.getByTestId('onboarding-textarea');
    fireEvent.change(textarea, { target: { value: '修改訊息' } });

    const saveBtn = screen.getByTestId('onboarding-save-btn');
    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent('版本衝突，請重新載入');
    });
  });
});
