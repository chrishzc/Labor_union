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
  'finance', 'historical-service-accounting', 'anomalies', 'account-management', 'system-status',
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

  it('AI 工作頁只顯示正式 catalog 與 server-owned router preview', () => {
    render(React.createElement(AiEventStudio));
    expect(screen.getByRole('searchbox', { name: '搜尋正式事件規則' })).toBeEnabled();
    expect(screen.getByRole('button', { name: '讀取 server router preview' })).toBeEnabled();
    expect(screen.getByRole('button', { name: '🧠 執行真實 Gemini 測試' })).toBeEnabled();
    expect(screen.getByText('舊版 4 筆 INITIAL_RULES 本機示範資料已移除。本頁只接受正式 QA 題庫與 server-owned navigation/event catalog 作為可見來源。')).toBeInTheDocument();
    expect(screen.getByLabelText('Server router 測試文字')).toHaveValue('我想修改登記資料');
    expect(screen.getByLabelText('Server router confidence')).toHaveValue(90);
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
    expect(screen.getByText('服務確認與導流')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '📝 已申請市府平台' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '🏛️ 未申請市府平台' })).toBeDisabled();
    expect(screen.queryByText('開始身分驗證與服務分流')).not.toBeInTheDocument();
    expect(screen.queryByText(/重新渲染 \d+ 次/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '🔄 重新整理預覽' }));
    expect(screen.getByText(/本機預覽已更新/)).toBeInTheDocument();
    expect(screen.getByText(/不呼叫外部 QR 服務或繪製不可掃描的假碼/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '開啟正式 LIFF 入口' })).toHaveAttribute(
      'href',
      'https://line-test.example.dev/line-gateway',
    );

    fireEvent.click(screen.getByText('2. register.html'));
    expect(screen.getByText('需求調查表單')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '預覽登記資料' })).toBeDisabled();
    expect(screen.getByRole('link', { name: '開啟正式 LIFF 入口' })).toHaveAttribute(
      'href',
      'https://line-test.example.dev/line-registration',
    );

    fireEvent.click(screen.getByText('3. bind.html'));
    expect(screen.getByText('服務綁定與訂單查詢')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '確認綁定' })).toBeDisabled();
    expect(screen.queryByText('服務確認與導流')).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: '開啟正式 LIFF 入口' })).toHaveAttribute(
      'href',
      'https://line-test.example.dev/line-bind',
    );

    fireEvent.click(screen.getByText('4. profile_update.html'));
    expect(screen.getByText('修改登記資料申請')).toBeInTheDocument();
    expect(screen.getByText(/正式異動流程已接通後端 API/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '開啟正式 LIFF 入口' })).toHaveAttribute(
      'href',
      'https://line-test.example.dev/line-profile-update',
    );
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
      'https://line-test.example.dev/line-gateway',
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
    expect(screen.getAllByText('typed 測試群組').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('typed 內部使用者')).toBeInTheDocument();
    const groupCard = screen.getAllByText('typed 測試群組')[1]?.closest('article') ?? screen.getAllByText('typed 測試群組')[0].closest('div');
    expect(groupCard).not.toBeNull();
    fireEvent.click(within(groupCard as HTMLElement).getByRole('button', { name: /停用/ }));
    await waitFor(() => expect(client.previewSetEnabled).toHaveBeenCalledTimes(1));
    expect(screen.getByText('🔎 異動影響確認')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.click(screen.getByRole('button', { name: '確認套用' }));
    await waitFor(() => expect(client.setEnabled).toHaveBeenCalledTimes(1));
    expect(screen.getByText(/通知對象已更新/)).toBeInTheDocument();
    expect(screen.getByText('已重新查詢並確認最新狀態。')).toBeInTheDocument();
  });
});
