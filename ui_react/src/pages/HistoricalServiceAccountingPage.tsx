/**
 * File: HistoricalServiceAccountingPage.tsx
 * Description: 帳務作業下的歷史訂單實際服務天數設定入口，重用既有帳務 workbench。
 */
import React from 'react';
import { HistoricalServiceAccountingWorkbench } from '../components/HistoricalServiceAccountingWorkbench';
import './DataImportPage.css';

export const HistoricalServiceAccountingPage: React.FC = () => (
  <div className="import-page-container" data-surface-id="finance.historical-service-accounting.page">
    <header className="page-header-banner import-result-header">
      <div>
        <h1 className="page-title">🧮 歷史訂單實際服務天數設定</h1>
        <p className="page-subtitle">核對歷史訂單最終實際服務天數，並沿用既有帳務預覽與建立流程。</p>
      </div>
    </header>
    <HistoricalServiceAccountingWorkbench />
  </div>
);

export default HistoricalServiceAccountingPage;
