import { useEffect, useId, useRef, useState, type FormEvent } from 'react';
import { ChevronDown, ChevronRight, FolderTree, LayoutTemplate, Smartphone } from 'lucide-react';
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

type EditorSelection = {
  categoryId: FaqCard['category_id'];
  qaId?: FaqCard['questions'][number]['qa_id'] | null;
  outlineOpen: boolean;
};
const emptyLayout: FaqLayout = { categories: [] };
const errorText = (error: unknown) => error instanceof FaqRequestError
  ? [error.message, error.field].filter(Boolean).join(' ')
  : '連線中斷或操作逾時，請再次確認。';

export function FaqChatLayoutPanel() {
  const [state, setState] = useState<FaqLayoutState>();
  const [layout, setLayout] = useState(emptyLayout);
  const [published, setPublished] = useState<PublishedFaq[]>([]);
  const [selection, setSelection] = useState<EditorSelection>({ categoryId: '', outlineOpen: true });
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
  const questionLabel = useRef<HTMLInputElement>(null);
  const questionPicker = useRef<HTMLSelectElement>(null);
  const focusQuestion = useRef(false);
  const outlineId = useId();
  const previewRequest = useRef(0);
  const { requestLeave } = useUnsavedNavigation();
  const dirty = Boolean(state && JSON.stringify(layout) !== JSON.stringify(state.draft_layout));
  const { categoryId: selected, qaId, outlineOpen } = selection;
  const card = layout.categories.find((category) => category.category_id === selected);
  const openQuestion = qaId === null || card?.questions.some(link => link.qa_id === qaId)
    ? qaId : card?.questions[0]?.qa_id;
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
    const nextCard = next.draft_layout.categories.find(item => item.category_id === preferred) ?? next.draft_layout.categories[0];
    const categoryId = nextCard?.category_id ?? '';
    setSelection(current => current.categoryId === categoryId ? current : { categoryId, outlineOpen: true });
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
  useEffect(() => {
    if (focusQuestion.current && !disabled) {
      (questionLabel.current ?? questionPicker.current)?.focus();
      focusQuestion.current = false;
    }
  }, [selection, card?.questions, disabled]);

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

  function questionText(questionId: PublishedFaq['qa_id']) {
    return published.find(item => item.qa_id === questionId)?.question ?? `題目已停用（${questionId}）`;
  }

  function selectQuestion(questionId: EditorSelection['qaId'], focusLabel = false) {
    focusQuestion.current = focusLabel;
    setSelection(current => ({ ...current, qaId: questionId }));
  }

  function moveQuestion(index: number, offset: number) {
    if (!card) return;
    const questions = [...card.questions];
    const next = index + offset;
    [questions[index], questions[next]] = [questions[next], questions[index]];
    selectQuestion(openQuestion, !questions[next + offset]);
    updateCard({ questions });
  }

  function removeQuestion(index: number) {
    if (!card) return;
    const questions = card.questions.filter((_, position) => position !== index);
    selectQuestion((questions[index] ?? questions[index - 1])?.qa_id, true);
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
    {loadFailed ? <><p className="line-error" role="alert">{error}</p><button className="line-primary-btn" type="button" onClick={() => void load()}>重試</button></> : <p className="line-card-description" role="status">載入版面與正式題庫中…</p>}
  </div>;

  const previewCards = (mode === 'draft' ? layout : state.published_layout)?.categories ?? [];
  const menuPage = previewCards.slice(previewPage * 6, previewPage * 6 + 6);
  const selectedAnswer = preview?.view.buttons.find((button) => button.qa_id === answer);

  return <div className="faq-layout-workspace" ref={guard}>
    {error && <p className="line-error" role="alert">{error}</p>}
    {notice && <p className="line-success" role="status">{notice}</p>}
    {pending && <button type="button" className="line-secondary-btn" disabled={busy} onClick={() => void checkOperation(pending)}>查詢原操作結果</button>}
    {remote && <button type="button" className="line-secondary-btn" disabled={busy} onClick={() => requestLeave(() => adopt(remote, selected))}>載入目前草稿（版本 {remote.draft_revision}）</button>}
    <div className="faq-layout-columns">
      <section className="ai-editor-card" aria-labelledby="faq-layout-categories">
        <h2 className="line-card-title line-heading-with-icon" id="faq-layout-categories"><FolderTree aria-hidden="true" />分類</h2>
        <button type="button" className="line-secondary-btn line-full-width" disabled={disabled} onClick={() => setAdding(!adding)}>＋ 新增分類</button>
        {adding && <form className="faq-layout-add-form" onSubmit={addCategory}>
          <label className="qa-editor-field">分類名稱<input autoFocus maxLength={24} value={name} onChange={event => setName(event.target.value)} /></label>
          <button type="submit" className="line-primary-btn" disabled={disabled}>建立分類</button>
        </form>}
        {layout.categories.length === 0 && <p className="faq-layout-hint">尚無分類。</p>}
        <ul className="faq-layout-category-list">{layout.categories.map((item, index) => {
          const active = selected === item.category_id;
          const expanded = active && outlineOpen;
          const groupId = `${outlineId}-category-${index}`;
          return <li key={item.category_id}>
            <button type="button" className="faq-layout-category-button" aria-pressed={active} aria-expanded={expanded} aria-controls={groupId}
              aria-labelledby={`${groupId}-name`} aria-describedby={`${groupId}-status`} onClick={() => {
                if (active) {
                  setSelection(current => ({ ...current, outlineOpen: !current.outlineOpen }));
                } else {
                  setSelection({ categoryId: item.category_id, outlineOpen: true });
                  resetPreview();
                }
              }}>
              <span>
                <span id={`${groupId}-name`}>{item.name}</span>
                <small id={`${groupId}-status`}>{item.questions.length} 題{!state.published_layout?.categories.some(row => row.category_id === item.category_id) && ' · 草稿'}</small>
              </span>
              <ChevronDown size={16} aria-hidden="true" />
            </button>
            <ol id={groupId} hidden={!expanded} className="faq-layout-category-questions">
              {item.questions.map((link, questionIndex) => <li key={link.qa_id}>
                <button type="button" className="faq-layout-question-shortcut" aria-current={active && openQuestion === link.qa_id ? 'step' : undefined}
                  aria-controls={active ? `${outlineId}-question-${questionIndex}` : undefined} disabled={disabled} onClick={() => selectQuestion(link.qa_id, true)}>
                  <span className="faq-layout-question-number" aria-hidden="true">{questionIndex + 1}</span>
                  <span>{questionText(link.qa_id)}</span>
                  <ChevronRight size={13} aria-hidden="true" />
                </button>
              </li>)}
            </ol>
          </li>;
        })}</ul>
      </section>
      <section className="ai-editor-card" aria-labelledby="faq-layout-editor">
        <h2 className="line-card-title line-heading-with-icon" id="faq-layout-editor"><LayoutTemplate aria-hidden="true" />編輯卡片</h2>
        {!card && <p className="faq-layout-hint">新增或選擇分類後，即可編輯卡片。</p>}
        {card && <fieldset className="line-fieldset-reset faq-layout-editor" disabled={disabled}>
          <label className="qa-editor-field">卡片標題<input ref={title} maxLength={36} value={card.title} onChange={event => updateCard({ title: event.target.value })} /></label>
          <label className="qa-editor-field">說明<textarea rows={3} maxLength={150} value={card.description} onChange={event => updateCard({ description: event.target.value })} /></label>
          <ol className="faq-layout-question-list">{card.questions.map((link, index) => {
            const expanded = openQuestion === link.qa_id;
            const questionId = `${outlineId}-question-${index}`;
            return <li key={link.qa_id}>
              <button type="button" className="faq-layout-question-toggle" aria-expanded={expanded} aria-controls={questionId}
                onClick={() => selectQuestion(expanded ? null : link.qa_id)}>
                <span className="faq-layout-question-number" aria-hidden="true">{index + 1}</span>
                <span>{questionText(link.qa_id)}</span>
                <ChevronDown size={16} aria-hidden="true" />
              </button>
              <div id={questionId} hidden={!expanded} className="faq-layout-question-fields">
                {expanded && <>
                  <label className="qa-editor-field">題目 {index + 1} 短標籤<input ref={questionLabel} maxLength={24} value={link.label} onChange={event => updateCard({
                    questions: card.questions.map(item => item.qa_id === link.qa_id ? { ...item, label: event.target.value } : item),
                  })} /></label>
                  <div className="faq-layout-actions">
                    <button type="button" className="line-secondary-btn" disabled={index === 0} onClick={() => moveQuestion(index, -1)}>上移</button>
                    <button type="button" className="line-secondary-btn" disabled={index === card.questions.length - 1} onClick={() => moveQuestion(index, 1)}>下移</button>
                    <button type="button" className="line-danger-btn" onClick={() => removeQuestion(index)}>移除引用</button>
                  </div>
                </>}
              </div>
            </li>;
          })}</ol>
          {card.questions.length < 4 && <label className="qa-editor-field">加入已發布題目<select ref={questionPicker} value="" onChange={event => {
            const questionId = event.target.value;
            if (!questionId) return;
            selectQuestion(questionId, true);
            updateCard({ questions: [...card.questions, { qa_id: questionId, label: '' }] });
          }}>
            <option value="">選擇題目</option>
            {published.filter(item => !card.questions.some(link => link.qa_id === item.qa_id)).map(item => <option key={item.qa_id} value={item.qa_id}>{item.question}</option>)}
          </select></label>}
          <div className="faq-layout-editor-footer">
            <div className="faq-layout-actions">
              <button type="button" className="line-secondary-btn" disabled={!dirty} onClick={() => command('/draft', { layout })}>儲存版面草稿</button>
              <button type="button" className="line-primary-btn" disabled={dirty} onClick={() => command('/publish')}>發布聊天室版面</button>
            </div>
            <small className="faq-layout-hint">{dirty ? '請先儲存草稿，再發布。' : '發布後，LINE 聊天室會使用新版分類選單與卡片。'}</small>
          </div>
        </fieldset>}
      </section>
      <section className="ai-editor-card" aria-labelledby="faq-layout-preview">
        <h2 className="line-card-title line-heading-with-icon" id="faq-layout-preview"><Smartphone aria-hidden="true" />手機預覽</h2>
        <div className="faq-preview-modes" role="group" aria-label="預覽版本">
          <button type="button" aria-pressed={mode === 'draft'} onClick={() => changeMode('draft')}>草稿</button>
          <button type="button" aria-pressed={mode === 'published'} onClick={() => changeMode('published')}>已發布</button>
        </div>
        <div className="faq-preview-phone">
          {previewError && <p className="line-warning" role="status">{previewError}</p>}
          {selectedAnswer ? <>
            <button type="button" className="faq-preview-navigation line-secondary-btn" onClick={() => setAnswer('')}>返回卡片</button>
            <div className="faq-preview-message">
              <p>{selectedAnswer.answer}</p>
            </div>
          </> : preview ? <>
            <button type="button" className="faq-preview-navigation line-secondary-btn" onClick={resetPreview}>返回分類選單</button>
            <div className="faq-preview-message">
              <h3>{preview.view.title}</h3><p>{preview.view.description}</p>
              {preview.issues.map(issue => <p className="line-warning" key={issue.field}>題目無法顯示（{issue.qa_id ?? issue.field}）</p>)}
              {preview.view.buttons.map(button => <button type="button" className="line-secondary-btn" key={button.qa_id} onClick={() => setAnswer(button.qa_id)}>{button.label}</button>)}
            </div>
          </> : <>
            <div className="faq-preview-message">
              <h3>分類選單</h3>
              {mode === 'published' && !state.published_layout && !previewError && <p className="faq-layout-hint">尚未發布</p>}
              {menuPage.map(item => <button type="button" className="line-secondary-btn" key={item.category_id} onClick={() => void showCard(item.category_id)}>{item.name}</button>)}
              <div className="faq-layout-actions">
                {previewPage > 0 && <button type="button" className="line-secondary-btn" onClick={() => setPreviewPage(previewPage - 1)}>上一頁</button>}
                {previewCards.length > (previewPage + 1) * 6 && <button type="button" className="line-secondary-btn" onClick={() => setPreviewPage(previewPage + 1)}>下一頁</button>}
              </div>
            </div>
          </>}
        </div>
      </section>
    </div>
  </div>;
}
