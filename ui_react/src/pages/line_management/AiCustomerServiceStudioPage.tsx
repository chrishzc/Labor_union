/**
 * Unified AI customer-service studio: curated common QA plus event-rule workspace.
 */
import React from 'react';
import { AiEventStudio } from './AiEventStudio';
import { CommonQaCatalogPanel } from './CommonQaCatalogPanel';

export const AiCustomerServiceStudioPage: React.FC = () => (
  <div>
    <CommonQaCatalogPanel />
    <AiEventStudio />
  </div>
);

export default AiCustomerServiceStudioPage;
