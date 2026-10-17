import { useRef as useValidationRef } from 'react';
import { useSaveValidation } from '../../components/useSaveValidation';
/** Governed Knowledge workflow for LINE common questions and approved answers. */
import React, { useEffect, useMemo, useState } from 'react';
import { ChevronDown, CircleHelp, Download, Pencil, Plus, RefreshCw, Search, SearchCheck } from 'lucide-react';
import { sessionClient } from '../../api/auth/session_client';
import { Drawer } from '../../components/Drawer';

const QA_SCHEMA = 'line.common_qa.v1';
const QA_SOURCE_PREFIX = 'line-common-qa:';

type LifecycleStatus = 'draft' | 'reviewed' | 'published' | 'retired';

interface KnowledgeItem {
  id: number;
  source_identity: string;
  title: string;
  lifecycle_status: LifecycleStatus;
  current_version: number;
  source_uri: string | null;
  content: string;
}

interface QaContent {
  schema: typeof QA_SCHEMA;
  id: string;
  category: string;
  tag: string;
  question: string;
  aliases: string[];
  answer: string;
  source_ref: string;
  notes: string | null;
  migration_status: string | null;
}

interface ManagedQa extends KnowledgeItem { qa: QaContent }

interface KnowledgeIndex {
  index_version: number;
  index_status: 'requested' | 'building' | 'ready' | 'stale' | 'failed';
  built_at_utc: string | null;
}

interface BuiltinCatalogImportResult {
  catalog_count: number;
  imported_count: number;
  skipped_existing_count: number;
  published_count: number;
  index_job_id: number | null;
}

const lifecycleLabels: Record<LifecycleStatus, string> = {
  draft: '草稿', reviewed: '待啟用（舊資料）', published: '已發布', retired: '已停用',
};

const indexLabels: Record<KnowledgeIndex['index_status'], string> = {
  requested: '等待更新', building: '更新中', ready: '更新完成', stale: '需要更新', failed: '更新失敗',
};

function requestHeaders(json = false): Record<string, string> {
  const headers: Record<string, string> = {};
  const token = sessionClient.getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  if (json) headers['Content-Type'] = 'application/json';
  return headers;
}

function operationIdentity(prefix: string): string {
  return `${prefix}:${Date.now()}:${Math.random().toString(16).slice(2)}`;
}

async function apiError(response: Response): Promise<string> {
  const payload = await response.json().catch(() => ({})) as { detail?: string | { code?: string } };
  const code = typeof payload.detail === 'string' ? payload.detail : payload.detail?.code;
  const messages: Record<string, string> = {
    knowledge_qa_answer_required: '標準回答尚未完成，不能發布。',
    knowledge_item_version_conflict: '內容已被其他人更新，請重新整理後再操作。',
    knowledge_review_required: '目前狀態不能執行這個動作，請重新整理確認。',
    knowledge_state_conflict: '目前狀態不能執行這個動作，請重新整理確認。',
  };
  return (code && messages[code]) || code || `操作失敗（${response.status}）`;
}

function decodeQa(item: KnowledgeItem): ManagedQa | null {
  if (!item.source_identity.startsWith(QA_SOURCE_PREFIX)) return null;
  try {
    const qa = JSON.parse(item.content) as QaContent;
    if (qa.schema !== QA_SCHEMA || !qa.id || !qa.question || !Array.isArray(qa.aliases)) return null;
    return { ...item, qa };
  } catch {
    return null;
  }
}

export const CommonQaCatalogPanel: React.FC<{ initialQaId?: string; initialQuestion?: string }> = ({ initialQaId, initialQuestion }) => {
  const [items, setItems] = useState<ManagedQa[]>([]);
  const [latestIndex, setLatestIndex] = useState<KnowledgeIndex | null>(null);
  const [readStatus, setReadStatus] = useState<'loading' | 'ready' | 'error'>('loading');
  const [query, setQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('ALL');
  const [notice, setNotice] = useState<string | null>(null);
  const [noticeKind, setNoticeKind] = useState<'success' | 'error' | 'info'>('info');
  const [busy, setBusy] = useState(false);
  const [editingItem, setEditingItem] = useState<ManagedQa | null>(null);
  const [isCreating, setIsCreating] = useState(false);
  const [initialEditorOpened, setInitialEditorOpened] = useState(false);
  const [modalNotice, setModalNotice] = useState<string | null>(null);
  const [formData, setFormData] = useState({
    id: '', question: '', answer: '', category: '月嫂媒合', tag: '常見問題', aliases: '', notes: '',
  });

  const loadState = async () => {
    setReadStatus('loading');
    try {
      const [itemsResponse, indexesResponse] = await Promise.all([
        fetch('/api/v1/knowledge/items?limit=500', { headers: requestHeaders(), credentials: 'include' }),
        fetch('/api/v1/knowledge/indexes?limit=20', { headers: requestHeaders(), credentials: 'include' }),
      ]);
      if (!itemsResponse.ok) throw new Error(await apiError(itemsResponse));
      if (!indexesResponse.ok) throw new Error(await apiError(indexesResponse));
      const rawItems = await itemsResponse.json() as KnowledgeItem[];
      const indexes = await indexesResponse.json() as KnowledgeIndex[];
      setItems(rawItems.map(decodeQa).filter((item): item is ManagedQa => item !== null));
      setLatestIndex(indexes[0] ?? null);
      setReadStatus('ready');
    } catch (error) {
      setReadStatus('error');
      setNotice(error instanceof Error ? error.message : '問答資料讀取失敗。');
      setNoticeKind('error');
    }
  };

  useEffect(() => { void loadState(); }, []);

  const filteredItems = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase('zh-TW');
    return items.filter((item) => {
      const statusMatches = statusFilter === 'ALL' || item.lifecycle_status === statusFilter;
      const textMatches = !normalized || [
        item.qa.id, item.qa.category, item.qa.tag, item.qa.question, item.qa.answer, ...item.qa.aliases,
      ].some((value) => value.toLocaleLowerCase('zh-TW').includes(normalized));
      return statusMatches && textMatches;
    });
  }, [items, query, statusFilter]);

  const publishedCount = items.filter((item) => item.lifecycle_status === 'published').length;

  const runMutation = async (operation: () => Promise<Response>, success: string) => {
    setBusy(true);
    try {
      const response = await operation();
      if (!response.ok) throw new Error(await apiError(response));
      await loadState();
      setNotice(success);
      setNoticeKind('success');
      return true;
    } catch (error) {
      setNotice(error instanceof Error ? error.message : '操作失敗。');
      setNoticeKind('error');
      return false;
    } finally {
      setBusy(false);
    }
  };

  const requestIndex = () => runMutation(() => fetch('/api/v1/knowledge/indexes', {
    method: 'POST', headers: { ...requestHeaders(), 'Idempotency-Key': operationIdentity('qa-index') }, credentials: 'include',
  }), '已送出問答搜尋資料更新工作；更新完成後才會供 AI 客服使用。');

  const importBuiltinCatalog = async () => {
    if (!window.confirm('將補齊系統內建的 54 題，不會覆寫既有編修。確定繼續？')) return;
    setBusy(true); setNotice(null);
    const identity = operationIdentity('qa-builtin-import');
    try {
      const response = await fetch('/api/v1/knowledge/catalogs/builtin-line-common-qa/import', {
        method: 'POST',
        headers: { ...requestHeaders(), 'Idempotency-Key': identity, 'X-Correlation-ID': identity },
        credentials: 'include',
      });
      if (!response.ok) throw new Error(await apiError(response));
      const result = await response.json() as BuiltinCatalogImportResult;
      await loadState();
      const indexMessage = result.index_job_id === null ? '目前不需更新問答搜尋資料。' : '問答搜尋資料更新工作已建立，更新完成後才會啟用。';
      setNotice(`內建題庫共 ${result.catalog_count} 題；本次補入 ${result.imported_count} 題、發布 ${result.published_count} 題。${indexMessage}`);
      setNoticeKind('success');
    } catch (error) {
      setNotice(error instanceof Error ? error.message : '內建題庫匯入失敗。');
      setNoticeKind('error');
    } finally {
      setBusy(false);
    }
  };

  const transition = (item: ManagedQa, action: 'publish' | 'retire') => {
    const identity = operationIdentity(`qa-${action}`);
    const success = action === 'publish' ? '新答案已發布，問答搜尋資料更新完成後才會啟用。' : '已停用，正在更新問答搜尋資料以移除舊答案。';
    return runMutation(() => fetch(`/api/v1/knowledge/items/${item.id}/${action}`, {
      method: 'POST',
      headers: { ...requestHeaders(true), 'Idempotency-Key': identity, 'X-Correlation-ID': identity },
      credentials: 'include',
      body: JSON.stringify({ expected_version: item.current_version, reason: `AI 客服工作室：${action} ${item.qa.id}` }),
    }), success);
  };

  const openCreate = () => {
    setFormData({ id: '', question: '', answer: '', category: '月嫂媒合', tag: '常見問題', aliases: '', notes: '' });
    setEditingItem(null); setIsCreating(true); setModalNotice(null);
  };

  const openEdit = (item: ManagedQa) => {
    setFormData({
      id: item.qa.id, question: item.qa.question, answer: item.qa.answer, category: item.qa.category,
      tag: item.qa.tag, aliases: item.qa.aliases.join('\n'), notes: item.qa.notes ?? '',
    });
    setEditingItem(item); setIsCreating(false); setModalNotice(null);
  };

  const closeEditor = () => { setEditingItem(null); setIsCreating(false); setModalNotice(null); };

  useEffect(() => {
    if (readStatus !== 'ready' || initialEditorOpened) return;
    if (initialQaId) {
      const item = items.find((row) => row.qa.id === initialQaId);
      if (item) openEdit(item);
      else { setNotice('目前問答清單中找不到這個題目，請搜尋確認。'); setNoticeKind('info'); }
    } else if (initialQuestion) {
      openCreate();
      setFormData((current) => ({ ...current, question: initialQuestion }));
    }
    setInitialEditorOpened(true);
  }, [readStatus, items, initialQaId, initialQuestion, initialEditorOpened]);

  const saveValidation = useSaveValidation();
  const questionRef = useValidationRef<HTMLInputElement>(null);
  const qaIdRef = useValidationRef<HTMLInputElement>(null);

  const save = async (event?: React.SyntheticEvent) => {
    event?.preventDefault();
    const qaId = formData.id.trim().toUpperCase();
    if (busy || !saveValidation.validate([
      { value: formData.question, label: '標準問題', ref: questionRef },
      { value: qaId, label: '題目編號', ref: qaIdRef, valid: /^[A-Z0-9][A-Z0-9-]{1,79}$/.test(qaId), message: '請填寫有效的題目編號（2～80 碼英文、數字或連字號）。' },
    ])) return;
    if (isCreating && items.some((item) => item.qa.id === qaId)) {
      setModalNotice('此題目編號已存在，請從清單開啟原題目編輯。'); return;
    }
    const qa: QaContent = {
      schema: QA_SCHEMA, id: qaId, category: formData.category.trim() || '一般諮詢',
      tag: formData.tag.trim() || '常見問題', question: formData.question.trim(),
      aliases: formData.aliases.split('\n').map((value) => value.trim()).filter(Boolean),
      answer: formData.answer.trim(), source_ref: editingItem?.qa.source_ref || 'admin-created',
      notes: formData.notes.trim() || null, migration_status: editingItem?.qa.migration_status ?? null,
    };
    setBusy(true); setModalNotice(null);
    const identity = operationIdentity('qa-save');
    try {
      const response = await fetch('/api/v1/knowledge/items', {
        method: 'POST', headers: { ...requestHeaders(true), 'Idempotency-Key': identity, 'X-Correlation-ID': identity }, credentials: 'include',
        body: JSON.stringify({
          source_identity: `${QA_SOURCE_PREFIX}${qa.id}`, source_trust_tier: 'internal_policy',
          title: qa.question, content: JSON.stringify(qa), source_uri: qa.source_ref,
        }),
      });
      if (!response.ok) throw new Error(await apiError(response));
      closeEditor(); await loadState();
      setNotice(editingItem ? '已建立新草稿版本，可直接發布啟用。' : '已新增草稿，可直接發布啟用。');
      setNoticeKind('success');
    } catch (error) {
      setModalNotice(error instanceof Error ? error.message : '儲存失敗。');
    } finally { setBusy(false); }
  };

  return (
    <div className="ai-editor-card qa-catalog-panel">
      <div className="ai-editor-header qa-catalog-header">
        <div>
          <h2>常見問答</h2>
          <p className="studio-description">管理客服可以使用的標準答案。</p>
        </div>
        <div className="qa-catalog-actions">
          <details className="studio-more-actions">
            <summary className="line-secondary-btn">更多操作<ChevronDown aria-hidden="true" /></summary>
            <div className="studio-action-menu">
              <button type="button" disabled={busy} onClick={() => void importBuiltinCatalog()}><Download aria-hidden="true" />匯入／補齊內建 54 題</button>
              <button type="button" disabled={busy || publishedCount === 0} onClick={() => void requestIndex()}><SearchCheck aria-hidden="true" />更新問答搜尋資料</button>
              <button type="button" disabled={busy || readStatus === 'loading'} onClick={() => void loadState()}><RefreshCw aria-hidden="true" />重新整理</button>
            </div>
          </details>
          <button type="button" className="line-primary-btn" disabled={busy} onClick={openCreate}><Plus aria-hidden="true" />新增問答</button>
        </div>
      </div>

      {readStatus !== 'ready' && <div className={readStatus === 'error' ? 'line-error' : 'studio-description'} role="status">{readStatus === 'loading' ? '正在讀取問答資料…' : '問答資料讀取失敗，請重新整理。'}</div>}
      {readStatus === 'ready' && items.length === 0 && <div className="line-warning" role="status">目前尚無題目，可匯入內建 54 題。</div>}
      <div className="studio-status-row">
        <div className={`qa-index-status is-${latestIndex?.index_status ?? 'missing'}`} role="status">
          <strong>問答搜尋資料：</strong>{readStatus === 'loading' ? '讀取中' : readStatus === 'error' ? '無法確認更新狀態' : latestIndex ? indexLabels[latestIndex.index_status] : '尚未建立'}
          {readStatus === 'ready' && <span className="studio-count">共 {items.length} 筆 · {publishedCount} 筆已發布</span>}
        </div>
        <details className="studio-help"><summary><CircleHelp aria-hidden="true" />發布與生效說明</summary><p>編輯後需發布新答案；問答搜尋資料更新完成後才會啟用。停用會保留歷程，並更新搜尋資料以移除舊答案。</p>{latestIndex && <small>索引版本：{latestIndex.index_version}</small>}</details>
      </div>
      {notice && <div className={noticeKind === 'error' ? 'line-error' : noticeKind === 'success' ? 'line-success' : 'studio-description'} role="status">{notice}</div>}

      <div className="studio-qa-toolbar">
        <label className="studio-search"><span className="sr-only">搜尋常見問答</span><Search aria-hidden="true" /><input id="qa-catalog-search" type="search" value={query} placeholder="搜尋題號、分類、問題、答案或常見問法" onChange={(event) => setQuery(event.target.value)} /></label>
        <label><span className="sr-only">問答狀態</span><select id="qa-catalog-status" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}><option value="ALL">全部狀態</option><option value="draft">草稿</option><option value="reviewed">待啟用（舊資料）</option><option value="published">已發布</option><option value="retired">已停用</option></select></label>
        {readStatus === 'ready' && <small>顯示 {filteredItems.length}／{items.length} 筆</small>}
      </div>
      <div className="qa-catalog-list">
        {filteredItems.map((item) => (
          <article key={item.id} className="studio-qa-row">
          <details className="qa-catalog-item studio-qa-item">
            <summary className="qa-catalog-summary">
              <div className="studio-question-title"><strong>{item.qa.question}</strong><small>{item.qa.category} · {item.qa.aliases.length} 種常見問法</small></div>
              <span className={`qa-lifecycle-badge is-${item.lifecycle_status}`}>{lifecycleLabels[item.lifecycle_status]}</span>
            </summary>
            <div className="qa-catalog-detail">
              <div><strong>常見問法：</strong>{item.qa.aliases.join('、') || '—'}</div>
              <div className="studio-answer-text"><strong>標準回答：</strong>{item.qa.answer || '尚無答案'}</div>
              {item.qa.notes && <div><strong>備註：</strong>{item.qa.notes}</div>}
              <div className="qa-catalog-actions">
                {(item.lifecycle_status === 'draft' || item.lifecycle_status === 'reviewed') && <button type="button" className="line-primary-btn" disabled={busy || !item.qa.answer} onClick={() => void transition(item, 'publish')}>發布</button>}
                {item.lifecycle_status === 'published' && <button type="button" className="line-danger-btn" disabled={busy} onClick={() => void transition(item, 'retire')}>停用</button>}
              </div>
              <details className="studio-technical"><summary>題號、版本與來源資訊</summary><small>{item.qa.id} · v{item.current_version} · {item.qa.category} / {item.qa.tag}<br />Knowledge #{item.id} · {item.source_identity} · 來源 {item.qa.source_ref}</small></details>
            </div>
          </details>
          <button type="button" className="studio-text-button studio-row-edit" disabled={busy} title="編輯此題目" aria-label={`編輯問答：${item.qa.question}`} onClick={() => openEdit(item)}><Pencil aria-hidden="true" />編輯</button>
          </article>
        ))}
        {readStatus === 'ready' && filteredItems.length === 0 && items.length > 0 && <div className="studio-empty" role="status">目前沒有符合條件的問答。</div>}
      </div>
      <p className="studio-list-footer">修改會先儲存為草稿，確認後再發布。</p>

      <Drawer isOpen={isCreating || editingItem !== null} onClose={closeEditor} title={isCreating ? '新增問答草稿' : `編輯問答（${editingItem?.qa.id}）`} size="normal" className="studio-qa-drawer" closeDisabled={busy} closeLabel="關閉問答編輯器" footer={<div className="line-drawer-footer">
        {editingItem && (editingItem.lifecycle_status === 'draft' || editingItem.lifecycle_status === 'reviewed') && <button type="button" disabled={busy || !editingItem.qa.answer} className="line-secondary-btn" onClick={() => { if (window.confirm('發布目前已儲存的草稿？尚未儲存的編輯內容不會納入；搜尋資料更新完成後才生效。')) void transition(editingItem, 'publish').then((ok) => { if (ok) closeEditor(); }); }}>發布已儲存草稿</button>}
        {editingItem?.lifecycle_status === 'published' && <button type="button" disabled={busy} className="line-danger-btn" onClick={() => { if (window.confirm('停用目前已發布的問答？歷程將保留。')) void transition(editingItem, 'retire').then((ok) => { if (ok) closeEditor(); }); }}>停用這則問答</button>}
        <button type="button" disabled={busy} className="line-secondary-btn" onClick={closeEditor}>取消</button><button type="button" disabled={busy} className="line-primary-btn" onClick={save}>{busy ? '儲存中…' : '儲存為草稿'}</button>
      </div>}>
        <p className="studio-description">編輯後會先建立草稿，確認答案後再發布。</p>
        <form className="qa-editor-form" onSubmit={save} noValidate>
          {saveValidation.feedback}
          {(modalNotice || (noticeKind === 'error' && notice)) && <div className="line-error" role="alert">{modalNotice || notice}</div>}
          <label className="qa-editor-field"><span>標準問題 *</span><input ref={questionRef} required value={formData.question} onChange={(event) => setFormData({ ...formData, question: event.target.value })} /></label>
          <label className="qa-editor-field"><span>標準回答</span><textarea rows={7} value={formData.answer} placeholder="可先留空；補齊後才能發布。" onChange={(event) => setFormData({ ...formData, answer: event.target.value })} /></label>
          <label className="qa-editor-field"><span>常見問法／別名（每行一筆）</span><textarea rows={3} value={formData.aliases} onChange={(event) => setFormData({ ...formData, aliases: event.target.value })} /></label>
          <details className="studio-editor-secondary" open={isCreating || undefined}><summary>分類與其他資訊</summary>
            <label className="qa-editor-field"><span>題目編號 *</span><input ref={qaIdRef} required disabled={!isCreating} value={formData.id} placeholder="例如 QA-030" onChange={(event) => setFormData({ ...formData, id: event.target.value })} /></label>
            <div className="qa-editor-columns"><label className="qa-editor-field"><span>業務分類</span><input value={formData.category} onChange={(event) => setFormData({ ...formData, category: event.target.value })} /></label><label className="qa-editor-field"><span>標籤</span><input value={formData.tag} onChange={(event) => setFormData({ ...formData, tag: event.target.value })} /></label></div>
            <label className="qa-editor-field"><span>內部備註</span><input value={formData.notes} onChange={(event) => setFormData({ ...formData, notes: event.target.value })} /></label>
          </details>
        </form>
      </Drawer>
    </div>
  );
};

export default CommonQaCatalogPanel;
