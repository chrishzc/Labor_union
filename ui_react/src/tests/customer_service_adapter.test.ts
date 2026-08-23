/**
 * File: customer_service_adapter.test.ts
 * Description: 驗證客服 Adapter 僅轉譯伺服器事實，不生成假摘要、狀態或時間。
 */
import { describe, expect, it } from 'vitest';
import {
  adaptCustomerServiceDetail,
  adaptCustomerServicePage,
  adaptCustomerServiceResolvePreview,
  adaptCustomerServiceSummary,
  CUSTOMER_SERVICE_LIST_SUMMARY_UNAVAILABLE,
} from '../adapters/customer_service/customer_service_adapter';
import {
  CUSTOMER_SERVICE_DETAIL_FIXTURE,
  CUSTOMER_SERVICE_PAGE_FIXTURE,
  CUSTOMER_SERVICE_RESOLVE_PREVIEW_FIXTURE,
  CUSTOMER_SERVICE_SUMMARY_FIXTURE,
} from './fixtures/customer_service/customer_service_contract_fixtures';

describe('customer service adapter', () => {
  it('映射 summary 與 page 原始計數，不自算 KPI', () => {
    expect(adaptCustomerServiceSummary(CUSTOMER_SERVICE_SUMMARY_FIXTURE)).toEqual(
      {
        waiting: 2,
        handling: 1,
        resolvedToday: 3,
      }
    );
    const page = adaptCustomerServicePage(CUSTOMER_SERVICE_PAGE_FIXTURE);
    expect(page.total).toBe(1);
    expect(page.page).toBe(1);
    expect(page.pageSize).toBe(25);
  });

  it('列表沒有 server 問題摘要時保留 null，不從分類或 internal note 猜測', () => {
    const page = adaptCustomerServicePage(CUSTOMER_SERVICE_PAGE_FIXTURE);
    expect(page.items[0].issueSummary).toBeNull();
    expect(CUSTOMER_SERVICE_LIST_SUMMARY_UNAVAILABLE).toBe(
      '請開啟明細查看訊息'
    );
    expect(page.items[0].categoryLabel).toBe('修改登記資料');
    expect(page.items[0].statusLabel).toBe('處理中');
    expect(page.items[0].maskedLineUserId).toBe('U12***789');
  });

  it('detail 逐筆映射 server events 且不改寫時間與 actor', () => {
    const detail = adaptCustomerServiceDetail(CUSTOMER_SERVICE_DETAIL_FIXTURE);
    expect(detail.events).toEqual([
      {
        id: 81,
        eventType: 'message_received',
        messageText: '請協助確認資料更新方式',
        actorId: 'line-user:masked',
        createdAt: '2026-08-16T08:00:00+00:00',
      },
    ]);
    expect(detail.ticket.createdAt).toBe('2026-08-16T08:00:00+00:00');
  });

  it('Preview 僅採 server apply_ready、blockers 與版本，不在前端推 eligibility', () => {
    const preview = adaptCustomerServiceResolvePreview(
      CUSTOMER_SERVICE_RESOLVE_PREVIEW_FIXTURE
    );
    expect(preview.applyReady).toBe(true);
    expect(preview.blockers).toEqual([]);
    expect(preview.currentVersion).toBe(4);
    expect(preview.expectedVersion).toBe(4);
    expect(preview.beforeStatusLabel).toBe('處理中');
    expect(preview.afterStatusLabel).toBe('已結案');
  });
});
