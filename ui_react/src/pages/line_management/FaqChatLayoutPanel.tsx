import { useEffect, useRef, useState, type FormEvent } from 'react';
import { useUnsavedDraft, useUnsavedNavigation } from '../../components/UnsavedChanges';
import {
  FaqRequestError, faqLayoutPath, faqRequest, getFaqLayout, getPublishedFaq,
  type FaqCard, type FaqLayout, type FaqLayoutState, type FaqPreview, type FaqReceipt, type PublishedFaq,
} from './faqLayoutApi';
import './FaqChatLayoutPanel.css';

type Mode = 'draft' | 'published';
type Operation = { path: '/categories' | '/draft' | '/publish'; key: string };
type Command = Operation & { body: string };
const storageKey = () => `line-faq-pending:${window.location.pathname}`;

function readPendingOperation(): Operation | undefined {
  try {
    const raw = window.sessionStorage.getItem(storageKey());
    if (!raw) return undefined;
    const value = JSON.parse(raw) as Partial<Operation> | null;
    if (value && typeof value.key === 'string' && /^[a-f0-9]{32}$/.test(value.key) &&
      (value.path === '/categories' || value.path === '/draft' || value.path === '/publish')) {
      return { key: value.key, path: value.path };
    }
  } catch { /* Storage may be unavailable; writes will report that explicitly. */ }
  return undefined;
}

const emptyLayout: FaqLayout = { categories: [] };
const errorText = (error: unknown) => error instanceof FaqRequestError
  ? [error.message, error.field].filter(Boolean).join(' ')
  : '連線中斷或操作逾時，請再次確認。';

export function FaqChatLayoutPanel() {
  const [state, setState] = useState<FaqLayoutState>();
  const [layout, setLayout] = useState(emptyLayout);
  const [published, setPublished] = useState<PublishedFaq[]>([]);
  const [selected, setSelected] = useState('');
  const [name, setName] = useState('');
  const [adding, setAdding] = useState(false);
  const [busy, setBusy] = useState(false);
  const [loadFailed, setLoadFailed] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [pending, setPending] = useState<Operation | undefined>(readPendingOperation);
  const [remote, setRemote] = useState<FaqLayoutState>();
  const [mode, setMode] = useState<Mode>('draft');
  const [preview, setPreview] = useState<FaqPreview>();
  const [previewError, setPreviewError] = useState('');
  const [previewPage, setPreviewPage] = useState(0);
  const [answer, setAnswer] = useState('');
  const title = useRef<HTMLInputElement>(null);
  const focusTitle = useRef(false);
  const previewRequest = useRef(0);
  const { requestLeave } = useUnsavedNavigation();
  const dirty = Boolean(state && JSON.stringify(layout) !== JSON.stringify(state.draft_layout));
  const card = layout.categories.find((category) => category.category_id === selected);
  const disabled = busy || Boolean(pending) || Boolean(remote);
  const guard = useUnsavedDraft('LINE 聊天室版面', { '分類卡片': layout.categories }, {
    baseline: { '分類卡片': state?.draft_layout.categories ?? [] },
    busy,
  });

  function resetPreview() {
    previewRequest.current += 1;
    setPreview(undefined);
    setPreviewError('');
    setAnswer('');
    setPreviewPage(0);
  }

  function adopt(next: FaqLayoutState, preferred = '') {
    setState(next);
    setLayout(next.draft_layout);
    setSelected(next.draft_layout.categories.some((item) => item.category_id === preferred)
      ? preferred : next.draft_layout.categories[0]?.category_id ?? '');
    setRemote(undefined);
    resetPreview();
  }

  async function load() {
    setLoadFailed(false);
    setError('');
    try {
      const [next, questions] = await Promise.all([getFaqLayout(), getPublishedFaq()]);
      setPublished(questions);
      adopt(next);
    } catch (failure) {
      setLoadFailed(true);
      setError(errorText(failure));
    }
  }

  useEffect(() => { void load(); }, []);
  useEffect(() => {
    if (focusTitle.current && selected && !busy) {
      title.current?.focus();
      focusTitle.current = false;
    }
  }, [selected, busy]);

  async function showCard(categoryId: string, source = mode) {
    const revision = ++previewRequest.current;
    setPreview(undefined);
    setAnswer('');
    setPreviewError('');
    try {
      const body = source === 'draft' ? { mode: source, category_id: categoryId, layout } : { mode: source, category_id: categoryId };
      const result = await faqRequest<FaqPreview>(`${faqLayoutPath}/preview`, { method: 'POST', body: JSON.stringify(body) });
      if (revision === previewRequest.current) setPreview(result);
    } catch (failure) {
      if (revision === previewRequest.current) setPreviewError(errorText(failure));
    }
  }

  function changeMode(next: Mode) {
    resetPreview();
    setMode(next);
    if (next === 'published' && selected && !state?.published_layout?.categories.some(row => row.category_id === selected)) {
      void showCard(selected, next);
    }
  }

  function updateCard(update: Partial<FaqCard>) {
    setLayout((current) => ({ categories: current.categories.map((item) => item.category_id === selected ? { ...item, ...update } : item) }));
    resetPreview();
  }

  function moveQuestion(index: number, offset: number) {
    if (!card) return;
    const questions = [...card.questions];
    const next = index + offset;
    [questions[index], questions[next]] = [questions[next], questions[index]];
    updateCard({ questions });
  }

  function clearPendingOperation() {
    window.sessionStorage.removeItem(storageKey());
    setPending(undefined);
  }

  async function complete(command: Operation, receipt: FaqReceipt, current?: FaqLayoutState) {
    const next = current ?? await getFaqLayout();
    if (receipt.operation_id !== command.key || next.draft_revision < receipt.draft_revision) {
      throw new Error('invalid readback');
    }
    clearPendingOperation();
    if (command.path === '/categories') {
      focusTitle.current = true;
      setAdding(false);
      setName('');
    }
    adopt(next, receipt.category_id ?? selected);
    if (command.path === '/publish') {
      if (receipt.published_revision !== undefined && next.published_revision === receipt.published_revision) {
        setMode('published');
        setNotice('已發布聊天室版面。');
      } else {
        setError('正式版已變更，畫面已讀回目前版本。');
      }
    } else {
      setNotice(command.path === '/categories' ? '已新增分類草稿。' : '已儲存版面草稿。');
    }
  }

  async function readOperation(command: Operation) {
    const headers = { 'Idempotency-Key': command.key };
    const [receipt, current] = await Promise.allSettled([
      faqRequest<FaqReceipt>(`${faqLayoutPath}/operations/${encodeURIComponent(command.key)}`, { headers }),
      getFaqLayout(),
    ]);
    if (receipt.status === 'fulfilled' && current.status === 'fulfilled') {
      await complete(command, receipt.value, current.value);
      return true;
    }
    return false;
  }

  async function checkOperation(operation: Operation) {
    setBusy(true);
    setError('');
    try {
      if (await readOperation(operation)) return;
    } catch { /* Keep the original reference if readback is incomplete. */ }
    finally { setBusy(false); }
    setError('尚無法確認原操作結果。你可離開此頁，稍後再查；系統不會重送。');
  }

  async function submit(command: Command) {
    const operation: Operation = { path: command.path, key: command.key };
    try {
      window.sessionStorage.setItem(storageKey(), JSON.stringify(operation));
    } catch {
      setError('此瀏覽器無法保留操作鍵，尚未送出。請先啟用工作階段儲存。');
      return;
    }
    setPending(operation);
    setBusy(true);
    setError('');
    setNotice('');
    let acknowledged = false;
    try {
      const receipt = await faqRequest<FaqReceipt>(faqLayoutPath + command.path, {
        method: command.path === '/draft' ? 'PUT' : 'POST',
        headers: { 'Idempotency-Key': command.key, 'X-Correlation-ID': command.key },
        body: command.body,
      });
      acknowledged = true;
      await complete(operation, receipt);
    } catch (failure) {
      if (!acknowledged && failure instanceof FaqRequestError && [400, 401, 403, 409, 422].includes(failure.status)) {
        clearPendingOperation();
        setError(errorText(failure));
        if (failure.status === 409) {
          try { setRemote(await getFaqLayout()); } catch { setError(errorText(failure) + ' 新版讀取失敗，請重新確認。'); }
        }
      } else {
        await checkOperation(operation);
      }
    } finally { setBusy(false); }
  }

  function command(path: Command['path'], fields: object = {}) {
    if (!state || disabled) return;
    void submit({ path, key: Array.from(crypto.getRandomValues(new Uint8Array(16)), part => part.toString(16).padStart(2, '0')).join(''), body: JSON.stringify({ ...fields, expected_revision: state.draft_revision }) });
  }

  function addCategory(event: FormEvent) {
    event.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) { setError('請輸入分類名稱。'); return; }
    if (layout.categories.some((item) => item.name.normalize('NFKC').toLowerCase() === trimmed.normalize('NFKC').toLowerCase())) {
      setError('分類名稱重複。'); return;
    }
    requestLeave(() => command('/categories', { name: trimmed }));
  }

  if (!state) return <div className="ai-editor-card" aria-busy={!loadFailed}>
    {loadFailed ? <><p role="alert">{error}</p><button type="button" onClick={() => void load()}>重試</button></> : <p role="status">載入版面與正式題庫中…</p>}
  </div>;

  const previewCards = (mode === 'draft' ? layout : state.published_layout)?.categories ?? [];
  const menuPage = previewCards.slice(previewPage * 6, previewPage * 6 + 6);
  const selectedAnswer = preview?.view.buttons.find((button) => button.qa_id === answer);

  return <div className="faq-layout-workspace" ref={guard}>
    {error && <p role="alert">{error}</p>}
    {notice && <p role="status">{notice}</p>}
    {pending && <button type="button" disabled={busy} onClick={() => void checkOperation(pending)}>查詢原操作結果</button>}
    {remote && <button type="button" disabled={busy} onClick={() => requestLeave(() => adopt(remote, selected))}>載入目前草稿（版本 {remote.draft_revision}）</button>}
    <div className="faq-layout-columns">
      <section className="ai-editor-card" aria-labelledby="faq-layout-categories">
        <h2 id="faq-layout-categories">分類</h2>
        <button type="button" disabled={disabled} onClick={() => setAdding(!adding)}>＋ 新增分類</button>
        {adding && <form onSubmit={addCategory}>
          <label>分類名稱<input autoFocus maxLength={24} value={name} onChange={event => setName(event.target.value)} /></label>
          <button type="submit" disabled={disabled}>建立分類</button>
        </form>}
        {layout.categories.length === 0 && <p>尚無分類。</p>}
        <ul>{layout.categories.map(item => <li key={item.category_id}>
          <button type="button" aria-pressed={selected === item.category_id} onClick={() => { setSelected(item.category_id); resetPreview(); }}>{item.name}</button>
          <small>{item.questions.length} 題{!state.published_layout?.categories.some(row => row.category_id === item.category_id) && ' · 草稿'}</small>
        </li>)}</ul>
      </section>
      <section className="ai-editor-card" aria-labelledby="faq-layout-editor">
        <h2 id="faq-layout-editor">編輯卡片</h2>
        {card && <fieldset disabled={disabled}>
          <label>卡片標題<input ref={title} maxLength={36} value={card.title} onChange={event => updateCard({ title: event.target.value })} /></label>
          <label>說明<textarea maxLength={150} value={card.description} onChange={event => updateCard({ description: event.target.value })} /></label>
          <ol>{card.questions.map((link, index) => <li key={link.qa_id}>
            <p>{published.find(item => item.qa_id === link.qa_id)?.question ?? `題目已停用（${link.qa_id}）`}</p>
            <label>題目 {index + 1} 短標籤<input maxLength={24} value={link.label} onChange={event => updateCard({
              questions: card.questions.map(item => item.qa_id === link.qa_id ? { ...item, label: event.target.value } : item),
            })} /></label>
            <div className="faq-layout-actions">
              <button type="button" disabled={index === 0} onClick={() => moveQuestion(index, -1)}>上移</button>
              <button type="button" disabled={index === card.questions.length - 1} onClick={() => moveQuestion(index, 1)}>下移</button>
              <button type="button" onClick={() => updateCard({ questions: card.questions.filter(item => item.qa_id !== link.qa_id) })}>移除引用</button>
            </div>
          </li>)}</ol>
          {card.questions.length < 4 && <label>加入已發布題目<select value="" onChange={event => {
            if (event.target.value) updateCard({ questions: [...card.questions, { qa_id: event.target.value, label: '' }] });
          }}>
            <option value="">選擇題目</option>
            {published.filter(item => !card.questions.some(link => link.qa_id === item.qa_id)).map(item => <option key={item.qa_id} value={item.qa_id}>{item.question}</option>)}
          </select></label>}
          <div className="faq-layout-actions">
            <button type="button" disabled={!dirty} onClick={() => command('/draft', { layout })}>儲存版面草稿</button>
            <button type="button" disabled={dirty} onClick={() => command('/publish')}>發布聊天室版面</button>
          </div>
          <small>{dirty ? '請先儲存草稿，再發布。' : '發布後，LINE 聊天室會使用新版分類選單與卡片。'}</small>
        </fieldset>}
      </section>
      <section className="ai-editor-card" aria-labelledby="faq-layout-preview">
        <h2 id="faq-layout-preview">手機預覽</h2>
        <div className="faq-layout-actions">
          <button type="button" aria-pressed={mode === 'draft'} onClick={() => changeMode('draft')}>草稿</button>
          <button type="button" aria-pressed={mode === 'published'} onClick={() => changeMode('published')}>已發布</button>
        </div>
        <div className="faq-preview-phone">
          {previewError && <p role="status">{previewError}</p>}
          {selectedAnswer ? <>
            <button type="button" onClick={() => setAnswer('')}>返回卡片</button>
            <h3>{selectedAnswer.question}</h3><p>{selectedAnswer.answer}</p>
          </> : preview ? <>
            <button type="button" onClick={resetPreview}>返回分類選單</button>
            <h3>{preview.view.title}</h3><p>{preview.view.description}</p>
            {preview.issues.map(issue => <p key={issue.field}>題目無法顯示（{issue.qa_id ?? issue.field}）</p>)}
            {preview.view.buttons.map(button => <button type="button" key={button.qa_id} onClick={() => setAnswer(button.qa_id)}>{button.label}</button>)}
          </> : <>
            <h3>分類選單</h3>
            {mode === 'published' && !state.published_layout && !previewError && <p>尚未發布</p>}
            {menuPage.map(item => <button type="button" key={item.category_id} onClick={() => void showCard(item.category_id)}>{item.name}</button>)}
            {previewPage > 0 && <button type="button" onClick={() => setPreviewPage(previewPage - 1)}>上一頁</button>}
            {previewCards.length > (previewPage + 1) * 6 && <button type="button" onClick={() => setPreviewPage(previewPage + 1)}>下一頁</button>}
          </>}
        </div>
      </section>
    </div>
  </div>;
}
