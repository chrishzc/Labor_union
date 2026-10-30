/**
 * File: line_flex_design_preview.test.tsx
 * Description: 驗證 LINE 表單入口、篩選及唯讀預覽，訊息卡片統一由通知與發送維護。
 */
import React from 'react';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { LINE_FLEX_DESIGN_SOURCES } from '../adapters/line_flex_design/line_flex_design_adapter';
import type {
  LineIdentityRuntimeConfig,
  LineIdentityRuntimeConfigClient,
} from '../api/line_identity/line_identity_runtime_config_client';
import { LineFlexDesignPreview } from '../components/LineFlexDesignPreview';
import { lineMessagePreviewClient } from '../api/line_notification_rules/line_message_preview_client';
import { LiffCardStudio } from '../pages/line_management/LiffCardStudio';

describe('LINE studio public preview', () => {
  beforeEach(() => {
    window.history.replaceState(null, '', '/#line-liff-studio');
    vi.spyOn(lineMessagePreviewClient, 'catalog').mockResolvedValue([]);
  });

  it('僅保留表單與正式預覽，不再查詢訊息卡片公版', async () => {
    const runtimeConfigClient: LineIdentityRuntimeConfigClient = { get: vi.fn().mockResolvedValue({ liff_id: 'test' }) };
    render(<LiffCardStudio runtimeConfigClient={runtimeConfigClient} />);
    expect(screen.getByRole('heading', { name: 'LINE 表單' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /訊息卡片/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /接案意願詢問|服務日期表|重大異常通知/ })).not.toBeInTheDocument();
    expect(screen.getByText('18 個項目')).toBeInTheDocument();
    await screen.findByRole('link', { name: '在預覽中開啟正式 LIFF 入口' });
    expect(lineMessagePreviewClient.catalog).not.toHaveBeenCalled();
  });

  it('舊卡片深連結回到表單，表單圖例保留原本的操作限制', () => {
    window.history.replaceState(null, '', '/#line-liff-studio?type=flex_card&asset=flex_dispatch');
    const runtimeConfigClient: LineIdentityRuntimeConfigClient = { get: vi.fn(() => new Promise<LineIdentityRuntimeConfig>(() => undefined)) };
    render(<LiffCardStudio runtimeConfigClient={runtimeConfigClient} />);
    expect(screen.getByRole('button', { name: /服務申請入口 確認/ })).toHaveAttribute('aria-pressed', 'true');
    expect(window.location.hash).toBe('#line-liff-studio');
    fireEvent.click(screen.getByRole('button', { name: /申請訂單異動 提出/ }));
    expect(screen.queryByText('服務日期／天數')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /寶寶日誌與餐食照片 依服務日/ }));
    expect(screen.getByRole('button', { name: '送出日誌' })).toBeDisabled();
    expect(screen.queryByText('預覽寶寶日誌')).not.toBeInTheDocument();
  });

  it('拒絕額外 provider 欄位且不把來源內容穿透畫面', () => {
    const forbiddenValue = 'demo-token-must-not-render';
    render(React.createElement(LineFlexDesignPreview, {
      source: {
        ...LINE_FLEX_DESIGN_SOURCES.flex_dispatch,
        raw_provider_payload: forbiddenValue,
      },
    }));

    expect(screen.getByRole('alert', { name: 'Flex 設計預覽錯誤' })).toHaveTextContent('已停止顯示');
    expect(screen.queryByText(forbiddenValue)).not.toBeInTheDocument();
    expect(screen.queryByText('案件編號：【寄送前依正式案件資料帶入】')).not.toBeInTheDocument();
  });

  it('保留正式入口、安全展示入口與案件專屬入口限制，移除下方說明', async () => {
    const runtimeConfigClient: LineIdentityRuntimeConfigClient = {
      get: vi.fn().mockResolvedValue({ liff_id: 'test-liff', public_base_url: 'https://line.example.test' }),
    };
    render(<LiffCardStudio runtimeConfigClient={runtimeConfigClient} />);

    expect(await screen.findByRole('link', { name: '在預覽中開啟正式 LIFF 入口' })).toHaveAttribute('href', 'https://line.example.test/line-gateway');
    fireEvent.click(screen.getByRole('button', { name: /修改個人資料 申請變更/ }));
    const officialLink = screen.getByRole('link', { name: '在預覽中開啟正式 LIFF 入口' });
    expect(officialLink).toHaveAttribute('href', 'https://line.example.test/line-profile-guard');
    expect(officialLink).toHaveAttribute('target', '_blank');

    fireEvent.click(screen.getByRole('button', { name: /申請訂單異動 提出/ }));
    expect(screen.getByRole('link', { name: '在預覽中開啟安全展示頁' })).toHaveAttribute('href', 'https://line.example.test/line-order-update?studio_preview=1');

    fireEvent.click(screen.getByRole('button', { name: /媒合條件協調 回覆可調整/ }));
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
    expect(screen.getByText(/必須由客戶收到的案件協調卡/)).toBeInTheDocument();
    expect(screen.queryByText('使用說明')).not.toBeInTheDocument();
    expect(screen.queryByText(/詳細與技術說明|獨立介面預覽|資安與存取摘要|關聯功能與目前狀態/)).not.toBeInTheDocument();
    expect(runtimeConfigClient.get).toHaveBeenCalledTimes(1);
  });

  it('搜尋與對象篩選共用選取結果，零筆結果清空預覽與入口', () => {
    const runtimeConfigClient: LineIdentityRuntimeConfigClient = {
      get: vi.fn(() => new Promise<LineIdentityRuntimeConfig>(() => undefined)),
    };
    render(<LiffCardStudio runtimeConfigClient={runtimeConfigClient} />);
    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'customer' } });
    expect(screen.getByText('6 個項目')).toBeInTheDocument();
    expect(screen.getAllByRole('button', { pressed: true })).toHaveLength(1);

    fireEvent.change(screen.getByRole('textbox', { name: '搜尋表單' }), { target: { value: '找不到的服務' } });
    expect(screen.getByText('0 個項目')).toBeInTheDocument();
    expect(screen.getByText('找不到符合條件的內容')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '放大預覽' })).not.toBeInTheDocument();
    expect(screen.queryByLabelText('正式資料狀態')).not.toBeInTheDocument();
    expect(screen.queryByRole('link')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '清除篩選' }));
    expect(screen.getByText('18 個項目')).toBeInTheDocument();
    fireEvent.change(screen.getByRole('textbox', { name: '搜尋表單' }), { target: { value: 'register.html' } });
    expect(screen.getByText('1 個項目')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /需求調查 填寫基本資料/ })).toHaveAttribute('aria-pressed', 'true');
  });

  it('放大檢視仍為唯讀設計預覽，關閉後恢復捲動', () => {
    const runtimeConfigClient: LineIdentityRuntimeConfigClient = {
      get: vi.fn(() => new Promise<LineIdentityRuntimeConfig>(() => undefined)),
    };
    render(<LiffCardStudio runtimeConfigClient={runtimeConfigClient} />);
    fireEvent.click(screen.getByRole('button', { name: '放大預覽' }));
    const dialog = screen.getByRole('dialog', { name: '服務申請入口' });
    expect(document.body.style.overflow).toBe('hidden');
    expect(within(dialog).getByRole('button', { name: '已申請市府平台' })).toBeDisabled();
    fireEvent.click(within(dialog).getByRole('button', { name: '關閉放大預覽' }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(document.body.style.overflow).toBe('');
  });

  it('身分認證顯示自身登入預覽，入口讀取失敗不顯示原始錯誤', async () => {
    const runtimeConfigClient: LineIdentityRuntimeConfigClient = {
      get: vi.fn().mockRejectedValue(new Error('technical-internal-detail')),
    };
    render(<LiffCardStudio runtimeConfigClient={runtimeConfigClient} />);
    expect(await screen.findByText('目前無法取得服務入口，請稍後再試。')).toBeInTheDocument();
    expect(screen.queryByText(/technical-internal-detail/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /身分認證 登入 LINE/ }));
    expect(screen.getByRole('button', { name: 'LINE 快速登入驗證' })).toBeDisabled();
    expect(screen.queryByRole('button', { name: '已申請市府平台' })).not.toBeInTheDocument();
  });
});
