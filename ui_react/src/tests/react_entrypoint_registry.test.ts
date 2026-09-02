/**
 * File: react_entrypoint_registry.test.ts
 * Description: 驗證 canonical React 導航、資料中心相容 deep link、LINE 原始功能保留與 typed mutation 邊界。
 */
import React from 'react';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { HASH_ALIASES } from '../App';
import { NAV_ITEMS } from '../components/MasterLayout';
import { AiEventStudio } from '../pages/line_management/AiEventStudio';
import {
  AlertGroupSecurity,
  type RuntimeTargetClient,
} from '../pages/line_management/AlertGroupSecurity';
import { LiffCardStudio } from '../pages/line_management/LiffCardStudio';

const EXPECTED_HASHES = [
  'order-tracker', 'orders', 'scheduling', 'staff', 'data-import', 'reports',
  'line-management', 'line-ai-events', 'line-llm-settings', 'line-liff-studio', 'line-security',
  'finance', 'anomalies', 'account-management', 'system-status',
] as const;

describe('React entrypoint registry', () => {
  it('canonical 側欄只保留資料中心，且沒有重複 identity', () => {
    const pages = NAV_ITEMS.map((item) => item.id);
    expect(new Set(pages).size).toBe(pages.length);
    expect(new Set(pages)).toEqual(new Set(EXPECTED_HASHES));
  });

  it('舊 Data Browser hash 保留為資料中心第三分頁的相容入口', () => {
    expect(HASH_ALIASES).toMatchObject({ databrowser: 'data-browser' });
    expect(NAV_ITEMS.some((item) => item.id === 'data-browser')).toBe(false);
    expect(NAV_ITEMS.find((item) => item.id === 'data-import')?.label).toBe('資料中心');
  });

  it('新版 LINE 工作頁 hash 各自導向 canonical page', () => {
    expect(HASH_ALIASES).toMatchObject({
      'line-ai': 'line-ai-events',
      'line-ai-events': 'line-ai-events',
      'line-studio': 'line-liff-studio',
      'line-liff-studio': 'line-liff-studio',
      'line-security': 'line-security',
    });
  });

  it('AI 工作頁保留編輯與新增功能，但不假造發布或 provider 發送', () => {
    render(React.createElement(AiEventStudio));
    expect(screen.getByRole('button', { name: '＋ 新增事件' })).toBeEnabled();
    expect(screen.getByRole('searchbox', { name: '搜尋事件名稱或標籤' })).toBeEnabled();
    expect(screen.getByRole('combobox', { name: '事件分類篩選' })).toBeEnabled();
    expect(screen.getByRole('button', { name: '預覽規則變更' })).toBeEnabled();
    expect(screen.getByRole('button', { name: '🗑️ 刪除本機草稿' })).toBeEnabled();
    expect(screen.getByRole('button', { name: '💾 儲存並發布' })).toBeDisabled();
    expect(screen.getByRole('button', { name: /預覽本機規則比對/ })).toBeEnabled();
    expect(screen.getByRole('button', { name: '👍 有幫助' })).toBeEnabled();
    expect(screen.getAllByText('回饋統計尚未接通')).toHaveLength(4);
    expect(screen.getByText('回覆滿意度調查：本則回覆是否有解答問題？')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '＋ 新增事件' }));
    expect(screen.getByDisplayValue('一般諮詢')).toBeInTheDocument();
    expect(screen.getByText('目前顯示 5／5 筆本機草稿；正式規則數量尚未接通。')).toBeInTheDocument();

    fireEvent.change(screen.getByRole('searchbox', { name: '搜尋事件名稱或標籤' }), {
      target: { value: '客訴' },
    });
    expect(screen.getByText('目前顯示 1／5 筆本機草稿；正式規則數量尚未接通。')).toBeInTheDocument();
    fireEvent.change(screen.getByRole('searchbox', { name: '搜尋事件名稱或標籤' }), {
      target: { value: '' },
    });

    fireEvent.click(screen.getByRole('checkbox', { name: /通報真人專員介入/ }));
    expect(screen.getByRole('combobox', { name: '人工工單優先級' })).toHaveValue('NORMAL');
    fireEvent.change(screen.getByRole('combobox', { name: '人工工單優先級' }), {
      target: { value: 'HIGH' },
    });
    expect(screen.getByRole('combobox', { name: '人工工單優先級' })).toHaveValue('HIGH');

    fireEvent.click(screen.getByRole('button', { name: '🗑️ 刪除本機草稿' }));
    expect(screen.getByRole('button', { name: '確認移除本機草稿' })).toBeEnabled();
    fireEvent.click(screen.getByRole('button', { name: '確認移除本機草稿' }));
    expect(screen.getByText(/重新載入頁面即恢復，後端與 LINE 均未變更/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '👍 有幫助' }));
    expect(screen.getByText(/Feedback 必須由已驗證 LINE 身分提交；本工作台未取得 token，未寫入或增加本機統計/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '👎 未解決' }));
    expect(screen.getByText(/Feedback 必須由已驗證 LINE 身分提交；本工作台未取得 token，未寫入或增加本機統計/)).toBeInTheDocument();
    expect(screen.queryByText(/已成功儲存並同步/)).not.toBeInTheDocument();
  });

  it('AI 本機預覽優先轉人工、遵守自動回覆暫停，且不顯示內部入口路徑', () => {
    render(React.createElement(AiEventStudio));
    const input = screen.getByPlaceholderText(/輸入民眾的測試問法/);
    const previewButton = screen.getByRole('button', { name: /預覽本機規則比對/ });

    fireEvent.change(input, { target: { value: '我要人工協助，補助怎麼算' } });
    fireEvent.click(previewButton);
    expect(screen.getByText(/正式流程必須優先轉人工，不會套用自動規則/)).toBeInTheDocument();

    const holdCheckbox = screen.getByRole('checkbox', { name: '模擬自動回覆暫停' });
    fireEvent.click(holdCheckbox);
    fireEvent.change(input, { target: { value: '補助怎麼算' } });
    fireEvent.click(previewButton);
    expect(screen.getByText(/目前模擬為自動回覆暫停/)).toBeInTheDocument();

    fireEvent.click(holdCheckbox);
    fireEvent.click(screen.getByText(/客戶資料與服務異動申請/));
    expect(screen.getByRole('option', { name: '服務登記入口' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: '身分確認入口' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: '客戶資料異動入口（正式流程待補）' })).toBeInTheDocument();
    expect(screen.queryByText(/profile_update\.html|\/line-registration|\/line-identity/)).not.toBeInTheDocument();

    fireEvent.change(input, { target: { value: '我想改地址' } });
    fireEvent.click(previewButton);
    expect(screen.getByText('草稿動作：客戶資料異動入口（正式流程待補）（本頁不開啟）')).toBeInTheDocument();
  });

  it('LIFF 視覺頁保留 8 個 LIFF 與 4 個 Flex，且只產生 canonical 測試連結', async () => {
    const runtimeConfigClient = {
      get: vi.fn(async () => ({
        liff_id: 'test-liff-id',
        public_base_url: 'https://line-test.example.dev',
      })),
    };
    render(React.createElement(LiffCardStudio, { runtimeConfigClient }));
    expect(screen.getByRole('button', { name: 'LIFF 表單 (8)' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Flex 卡片 (4)' })).toBeInTheDocument();
    expect(screen.queryByText(/原始 8 個 LIFF 與 4 個 Flex 功能均保留/)).not.toBeInTheDocument();
    expect(screen.getAllByRole('button')
      .map((button) => button.textContent?.match(/\d+\. [a-z_]+\.html/)?.[0])
      .filter(Boolean)).toEqual([
        '1. gateway.html',
        '2. register.html',
        '3. bind.html',
        '4. profile_update.html',
        '5. staff_order_search.html',
        '6. staff_schedule.html',
        '7. identity.html',
        '8. mobile_admin.html',
      ]);
    expect(screen.queryByText(/15 分鐘.*Token/)).not.toBeInTheDocument();
    expect(screen.queryByText(/demo-token/)).not.toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole('button', { name: /複製正式測試連結/ })).toBeEnabled());
    expect(screen.getByText(/本機預覽已更新/)).toBeInTheDocument();
    expect(screen.getByText('服務登記')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '📝 已登記服務／補助' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '✨ 尚未填寫登記表單' })).toBeDisabled();
    expect(screen.queryByText('開始身分驗證與服務分流')).not.toBeInTheDocument();
    expect(screen.queryByText(/重新渲染 \d+ 次/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '🔄 重新整理預覽' }));
    expect(screen.getByText(/本機預覽已更新/)).toBeInTheDocument();
    expect(screen.getByText(/不呼叫外部 QR 服務或繪製不可掃描的假碼/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '開啟正式 LIFF 入口' })).toHaveAttribute(
      'href',
      'https://line-test.example.dev/line-identity',
    );

    fireEvent.click(screen.getByText('2. register.html'));
    expect(screen.getByText('產婦服務登記表單')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '預覽登記資料' })).toBeDisabled();

    fireEvent.click(screen.getByText('3. bind.html'));
    expect(screen.getByText('服務登記')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '📝 已登記服務／補助' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '✨ 尚未填寫登記表單' })).toBeDisabled();
    expect(screen.queryByText('候選紀錄摘要')).not.toBeInTheDocument();
  });

  it('LIFF 視覺頁使用後端核定的公開測試網址', async () => {
    const runtimeConfigClient = {
      get: vi.fn(async () => ({
        liff_id: 'test-liff-id',
        public_base_url: 'https://line-test.example.dev',
      })),
    };
    render(React.createElement(LiffCardStudio, { runtimeConfigClient }));
    await waitFor(() => expect(screen.getByRole('link', { name: '開啟正式 LIFF 入口' })).toHaveAttribute(
      'href',
      'https://line-test.example.dev/line-identity',
    ));
  });

  it('LIFF runtime config 失敗時顯示原因且不產生替代連結', async () => {
    const runtimeConfigClient = {
      get: vi.fn(async () => { throw new Error('公開網址尚未設定'); }),
    };
    render(React.createElement(LiffCardStudio, { runtimeConfigClient }));

    expect(await screen.findByText(/正式 LIFF 測試網址無法使用：公開網址尚未設定/)).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: '開啟正式 LIFF 入口' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /複製正式測試連結/ })).toBeDisabled();
  });

  it('群組安全頁以 typed client 完成 enable-disable Preview、確認、Apply 與 receipt/readback', async () => {
    const target = {
      target_id: 8,
      target_kind: 'group' as const,
      display_label: 'typed 測試群組',
      state: 'active' as const,
      minimum_status: 'critical' as const,
      current_version: 'version-8',
      updated_at: '2026-08-25T01:02:03+08:00',
    };
    const internalUserTarget = {
      target_id: 18,
      target_kind: 'admin_user' as const,
      display_label: 'typed 內部使用者',
      state: 'active' as const,
      minimum_status: 'warning' as const,
      current_version: 'version-18',
      updated_at: '2026-08-25T01:02:03+08:00',
    };
    const client: RuntimeTargetClient = {
      listTargets: vi.fn(async () => [target, internalUserTarget]),
      previewSetEnabled: vi.fn(async () => ({
        operation: 'disable' as const, target_id: 8, previous_state: 'active' as const,
        resulting_state: 'disabled' as const, current_version: 'version-8',
        preview_fingerprint: 'a'.repeat(64), apply_ready: true as const,
      })),
      setEnabled: vi.fn(async () => ({
        receipt_id: 'receipt-toggle', command_family: 'line_alert_target' as const,
        operation: 'disable' as const, target_id: 8, previous_state: 'active' as const,
        resulting_state: 'disabled' as const, current_version: 'version-9', replayed: false,
        correlation_id: 'line-security:toggle:test', committed_at: '2026-08-25T01:03:03+08:00',
      })),
      previewResetGroup: vi.fn(),
      resetGroup: vi.fn(),
    };
    render(React.createElement(AlertGroupSecurity, { runtimeTargetClient: client }));

    await waitFor(() => expect(client.listTargets).toHaveBeenCalledTimes(1));
    expect(screen.getByText('typed 測試群組')).toBeInTheDocument();
    expect(screen.getByText('typed 內部使用者')).toBeInTheDocument();
    const groupRow = screen.getByText('typed 測試群組').closest('tr');
    expect(groupRow).not.toBeNull();
    fireEvent.click(within(groupRow as HTMLElement).getByRole('button', { name: '停用' }));
    await waitFor(() => expect(client.previewSetEnabled).toHaveBeenCalledTimes(1));
    expect(screen.getByText(/停用 typed 測試群組/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '確認停用' }));
    await waitFor(() => expect(client.setEnabled).toHaveBeenCalledTimes(1));
    expect(screen.getByText(/receipt-toggle/)).toBeInTheDocument();
  });
});
