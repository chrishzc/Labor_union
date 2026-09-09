/** Governed Knowledge workflow for LINE common questions and approved answers. */
import React, { useEffect, useMemo, useState } from 'react';
import { BookOpenCheck, Pencil, Plus, SearchCheck, ShieldCheck } from 'lucide-react';
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

const lifecycleLabels: Record<LifecycleStatus, string> = {
  draft: '草稿', reviewed: '已審核', published: '已發布', retired: '已停用',
};

const indexLabels: Record<KnowledgeIndex['index_status'], string> = {
  requested: '等待建立', building: '建立中', ready: 'READY', stale: '需重建', failed: '建立失敗',
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
    knowledge_qa_answer_required: '標準回答尚未完成，不能送審或發布。',
    knowledge_item_version_conflict: '內容已被其他人更新，請重新整理後再操作。',
    knowledge_review_required: '目前狀態不能執行這個動作，請重新整理確認。',
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

export const CommonQaCatalogPanel: React.FC = () => {
  const [items, setItems] = useState<ManagedQa[]>([]);
  const [latestIndex, setLatestIndex] = useState<KnowledgeIndex | null>(null);
  const [query, setQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('ALL');
  const [notice, setNotice] = useState<string | null>(null);
  const [noticeKind, setNoticeKind] = useState<'success' | 'error' | 'info'>('info');
  const [busy, setBusy] = useState(false);
  const [editingItem, setEditingItem] = useState<ManagedQa | null>(null);
  const [isCreating, setIsCreating] = useState(false);
  const [modalNotice, setModalNotice] = useState<string | null>(null);
  const [formData, setFormData] = useState({
    id: '', question: '', answer: '', category: '月嫂媒合', tag: '常見問題', aliases: '', notes: '',
  });

  const loadState = async () => {
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
    } catch (error) {
      setNotice(error instanceof Error ? error.message : 'Knowledge 題庫讀取失敗。');
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
  }), '已送出索引建立工作；狀態變成 READY 後才會供 AI 客服使用。');

  const transition = (item: ManagedQa, action: 'review' | 'publish' | 'retire') => {
    const identity = operationIdentity(`qa-${action}`);
    const success = action === 'review' ? '已完成審核。' : action === 'publish' ? '已發布；請重建索引後供 AI 使用。' : '已停用；請重建索引以移除舊答案。';
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

  const save = async (event?: React.SyntheticEvent) => {
    event?.preventDefault();
    const qaId = formData.id.trim().toUpperCase();
    if (!/^[A-Z0-9][A-Z0-9-]{1,79}$/.test(qaId) || !formData.question.trim()) {
      setModalNotice('請輸入有效的題目編號與標準問題。'); return;
    }
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
      setNotice(editingItem ? '已建立新草稿版本，需重新審核與發布。' : '已新增草稿，審核後即可發布。');
      setNoticeKind('success');
    } catch (error) {
      setModalNotice(error instanceof Error ? error.message : '儲存失敗。');
    } finally { setBusy(false); }
  };

  return (
    <div className="ai-editor-card qa-catalog-panel">
      <div className="ai-editor-header qa-catalog-header">
        <div className="qa-catalog-title">
          <h2><BookOpenCheck aria-hidden="true" />常見 QA Knowledge</h2>
          <span className="category-badge">共 {items.length} 筆 · {publishedCount} 筆已發布</span>
        </div>
        <div className="qa-catalog-actions">
          <button type="button" className="line-secondary-btn" disabled={busy || publishedCount === 0} onClick={() => void requestIndex()}><SearchCheck aria-hidden="true" />建立／重建索引</button>
          <button type="button" className="line-primary-btn" disabled={busy} onClick={openCreate}><Plus aria-hidden="true" />新增 QA</button>
        </div>
      </div>

      <div className="line-warning" role="status">
        <ShieldCheck aria-hidden="true" /> 系統已內建 29 題基礎題庫。編輯會產生草稿版本；「發布」才代表啟用，「停用」會保留歷程；發布後仍須重建索引。
      </div>
      <div className={`qa-index-status is-${latestIndex?.index_status ?? 'missing'}`} role="status">
        <strong>AI 索引：</strong>{latestIndex ? `v${latestIndex.index_version} · ${indexLabels[latestIndex.index_status]}` : '尚未建立'}
      </div>
      {notice && <div className={noticeKind === 'error' ? 'line-error' : noticeKind === 'success' ? 'line-success' : 'line-warning'} role="status">{notice}</div>}

      <div className="form-group-row qa-catalog-filters">
        <div className="form-field-half"><label htmlFor="qa-catalog-search">搜尋常見 QA</label><input id="qa-catalog-search" type="search" value={query} placeholder="題號、分類、問題或別名" onChange={(event) => setQuery(event.target.value)} /></div>
        <div className="form-field-half"><label htmlFor="qa-catalog-status">治理狀態</label><select id="qa-catalog-status" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}><option value="ALL">全部</option><option value="draft">草稿</option><option value="reviewed">已審核</option><option value="published">已發布（啟用）</option><option value="retired">已停用</option></select></div>
      </div>
      <small>顯示 {filteredItems.length}／{items.length} 筆正式 Knowledge 項目</small>

      <div className="qa-catalog-list">
        {filteredItems.map((item) => (
          <details key={item.id} className="ai-rule-item-card qa-catalog-item">
            <summary className="qa-catalog-summary">
              <div><strong>{item.qa.id} · {item.qa.question}</strong><span className="category-badge qa-catalog-category">{item.qa.category} / {item.qa.tag}</span><span className={`qa-lifecycle-badge is-${item.lifecycle_status}`}>{lifecycleLabels[item.lifecycle_status]} · v{item.current_version}</span></div>
              <div className="qa-catalog-actions">
                {item.lifecycle_status === 'draft' && <button type="button" className="line-secondary-btn" disabled={busy || !item.qa.answer} onClick={(event) => { event.preventDefault(); void transition(item, 'review'); }}>送審完成</button>}
                {item.lifecycle_status === 'reviewed' && <button type="button" className="line-primary-btn" disabled={busy} onClick={(event) => { event.preventDefault(); void transition(item, 'publish'); }}>發布啟用</button>}
                {item.lifecycle_status === 'published' && <button type="button" className="line-danger-btn" disabled={busy} onClick={(event) => { event.preventDefault(); void transition(item, 'retire'); }}>停用</button>}
                <button type="button" className="line-secondary-btn" disabled={busy} title="編輯此題目" onClick={(event) => { event.preventDefault(); openEdit(item); }}><Pencil aria-hidden="true" />編輯</button>
              </div>
            </summary>
            <div className="qa-catalog-detail"><div><strong>常見問法：</strong>{item.qa.aliases.join('、') || '—'}</div><div><strong>標準回答：</strong>{item.qa.answer || '尚無答案'}</div>{item.qa.notes && <div><strong>備註：</strong>{item.qa.notes}</div>}<details className="qa-catalog-technical"><summary>技術資訊</summary><small>Knowledge #{item.id} · {item.source_identity} · 來源 {item.qa.source_ref}</small></details></div>
          </details>
        ))}
        {filteredItems.length === 0 && <div className="line-warning" role="status">{items.length === 0 ? '內建題庫尚未完成初始化，請重新啟動服務；若仍為空白，請聯絡系統管理者。' : '目前沒有符合條件的正式 Knowledge QA。'}</div>}
      </div>

      <Drawer isOpen={isCreating || editingItem !== null} onClose={closeEditor} title={isCreating ? '新增 QA 草稿' : `編輯 QA（${editingItem?.qa.id}）`} size="wide" closeDisabled={busy} closeLabel="關閉 QA 編輯器" footer={<div className="line-drawer-footer"><button type="button" disabled={busy} className="line-secondary-btn" onClick={closeEditor}>取消</button><button type="button" disabled={busy} className="line-primary-btn" onClick={save}>{busy ? '儲存中…' : '儲存為草稿'}</button></div>}>
        <form className="qa-editor-form" onSubmit={save} noValidate>
          {modalNotice && <div className="line-error" role="alert">{modalNotice}</div>}
          <label className="qa-editor-field"><span>題目編號 *</span><input required disabled={!isCreating} value={formData.id} placeholder="例如 QA-030" onChange={(event) => setFormData({ ...formData, id: event.target.value })} /></label>
          <label className="qa-editor-field"><span>標準問題 *</span><input required value={formData.question} onChange={(event) => setFormData({ ...formData, question: event.target.value })} /></label>
          <label className="qa-editor-field"><span>標準回答</span><textarea rows={5} value={formData.answer} placeholder="可先留空；補齊後才能送審。" onChange={(event) => setFormData({ ...formData, answer: event.target.value })} /></label>
          <label className="qa-editor-field"><span>常見問法／別名（每行一筆）</span><textarea rows={4} value={formData.aliases} onChange={(event) => setFormData({ ...formData, aliases: event.target.value })} /></label>
          <div className="qa-editor-columns"><label className="qa-editor-field"><span>業務分類</span><input value={formData.category} onChange={(event) => setFormData({ ...formData, category: event.target.value })} /></label><label className="qa-editor-field"><span>標籤</span><input value={formData.tag} onChange={(event) => setFormData({ ...formData, tag: event.target.value })} /></label></div>
          <label className="qa-editor-field"><span>內部備註</span><input value={formData.notes} onChange={(event) => setFormData({ ...formData, notes: event.target.value })} /></label>
        </form>
      </Drawer>
    </div>
  );
};

export default CommonQaCatalogPanel;
