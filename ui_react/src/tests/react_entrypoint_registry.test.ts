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
import { LiffCardStudio } from '../pages/line_management/LiffCardStudio';

const EXPECTED_HASHES = [
  'order-workbench-v2', 'scheduling', 'staff', 'clients', 'data-import', 'reports',
  'line-management', 'line-ai-events', 'line-llm-settings', 'line-liff-studio', 'line-security',
  'finance', 'accounting-parameters', 'historical-service-accounting', 'account-management', 'contract-templates',
] as const;

// Explicit test oracle: presentation names map to the same 18 canonical LIFF assets.
const LIFF_ASSETS = [
  ['gateway.html', '服務申請入口'], ['register.html', '需求調查'],
  ['非市民服務申請', '非市民服務申請'],
  ['bind.html', '連結客戶資料'], ['profile_guard.html', '修改資料前的身分確認'],
  ['profile_update.html', '修改個人資料'], ['order_update.html', '申請訂單異動'],
  ['candidate_contact_customer.html', '媒合條件協調'], ['staff_order_search.html', '我的案件'],
  ['staff_schedule.html', '班表與請假'], ['staff_baby_log.html', '寶寶日誌與餐食照片'],
  ['staff_payout.html', '薪資與付款紀錄'], ['candidate_contact.html', '接案回覆'],
  ['identity.html', '身分認證'], ['mobile_admin.html · 待辦工作台', '待辦工作台'],
  ['mobile_admin.html · 客服中心', '客服中心'], ['mobile_admin.html · 狀態追蹤', '訂單進度'],
  ['mobile_admin.html · 營運摘要', '營運摘要'],
] as const;
function liffAsset(file: string) {
  const title = LIFF_ASSETS.find(([key]) => key === file)?.[1];
  const buttons = Array.from(document.querySelectorAll<HTMLButtonElement>('button.liff-asset-card'))
    .filter(button => button.querySelector('strong')?.textContent === title);
  expect(buttons).toHaveLength(1);
  return buttons[0];
}
function visibleLiffNames() {
  return Array.from(document.querySelectorAll<HTMLButtonElement>('button.liff-asset-card')).map(button => {
    const match = LIFF_ASSETS.find(([, title]) => title === button.querySelector('strong')?.textContent);
    expect(match).toBeDefined();
    return match![0].split(' · ')[0];
  }).sort();
}

describe('React entrypoint registry', () => {
  it('canonical 側欄只保留資料中心，且沒有重複 identity', () => {
    const pages = NAV_ITEMS.map((item) => item.id);
    expect(new Set(pages).size).toBe(pages.length);
    expect(new Set(pages)).toEqual(new Set(EXPECTED_HASHES));
    // 06_Anomalies_Domain §8: the 2026-10-16 decision retires this presentation entry.
    expect(pages).not.toContain('anomalies');
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

  it('AI 工作頁以分頁顯示正式 catalog、server-owned router preview 與真實模型測試', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = String(input);
      const data = url === '/api/v1/line/ai-events/catalog'
        ? { revision: 7, entries: [{ alias: '測試正式引導問句', route_key: 'profile_guard', tier: 'customer', public_route: '/line-profile-guard', source_identity: 'test-catalog:7', revision: 7 }] }
        : url === '/api/v1/line/identity/runtime-config' ? { liff_id: 'test-liff-id' } : { items: [], next_cursor: null };
      return new Response(JSON.stringify({ data }), { status: 200, headers: { 'Content-Type': 'application/json' } });
    });
    render(React.createElement(AiCustomerServiceStudioPage));
    expect(screen.getByRole('button', { name: '回饋分析' })).toBeEnabled();
    fireEvent.click(screen.getByRole('button', { name: '引導動作' }));
    expect(screen.getByRole('searchbox', { name: '搜尋引導動作' })).toBeEnabled();
    expect(screen.getByRole('button', { name: '預覽引導動作' })).toBeEnabled();
    expect(await screen.findByRole('button', { name: '測試正式引導問句' })).toBeInTheDocument();
    expect(fetchSpy).toHaveBeenCalledWith('/api/v1/line/ai-events/catalog', expect.objectContaining({ credentials: 'include' }));
    expect(screen.queryByText(/INITIAL_RULES|本機示範資料/)).not.toBeInTheDocument();
    expect(screen.getByLabelText('客服測試問句')).toHaveValue('我想修改登記資料');

    fireEvent.click(screen.getByRole('button', { name: '回答測試' }));
    expect(screen.getByRole('button', { name: '測試回答' })).toBeDisabled();
    expect(screen.getByLabelText('測試問題')).toHaveValue('');
    fetchSpy.mockRestore();
  });



  it('LIFF 視覺頁保留 18 個正式表單，且只產生 canonical 測試連結', async () => {
    const runtimeConfigClient = {
      get: vi.fn(async () => ({
        liff_id: 'test-liff-id',
        public_base_url: 'https://line-test.example.dev',
      })),
    };
    render(React.createElement(LiffCardStudio, { runtimeConfigClient }));
    expect(screen.getByRole('heading', { name: 'LINE 表單' })).toBeInTheDocument();
    expect(NAV_ITEMS.find(item => item.id === 'line-liff-studio')?.label).toBe('表單');
    expect(screen.queryByRole('button', { name: /訊息卡片/ })).not.toBeInTheDocument();
    expect(screen.queryByText(/原始 8 個 LIFF 與 4 個 Flex 功能均保留/)).not.toBeInTheDocument();
    expect(visibleLiffNames()).toEqual([
        'gateway.html',
        'register.html',
        '非市民服務申請',
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
      ].sort());
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

    fireEvent.click(liffAsset('register.html'));
    expect(screen.getByText('需求調查表單')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '送出完整服務登記表單' })).toBeDisabled();
    expect(screen.getByRole('link', { name: '在預覽中開啟正式 LIFF 入口' })).toHaveAttribute(
      'href',
      'https://line-test.example.dev/line-registration',
    );

    fireEvent.click(liffAsset('bind.html'));
    expect(screen.getByText('服務綁定與訂單查詢')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '確認綁定' })).toBeDisabled();
    expect(screen.queryByText('服務確認與導流')).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: '在預覽中開啟正式 LIFF 入口' })).toHaveAttribute(
      'href',
      'https://line-test.example.dev/line-bind',
    );

    fireEvent.click(liffAsset('profile_guard.html'));
    expect(screen.getByText('尚未完成工會服務綁定')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '在預覽中開啟正式 LIFF 入口' })).toHaveAttribute(
      'href',
      'https://line-test.example.dev/line-profile-guard',
    );

    fireEvent.click(liffAsset('profile_update.html'));
    expect(screen.getByText('修改登記資料申請')).toBeInTheDocument();
    expect(screen.getByText(/正式異動流程示意後端 API；送出後等待工會人員審核/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '在預覽中開啟正式 LIFF 入口' })).toHaveAttribute(
      'href',
      'https://line-test.example.dev/line-profile-guard',
    );

    fireEvent.click(liffAsset('order_update.html'));
    expect(screen.getByText('修改訂單資訊申請')).toBeInTheDocument();
    expect(screen.getByText(/正式訂單維持不變並等待工會確認/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '在預覽中開啟安全展示頁' })).toHaveAttribute(
      'href',
      'https://line-test.example.dev/line-order-update?studio_preview=1',
    );

    fireEvent.click(liffAsset('candidate_contact_customer.html'));
    expect(within(screen.getByRole('region', { name: '所選項目預覽' })).getByRole('heading', { name: '媒合條件協調', level: 3 })).toBeInTheDocument();
    expect(screen.getByText(/必須由客戶收到的案件協調卡帶入專屬識別碼/)).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /正式 LIFF 入口|安全展示頁/ })).not.toBeInTheDocument();

    fireEvent.click(liffAsset('candidate_contact.html'));
    expect(screen.getByText('候選月嫂案件回覆')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '在預覽中開啟安全展示頁' })).toHaveAttribute(
      'href',
      'https://line-test.example.dev/line-candidate-contact?studio_preview=1',
    );

    fireEvent.click(liffAsset('mobile_admin.html · 待辦工作台'));
    expect(screen.getByText(/列出身分審核與案件待辦，可由工會決定是否發送提醒/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '在預覽中開啟安全展示頁' })).toHaveAttribute(
      'href',
      'https://line-test.example.dev/line-mobile-admin?target=staff_review&studio_preview=1',
    );

    fireEvent.click(liffAsset('mobile_admin.html · 客服中心'));
    expect(screen.getByText(/集中查看待處理客服案件/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '在預覽中開啟安全展示頁' })).toHaveAttribute(
      'href',
      'https://line-test.example.dev/line-mobile-admin?target=customer_service&studio_preview=1',
    );

    fireEvent.click(liffAsset('mobile_admin.html · 狀態追蹤'));
    expect(screen.getByText(/查詢未完成訂單的目前階段/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '在預覽中開啟安全展示頁' })).toHaveAttribute(
      'href',
      'https://line-test.example.dev/line-mobile-admin?target=order_tracking&studio_preview=1',
    );

    fireEvent.click(liffAsset('mobile_admin.html · 營運摘要'));
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
    const roleFilter = screen.getByRole('combobox', { name: '依適用角色篩選表單' });

    fireEvent.change(roleFilter, { target: { value: 'union_staff' } });
    await waitFor(() => expect(visibleLiffNames()).toEqual([
      'identity.html',
      'mobile_admin.html',
      'mobile_admin.html',
      'mobile_admin.html',
      'mobile_admin.html',
    ].sort()));
    expect(screen.queryByRole('button', { name: /服務申請入口/ })).not.toBeInTheDocument();

    fireEvent.change(roleFilter, { target: { value: 'visitor' } });
    await waitFor(() => expect(visibleLiffNames()).toEqual([
      'gateway.html', 'register.html', 'bind.html', 'identity.html', '非市民服務申請',
    ].sort()));

    fireEvent.change(roleFilter, { target: { value: 'customer' } });
    await waitFor(() => expect(visibleLiffNames()).toEqual([
      'profile_guard.html', 'profile_update.html', 'order_update.html', 'candidate_contact_customer.html', 'identity.html', '非市民服務申請',
    ].sort()));

    fireEvent.change(roleFilter, { target: { value: 'staff' } });
    await waitFor(() => expect(visibleLiffNames()).toEqual([
      'staff_order_search.html', 'staff_schedule.html', 'staff_baby_log.html', 'staff_payout.html', 'candidate_contact.html', 'identity.html',
    ].sort()));
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

  it('LIFF runtime config 失敗時顯示 closed 指引且不產生替代連結或洩漏內部錯誤', async () => {
    const runtimeConfigClient = {
      get: vi.fn(async () => { throw new Error('synthetic raw runtime detail: SQL config failure'); }),
    };
    render(React.createElement(LiffCardStudio, { runtimeConfigClient }));

    expect(await screen.findByText('目前無法取得服務入口，請稍後再試。')).toBeInTheDocument();
    expect(screen.queryByText(/synthetic raw runtime detail|SQL config failure/)).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: '在預覽中開啟正式 LIFF 入口' })).not.toBeInTheDocument();
    expect(screen.queryByTitle(/正式 LIFF 測試入口 QR Code/)).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: '實機驗收入口' })).not.toBeInTheDocument();
  });

  it('通知對象入口排除舊群組且不啟動群組寫入', async () => {
    const client: RuntimeTargetClient = {
      listTargets: vi.fn().mockResolvedValue([
        { target_id: 1, target_kind: 'group', display_label: 'typed 測試群組', state: 'active', minimum_status: 'warning', current_version: 'v1', updated_at: '2026-10-22' },
        { target_id: 2, target_kind: 'admin_user', display_label: 'typed 內部使用者', state: 'active', minimum_status: 'warning', current_version: 'v2', updated_at: '2026-10-22' },
      ]),
      previewResetGroup: vi.fn(), resetGroup: vi.fn(), previewSetEnabled: vi.fn(), setEnabled: vi.fn(),
    };
    render(React.createElement(AlertGroupSecurity, { runtimeTargetClient: client }));
    await screen.findByText('typed 內部使用者');
    expect(screen.queryByText('typed 測試群組')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '預覽解除群組' })).not.toBeInTheDocument();
    expect(client.previewResetGroup).not.toHaveBeenCalled();
    expect(client.resetGroup).not.toHaveBeenCalled();
  });
});
