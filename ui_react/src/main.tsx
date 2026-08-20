/**
 * @file main.tsx
 * @description 前端應用程式入口點，掛載 React 根節點並套用全域設計標籤樣式。
 */
import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import './styles/design-tokens.css';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
