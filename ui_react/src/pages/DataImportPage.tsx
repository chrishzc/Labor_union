import React, { useRef, useState } from 'react';
import './DataImportPage.css';
import { requestPreview, requestApply, type PreviewResult } from '../api/client';

interface ImportCategory {
  id: string;
  title: string;
  subtitle: string;
  icon: string;
  statusText: string;
  statusType: 'ready' | 'pending';
  fileInfo: string;
}

const CATEGORIES: ImportCategory[] = [
  {
    id: 'hcm',
    title: 'HCM 案件資料',
    subtitle: 'HCM 案件日常與歷史 Workbook 匯入',
    icon: '📁',
    statusText: '可供上傳預覽',
    statusType: 'ready',
    fileInfo: '支援 .xlsx / .xls 格式',
  },
  {
    id: 'client-beclass',
    title: 'Client BeClass 資料',
    subtitle: 'BeClass 客戶登記過渡匯入 (LIFF 穩定後退役)',
    icon: '👥',
    statusText: '過渡入口',
    statusType: 'pending',
    fileInfo: '支援 .xlsx / .csv 格式',
  },
  {
    id: 'staff-beclass',
    title: 'Staff BeClass 資料',
    subtitle: 'BeClass 月嫂履歷過渡匯入 (LIFF 穩定後退役)',
    icon: '👩‍⚕️',
    statusText: '過渡入口',
    statusType: 'pending',
    fileInfo: '支援 .xlsx / .csv 格式',
  },
  {
    id: 'historical-orders',
    title: '訂單狀態與月嫂歷史配對',
    subtitle: '歷史訂單狀態、配對 Evidence 與實際服務日期 (WP85)',
    icon: '📜',
    statusText: '可供上傳預覽',
    statusType: 'ready',
    fileInfo: '支援 .xlsx 格式',
  },
  {
    id: 'bank-statements',
    title: '銀行流水與歷史帳務',
    subtitle: '台新 / 永豐銀行流水與歷史帳務轉帳記錄',
    icon: '🏦',
    statusText: '可供上傳預覽',
    statusType: 'ready',
    fileInfo: '支援 .xlsx / .csv 格式',
  },
];

export const DataImportPage: React.FC = () => {
  const [activeCategoryId, setActiveCategoryId] = useState<string | null>(null);
  const [previewData, setPreviewData] = useState<Record<string, PreviewResult>>({});
  const [loadingCategory, setLoadingCategory] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleSelectFile = (categoryId: string) => {
    setActiveCategoryId(categoryId);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
      fileInputRef.current.click();
    }
  };

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !activeCategoryId) return;

    setLoadingCategory(activeCategoryId);
    setMessage(`[Preview 進行中] 正在發送 ${file.name} 至零寫入驗證器...`);

    const response = await requestPreview(activeCategoryId, file);
    setLoadingCategory(null);

    if (response.success && response.data) {
      setPreviewData((prev) => ({ ...prev, [activeCategoryId]: response.data! }));
      setMessage(`✅ ${file.name} Preview 完成！可接受筆數: ${response.data.acceptedRows}，需審核: ${response.data.reviewRows}`);
    } else {
      setMessage(`❌ Preview 失敗：${response.error}`);
    }
  };

  const handleApply = async (categoryId: string) => {
    const pData = previewData[categoryId];
    if (!pData || !pData.previewSummary) {
      alert('請先點選 Preview 並完成驗證後才能 Apply！');
      return;
    }

    setLoadingCategory(categoryId);
    setMessage(`[Apply 進行中] 發送指令中...`);

    const response = await requestApply(categoryId, pData.previewSummary);
    setLoadingCategory(null);

    if (response.success && response.data) {
      setMessage(`🎉 Apply 成功！狀態: ${response.data.status}，已寫入筆數: ${response.data.appliedCount}`);
    } else {
      setMessage(`❌ Apply 失敗：${response.error}`);
    }
  };

  return (
    <div className="import-center-container">
      {/* 隱藏的檔案選擇器 */}
      <input
        ref={fileInputRef}
        className="file-input"
        type="file"
        accept=".xlsx,.xls,.csv"
        onChange={handleFileChange}
      />

      {/* 左側導航 */}
      <aside className="sidebar">
        <div className="brand-title">🏛️ Lobar Union</div>
        <ul className="nav-list">
          <li><a href="#orders" className="nav-link">📦 訂單管理</a></li>
          <li><a href="#data-import" className="nav-link active">📥 資料匯入中心</a></li>
          <li><a href="#scheduling" className="nav-link">📅 多月嫂排班</a></li>
          <li><a href="#finance" className="nav-link">💰 帳務作業中心</a></li>
          <li><a href="#anomalies" className="nav-link">⚠️ 異常警示中心</a></li>
        </ul>
      </aside>

      {/* 主內容區 */}
      <main className="main-wrapper">
        <header className="page-header">
          <div>
            <h1 className="page-title">資料匯入中心</h1>
            <p className="page-subtitle">單一入口以獨立 Typed Category Cards 進行 Preview (零寫入) 與 Apply (Fresh-Validate)。</p>
          </div>
        </header>

        {message && (
          <div style={{
            padding: '12px 16px',
            borderRadius: '8px',
            backgroundColor: '#e0f2fe',
            color: '#0369a1',
            marginBottom: '24px',
            fontWeight: 500
          }}>
            {message}
          </div>
        )}

        <div className="cards-grid">
          {CATEGORIES.map((cat) => {
            const pData = previewData[cat.id];
            const isLoading = loadingCategory === cat.id;

            return (
              <div className="category-card" key={cat.id}>
                <div>
                  <div className="card-top">
                    <div className="card-icon">{cat.icon}</div>
                    <span className={`badge ${cat.statusType}`}>{cat.statusText}</span>
                  </div>

                  <h2 className="card-title">{cat.title}</h2>
                  <p className="card-desc">{cat.subtitle}</p>

                  {pData && (
                    <div style={{
                      backgroundColor: '#f1f5f9',
                      padding: '8px 12px',
                      borderRadius: '6px',
                      fontSize: '0.85rem',
                      marginBottom: '12px'
                    }}>
                      <div>總筆數: {pData.totalRows} | 通過: {pData.acceptedRows}</div>
                      <div>待審核: {pData.reviewRows} | 衝突: {pData.conflictRows}</div>
                    </div>
                  )}

                  <div className="card-meta">
                    📌 {cat.fileInfo}
                  </div>
                </div>

                <div className="card-actions">
                  <button
                    className="btn btn-outline"
                    disabled={isLoading}
                    onClick={() => handleSelectFile(cat.id)}
                  >
                    {isLoading ? '處理中...' : 'Preview (預覽)'}
                  </button>
                  <button
                    className="btn btn-primary"
                    disabled={isLoading || !pData}
                    onClick={() => handleApply(cat.id)}
                  >
                    Apply (寫入)
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      </main>
    </div>
  );
};

export default DataImportPage;
