import React from 'react';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { CommonQaCatalogPanel } from '../../../../../../pages/line_management/CommonQaCatalogPanel';


const qaContent = (id: string, answer: string) => JSON.stringify({
  schema: 'line.common_qa.v1', id, category: '月嫂媒合', category_id: 'service_flow', tag: '常見問題',
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
    if (path.endsWith('/knowledge/items/1/publish')) return Response.json({ version: 2 });
    if (path.includes('/faq-layout/published-questions')) {
      return Response.json({ data: { items: path.endsWith('qa_id=QA-001')
        ? [{ qa_id: 'QA-001', version: 2, question: 'QA-001 的標準問題', answer: '草稿答案' }] : [] } });
    }
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

  it('既有草稿可確認發布，並可停用與重建索引', async () => {
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
    const draft = screen.getByText('QA-001 的標準問題');
    const draftRow = within(draft.closest('article')!);
    fireEvent.click(draft);
    fireEvent.click(draftRow.getByRole('button', { name: '發布' }));
    fireEvent.click(draftRow.getByRole('button', { name: '確認發布' }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith('/api/v1/knowledge/items/1/publish', expect.objectContaining({ method: 'POST', credentials: 'include', body: JSON.stringify({ expected_version: 1, reason: 'LINE 常見問答：publish QA-001' }) })));
    expect(await screen.findByText('已讀回正式答案。')).toBeInTheDocument();

    const published = screen.getByText('QA-003 的標準問題');
    fireEvent.click(published);
    fireEvent.click(within(published.closest('article')!).getByRole('button', { name: '停用' }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith('/api/v1/knowledge/items/3/retire', expect.objectContaining({ method: 'POST' })));
    expect(await screen.findByText('已停用，聊天室不再提供該答案。')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /更新問答搜尋資料/ }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith('/api/v1/knowledge/indexes', expect.objectContaining({ method: 'POST' })));
  });

  it('重新整理找不到原題目時，仍可查看未儲存內容並取消編輯', async () => {
    const requests = mockKnowledgeApi();
    const read = requests.getMockImplementation()!;
    let catalog = items;
    requests.mockImplementation((url, init) => String(url).includes('/knowledge/items?')
      ? Promise.resolve(Response.json(catalog))
      : read(url, init));
    render(<CommonQaCatalogPanel />);
    fireEvent.click(await screen.findByRole('button', { name: '編輯問答：QA-001 的標準問題' }));
    fireEvent.change(screen.getByLabelText('標準回答'), { target: { value: '尚未儲存的答案' } });

    catalog = items.slice(1);
    fireEvent.click(screen.getByText('更多操作'));
    fireEvent.click(screen.getByRole('button', { name: '重新整理' }));

    expect(await screen.findByText(/清單已找不到這則問答/)).toBeInTheDocument();
    const heading = screen.getByRole('heading', { name: '編輯問答（QA-001）' });
    const editor = within(heading.closest('article')!);
    expect(editor.getByLabelText('標準回答')).toHaveValue('尚未儲存的答案');
    expect(editor.getByRole('button', { name: '發布（儲存）' })).toBeDisabled();
    expect(editor.getByRole('button', { name: '永久刪除' })).toBeDisabled();
    fireEvent.click(editor.getByRole('button', { name: '取消' }));
    expect(heading).not.toBeInTheDocument();
    expect(requests.mock.calls.every(([, init]) => init?.method !== 'POST')).toBe(true);
  });

  it('跨頁指定題目會在同一張卡片編輯，確認後發布這次儲存的版本', async () => {
    const requests = mockKnowledgeApi();
    const read = requests.getMockImplementation()!;
    requests.mockImplementation(async (url, init) => {
      const path = String(url);
      if (path === '/api/v1/knowledge/items' && init?.method === 'POST') return Response.json({ item_id: 3, created: true });
      if (path.endsWith('/knowledge/items/3/publish')) return Response.json({ version: 5 });
      if (path.endsWith('qa_id=QA-003')) return Response.json({ data: { items: [{
        qa_id: 'QA-003', version: 5, question: 'QA-003 的標準問題', answer: '調整後的正式答案',
      }] } });
      return read(url, init);
    });
    render(<CommonQaCatalogPanel initialQaId="QA-003" />);
    const editor = await screen.findByRole('heading', { name: '編輯問答（QA-003）' });
    const row = within(editor.closest('article')!);
    const answer = row.getByLabelText('標準回答');
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(screen.queryByText(/分類與其他資訊|常見問法／別名|儲存為草稿/)).toBeNull();
    fireEvent.change(answer, { target: { value: '調整後的正式答案' } });
    fireEvent.click(row.getByRole('button', { name: '發布（儲存）' }));
    expect(requests.mock.calls.some(([, init]) => init?.method === 'POST')).toBe(false);
    fireEvent.click(row.getByRole('button', { name: '確認發布' }));
    expect(await screen.findByText('已讀回正式答案。')).toBeInTheDocument();
    const write = requests.mock.calls.find(([url, init]) => String(url) === '/api/v1/knowledge/items' && init?.method === 'POST');
    const payload = JSON.parse(String(write?.[1]?.body));
    expect(payload.source_identity).toBe('line-common-qa:QA-003');
    expect(payload.expected_version).toBe(3);
    expect(JSON.parse(payload.content)).toMatchObject({
      answer: '調整後的正式答案', category_id: 'service_flow', aliases: ['QA-003 的別名'],
    });
    const publish = requests.mock.calls.find(([url]) => String(url).endsWith('/knowledge/items/3/publish'));
    expect(JSON.parse(String(publish?.[1]?.body)).expected_version).toBe(4);
  });

  it('發布無法確認時保留表單，重試沿用同一版本與操作識別', async () => {
    const requests = mockKnowledgeApi();
    const read = requests.getMockImplementation()!;
    let publishAttempts = 0;
    requests.mockImplementation(async (url, init) => {
      const path = String(url);
      if (path === '/api/v1/knowledge/items' && init?.method === 'POST') return Response.json({ item_id: 3, created: true });
      if (path.endsWith('/knowledge/items/3/publish')) {
        publishAttempts += 1;
        return publishAttempts === 1 ? Response.json({}, { status: 503 }) : Response.json({ version: 5 });
      }
      if (path.endsWith('qa_id=QA-003')) return Response.json({ data: { items: [{
        qa_id: 'QA-003', version: 5, question: 'QA-003 的標準問題', answer: '重試後讀回的答案',
      }] } });
      return read(url, init);
    });
    render(<CommonQaCatalogPanel initialQaId="QA-003" />);
    const answer = await screen.findByLabelText('標準回答');
    fireEvent.change(answer, { target: { value: '重試後讀回的答案' } });
    fireEvent.click(screen.getByRole('button', { name: '發布（儲存）' }));
    fireEvent.click(screen.getByRole('button', { name: '確認發布' }));
    const retry = await screen.findByRole('button', { name: '重試發布' });
    expect(answer).toHaveValue('重試後讀回的答案');
    expect(screen.queryByText('已讀回正式答案。')).toBeNull();
    fireEvent.click(retry);
    expect(await screen.findByText('已讀回正式答案。')).toBeInTheDocument();
    const attempts = requests.mock.calls.filter(([url]) => String(url).endsWith('/knowledge/items/3/publish'));
    expect(attempts).toHaveLength(2);
    expect(attempts[0][1]?.body).toBe(attempts[1][1]?.body);
    expect(new Headers(attempts[0][1]?.headers).get('Idempotency-Key')).toBe(
      new Headers(attempts[1][1]?.headers).get('Idempotency-Key'),
    );
  });

  it('只顯示未生效題目的永久刪除，確認及正式讀回後移除題目', async () => {
    const catalog = [
      ...items,
      { ...items[0], id: 4, lifecycle_status: 'retired', content: qaContent('QA-004', '已停用答案') },
      { ...items[0], id: 5, published_version: 1, content: qaContent('QA-005', '仍有正式答案') },
      { ...items[0], id: 6, faq_delete_eligible: 0, content: qaContent('QA-006', '舊版正式答案') },
    ];
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (url, init) => {
      const path = String(url);
      if (path.includes('/knowledge/items?')) return Response.json(catalog);
      if (path.endsWith('/knowledge/items/1/delete-faq') && init?.method === 'POST') {
        catalog.shift();
        return Response.json({ item_id: 1 });
      }
      if (path.endsWith('/knowledge/items/1')) {
        return Response.json({ detail: { code: 'knowledge_item_not_found' } }, { status: 404 });
      }
      return Response.json([]);
    });
    render(<CommonQaCatalogPanel />);
    await screen.findByText('QA-001 的標準問題');
    const row = (id: string) => within(screen.getByText(`${id} 的標準問題`).closest('article')!);
    for (const id of ['QA-001', 'QA-002', 'QA-003', 'QA-004', 'QA-005', 'QA-006']) {
      fireEvent.click(screen.getByText(`${id} 的標準問題`));
    }
    for (const id of ['QA-001', 'QA-002', 'QA-004']) {
      expect(row(id).getByRole('button', { name: '永久刪除' })).toBeVisible();
    }
    for (const id of ['QA-003', 'QA-005']) {
      expect(row(id).queryByRole('button', { name: '永久刪除' })).toBeNull();
      expect(row(id).getByRole('button', { name: '停用' })).toBeVisible();
    }
    expect(row('QA-006').queryByRole('button', { name: '永久刪除' })).toBeNull();

    const remove = row('QA-001').getByRole('button', { name: '永久刪除' });
    fireEvent.click(remove);
    const returnButton = row('QA-001').getByRole('button', { name: '返回' });
    expect(returnButton).toHaveFocus();
    fireEvent.click(returnButton);
    expect(remove).toHaveFocus();
    expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith('/delete-faq'))).toBe(false);
    fireEvent.click(remove);
    fireEvent.click(row('QA-001').getByRole('button', { name: '確認刪除' }));
    expect(await screen.findByText('已永久刪除這則問答。')).toBeInTheDocument();
    expect(screen.queryByText('QA-001 的標準問題')).toBeNull();
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/knowledge/items/1/delete-faq', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ expected_version: 1, reason: '永久刪除 LINE 常見問答 QA-001' }),
    }));
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/knowledge/items/1', expect.objectContaining({ credentials: 'include' }));
  });

  it('帶入問題只開啟表單，新增會產生編號並在確定後發布', async () => {
    const requests = mockKnowledgeApi();
    const read = requests.getMockImplementation()!;
    let saved: { id: string; question: string; answer: string } | undefined;
    requests.mockImplementation(async (url, init) => {
      const path = String(url);
      if (path === '/api/v1/knowledge/items' && init?.method === 'POST') {
        saved = JSON.parse(JSON.parse(String(init.body)).content);
        return Response.json({ item_id: 7, created: true });
      }
      if (path.endsWith('/knowledge/items/7/publish')) return Response.json({ version: 2 });
      if (path.includes('/faq-layout/published-questions')) return Response.json({ data: { items: [{
        qa_id: saved?.id, version: 2, question: saved?.question, answer: saved?.answer,
      }] } });
      return read(url, init);
    });
    render(<CommonQaCatalogPanel initialQuestion="需要補強的新問題" />);
    expect(await screen.findByLabelText('標準問題 *')).toHaveValue('需要補強的新問題');
    expect(screen.queryByLabelText('題目編號 *')).toBeNull();
    const action = screen.getByRole('button', { name: '發布（儲存）' });
    fireEvent.click(action);
    expect(screen.queryByRole('button', { name: '確認發布' })).toBeNull();
    expect(requests.mock.calls.every(([, init]) => !init?.method || init.method === 'GET')).toBe(true);
    fireEvent.change(screen.getByLabelText('標準回答'), { target: { value: '補強後的標準回答' } });
    fireEvent.click(action);
    fireEvent.click(screen.getByRole('button', { name: '確認發布' }));
    expect(await screen.findByText('已讀回正式答案。')).toBeInTheDocument();
    expect(saved).toMatchObject({ id: expect.stringMatching(/^[A-Z0-9-]+$/i), category: '未分類', aliases: [] });
    const publish = requests.mock.calls.find(([url]) => String(url).endsWith('/knowledge/items/7/publish'));
    expect(JSON.parse(String(publish?.[1]?.body)).expected_version).toBe(1);
  });
});
