/**
 * Unified AI customer-service studio: curated common QA plus event-rule workspace.
 */
import React, { useState } from 'react';
import { Bot, BookOpenText, FlaskConical, MessageSquareHeart, Workflow } from 'lucide-react';
import { AiEventStudio } from './AiEventStudio';
import { CommonQaCatalogPanel } from './CommonQaCatalogPanel';
import { RealLlmSemanticTestPanel } from './RealLlmSemanticTestPanel';
import { KnowledgeFeedbackPanel } from './KnowledgeFeedbackPanel';

type StudioTab = 'qa' | 'rules' | 'test' | 'feedback';

export const AiCustomerServiceStudioPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState<StudioTab>('qa');

  return (
    <section className="line-hub-page ai-customer-service-page" aria-labelledby="ai-studio-title">
      <header className="line-hub-page-header">
        <div className="line-hub-page-heading">
          <span className="line-hub-page-icon" aria-hidden="true"><Bot /></span>
          <div>
            <p className="line-hub-eyebrow">LINE 專區</p>
            <h1 id="ai-studio-title">AI 客服工作室</h1>
            <p>管理常見問答與客服處理規則、測試 AI 回答，並查看使用者回饋。</p>
          </div>
        </div>
      </header>

      <nav className="line-hub-section-tabs" aria-label="AI 客服工作室功能">
        <button type="button" className={activeTab === 'qa' ? 'active' : ''} aria-current={activeTab === 'qa' ? 'page' : undefined} onClick={() => setActiveTab('qa')}>
          <BookOpenText aria-hidden="true" />常見問答
        </button>
        <button type="button" className={activeTab === 'rules' ? 'active' : ''} aria-current={activeTab === 'rules' ? 'page' : undefined} onClick={() => setActiveTab('rules')}>
          <Workflow aria-hidden="true" />事件規則
        </button>
        <button type="button" className={activeTab === 'test' ? 'active' : ''} aria-current={activeTab === 'test' ? 'page' : undefined} onClick={() => setActiveTab('test')}>
          <FlaskConical aria-hidden="true" />AI 測試
        </button>
        <button type="button" className={activeTab === 'feedback' ? 'active' : ''} aria-current={activeTab === 'feedback' ? 'page' : undefined} onClick={() => setActiveTab('feedback')}>
          <MessageSquareHeart aria-hidden="true" />回饋分析
        </button>
      </nav>

      <div className="line-hub-tab-panel">
        {activeTab === 'qa' && <CommonQaCatalogPanel />}
        {activeTab === 'rules' && <AiEventStudio />}
        {activeTab === 'test' && (
          <div className="ai-simulator-card">
            <RealLlmSemanticTestPanel />
          </div>
        )}
        {activeTab === 'feedback' && <KnowledgeFeedbackPanel />}
      </div>
    </section>
  );
};

export default AiCustomerServiceStudioPage;
