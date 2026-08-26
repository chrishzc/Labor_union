/**
 * File: line_delivery_task_workbench.test.tsx
 * Description: 驗證 LINE Delivery 工作台使用 server metadata 翻頁、篩選重設與拒絕晚到回應。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { LineDeliveryPage } from '../api/line_delivery/line_delivery_query_schemas';
import {
  LineDeliveryTaskWorkbench,
  type LineDeliveryTaskWorkbenchClient,
} from '../components/LineDeliveryTaskWorkbench';

function task(taskId: number, sourceType: 'customer_service' | 'contract' = 'customer_service') {
  return {
    id: taskId,
    task_id: taskId,
    task_type: 'follow_up',
    source_type: sourceType,
    status: 'sent' as const,
    scheduled_at: '2026-08-25T10:00:00+08:00',
    completed_attempts: 1,
    max_attempts: 3,
    next_retry_at: null,
    sent_at: '2026-08-25T10:01:00+08:00',
    failed_at: null,
    created_at: '2026-08-25T09:00:00+08:00',
    updated_at: '2026-08-25T10:01:00+08:00',
  };
}

function page(pageNumber: number, taskId: number, total = 26): LineDeliveryPage {
  return {
    items: [task(taskId, pageNumber === 1 ? 'customer_service' : 'contract')],
    page: pageNumber,
    page_size: 25,
    total,
    total_pages: Math.ceil(total / 25),
  };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => { resolve = done; });
  return { promise, resolve };
}

describe('LineDeliveryTaskWorkbench', () => {
  it('使用 server range/total 前後翻頁，末頁鎖定並由列開啟明細', async () => {
    const client: LineDeliveryTaskWorkbenchClient = {
      list: vi.fn(async (query) => page(query?.page ?? 1, query?.page === 2 ? 26 : 17)),
    };
    const onOpenTask = vi.fn();
    render(<LineDeliveryTaskWorkbench client={client} onOpenTask={onOpenTask} />);

    expect(await screen.findByText('第 1／2 頁，顯示第 1–25 筆，共 26 筆')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '上一頁' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: '下一頁' }));

    expect(await screen.findByText('第 2／2 頁，顯示第 26–26 筆，共 26 筆')).toBeInTheDocument();
    expect(client.list).toHaveBeenLastCalledWith(
      { page: 2, pageSize: 25, sourceType: undefined, status: undefined },
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
    expect(screen.getByRole('button', { name: '下一頁' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '上一頁' })).toBeEnabled();
    fireEvent.click(screen.getByRole('button', { name: /查看明細/ }));
    expect(onOpenTask).toHaveBeenCalledWith(26);
  });

  it('變更 server allowlist 篩選時重設第一頁，不以記憶體切片清單', async () => {
    const client: LineDeliveryTaskWorkbenchClient = {
      list: vi.fn(async (query) => page(query?.page ?? 1, query?.page === 2 ? 26 : 17)),
    };
    render(<LineDeliveryTaskWorkbench client={client} onOpenTask={vi.fn()} />);
    await screen.findByText(/第 1／2 頁/);
    fireEvent.click(screen.getByRole('button', { name: '下一頁' }));
    await screen.findByText(/第 2／2 頁/);

    fireEvent.change(screen.getByRole('combobox', { name: '任務狀態' }), { target: { value: 'sent' } });
    await waitFor(() => expect(client.list).toHaveBeenLastCalledWith(
      { page: 1, pageSize: 25, sourceType: undefined, status: 'sent' },
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    ));
    fireEvent.change(screen.getByRole('combobox', { name: '通知用途' }), { target: { value: 'contract' } });
    await waitFor(() => expect(client.list).toHaveBeenLastCalledWith(
      { page: 1, pageSize: 25, sourceType: 'contract', status: 'sent' },
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    ));
  });

  it('取消舊 request 並拒絕晚到的舊頁覆蓋最新篩選結果', async () => {
    const pageTwo = deferred<LineDeliveryPage>();
    const filteredPage = deferred<LineDeliveryPage>();
    const signals: AbortSignal[] = [];
    const client: LineDeliveryTaskWorkbenchClient = {
      list: vi.fn((query, options) => {
        if (options?.signal) signals.push(options.signal);
        if (query?.status === 'sent') return filteredPage.promise;
        if (query?.page === 2) return pageTwo.promise;
        return Promise.resolve(page(1, 17));
      }),
    };
    render(<LineDeliveryTaskWorkbench client={client} onOpenTask={vi.fn()} />);
    await screen.findByText(/第 1／2 頁/);
    fireEvent.click(screen.getByRole('button', { name: '下一頁' }));
    await waitFor(() => expect(client.list).toHaveBeenCalledTimes(2));
    fireEvent.change(screen.getByRole('combobox', { name: '任務狀態' }), { target: { value: 'sent' } });
    await waitFor(() => expect(client.list).toHaveBeenCalledTimes(3));
    expect(signals[1]?.aborted).toBe(true);

    filteredPage.resolve({ items: [task(88)], page: 1, page_size: 25, total: 1, total_pages: 1 });
    expect(await screen.findByText('第 1／1 頁，顯示第 1–1 筆，共 1 筆')).toBeInTheDocument();
    pageTwo.resolve(page(2, 26));
    await Promise.resolve();
    expect(screen.queryByText(/第 2／2 頁/)).not.toBeInTheDocument();
  });
});
