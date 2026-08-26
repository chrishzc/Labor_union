/**
 * File: LineDeliveryTaskWorkbench.tsx
 * Description: 以 LINE Delivery server page metadata 呈現遮罩任務清單、篩選與抗競態翻頁。
 */
import React, { useEffect, useRef, useState } from 'react';
import {
  lineDeliveryQueryClient,
  type LineDeliveryListQuery,
  type LineDeliveryQueryOptions,
} from '../api/line_delivery/line_delivery_query_client';
import { LineDeliveryQueryError } from '../api/line_delivery/line_delivery_query_errors';
import type {
  LineDeliveryPage,
  LineDeliverySourceType,
  LineDeliveryStatus,
} from '../api/line_delivery/line_delivery_query_schemas';
import { adaptLineDeliveryItem } from '../adapters/line_delivery/line_delivery_query_adapter';

const PAGE_SIZE = 25;

const STATUS_OPTIONS: ReadonlyArray<{ value: LineDeliveryStatus; label: string }> = [
  { value: 'pending', label: '待執行' },
  { value: 'processing', label: '處理中' },
  { value: 'sent', label: '已送出' },
  { value: 'retryable_failed', label: '等待重試' },
  { value: 'failed', label: '失敗' },
  { value: 'cancelled', label: '已取消' },
];

const SOURCE_OPTIONS: ReadonlyArray<{ value: LineDeliverySourceType; label: string }> = [
  { value: 'general_push', label: '一般推播' },
  { value: 'customer_service', label: '客服通知' },
  { value: 'contract', label: '契約通知' },
  { value: 'follow_schedule', label: '追蹤排程' },
  { value: 'identity', label: '身分通知' },
  { value: 'identity_review', label: '身分審核' },
  { value: 'rich_menu', label: 'Rich Menu' },
  { value: 'rich_menu_link', label: 'Rich Menu 綁定' },
  { value: 'rich_menu_unlink', label: 'Rich Menu 解除' },
  { value: 'webhook', label: 'Webhook 回覆' },
  { value: 'group_invitation', label: '群組邀請' },
  { value: 'runtime', label: '系統通知' },
  { value: 'matching', label: '媒合通知' },
  { value: 'order', label: '訂單通知' },
  { value: 'finance', label: '帳務通知' },
  { value: 'assignment', label: '排班通知' },
];

export interface LineDeliveryTaskWorkbenchClient {
  list(query?: LineDeliveryListQuery, options?: LineDeliveryQueryOptions): Promise<LineDeliveryPage>;
}

interface LineDeliveryTaskWorkbenchProps {
  client?: LineDeliveryTaskWorkbenchClient;
  reloadToken?: number;
  onOpenTask(taskId: number): void;
}

type QueryState =
  | { status: 'loading'; page: null; message: null }
  | { status: 'loaded'; page: LineDeliveryPage; message: null }
  | { status: 'error'; page: null; message: string };

function displayError(error: unknown): string {
  if (error instanceof LineDeliveryQueryError) return error.message;
  if (error instanceof Error && error.message.trim()) return error.message;
  return '發送任務清單載入失敗，請稍後重新整理。';
}

export const LineDeliveryTaskWorkbench: React.FC<LineDeliveryTaskWorkbenchProps> = ({
  client = lineDeliveryQueryClient,
  reloadToken = 0,
  onOpenTask,
}) => {
  const [pageNumber, setPageNumber] = useState(1);
  const [statusFilter, setStatusFilter] = useState<LineDeliveryStatus | 'all'>('all');
  const [sourceFilter, setSourceFilter] = useState<LineDeliverySourceType | 'all'>('all');
  const [query, setQuery] = useState<QueryState>({ status: 'loading', page: null, message: null });
  const requestGeneration = useRef(0);

  useEffect(() => {
    const controller = new AbortController();
    const generation = requestGeneration.current + 1;
    requestGeneration.current = generation;
    setQuery({ status: 'loading', page: null, message: null });

    void client.list({
      page: pageNumber,
      pageSize: PAGE_SIZE,
      status: statusFilter === 'all' ? undefined : statusFilter,
      sourceType: sourceFilter === 'all' ? undefined : sourceFilter,
    }, { signal: controller.signal }).then((page) => {
      if (!controller.signal.aborted && generation === requestGeneration.current) {
        setQuery({ status: 'loaded', page, message: null });
      }
    }).catch((error: unknown) => {
      if (!controller.signal.aborted && generation === requestGeneration.current) {
        setQuery({ status: 'error', page: null, message: displayError(error) });
      }
    });

    return () => controller.abort();
  }, [client, pageNumber, reloadToken, sourceFilter, statusFilter]);

  const page = query.page;
  const items = page?.items.map(adaptLineDeliveryItem) ?? [];
  const rangeStart = page && page.total > 0 ? ((page.page - 1) * page.page_size) + 1 : 0;
  const rangeEnd = page ? Math.min(page.page * page.page_size, page.total) : 0;
  const isLastPage = page === null || page.total_pages === 0 || page.page >= page.total_pages;

  return (
    <div data-control-id="line.delivery.workbench">
      <div className="line-search-filter-toolbar" aria-label="LINE 發送任務篩選">
        <div className="line-filter-selects">
          <label>
            <span className="line-filter-label">任務狀態</span>
            <select
              aria-label="任務狀態"
              className="line-filter-select"
              value={statusFilter}
              onChange={(event) => {
                setPageNumber(1);
                setStatusFilter(event.target.value as LineDeliveryStatus | 'all');
              }}
            >
              <option value="all">全部狀態</option>
              {STATUS_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
            </select>
          </label>
          <label>
            <span className="line-filter-label">通知用途</span>
            <select
              aria-label="通知用途"
              className="line-filter-select"
              value={sourceFilter}
              onChange={(event) => {
                setPageNumber(1);
                setSourceFilter(event.target.value as LineDeliverySourceType | 'all');
              }}
            >
              <option value="all">全部用途</option>
              {SOURCE_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
            </select>
          </label>
        </div>
      </div>

      {query.status === 'loading' && <p role="status">正在載入發送任務…</p>}
      {query.status === 'error' && <p className="line-error" role="alert">{query.message}</p>}

      {query.status === 'loaded' && items.length === 0 && (
        <div className="line-empty-state" style={{ marginTop: '16px' }}>
          <div>📮</div>
          <h4>目前沒有符合篩選條件的發送任務</h4>
          <p>請調整篩選條件；系統不會以假資料補齊清單。</p>
        </div>
      )}

      {query.status === 'loaded' && items.length > 0 && (
        <div className="line-table-scroll" style={{ marginTop: '16px' }}>
          <table className="line-data-table" data-control-id="line.delivery.table">
            <thead><tr><th>通知用途</th><th>排程時間</th><th>處理進度</th><th>狀態</th><th style={{ textAlign: 'right' }}>操作</th></tr></thead>
            <tbody>
              {items.map((task) => (
                <tr key={task.taskId}>
                  <td><span className="line-category-badge category-service_flow">{task.sourceLabel}</span></td>
                  <td style={{ color: '#74593f', fontSize: '0.82rem' }}>{task.scheduledAt}</td>
                  <td><span aria-label={`已嘗試 ${task.attempts} 次`}>{task.attempts}</span></td>
                  <td><span className={`line-status line-status-${task.status}`}>{task.statusLabel}</span></td>
                  <td style={{ textAlign: 'right' }}>
                    <button type="button" className="line-action-link-btn" onClick={() => onOpenTask(task.taskId)}>[ 🔍 查看明細 ]</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {query.status === 'loaded' && page && (
        <div className="line-pagination-bar">
          <button type="button" className="line-secondary-btn" disabled={page.page <= 1} onClick={() => setPageNumber((value) => Math.max(1, value - 1))}>上一頁</button>
          <span aria-live="polite" style={{ fontSize: '0.85rem', color: '#74593f' }}>
            第 {page.page}／{Math.max(1, page.total_pages)} 頁，顯示第 {rangeStart}–{rangeEnd} 筆，共 {page.total} 筆
          </span>
          <button type="button" className="line-secondary-btn" disabled={isLastPage} onClick={() => setPageNumber((value) => value + 1)}>下一頁</button>
        </div>
      )}
    </div>
  );
};
