import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { CommonQaCatalogPanel } from '../../../../../../pages/line_management/CommonQaCatalogPanel';


const qaContent = (id: string, answer: string) => JSON.stringify({
  schema: 'line.common_qa.v1', id, category: '月嫂媒合', tag: '常見問題',
  question: `${id} 的標準問題`, aliases: [`${id} 的別名`], answer,
  source_ref: 'document/line/QA問答集.xlsx', notes: null, migration_status: 'ready',
});

const items = [
  { id: 1, source_identity: 'line-common-qa:QA-001', title: 'QA-001 的標準問題', lifecycle_status: 'draft', current_version: 1, source_uri: 'source', content: qaContent('QA-001', '草稿答案') },
  { id: 2, source_identity: 'line-common-qa:QA-002', title: 'QA-002 的標準問題', lifecycle_status: 'reviewed', current_version: 2, source_uri: 'source', content: qaContent('QA-002', '已審答案') },
  { id: 3, source_identity: 'line-common-qa:QA-003', title: 'QA-003 的標準問題', lifecycle_status: 'published', current_version: 3, source_uri: 'source', content: qaContent('QA-003', '發布答案') },
];

function mockKnowledgeApi() {
  return vi.spyOn(globalThis, 'fetch').mockImplementation(async (url) => {
    const path = String(url);
    if (path.includes('/knowledge/items?')) return new Response(JSON.stringify(items), { status: 200 });
    if (path.includes('/knowledge/indexes?')) return new Response(JSON.stringify([{ index_version: 4, index_status: 'stale', built_at_utc: null }]), { status: 200 });
    return new Response(JSON.stringify({}), { status: 200 });
  });
}

describe('正式 Knowledge QA 管理 panel', () => {
  afterEach(() => vi.restoreAllMocks());

  it('顯示治理狀態、已發布數量與索引 freshness', async () => {
    mockKnowledgeApi();
    render(React.createElement(CommonQaCatalogPanel));

    await waitFor(() => expect(screen.getByText(/共 3 筆 · 1 筆已發布/)).toBeInTheDocument());
    expect(screen.getByText(/AI 索引：/).parentElement).toHaveTextContent('v4 · 需重建');
    expect(globalThis.fetch).toHaveBeenCalledWith('/api/v1/knowledge/items?limit=500', expect.objectContaining({ credentials: 'include' }));

    fireEvent.change(screen.getByLabelText('治理狀態'), { target: { value: 'published' } });
    expect(screen.getByText(/QA-003 · QA-003 的標準問題/)).toBeInTheDocument();
    expect(screen.queryByText(/QA-001 · QA-001 的標準問題/)).not.toBeInTheDocument();
  });

  it('草稿可直接發布，並可停用、編修與重建索引', async () => {
    const fetchMock = mockKnowledgeApi();
    render(React.createElement(CommonQaCatalogPanel));
    await waitFor(() => expect(screen.getByText(/共 3 筆/)).toBeInTheDocument());

    expect(screen.getByText(/系統已載入基礎題庫/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /匯入/ })).not.toBeInTheDocument();

    expect(screen.queryByRole('button', { name: '送審完成' })).not.toBeInTheDocument();
    fireEvent.click(screen.getAllByRole('button', { name: '發布啟用' })[0]);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith('/api/v1/knowledge/items/1/publish', expect.objectContaining({ method: 'POST' })));
    expect(await screen.findByText('已發布，正在更新 AI 索引；READY 後即啟用。')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '停用' }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith('/api/v1/knowledge/items/3/retire', expect.objectContaining({ method: 'POST' })));

    fireEvent.click(screen.getByRole('button', { name: /手動重建索引/ }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith('/api/v1/knowledge/indexes', expect.objectContaining({ method: 'POST' })));

    fireEvent.click(screen.getAllByTitle('編輯此題目')[0]);
    expect(screen.getByRole('heading', { name: '編輯 QA（QA-001）' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '儲存為草稿' }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith('/api/v1/knowledge/items', expect.objectContaining({ method: 'POST' })));
  });
});
