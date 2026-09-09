/**
 * Unified AI customer-service studio: curated common QA plus event-rule workspace.
 */
import React, { useState } from 'react';
import { Bot, BookOpenText, FlaskConical, Workflow } from 'lucide-react';
import { AiEventStudio } from './AiEventStudio';
import { CommonQaCatalogPanel } from './CommonQaCatalogPanel';
import { RealLlmSemanticTestPanel } from './RealLlmSemanticTestPanel';

type StudioTab = 'qa' | 'rules' | 'test';

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
            <p>分開管理固定回答、事件導向與真實模型測試，避免在同一長頁混用不同工作。</p>
          </div>
        </div>
      </header>

      <nav className="line-hub-section-tabs" aria-label="AI 客服工作室功能">
        <button type="button" className={activeTab === 'qa' ? 'active' : ''} aria-current={activeTab === 'qa' ? 'page' : undefined} onClick={() => setActiveTab('qa')}>
          <BookOpenText aria-hidden="true" />常見 QA
        </button>
        <button type="button" className={activeTab === 'rules' ? 'active' : ''} aria-current={activeTab === 'rules' ? 'page' : undefined} onClick={() => setActiveTab('rules')}>
          <Workflow aria-hidden="true" />事件規則
        </button>
        <button type="button" className={activeTab === 'test' ? 'active' : ''} aria-current={activeTab === 'test' ? 'page' : undefined} onClick={() => setActiveTab('test')}>
          <FlaskConical aria-hidden="true" />AI 測試
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
      </div>
    </section>
  );
};

export default AiCustomerServiceStudioPage;
