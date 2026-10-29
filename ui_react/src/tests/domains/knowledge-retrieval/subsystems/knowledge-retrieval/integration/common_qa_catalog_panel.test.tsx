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
    if (path.includes('/catalogs/builtin-line-common-qa/import')) return new Response(JSON.stringify({ catalog_count: 54, imported_count: 51, skipped_existing_count: 3, published_count: 39, index_job_id: 88 }), { status: 200 });
    if (path.includes('/knowledge/items?')) return new Response(JSON.stringify(items), { status: 200 });
    if (path.includes('/knowledge/indexes?')) return new Response(JSON.stringify([{ index_version: 4, index_status: 'stale', built_at_utc: null }]), { status: 200 });
    return new Response(JSON.stringify({}), { status: 200 });
  });
}

describe('正式 Knowledge QA 管理 panel', () => {
  afterEach(() => vi.restoreAllMocks());

  it('does not claim the catalog is loaded or empty until reads complete, and distinguishes failed reads', async () => {
    let finishItems!: (value: Response) => void;
    const pending = new Promise<Response>((resolve) => { finishItems = resolve; });
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (url) => String(url).includes('/knowledge/items?')
      ? pending : new Response('[]', { status: 200 }));
    const { unmount } = render(React.createElement(CommonQaCatalogPanel));
    expect(screen.getByText(/正在讀取問答資料/)).toBeInTheDocument();
    expect(screen.queryByText(/目前尚無題目/)).not.toBeInTheDocument();
    finishItems(new Response('[]', { status: 200 }));
    expect(await screen.findByText(/目前尚無題目，可匯入內建 54 題/)).toBeInTheDocument();
    expect(screen.queryByText(/已載入/)).not.toBeInTheDocument();
    unmount();
    vi.restoreAllMocks();
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('{}', { status: 503 }));
    render(React.createElement(CommonQaCatalogPanel));
    expect(await screen.findByText(/問答資料讀取失敗，請重新整理/)).toBeInTheDocument();
    expect(screen.queryByText(/目前尚無題目/)).not.toBeInTheDocument();
    expect(screen.queryByText(/共 0 筆/)).not.toBeInTheDocument();
  });

  it('顯示問答狀態、已發布數量與索引 freshness', async () => {
    mockKnowledgeApi();
    render(React.createElement(CommonQaCatalogPanel));

    await waitFor(() => expect(screen.getByText(/共 3 筆 · 1 筆已發布/)).toBeInTheDocument());
    expect(screen.getByText(/問答搜尋資料：/).parentElement).toHaveTextContent('需要更新');
    expect(globalThis.fetch).toHaveBeenCalledWith('/api/v1/knowledge/items?limit=500', expect.objectContaining({ credentials: 'include' }));

    fireEvent.change(screen.getByLabelText('問答狀態'), { target: { value: 'published' } });
    expect(screen.getByText(/QA-003 的標準問題/)).toBeInTheDocument();
    expect(screen.queryByText(/QA-001 的標準問題/)).not.toBeInTheDocument();
  });

  it('草稿可直接發布，並可停用、編修與重建索引', async () => {
    const fetchMock = mockKnowledgeApi();
    render(React.createElement(CommonQaCatalogPanel));
    await waitFor(() => expect(screen.getByText(/共 3 筆/)).toBeInTheDocument());

    fireEvent.click(screen.getByText('更多操作'));
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true);
    fireEvent.click(screen.getByRole('button', { name: '匯入／補齊內建 54 題' }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith('/api/v1/knowledge/catalogs/builtin-line-common-qa/import', expect.objectContaining({ method: 'POST' })));
    expect(confirm).not.toHaveBeenCalled();
    expect(await screen.findByText(/本次補入 51 題、發布 39 題/)).toBeInTheDocument();

    expect(screen.queryByRole('button', { name: '送審完成' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByText('QA-001 的標準問題'));
    fireEvent.click(screen.getAllByRole('button', { name: '發布' })[0]);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith('/api/v1/knowledge/items/1/publish', expect.objectContaining({ method: 'POST', credentials: 'include', body: JSON.stringify({ expected_version: 1, reason: 'AI 客服工作室：publish QA-001' }) })));
    expect(await screen.findByText('新答案已發布，問答搜尋資料更新完成後才會啟用。')).toBeInTheDocument();

    fireEvent.click(screen.getByText('QA-003 的標準問題'));
    fireEvent.click(screen.getByRole('button', { name: '停用' }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith('/api/v1/knowledge/items/3/retire', expect.objectContaining({ method: 'POST' })));

    fireEvent.click(screen.getByRole('button', { name: /更新問答搜尋資料/ }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith('/api/v1/knowledge/indexes', expect.objectContaining({ method: 'POST' })));

    fireEvent.click(screen.getAllByTitle('編輯此題目')[0]);
    expect(screen.getByRole('heading', { name: '編輯問答（QA-001）' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '儲存為草稿' }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith('/api/v1/knowledge/items', expect.objectContaining({ method: 'POST' })));
  });
  it('跨頁指定題目會開啟正式資料編輯器，儲存仍建立同一來源的新草稿', async () => {
    const fetchMock = mockKnowledgeApi();
    render(<CommonQaCatalogPanel initialQaId="QA-003" />);
    expect(await screen.findByRole('heading', { name: '編輯問答（QA-003）' })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('標準回答'), { target: { value: '調整後的正式草稿答案' } });
    fireEvent.click(screen.getByRole('button', { name: '儲存為草稿' }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith('/api/v1/knowledge/items', expect.objectContaining({ method: 'POST' })));
    const write = fetchMock.mock.calls.find(([url, init]) => String(url) === '/api/v1/knowledge/items' && init?.method === 'POST');
    const payload = JSON.parse(String(write?.[1]?.body));
    expect(payload.source_identity).toBe('line-common-qa:QA-003');
    expect(JSON.parse(payload.content).answer).toBe('調整後的正式草稿答案');
    expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith('/publish'))).toBe(false);
  });

  it('從知識缺口帶入問題時只開啟新草稿，不會自動寫入或發布', async () => {
    const fetchMock = mockKnowledgeApi();
    render(<CommonQaCatalogPanel initialQuestion="需要補強的新問題" />);
    expect(await screen.findByLabelText('標準問題 *')).toHaveValue('需要補強的新問題');
    expect(screen.getByLabelText('題目編號 *')).toHaveValue('');
    expect(fetchMock.mock.calls.every(([, init]) => !init?.method || init.method === 'GET')).toBe(true);
  });
});
