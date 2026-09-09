/**
 * Read-only curated common-QA catalog shown inside the AI customer-service studio.
 */
import React, { useEffect, useMemo, useState } from 'react';
import { Pencil, Plus, Trash2 } from 'lucide-react';
import { sessionClient } from '../../api/auth/session_client';
import { Drawer } from '../../components/Drawer';

interface QaCatalogItem {
  id: string;
  category: string;
  tag: string;
  question: string;
  aliases: string[];
  answer: string;
  enabled: boolean;
  source_ref: string;
  notes: string | null;
}

interface QaCatalog {
  source_identity: string;
  total_count: number;
  enabled_count: number;
  items: QaCatalogItem[];
}

export const CommonQaCatalogPanel: React.FC = () => {
  const [catalog, setCatalog] = useState<QaCatalog | null>(null);
  const [query, setQuery] = useState('');
  const [enabledFilter, setEnabledFilter] = useState('ALL');
  const [notice, setNotice] = useState<string | null>(null);
  const [editingItem, setEditingItem] = useState<QaCatalogItem | null>(null);
  const [isCreating, setIsCreating] = useState(false);
  const [modalNotice, setModalNotice] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [formData, setFormData] = useState({
    question: '',
    answer: '',
    category: '月嫂媒合',
    tag: '常見問題',
    aliases: '',
    enabled: true,
    notes: '',
  });

  const loadCatalog = async () => {
    const token = sessionClient.getToken();
    const headers: Record<string, string> = {};
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }
    try {
      const response = await fetch('/api/v1/line/ai-events/qa-catalog', {
        headers,
        credentials: 'include',
      });
      if (!response.ok) throw new Error('qa_catalog_readback_failed');
      const payload = await response.json() as { data?: QaCatalog };
      if (payload.data) {
        setCatalog(payload.data);
        setNotice(null);
      }
    } catch {
      setNotice('常見 QA 題庫讀取失敗；本頁不以硬編碼資料替代。');
    }
  };

  useEffect(() => {
    loadCatalog();
  }, []);

  const openCreateModal = () => {
    setFormData({
      question: '',
      answer: '',
      category: '月嫂媒合',
      tag: '常見問題',
      aliases: '',
      enabled: true,
      notes: '',
    });
    setModalNotice(null);
    setIsSaving(false);
    setIsCreating(true);
    setEditingItem(null);
  };

  const openEditModal = (item: QaCatalogItem) => {
    setFormData({
      question: item.question,
      answer: item.answer || '',
      category: item.category || '月嫂媒合',
      tag: item.tag || '常見問題',
      aliases: item.aliases ? item.aliases.join('\n') : '',
      enabled: item.enabled,
      notes: item.notes || '',
    });
    setModalNotice(null);
    setIsSaving(false);
    setEditingItem(item);
    setIsCreating(false);
  };

  const closeModal = () => {
    setEditingItem(null);
    setIsCreating(false);
    setModalNotice(null);
    setIsSaving(false);
  };

  const handleToggleStatus = async (item: QaCatalogItem) => {
    const token = sessionClient.getToken();
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    if (token) headers['Authorization'] = `Bearer ${token}`;

    try {
      const response = await fetch(`/api/v1/line/ai-events/qa-catalog/${item.id}/status`, {
        method: 'PATCH',
        headers,
        credentials: 'include',
        body: JSON.stringify({ enabled: !item.enabled }),
      });
      if (!response.ok) throw new Error('toggle_failed');
      await loadCatalog();
      setNotice(`已${!item.enabled ? '啟用' : '停用'}題目：${item.id}`);
    } catch {
      setNotice(`切換題目 ${item.id} 啟用狀態失敗。`);
    }
  };

  const handleDeleteItem = async (item: QaCatalogItem) => {
    if (!window.confirm(`確定要移除題目【${item.id} · ${item.question}】嗎？此操作將自題庫中刪除。`)) {
      return;
    }
    const token = sessionClient.getToken();
    const headers: Record<string, string> = {};
    if (token) headers['Authorization'] = `Bearer ${token}`;

    try {
      const response = await fetch(`/api/v1/line/ai-events/qa-catalog/${item.id}`, {
        method: 'DELETE',
        headers,
        credentials: 'include',
      });
      if (!response.ok) throw new Error('delete_failed');
      await loadCatalog();
      setNotice(`已成功移除題目：${item.id}`);
    } catch {
      setNotice(`移除題目 ${item.id} 失敗。`);
    }
  };

  const executeSave = async (event?: React.SyntheticEvent) => {
    if (event) {
      event.preventDefault();
      event.stopPropagation();
    }

    const question = formData.question.trim();
    if (!question) {
      setModalNotice('請輸入標準問題（Question）！');
      return;
    }

    setIsSaving(true);
    setModalNotice(null);

    const token = sessionClient.getToken();
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    if (token) headers['Authorization'] = `Bearer ${token}`;

    const aliases = formData.aliases
      .split('\n')
      .map((line) => line.trim())
      .filter(Boolean);

    const body = {
      question,
      answer: formData.answer.trim(),
      category: formData.category.trim() || '月嫂媒合',
      tag: formData.tag.trim() || '常見問題',
      aliases,
      enabled: formData.enabled,
      notes: formData.notes.trim() || null,
    };

    try {
      if (isCreating) {
        const response = await fetch('/api/v1/line/ai-events/qa-catalog', {
          method: 'POST',
          headers,
          credentials: 'include',
          body: JSON.stringify(body),
        });
        if (!response.ok) {
          const errData = await response.json().catch(() => ({}));
          const msg = (errData as { detail?: { error?: { message?: string } } | string })?.detail;
          const text = typeof msg === 'object' ? msg?.error?.message : msg;
          throw new Error(text || '新增失敗');
        }
        setNotice('已成功新增 QA 題目。');
      } else if (editingItem) {
        const response = await fetch(`/api/v1/line/ai-events/qa-catalog/${editingItem.id}`, {
          method: 'PUT',
          headers,
          credentials: 'include',
          body: JSON.stringify(body),
        });
        if (!response.ok) {
          const errData = await response.json().catch(() => ({}));
          const msg = (errData as { detail?: { error?: { message?: string } } | string })?.detail;
          const text = typeof msg === 'object' ? msg?.error?.message : msg;
          throw new Error(text || '更新失敗');
        }
        setNotice(`已成功儲存題目：${editingItem.id}`);
      }
      closeModal();
      await loadCatalog();
    } catch (err: unknown) {
      const errMsg = err instanceof Error ? err.message : '儲存變更失敗';
      setModalNotice(errMsg);
    } finally {
      setIsSaving(false);
    }
  };

  const filteredItems = useMemo(() => {
    if (!catalog) return [];
    const normalized = query.trim().toLocaleLowerCase('zh-TW');
    return catalog.items.filter((item) => {
      const enabledMatches = enabledFilter === 'ALL'
        || (enabledFilter === 'ENABLED' && item.enabled)
        || (enabledFilter === 'DISABLED' && !item.enabled);
      const textMatches = !normalized || [
        item.id,
        item.category,
        item.tag,
        item.question,
        item.answer,
        ...item.aliases,
      ].some((value) => value.toLocaleLowerCase('zh-TW').includes(normalized));
      return enabledMatches && textMatches;
    });
  }, [catalog, query, enabledFilter]);

  return (
    <div className="ai-editor-card qa-catalog-panel">
      <div className="ai-editor-header qa-catalog-header">
        <div className="qa-catalog-title">
          <h2>常見 QA 題庫</h2>
          {catalog && (
            <span className="category-badge">
              共 {catalog.total_count} 筆 · {catalog.enabled_count} 筆已啟用
            </span>
          )}
        </div>
        <button
          type="button"
          className="line-primary-btn"
          onClick={openCreateModal}
        >
          <Plus aria-hidden="true" />新增 QA
        </button>
      </div>

      <div className="line-warning" role="status">
        這裡是固定回答題庫，不是事件規則。LLM 可用它做語意比對；只有 enabled=true 的項目可進自動回答鏈。支援編輯標準回答、同義問法、快速啟用與移除。
      </div>

      {notice && <div className="line-warning" role="status">{notice}</div>}

      {catalog && (
        <>
          <div className="form-group-row qa-catalog-filters">
            <div className="form-field-half">
              <label htmlFor="qa-catalog-search">搜尋常見 QA</label>
              <input
                id="qa-catalog-search"
                type="search"
                value={query}
                placeholder="題號、分類、標籤、問題或別名"
                onChange={(event) => setQuery(event.target.value)}
              />
            </div>
            <div className="form-field-half">
              <label htmlFor="qa-catalog-status">啟用狀態</label>
              <select
                id="qa-catalog-status"
                value={enabledFilter}
                onChange={(event) => setEnabledFilter(event.target.value)}
              >
                <option value="ALL">全部</option>
                <option value="ENABLED">啟用</option>
                <option value="DISABLED">未啟用</option>
              </select>
            </div>
          </div>
          <small>
            顯示 {filteredItems.length}／{catalog.total_count} 筆 · 來源 {catalog.source_identity}
          </small>

          <div className="qa-catalog-list">
            {filteredItems.map((item) => (
              <details key={item.id} className="ai-rule-item-card qa-catalog-item">
                <summary className="qa-catalog-summary">
                  <div>
                    <strong>{item.id} · {item.question}</strong>
                    <span className="category-badge qa-catalog-category">
                      {item.category} / {item.tag}
                    </span>
                  </div>
                  <div className="qa-catalog-actions">
                    <button
                      type="button"
                      className={`qa-status-toggle ${item.enabled ? 'active' : ''}`}
                      title="點擊切換啟用/停用"
                      onClick={(e) => { e.preventDefault(); e.stopPropagation(); handleToggleStatus(item); }}
                    >
                      {item.enabled ? '啟用中' : '停用中'}
                    </button>
                    <button
                      type="button"
                      className="line-secondary-btn"
                      title="編輯此題目"
                      onClick={(e) => { e.preventDefault(); e.stopPropagation(); openEditModal(item); }}
                    >
                      <Pencil aria-hidden="true" />編輯
                    </button>
                    <button
                      type="button"
                      className="line-danger-btn"
                      title="移除此題目"
                      onClick={(e) => { e.preventDefault(); e.stopPropagation(); handleDeleteItem(item); }}
                    >
                      <Trash2 aria-hidden="true" />移除
                    </button>
                  </div>
                </summary>
                <div className="qa-catalog-detail">
                  <div><strong>常見問法：</strong>{item.aliases.length > 0 ? item.aliases.join('、') : '—'}</div>
                  <div>
                    <strong>固定答案：</strong>{item.answer || '尚無答案'}
                  </div>
                  {item.notes && <div><strong>備註：</strong>{item.notes}</div>}
                  <details className="qa-catalog-technical"><summary>技術資訊</summary><small>來源：{item.source_ref}</small></details>
                </div>
              </details>
            ))}
            {filteredItems.length === 0 && (
              <div className="line-warning" role="status">沒有符合目前條件的 QA。</div>
            )}
          </div>
        </>
      )}

      <Drawer
        isOpen={isCreating || editingItem !== null}
        onClose={closeModal}
        title={isCreating ? '新增 QA' : `編輯 QA（${editingItem?.id}）`}
        size="wide"
        closeDisabled={isSaving}
        closeLabel="關閉 QA 編輯器"
        footer={(
          <div className="line-drawer-footer">
            <button type="button" disabled={isSaving} className="line-secondary-btn" onClick={closeModal}>取消</button>
            <button type="button" disabled={isSaving} className="line-primary-btn" onClick={executeSave}>
              {isSaving ? '儲存中…' : (isCreating ? '新增 QA' : '儲存變更')}
            </button>
          </div>
        )}
      >
        <form className="qa-editor-form" onSubmit={executeSave} noValidate>
          {modalNotice && <div className="line-error" role="alert">{modalNotice}</div>}

          <label className="qa-editor-field">
            <span>標準問題 <span aria-hidden="true">*</span></span>
            <input required type="text" value={formData.question} placeholder="例如：如果和月嫂合作不適合，可以更換月嫂嗎？" onChange={(e) => setFormData({ ...formData, question: e.target.value })} />
          </label>
          <label className="qa-editor-field">
            <span>標準回答</span>
            <textarea rows={5} value={formData.answer} placeholder="請輸入核准的標準答案內容（可暫留空待審核）…" onChange={(e) => setFormData({ ...formData, answer: e.target.value })} />
          </label>
          <label className="qa-editor-field">
            <span>常見問法／別名（每行一筆）</span>
            <textarea rows={4} value={formData.aliases} placeholder={'可以換月嫂嗎？\n跟月嫂觀念不合可以換人嗎？'} onChange={(e) => setFormData({ ...formData, aliases: e.target.value })} />
            <small>多個問句請換行輸入，供語意比對與關鍵字命中。</small>
          </label>
          <div className="qa-editor-columns">
            <label className="qa-editor-field"><span>業務分類</span><input type="text" value={formData.category} placeholder="例如：月嫂媒合、合約、費用" onChange={(e) => setFormData({ ...formData, category: e.target.value })} /></label>
            <label className="qa-editor-field"><span>標籤</span><input type="text" value={formData.tag} placeholder="例如：更換月嫂、試用期" onChange={(e) => setFormData({ ...formData, tag: e.target.value })} /></label>
          </div>
          <label className="qa-editor-field"><span>內部備註（選填）</span><input type="text" value={formData.notes} placeholder="補充說明或審核紀錄" onChange={(e) => setFormData({ ...formData, notes: e.target.value })} /></label>
          <label className="checkbox-item qa-editor-enabled">
            <input type="checkbox" checked={formData.enabled} onChange={(e) => setFormData({ ...formData, enabled: e.target.checked })} />
            <span>立即啟用此題目，允許進入自動回答鏈</span>
          </label>
        </form>
      </Drawer>
    </div>
  );
};

export default CommonQaCatalogPanel;
