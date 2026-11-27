import { applicationFetch } from '../../api/shared/application_fetch';
import { useUnsavedDraft, useUnsavedNavigation } from '../../components/UnsavedChanges';
/** Governed Knowledge workflow for LINE common questions and approved answers. */
import React, { useEffect, useId, useMemo, useRef, useState } from 'react';
import { ChevronDown, CircleHelp, Download, Pencil, Plus, RefreshCw, Search, SearchCheck } from 'lucide-react';
import { sessionClient } from '../../api/auth/session_client';
import { faqRequest, type PublishedFaq } from './faqLayoutApi';

const QA_SCHEMA = 'line.common_qa.v1';
const QA_SOURCE_PREFIX = 'line-common-qa:';

type LifecycleStatus = 'draft' | 'reviewed' | 'published' | 'retired';

interface KnowledgeItem {
  id: number;
  source_identity: string;
  title: string;
  lifecycle_status: LifecycleStatus;
  current_version: number;
  published_version?: number | null;
  faq_delete_eligible?: 0 | 1 | boolean;
  source_uri: string | null;
  content: string;
}

interface QaContent {
  schema: typeof QA_SCHEMA;
  id: string;
  category: string;
  category_id?: string;
  tag: string;
  question: string;
  aliases: string[];
  answer: string;
  source_ref: string;
  notes: string | null;
  migration_status: string | null;
}

interface ManagedQa extends KnowledgeItem { qa: QaContent }

type Editor = { item: ManagedQa | null; baseline: { question: string; answer: string } };
type Revision = { itemId: number; version: number };
type Action = {
  kind: 'publish';
  qa: QaContent;
  rowId: number | null;
  identity: string;
  source: { kind: 'saved'; revision: Revision } | { kind: 'edit'; previous: Revision | null };
} | {
  kind: 'delete';
  item: ManagedQa;
  rowId: number;
  identity: string;
};
type Confirmation = {
  action: Action;
  revision?: Revision;
  publishedVersion?: number;
  error?: string;
};

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

function newQaId(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  return 'QA-' + Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0')).join('').toUpperCase();
}

async function apiError(response: Response): Promise<string> {
  const payload = await response.json().catch(() => ({})) as { detail?: string | { code?: string } };
  const code = typeof payload.detail === 'string' ? payload.detail : payload.detail?.code;
  const messages: Record<string, string> = {
    knowledge_qa_answer_required: '標準回答尚未完成，不能發布。',
    knowledge_qa_line_reply_too_long: '答案原文超過 LINE 上限，請縮短答案再發布。',
    knowledge_faq_delete_published: '這則問答仍有生效的正式答案，請先停用再刪除。',
    knowledge_faq_identity_deleted: '這個題目編號曾被永久刪除，請使用其他編號。',
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
  const [editor, setEditor] = useState<Editor | null>(null);
  const [initialEditorOpened, setInitialEditorOpened] = useState(false);
  const [confirmation, setConfirmation] = useState<Confirmation | null>(null);
  const [editorError, setEditorError] = useState<{ field: 'question' | 'answer'; message: string } | null>(null);
  const [formData, setFormData] = useState({ question: '', answer: '' });
  const [focusAfterClose, setFocusAfterClose] = useState<number | 'create' | null>(null);
  const idPrefix = useId();
  const questionRef = useRef<HTMLInputElement>(null);
  const answerRef = useRef<HTMLTextAreaElement>(null);
  const confirmationReturnRef = useRef<HTMLButtonElement>(null);
  const confirmationTrigger = useRef<HTMLElement | null>(null);
  const editingItem = editor?.item;
  const missingEditorItem = editingItem && !items.some((item) => item.id === editingItem.id) ? editingItem : null;
  const operationPending = busy || confirmation !== null;
  const editorWriteDisabled = operationPending || missingEditorItem !== null;

  const loadState = async () => {
    setReadStatus('loading');
    try {
      const [itemsResponse, indexesResponse] = await Promise.all([
        applicationFetch('/api/v1/knowledge/items?limit=500', { headers: requestHeaders(), credentials: 'include' }),
        applicationFetch('/api/v1/knowledge/indexes?limit=20', { headers: requestHeaders(), credentials: 'include' }),
      ]);
      if (!itemsResponse.ok) throw new Error(await apiError(itemsResponse));
      if (!indexesResponse.ok) throw new Error(await apiError(indexesResponse));
      const rawItems = await itemsResponse.json() as KnowledgeItem[];
      const indexes = await indexesResponse.json() as KnowledgeIndex[];
      setItems(rawItems.map(decodeQa).filter((item): item is ManagedQa => item !== null));
      setLatestIndex(indexes[0] ?? null);
      setReadStatus('ready');
      return true;
    } catch (error) {
      setReadStatus('error');
      setNotice(error instanceof Error ? error.message : '問答資料讀取失敗。');
      setNoticeKind('error');
      return false;
    }
  };

  useEffect(() => { void loadState(); }, []);

  const filteredItems = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase('zh-TW');
    return items.filter((item) => {
      const statusMatches = statusFilter === 'ALL' || item.lifecycle_status === statusFilter;
      const textMatches = !normalized || [
        item.qa.id, item.qa.category, item.qa.question, item.qa.answer,
      ].some((value) => value.toLocaleLowerCase('zh-TW').includes(normalized));
      return item.id === editingItem?.id || item.id === confirmation?.action.rowId || (statusMatches && textMatches);
    });
  }, [items, query, statusFilter, editingItem?.id, confirmation?.action.rowId]);

  const isPublished = (item: ManagedQa) => item.published_version != null || item.lifecycle_status === 'published';
  const canDelete = (item: ManagedQa) => !isPublished(item) && Boolean(item.faq_delete_eligible ?? true);
  const publishedCount = items.filter(isPublished).length;

  const runMutation = async (operation: () => Promise<Response>, success: string, verify?: (response: Response) => Promise<void>) => {
    setBusy(true);
    try {
      const response = await operation();
      if (!response.ok) throw new Error(await apiError(response));
      await verify?.(response);
      if (await loadState()) {
        setNotice(success);
        setNoticeKind('success');
      }
      return true;
    } catch (error) {
      setNotice(error instanceof Error ? error.message : '操作失敗。');
      setNoticeKind('error');
      return false;
    } finally {
      setBusy(false);
    }
  };

  const requestIndex = () => runMutation(() => applicationFetch('/api/v1/knowledge/indexes', {
    method: 'POST', headers: { ...requestHeaders(), 'Idempotency-Key': operationIdentity('qa-index') }, credentials: 'include',
  }), '已送出問答搜尋資料更新工作。');

  const importBuiltinCatalog = async () => {
    setBusy(true); setNotice(null);
    const identity = operationIdentity('qa-builtin-import');
    try {
      const response = await applicationFetch('/api/v1/knowledge/catalogs/builtin-line-common-qa/import', {
        method: 'POST',
        headers: { ...requestHeaders(), 'Idempotency-Key': identity, 'X-Correlation-ID': identity },
        credentials: 'include',
      });
      if (!response.ok) throw new Error(await apiError(response));
      const result = await response.json() as BuiltinCatalogImportResult;
      await loadState();
      const indexMessage = result.index_job_id === null ? '目前不需更新問答搜尋資料。' : '問答搜尋資料更新工作已建立。';
      setNotice(`內建題庫共 ${result.catalog_count} 題；本次補入 ${result.imported_count} 題、發布 ${result.published_count} 題。${indexMessage}`);
      setNoticeKind('success');
    } catch (error) {
      setNotice(error instanceof Error ? error.message : '內建題庫匯入失敗。');
      setNoticeKind('error');
    } finally {
      setBusy(false);
    }
  };

  const readPublished = async (qaId: string) => {
    const data = await faqRequest<{ items: PublishedFaq[] }>(
      `/api/v1/line/faq-layout/published-questions?qa_id=${encodeURIComponent(qaId)}`,
    );
    return data.items.find((row) => row.qa_id === qaId);
  };

  const retire = (item: ManagedQa) => {
    const identity = operationIdentity('qa-retire');
    return runMutation(() => applicationFetch(`/api/v1/knowledge/items/${item.id}/retire`, {
      method: 'POST',
      headers: { ...requestHeaders(true), 'Idempotency-Key': identity, 'X-Correlation-ID': identity },
      credentials: 'include',
      body: JSON.stringify({ expected_version: item.current_version, reason: `LINE 常見問答：retire ${item.qa.id}` }),
    }), '已停用，聊天室不再提供該答案。', async () => {
      if (await readPublished(item.qa.id)) {
        throw new Error('操作已受理，正式題庫仍有生效答案。請重新整理確認。');
      }
    });
  };

  const { requestLeave } = useUnsavedNavigation();
  const openEditor = (item: ManagedQa | null, question = '') => {
    const baseline = { question: item?.qa.question ?? question, answer: item?.qa.answer ?? '' };
    setFormData(baseline);
    setEditor({ item, baseline });
    setEditorError(null);
  };
  const closeEditor = () => {
    setFocusAfterClose(editingItem?.id ?? 'create');
    setEditor(null);
    setEditorError(null);
  };

  useEffect(() => {
    if (readStatus !== 'ready' || initialEditorOpened) return;
    if (initialQaId) {
      const item = items.find((row) => row.qa.id === initialQaId);
      if (item) openEditor(item);
      else { setNotice('目前問答清單中找不到這個題目，請搜尋確認。'); setNoticeKind('info'); }
    } else if (initialQuestion) {
      openEditor(null, initialQuestion);
    }
    setInitialEditorOpened(true);
  }, [readStatus, items, initialQaId, initialQuestion, initialEditorOpened]);

  useEffect(() => {
    if (!editor) return;
    questionRef.current?.scrollIntoView?.({ block: 'nearest' });
    questionRef.current?.focus({ preventScroll: true });
  }, [editor]);
  useEffect(() => {
    if (focusAfterClose === null || busy) return;
    const focusTarget = document.getElementById(`${idPrefix}-edit-${focusAfterClose}`)
      ?? document.getElementById(`${idPrefix}-edit-create`);
    focusTarget?.focus();
    setFocusAfterClose(null);
  }, [focusAfterClose, busy, idPrefix]);
  useEffect(() => {
    if (!confirmation) {
      confirmationTrigger.current?.focus();
      confirmationTrigger.current = null;
      return;
    }
    if (!busy) {
      confirmationReturnRef.current?.scrollIntoView?.({ block: 'nearest' });
      confirmationReturnRef.current?.focus({ preventScroll: true });
    }
  }, [confirmation, busy]);

  const draftRef = useUnsavedDraft('常見問答', { '問題': formData.question, '答案': formData.answer }, {
    enabled: editor !== null,
    baseline: editor ? { '問題': editor.baseline.question, '答案': editor.baseline.answer } : null,
    busy,
  });

  const askConfirmation = (action: Action, trigger: HTMLElement | null) => {
    confirmationTrigger.current = trigger;
    setConfirmation({ action });
    setNotice(null);
  };

  const preparePublish = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (editorWriteDisabled || !editor) return;
    const question = formData.question.trim();
    const answer = formData.answer.trim();
    if (!question || Array.from(question).length > 500) {
      setEditorError({ field: 'question', message: '請輸入不超過 500 字的標準問題。' });
      questionRef.current?.focus();
      return;
    }
    if (!answer || answer.length > 5000) {
      setEditorError({ field: 'answer', message: answer ? '答案原文超過 LINE 上限，請縮短答案再發布。' : '請輸入標準回答後再發布。' });
      answerRef.current?.focus();
      return;
    }
    const qa: QaContent = {
      ...(editingItem?.qa ?? {
        schema: QA_SCHEMA, id: newQaId(), category: '未分類', tag: '常見問題',
        aliases: [], source_ref: 'admin-created', notes: null, migration_status: null,
      }),
      question, answer,
    };
    const previous = editingItem ? { itemId: editingItem.id, version: editingItem.current_version } : null;
    const trigger = event.currentTarget.querySelector<HTMLButtonElement>('button[type="submit"]');
    setEditorError(null);
    askConfirmation({ kind: 'publish', qa, rowId: editingItem?.id ?? null, identity: operationIdentity('qa-edit'), source: { kind: 'edit', previous } }, trigger);
  };

  const askRowPublish = (item: ManagedQa, trigger: HTMLButtonElement) => {
    askConfirmation({
      kind: 'publish', qa: item.qa, rowId: item.id, identity: operationIdentity('qa-publish'),
      source: { kind: 'saved', revision: { itemId: item.id, version: item.current_version } },
    }, trigger);
  };
  const askDelete = (item: ManagedQa, trigger: HTMLButtonElement) => {
    askConfirmation({ kind: 'delete', item, rowId: item.id, identity: operationIdentity('qa-delete') }, trigger);
  };

  const submitAction = async () => {
    if (!confirmation || busy) return;
    const { action } = confirmation;
    let revision = confirmation.revision;
    let publishedVersion = confirmation.publishedVersion;
    let errorPrefix = '';
    setBusy(true);
    try {
      if (action.kind === 'delete') {
        const { item, identity } = action;
        const path = `/api/v1/knowledge/items/${item.id}`;
        const response = await applicationFetch(`${path}/delete-faq`, {
          method: 'POST',
          headers: { ...requestHeaders(true), 'Idempotency-Key': identity, 'X-Correlation-ID': identity },
          credentials: 'include',
          body: JSON.stringify({ expected_version: item.current_version, reason: `永久刪除 LINE 常見問答 ${item.qa.id}` }),
        });
        if (!response.ok) throw new Error(await apiError(response));
        const readback = await applicationFetch(path, { headers: requestHeaders(), credentials: 'include' });
        if (readback.status !== 404) throw new Error('無法確認刪除結果，請重新整理題庫。');
        setItems((current) => current.filter((row) => row.id !== item.id));
      } else {
        const { qa, source, identity } = action;
        if (!revision && source.kind === 'edit') {
          errorPrefix = '尚未確認修訂是否儲存。';
          const response = await applicationFetch('/api/v1/knowledge/items', {
            method: 'POST',
            headers: { ...requestHeaders(true), 'Idempotency-Key': `${identity}:save`, 'X-Correlation-ID': identity },
            credentials: 'include',
            body: JSON.stringify({
              source_identity: `${QA_SOURCE_PREFIX}${qa.id}`, source_trust_tier: 'internal_policy',
              title: qa.question, content: JSON.stringify(qa), source_uri: qa.source_ref,
              expected_version: source.previous?.version,
            }),
          });
          if (!response.ok) throw new Error(await apiError(response));
          const saved = await response.json() as { item_id?: number; created?: boolean };
          if (saved.created !== true || typeof saved.item_id !== 'number' || !Number.isSafeInteger(saved.item_id) || saved.item_id < 1
              || (source.previous && saved.item_id !== source.previous.itemId)) {
            throw new Error('無法確認這次儲存的題目版本，請重新整理題庫。');
          }
          revision = { itemId: saved.item_id, version: (source.previous?.version ?? 0) + 1 };
        }
        const target = revision ?? (source.kind === 'saved' ? source.revision : null);
        if (!target) throw new Error('無法取得本次發布的版本。');
        if (publishedVersion === undefined) {
          errorPrefix = source.kind === 'edit' ? '修訂已儲存，尚未確認正式發布。' : '尚未確認正式發布。';
          const response = await applicationFetch(`/api/v1/knowledge/items/${target.itemId}/publish`, {
            method: 'POST',
            headers: { ...requestHeaders(true), 'Idempotency-Key': `${identity}:publish`, 'X-Correlation-ID': identity },
            credentials: 'include',
            body: JSON.stringify({ expected_version: target.version, reason: `LINE 常見問答：publish ${qa.id}` }),
          });
          if (!response.ok) throw new Error(await apiError(response));
          const result = await response.json() as { version?: number };
          if (result.version !== target.version + 1) throw new Error('發布回應的版本與這次操作不同。');
          publishedVersion = result.version;
        }
        errorPrefix = '發布已受理，尚未確認正式答案。';
        const visible = await readPublished(qa.id);
        if (visible?.version !== publishedVersion || visible.question !== qa.question || visible.answer !== qa.answer) {
          throw new Error('正式題庫讀回的內容或版本與本次操作不同。請重新整理確認。');
        }
      }
      if (editor && editingItem?.id === (action.rowId ?? undefined)) closeEditor();
      setFocusAfterClose(action.kind === 'delete' ? 'create' : (revision?.itemId ?? action.rowId ?? 'create'));
      confirmationTrigger.current = null;
      setConfirmation(null);
      if (await loadState()) {
        setNotice(action.kind === 'delete' ? '已永久刪除這則問答。' : '已讀回正式答案。');
        setNoticeKind('success');
      }
    } catch (error) {
      setConfirmation({ action, revision, publishedVersion, error: errorPrefix + (error instanceof Error ? error.message : '操作失敗。') });
    } finally {
      setBusy(false);
    }
  };

  const returnFromConfirmation = async () => {
    if (!confirmation || busy) return;
    if (confirmation.error) {
      setBusy(true);
      const refreshed = await loadState();
      setBusy(false);
      if (!refreshed) return;
      if (editor && editingItem?.id === (confirmation.action.rowId ?? undefined)) closeEditor();
      else setFocusAfterClose(confirmation.action.rowId ?? 'create');
      confirmationTrigger.current = null;
    }
    setConfirmation(null);
  };

  const renderConfirmation = (rowId: number | null) => {
    if (!confirmation || confirmation.action.rowId !== rowId) return null;
    const { action, error } = confirmation;
    return <div className="studio-qa-confirmation" role="group" aria-label={action.kind === 'delete' ? '確認永久刪除問答' : '確認發布問答'}>
      <div>
        {action.kind === 'delete'
          ? <strong>永久刪除「{action.item.qa.question}」（{action.item.qa.id}）及其內容版本？刪除後無法復原。</strong>
          : <strong>{action.source.kind === 'edit' ? '儲存並發布目前內容？' : '發布這筆已儲存的草稿？'}</strong>}
        {error && <p className="line-error" role="alert">{error}</p>}
      </div>
      <div className="qa-catalog-actions">
        <button ref={confirmationReturnRef} type="button" className="line-secondary-btn" disabled={busy} onClick={() => void returnFromConfirmation()}>{error ? '重新整理題庫' : '返回'}</button>
        <button type="button" className={action.kind === 'delete' ? 'line-danger-btn' : 'line-primary-btn'} disabled={busy} onClick={() => void submitAction()}>
          {busy ? '處理中…' : error ? (action.kind === 'delete' ? '重試刪除' : '重試發布') : (action.kind === 'delete' ? '確認刪除' : '確認發布')}
        </button>
      </div>
    </div>;
  };

  const renderEditor = (item: ManagedQa | null) => <article className="studio-qa-row studio-qa-editing" aria-labelledby={`${idPrefix}-editor-heading`}>
    <header className="studio-qa-editor-header">
      <div className="studio-question-title">
        <h3 id={`${idPrefix}-editor-heading`}>{item ? `編輯問答（${item.qa.id}）` : '新增問答'}</h3>
        {item && <small>{item.qa.question}</small>}
      </div>
      {item && <span className={`qa-lifecycle-badge is-${item.lifecycle_status}`}>{lifecycleLabels[item.lifecycle_status]}</span>}
    </header>
    <form className="qa-editor-form studio-inline-qa-form" onSubmit={preparePublish} ref={draftRef} noValidate>
      <div className="studio-qa-fields">
        {missingEditorItem && <p role="status" className="line-error">清單已找不到這則問答。可複製需要保留的內容，再取消編輯。</p>}
        {editorError && <p role="alert" className="line-error" id={`${idPrefix}-validation`}>{editorError.message}</p>}
        <label className="qa-editor-field">
          <span>標準問題 *</span>
          <input ref={questionRef} required readOnly={editorWriteDisabled} value={formData.question}
            aria-invalid={editorError?.field === 'question' || undefined}
            aria-describedby={editorError?.field === 'question' ? `${idPrefix}-validation` : undefined}
            onChange={(event) => { setFormData({ ...formData, question: event.target.value }); setEditorError(null); }} />
        </label>
        <label className="qa-editor-field">
          <span>標準回答</span>
          <textarea ref={answerRef} required rows={5} readOnly={editorWriteDisabled} value={formData.answer}
            aria-invalid={editorError?.field === 'answer' || undefined}
            aria-describedby={editorError?.field === 'answer' ? `${idPrefix}-validation` : undefined}
            onChange={(event) => { setFormData({ ...formData, answer: event.target.value }); setEditorError(null); }} />
        </label>
      </div>
      <div className="studio-qa-editor-actions">
        <small>{!missingEditorItem && '確認後會儲存並發布目前內容。'}</small>
        <div className="qa-catalog-actions">
          {item && isPublished(item) && <button type="button" className="line-danger-btn" disabled={editorWriteDisabled} onClick={() => requestLeave(() => { void retire(item).then((ok) => { if (ok) closeEditor(); }); })}>停用</button>}
          {item && canDelete(item) && <button type="button" className="line-danger-btn" disabled={editorWriteDisabled} onClick={(event) => askDelete(item, event.currentTarget)}>永久刪除</button>}
          <button type="button" className="line-secondary-btn" disabled={operationPending} onClick={() => requestLeave(closeEditor)}>取消</button>
          <button type="submit" className="line-primary-btn" disabled={editorWriteDisabled}>發布（儲存）</button>
        </div>
      </div>
    </form>
    {renderConfirmation(item?.id ?? null)}
  </article>;


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
              <button type="button" disabled={operationPending} onClick={() => void importBuiltinCatalog()}><Download aria-hidden="true" />匯入／補齊內建 54 題</button>
              <button type="button" disabled={operationPending || publishedCount === 0} onClick={() => void requestIndex()}><SearchCheck aria-hidden="true" />更新問答搜尋資料</button>
              <button type="button" disabled={operationPending || readStatus === 'loading'} onClick={() => void loadState()}><RefreshCw aria-hidden="true" />重新整理</button>
            </div>
          </details>
          <button id={`${idPrefix}-edit-create`} type="button" className="line-primary-btn" disabled={operationPending} onClick={() => requestLeave(() => openEditor(null))}><Plus aria-hidden="true" />新增問答</button>
        </div>
      </div>

      {readStatus !== 'ready' && <div className={readStatus === 'error' ? 'line-error' : 'studio-description'} role="status">{readStatus === 'loading' ? '正在讀取問答資料…' : '問答資料讀取失敗，請重新整理。'}</div>}
      {readStatus === 'ready' && items.length === 0 && <div className="line-warning" role="status">目前尚無題目，可匯入內建 54 題。</div>}
      <div className="studio-status-row">
        <div className={`qa-index-status is-${latestIndex?.index_status ?? 'missing'}`} role="status">
          <strong>問答搜尋資料：</strong>{readStatus === 'loading' ? '讀取中' : readStatus === 'error' ? '無法確認更新狀態' : latestIndex ? indexLabels[latestIndex.index_status] : '尚未建立'}
          {readStatus === 'ready' && <span className="studio-count">共 {items.length} 筆 · {publishedCount} 筆已發布</span>}
        </div>
        <details className="studio-help"><summary><CircleHelp aria-hidden="true" />發布與生效說明</summary><p>題目正式發布後，LINE 聊天室會立即使用新的正式答案。停用會保留歷程，並從搜尋資料移除舊答案。</p>{latestIndex && <small>索引版本：{latestIndex.index_version}</small>}</details>
      </div>
      {notice && <div className={noticeKind === 'error' ? 'line-error' : noticeKind === 'success' ? 'line-success' : 'studio-description'} role="status">{notice}</div>}

      <div className="studio-qa-toolbar">
        <label className="studio-search"><span className="sr-only">搜尋常見問答</span><Search aria-hidden="true" /><input id="qa-catalog-search" type="search" value={query} placeholder="搜尋題號、分類、問題或答案" onChange={(event) => setQuery(event.target.value)} /></label>
        <label><span className="sr-only">問答狀態</span><select id="qa-catalog-status" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}><option value="ALL">全部狀態</option><option value="draft">草稿</option><option value="reviewed">待啟用（舊資料）</option><option value="published">已發布</option><option value="retired">已停用</option></select></label>
        {readStatus === 'ready' && <small>顯示 {filteredItems.length}／{items.length} 筆</small>}
      </div>
      <div className="qa-catalog-list">
        {editor && !editingItem && renderEditor(null)}
        {(missingEditorItem ? [missingEditorItem, ...filteredItems] : filteredItems).map((item) => editingItem?.id === item.id ? (
          <React.Fragment key={item.id}>{renderEditor(editingItem)}</React.Fragment>
        ) : (
          <article key={item.id} className="studio-qa-row">
            <details className="qa-catalog-item studio-qa-item">
              <summary className="qa-catalog-summary">
                <div className="studio-question-title"><strong>{item.qa.question}</strong><small>{item.qa.category}</small></div>
                <span className={`qa-lifecycle-badge is-${item.lifecycle_status}`}>{lifecycleLabels[item.lifecycle_status]}</span>
              </summary>
              <div className="qa-catalog-detail">
                <div className="studio-answer-text"><strong>標準回答：</strong>{item.qa.answer || '尚無答案'}</div>
                {item.qa.notes && <div><strong>備註：</strong>{item.qa.notes}</div>}
                <div className="qa-catalog-actions">
                  {(item.lifecycle_status === 'draft' || item.lifecycle_status === 'reviewed') && <button type="button" className="line-primary-btn" disabled={operationPending || !item.qa.answer.trim()} onClick={(event) => askRowPublish(item, event.currentTarget)}>發布</button>}
                  {isPublished(item) && <button type="button" className="line-danger-btn" disabled={operationPending} onClick={() => void retire(item)}>停用</button>}
                  {canDelete(item) && <button type="button" className="line-danger-btn" disabled={operationPending} onClick={(event) => askDelete(item, event.currentTarget)}>永久刪除</button>}
                </div>
              </div>
            </details>
            <button id={`${idPrefix}-edit-${item.id}`} type="button" className="studio-text-button studio-row-edit"
              disabled={operationPending} title="編輯此題目" aria-label={`編輯問答：${item.qa.question}`}
              onClick={() => requestLeave(() => openEditor(item))}><Pencil aria-hidden="true" />編輯</button>
            {renderConfirmation(item.id)}
          </article>
        ))}
        {readStatus === 'ready' && filteredItems.length === 0 && items.length > 0 && <div className="studio-empty" role="status">目前沒有符合條件的問答。</div>}
      </div>
    </div>
  );
};

export default CommonQaCatalogPanel;
