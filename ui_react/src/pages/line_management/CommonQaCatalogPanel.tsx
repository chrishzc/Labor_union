/**
 * Read-only curated common-QA catalog shown inside the AI customer-service studio.
 */
import React, { useEffect, useMemo, useState } from 'react';

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

  useEffect(() => {
    let active = true;
    fetch('/api/v1/line/ai-events/qa-catalog')
      .then((response) => response.ok ? response.json() : Promise.reject(new Error('qa_catalog_readback_failed')))
      .then((payload: { data?: QaCatalog }) => {
        if (!active || !payload.data) return;
        setCatalog(payload.data);
        setNotice(null);
      })
      .catch(() => {
        if (active) setNotice('常見 QA 題庫讀取失敗；本頁不以硬編碼資料替代。');
      });
    return () => { active = false; };
  }, []);

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
    <div className="ai-editor-card" style={{ marginBottom: '16px' }}>
      <div className="ai-editor-header">
        <h4>📚 常見 QA 題庫</h4>
        {catalog && (
          <span className="category-badge">
            共 {catalog.total_count} 筆 · {catalog.enabled_count} 筆已啟用
          </span>
        )}
      </div>
      <div className="line-warning" role="status">
        這裡是固定回答題庫，不是事件規則。LLM 可用它做語意比對；只有 enabled=true 的項目可進自動回答鏈。
      </div>
      {notice && <div className="line-warning" role="status">{notice}</div>}
      {catalog && (
        <>
          <div className="form-group-row" style={{ marginTop: '12px' }}>
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
          <div style={{ maxHeight: '420px', overflowY: 'auto', marginTop: '10px' }}>
            {filteredItems.map((item) => (
              <details key={item.id} className="ai-rule-item-card" style={{ marginBottom: '8px' }}>
                <summary style={{ cursor: 'pointer' }}>
                  <strong>{item.id} · {item.question}</strong>
                  <span className="category-badge" style={{ marginLeft: '8px' }}>
                    {item.category} / {item.tag} · {item.enabled ? '啟用' : '未啟用'}
                  </span>
                </summary>
                <div style={{ marginTop: '10px' }}>
                  <div><strong>常見問法：</strong>{item.aliases.length > 0 ? item.aliases.join('、') : '—'}</div>
                  <div style={{ marginTop: '6px' }}>
                    <strong>固定答案：</strong>{item.answer || '尚無答案'}
                  </div>
                  {item.notes && <div style={{ marginTop: '6px' }}><strong>備註：</strong>{item.notes}</div>}
                  <small>原始來源：{item.source_ref}</small>
                </div>
              </details>
            ))}
            {filteredItems.length === 0 && (
              <div className="line-warning" role="status">沒有符合目前條件的 QA。</div>
            )}
          </div>
        </>
      )}
    </div>
  );
};

export default CommonQaCatalogPanel;
