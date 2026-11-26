/**
 * File: LineFaqStudioPage.tsx
 * Description: LINE 常見問答，維護正式題庫與聊天室版面。
 */
import { ManagementPageHeader } from '../../components/ManagementPageHeader';
import React, { useState } from 'react';
import { useUnsavedNavigation } from '../../components/UnsavedChanges';
import { BookOpenText } from 'lucide-react';
import { FaqChatLayoutPanel } from './FaqChatLayoutPanel';
import { CommonQaCatalogPanel } from './CommonQaCatalogPanel';

type StudioTab = 'qa' | 'layout';

export const LineFaqStudioPage: React.FC = () => {
  const { requestLeave } = useUnsavedNavigation();
  const [activeTab, setActiveTab] = useState<StudioTab>('qa');

  return (
    <section className="line-hub-page ai-customer-service-page" aria-labelledby="ai-studio-title">
      <ManagementPageHeader titleId="ai-studio-title" title={<><span className="line-hub-page-icon" aria-hidden="true"><BookOpenText /></span>LINE 常見問答</>} description="維護題目、答案與 LINE 聊天室的分類卡片。">
        <span className="line-hub-eyebrow">LINE 專區</span>
      </ManagementPageHeader>

      <nav className="line-hub-section-tabs" aria-label="LINE 常見問答功能">
        <button type="button" className={activeTab === 'qa' ? 'active' : ''} aria-current={activeTab === 'qa' ? 'page' : undefined} onClick={() => requestLeave(() => setActiveTab('qa'))}>
          <BookOpenText aria-hidden="true" />常見問答題庫
        </button>
        <button type="button" className={activeTab === 'layout' ? 'active' : ''} aria-current={activeTab === 'layout' ? 'page' : undefined} onClick={() => { if (activeTab !== 'layout') requestLeave(() => setActiveTab('layout')); }}>
          <BookOpenText aria-hidden="true" />LINE 聊天室版面
        </button>
      </nav>

      <div className="line-hub-tab-panel">
        {activeTab === 'qa' && <CommonQaCatalogPanel />}
        {activeTab === 'layout' && <FaqChatLayoutPanel />}
      </div>
    </section>
  );
};

export default LineFaqStudioPage;
