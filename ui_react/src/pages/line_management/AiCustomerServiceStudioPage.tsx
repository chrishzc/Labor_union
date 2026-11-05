import { useUnsavedNavigation } from '../../components/UnsavedChanges';
/**
 * File: AiCustomerServiceStudioPage.tsx
 * Description: AI 客服工作室，整合常見問答、引導動作、回答測試、回饋分析與 AI 模型設定。
 */
import React, { useState } from 'react';
import { Bot, BookOpenText, FlaskConical, KeyRound, MessageSquareHeart, Workflow } from 'lucide-react';
import { AiEventStudio } from './AiEventStudio';
import { CommonQaCatalogPanel } from './CommonQaCatalogPanel';
import { RealLlmSemanticTestPanel } from './RealLlmSemanticTestPanel';
import { KnowledgeFeedbackPanel } from './KnowledgeFeedbackPanel';
import { LlmConfigurationPage } from './LlmConfigurationPage';

type StudioTab = 'qa' | 'rules' | 'test' | 'feedback' | 'model';

export const AiCustomerServiceStudioPage: React.FC = () => {
  const { requestLeave } = useUnsavedNavigation();
  const [activeTab, setActiveTab] = useState<StudioTab>(() => {
    const route = window.location.hash.replace(/^#\/?/, '').split('?', 1)[0];
    return route === 'line-llm' || route === 'line-llm-settings' ? 'model' : 'qa';
  });
  const [qaTarget, setQaTarget] = useState<{ id?: string; question?: string }>({});

  const openQa = (id: string) => { setQaTarget({ id }); setActiveTab('qa'); };
  const createQa = (question: string) => { setQaTarget({ question }); setActiveTab('qa'); };

  return (
    <section className="line-hub-page ai-customer-service-page" aria-labelledby="ai-studio-title">
      <header className="line-hub-page-header">
        <div className="line-hub-page-heading">
          <span className="line-hub-page-icon" aria-hidden="true"><Bot /></span>
          <div>
            <p className="line-hub-eyebrow">LINE 專區</p>
            <h1 id="ai-studio-title">AI 客服工作室</h1>
            <p>維護答案，測試回覆，持續改善客服品質，並管理 AI 模型設定。</p>
          </div>
        </div>
      </header>

      <nav className="line-hub-section-tabs" aria-label="AI 客服工作室功能">
        <button type="button" className={activeTab === 'qa' ? 'active' : ''} aria-current={activeTab === 'qa' ? 'page' : undefined} onClick={() => requestLeave(() => { setQaTarget({}); setActiveTab('qa'); })}>
          <BookOpenText aria-hidden="true" />常見問答
        </button>
        <button type="button" className={activeTab === 'rules' ? 'active' : ''} aria-current={activeTab === 'rules' ? 'page' : undefined} onClick={() => { if (('rules') !== activeTab) requestLeave(() => setActiveTab('rules')); }}>
          <Workflow aria-hidden="true" />引導動作
        </button>
        <button type="button" className={activeTab === 'test' ? 'active' : ''} aria-current={activeTab === 'test' ? 'page' : undefined} onClick={() => { if (('test') !== activeTab) requestLeave(() => setActiveTab('test')); }}>
          <FlaskConical aria-hidden="true" />回答測試
        </button>
        <button type="button" className={activeTab === 'feedback' ? 'active' : ''} aria-current={activeTab === 'feedback' ? 'page' : undefined} onClick={() => { if (('feedback') !== activeTab) requestLeave(() => setActiveTab('feedback')); }}>
          <MessageSquareHeart aria-hidden="true" />回饋分析
        </button>
        <button type="button" className={activeTab === 'model' ? 'active' : ''} aria-current={activeTab === 'model' ? 'page' : undefined} onClick={() => { if (('model') !== activeTab) requestLeave(() => setActiveTab('model')); }}>
          <KeyRound aria-hidden="true" />模型設定
        </button>
      </nav>

      <div className="line-hub-tab-panel">
        {activeTab === 'qa' && <CommonQaCatalogPanel initialQaId={qaTarget.id} initialQuestion={qaTarget.question} />}
        {activeTab === 'rules' && <AiEventStudio />}
        {activeTab === 'test' && (
          <RealLlmSemanticTestPanel onOpenQa={openQa} onCreateQa={createQa} />
        )}
        {activeTab === 'feedback' && <KnowledgeFeedbackPanel onOpenQa={openQa} onCreateQa={createQa} />}
        {activeTab === 'model' && <LlmConfigurationPage embedded />}
      </div>
    </section>
  );
};

export default AiCustomerServiceStudioPage;
