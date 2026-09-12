/**
 * File: react_entrypoint_registry.test.ts
 * Description: 驗證 canonical React 導航、資料中心相容 deep link、LINE 原始功能保留與 typed mutation 邊界。
 */
import React from 'react';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { HASH_ALIASES } from '../App';
import { NAV_ITEMS } from '../components/MasterLayout';
import { AiCustomerServiceStudioPage } from '../pages/line_management/AiCustomerServiceStudioPage';
import {
  AlertGroupSecurity,
  type RuntimeTargetClient,
} from '../pages/line_management/AlertGroupSecurity';
import { LineRuntimeTargetError } from '../api/line_runtime_targets/line_runtime_target_errors';
import { LiffCardStudio } from '../pages/line_management/LiffCardStudio';

const EXPECTED_HASHES = [
  'order-workbench-v2', 'scheduling', 'staff', 'clients', 'data-import', 'reports',
  'line-management', 'line-ai-events', 'line-llm-settings', 'line-liff-studio', 'line-security',
  'finance', 'historical-service-accounting', 'anomalies', 'account-management', 'storage-management',
] as const;

describe('React entrypoint registry', () => {
  it('canonical 側欄只保留資料中心，且沒有重複 identity', () => {
    const pages = NAV_ITEMS.map((item) => item.id);
    expect(new Set(pages).size).toBe(pages.length);
    expect(new Set(pages)).toEqual(new Set(EXPECTED_HASHES));
  });

  it('客戶名冊只保留單一側欄入口，舊清單與 Data Browser hash 皆導向整合頁', () => {
    expect(HASH_ALIASES).toMatchObject({ databrowser: 'clients', 'data-browser': 'clients', 'client-roster': 'clients' });
    expect(NAV_ITEMS.map((item) => String(item.id))).not.toContain('client-roster');
    expect(NAV_ITEMS.find((item) => item.id === 'clients')?.label).toBe('客戶名冊');
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

  it('AI 工作頁以分頁顯示正式 catalog、server-owned router preview 與真實模型測試', () => {
    render(React.createElement(AiCustomerServiceStudioPage));
    expect(screen.getByRole('button', { name: '回饋分析' })).toBeEnabled();
    fireEvent.click(screen.getByRole('button', { name: '事件規則' }));
    expect(screen.getByRole('searchbox', { name: '搜尋正式事件規則' })).toBeEnabled();
    expect(screen.getByRole('button', { name: '讀取 server router preview' })).toBeEnabled();
    expect(screen.getByText('舊版 4 筆 INITIAL_RULES 本機示範資料已移除。本頁只接受正式 QA 題庫與 server-owned navigation/event catalog 作為可見來源。')).toBeInTheDocument();
    expect(screen.getByLabelText('Server router 測試文字')).toHaveValue('我想修改登記資料');

    fireEvent.click(screen.getByRole('button', { name: 'AI 測試' }));
    expect(screen.getByRole('button', { name: '執行真實 AI 智能解答' })).toBeDisabled();
    expect(screen.getByLabelText('Gemini 真實語意測試文字')).toHaveValue('');
  });



  it('LIFF 視覺頁保留 17 個正式 LIFF 與 4 個 Flex，且只產生 canonical 測試連結', async () => {
    const runtimeConfigClient = {
      get: vi.fn(async () => ({
        liff_id: 'test-liff-id',
        public_base_url: 'https://line-test.example.dev',
      })),
    };
    render(React.createElement(LiffCardStudio, { runtimeConfigClient }));
    expect(screen.getByRole('button', { name: 'LIFF 表單 (17)' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Flex 卡片 (4)' })).toBeInTheDocument();
    expect(screen.queryByText(/原始 8 個 LIFF 與 4 個 Flex 功能均保留/)).not.toBeInTheDocument();
    expect(screen.getAllByRole('button')
      .map((button) => button.textContent?.match(/[a-z_]+\.html/)?.[0])
      .filter(Boolean)).toEqual([
        'gateway.html',
        'register.html',
        'bind.html',
        'profile_guard.html',
        'profile_update.html',
        'order_update.html',
        'candidate_contact_customer.html',
        'staff_order_search.html',
        'staff_schedule.html',
        'staff_baby_log.html',
        'staff_payout.html',
        'candidate_contact.html',
        'identity.html',
        'mobile_admin.html',
        'mobile_admin.html',
        'mobile_admin.html',
        'mobile_admin.html',
      ]);
    expect(screen.queryByText(/15 分鐘.*Token/)).not.toBeInTheDocument();
    expect(screen.queryByText(/demo-token/)).not.toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole('link', { name: '在預覽中開啟正式 LIFF 入口' })).toBeInTheDocument());
    expect(screen.getByText('服務確認與導流')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '已申請市府平台' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '未申請市府平台' })).toBeDisabled();
    expect(screen.queryByText('開始身分驗證與服務分流')).not.toBeInTheDocument();
    expect(screen.queryByText(/重新渲染 \d+ 次/)).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: '實機驗收入口' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /複製正式測試連結|重新整理預覽/ })).not.toBeInTheDocument();
    expect(screen.getAllByRole('link', { name: /正式 LIFF 入口/ })).toHaveLength(1);
    expect(screen.getByRole('link', { name: '在預覽中開啟正式 LIFF 入口' })).toHaveAttribute(
      'href',
      'https://line-test.example.dev/line-gateway',
    );

    fireEvent.click(screen.getByText('register.html'));
    expect(screen.getByText('需求調查表單')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '預覽登記資料' })).toBeDisabled();
    expect(screen.getByRole('link', { name: '在預覽中開啟正式 LIFF 入口' })).toHaveAttribute(
      'href',
      'https://line-test.example.dev/line-registration',
    );

    fireEvent.click(screen.getByText('bind.html'));
    expect(screen.getByText('服務綁定與訂單查詢')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '確認綁定' })).toBeDisabled();
    expect(screen.queryByText('服務確認與導流')).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: '在預覽中開啟正式 LIFF 入口' })).toHaveAttribute(
      'href',
      'https://line-test.example.dev/line-bind',
    );

    fireEvent.click(screen.getByText('profile_guard.html'));
    expect(screen.getByText('尚未完成工會服務綁定')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '在預覽中開啟正式 LIFF 入口' })).toHaveAttribute(
      'href',
      'https://line-test.example.dev/line-profile-guard',
    );

    fireEvent.click(screen.getByText('profile_update.html'));
    expect(screen.getByText('修改登記資料申請')).toBeInTheDocument();
    expect(screen.getByText(/正式異動流程已接通後端 API/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '在預覽中開啟正式 LIFF 入口' })).toHaveAttribute(
      'href',
      'https://line-test.example.dev/line-profile-guard',
    );

    fireEvent.click(screen.getByText('order_update.html'));
    expect(screen.getByText('修改訂單資訊申請')).toBeInTheDocument();
    expect(screen.getByText(/正式訂單維持不變並等待工會確認/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '在預覽中開啟安全展示頁' })).toHaveAttribute(
      'href',
      'https://line-test.example.dev/line-order-update?studio_preview=1',
    );

    fireEvent.click(screen.getByText('candidate_contact_customer.html'));
    expect(screen.getByText('媒合條件協調')).toBeInTheDocument();
    expect(screen.getByText(/必須由客戶收到的案件協調卡帶入專屬識別碼/)).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /正式 LIFF 入口|安全展示頁/ })).not.toBeInTheDocument();

    fireEvent.click(screen.getByText('candidate_contact.html'));
    expect(screen.getByText('候選月嫂案件回覆')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '在預覽中開啟安全展示頁' })).toHaveAttribute(
      'href',
      'https://line-test.example.dev/line-candidate-contact?studio_preview=1',
    );

    fireEvent.click(screen.getByText('mobile_admin.html · 待辦工作台'));
    expect(screen.getByText(/目前只列出待處理的月嫂身分審核/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '在預覽中開啟安全展示頁' })).toHaveAttribute(
      'href',
      'https://line-test.example.dev/line-mobile-admin?target=staff_review&studio_preview=1',
    );

    fireEvent.click(screen.getByText('mobile_admin.html · 客服中心'));
    expect(screen.getByText(/集中查看待處理客服案件/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '在預覽中開啟安全展示頁' })).toHaveAttribute(
      'href',
      'https://line-test.example.dev/line-mobile-admin?target=customer_service&studio_preview=1',
    );

    fireEvent.click(screen.getByText('mobile_admin.html · 狀態追蹤'));
    expect(screen.getByText(/查詢未完成訂單的目前階段/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '在預覽中開啟安全展示頁' })).toHaveAttribute(
      'href',
      'https://line-test.example.dev/line-mobile-admin?target=order_tracking&studio_preview=1',
    );

    fireEvent.click(screen.getByText('mobile_admin.html · 營運摘要'));
    expect(screen.getByText(/依台北時區顯示本週營運統計/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '在預覽中開啟安全展示頁' })).toHaveAttribute(
      'href',
      'https://line-test.example.dev/line-mobile-admin?target=dashboard&studio_preview=1',
    );
  });

  it('LIFF 目錄依正式四種 audience 分類，工會人員不會看到訪客 gateway', async () => {
    const runtimeConfigClient = {
      get: vi.fn(async () => ({
        liff_id: 'test-liff-id',
        public_base_url: 'https://line-test.example.dev',
      })),
    };
    render(React.createElement(LiffCardStudio, { runtimeConfigClient }));
    fireEvent.click(screen.getByRole('button', { name: 'LIFF 表單 (17)' }));
    const roleFilter = screen.getByRole('combobox', { name: '依適用角色篩選資產' });
    const visibleLiffNames = () => screen.getAllByRole('button')
      .map((button) => button.textContent?.match(/[a-z_]+\.html/)?.[0])
      .filter(Boolean);

    fireEvent.change(roleFilter, { target: { value: 'union_staff' } });
    await waitFor(() => expect(visibleLiffNames()).toEqual([
      'identity.html',
      'mobile_admin.html',
      'mobile_admin.html',
      'mobile_admin.html',
      'mobile_admin.html',
    ]));
    expect(screen.queryByText('gateway.html')).not.toBeInTheDocument();

    fireEvent.change(roleFilter, { target: { value: 'visitor' } });
    await waitFor(() => expect(visibleLiffNames()).toEqual([
      'gateway.html', 'register.html', 'bind.html', 'identity.html',
    ]));

    fireEvent.change(roleFilter, { target: { value: 'customer' } });
    await waitFor(() => expect(visibleLiffNames()).toEqual([
      'profile_guard.html', 'profile_update.html', 'order_update.html', 'candidate_contact_customer.html', 'identity.html',
    ]));

    fireEvent.change(roleFilter, { target: { value: 'staff' } });
    await waitFor(() => expect(visibleLiffNames()).toEqual([
      'staff_order_search.html', 'staff_schedule.html', 'staff_baby_log.html', 'staff_payout.html', 'candidate_contact.html', 'identity.html',
    ]));
  });

  it('LIFF 視覺頁使用後端核定的公開測試網址', async () => {
    const runtimeConfigClient = {
      get: vi.fn(async () => ({
        liff_id: 'test-liff-id',
        public_base_url: 'https://line-test.example.dev',
      })),
    };
    render(React.createElement(LiffCardStudio, { runtimeConfigClient }));
    await waitFor(() => expect(screen.getByRole('link', { name: '在預覽中開啟正式 LIFF 入口' })).toHaveAttribute(
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
    expect(screen.queryByRole('link', { name: '在預覽中開啟正式 LIFF 入口' })).not.toBeInTheDocument();
    expect(screen.queryByTitle(/正式 LIFF 測試入口 QR Code/)).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: '實機驗收入口' })).not.toBeInTheDocument();
  });

  it('群組安全頁以 typed client 完成解除 Preview、確認、Apply、停用 readback 與 request identity 承接', async () => {
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
    let groupDisabled = false;
    const client: RuntimeTargetClient = {
      listTargets: vi.fn(async () => [{ ...target, state: groupDisabled ? 'disabled' as const : 'active' as const }, internalUserTarget]),
      previewSetEnabled: vi.fn(),
      setEnabled: vi.fn(),
      previewResetGroup: vi.fn(async () => ({
        operation: 'group_reset' as const, target_id: 8, previous_state: 'active' as const,
        resulting_state: 'disabled' as const, current_version: 'version-8',
        preview_fingerprint: 'a'.repeat(64), apply_ready: true as const,
      })),
      resetGroup: vi.fn(async (request) => {
        groupDisabled = true;
        return {
        receipt_id: 'receipt-toggle', command_family: 'line_alert_target' as const,
        operation: 'group_reset' as const, target_id: 8, previous_state: 'active' as const,
        resulting_state: 'disabled' as const, current_version: 'version-9', replayed: false,
        correlation_id: request.correlation_id, committed_at: '2026-08-25T01:03:03+08:00',
        };
      }),
    };
    render(React.createElement(AlertGroupSecurity, { runtimeTargetClient: client }));

    await waitFor(() => expect(client.listTargets).toHaveBeenCalledTimes(1));
    expect(screen.getAllByText('typed 測試群組').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('typed 內部使用者')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '預覽解除群組' }));
    await waitFor(() => expect(client.previewResetGroup).toHaveBeenCalledTimes(1));
    expect(screen.getByText('異動影響確認')).toBeInTheDocument();
    const previewCard = screen.getByText('異動影響確認').closest('.alert-security-preview-card');
    expect(previewCard).not.toBeNull();
    expect(within(previewCard as HTMLElement).getByText('解除目前群組')).toBeInTheDocument();
    expect(within(previewCard as HTMLElement).getByText('啟用')).toBeInTheDocument();
    expect(within(previewCard as HTMLElement).getByText('停用')).toBeInTheDocument();
    const confirmation = screen.getByRole('checkbox', { name: /目前群組將從有效通知群組解除/ });
    expect(screen.getByRole('button', { name: '確認解除群組' })).toBeDisabled();
    fireEvent.click(confirmation);
    fireEvent.click(screen.getByRole('button', { name: '確認解除群組' }));
    await waitFor(() => expect(client.resetGroup).toHaveBeenCalledTimes(1));
    const previewRequest = vi.mocked(client.previewResetGroup).mock.calls[0][0];
    expect(client.resetGroup).toHaveBeenCalledWith({
      ...previewRequest,
      preview_fingerprint: 'a'.repeat(64),
    });
    expect(screen.getByText(/通知群組已解除/)).toBeInTheDocument();
    expect(screen.getByText('已重新查詢並確認最新狀態。')).toBeInTheDocument();
    await waitFor(() => expect(screen.getAllByText('停用').length).toBeGreaterThan(0));
    expect(client.previewSetEnabled).not.toHaveBeenCalled();
    expect(client.setEnabled).not.toHaveBeenCalled();
  });

  it('群組解除 Preview 衝突會在畫面顯示 typed error，而非按鈕無反應', async () => {
    const target = {
      target_id: 8,
      target_kind: 'group' as const,
      display_label: '衝突測試群組',
      state: 'active' as const,
      minimum_status: 'critical' as const,
      current_version: 'version-8',
      updated_at: '2026-08-25T01:02:03+08:00',
    };
    const client: RuntimeTargetClient = {
      listTargets: vi.fn(async () => [target]),
      previewSetEnabled: vi.fn(),
      setEnabled: vi.fn(),
      previewResetGroup: vi.fn(async () => {
        throw new LineRuntimeTargetError(
          'LINE_RUNTIME_TARGET_CONFLICT',
          'LINE 告警對象 Preview 已過期，請重新查詢並預覽',
          { publicCode: 'line_alert_target_preview_conflict' },
        );
      }),
      resetGroup: vi.fn(),
    };
    render(React.createElement(AlertGroupSecurity, { runtimeTargetClient: client }));

    await waitFor(() => expect(client.listTargets).toHaveBeenCalledTimes(1));
    expect(screen.getAllByText('衝突測試群組')).not.toHaveLength(0);
    fireEvent.click(screen.getByRole('button', { name: '預覽解除群組' }));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'line_alert_target_preview_conflict：LINE 告警對象 Preview 已過期，請重新查詢並預覽',
    );
    expect(screen.queryByText('異動影響確認')).not.toBeInTheDocument();
  });
});
